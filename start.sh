#!/usr/bin/env bash
# =============================================================================
# babyloon.ai — RunPod A40 startup script
# Place at: /workspace/start.sh
# chmod +x /workspace/start.sh && bash /workspace/start.sh
#
# WHY VENV INSTEAD OF pip --target
# ─────────────────────────────────
# pip --target copies compiled .so files (from cryptography, pycurl, etc.)
# alongside Python modules. The dynamic linker finds them BEFORE system libs,
# causing "cannot apply additional memory protection" on libnettle/libcurl.
# A venv keeps site-packages in a standard tree and resolves .so files through
# the normal ld.so path — no conflicts.
#
# WHY --system-site-packages
# ──────────────────────────
# RunPod's PyTorch template pre-installs CUDA-enabled PyTorch system-wide
# (e.g. /usr/local/lib/python3.11/dist-packages/torch with CUDA 12.x).
# Re-installing torch from PyPI inside the venv would pull the CPU-only wheel
# and waste 5–10 minutes + ~3 GB of download. Inheriting system packages lets
# the venv use the pre-built CUDA torch while still isolating everything else.
#
# DISK LAYOUT  (all on /workspace — 50 GB network volume, persistent)
# ───────────────────────────────────────────────────────────────────
#   /workspace/venv              Python venv (inherits system torch+CUDA)
#   /workspace/hf-cache          HuggingFace model weights (Mistral 7B ≈ 14 GB)
#   /workspace/pip-cache         pip wheel cache
#   /workspace/tmp               pip/torch build temps (keep off 5 GB root disk)
#   /workspace/torch-cache       torch hub cache
#   /workspace/babyloon-manifests  live manifests (E4)
#   /workspace/babyloon-mvp      project source (git clone)
#
# USAGE
# ─────
#   First boot   :  bash /workspace/start.sh
#   Warm restart :  bash /workspace/start.sh --skip-install
#   Background   :  nohup bash /workspace/start.sh > /workspace/server.log 2>&1 &
#   Custom port  :  PORT=8080 bash /workspace/start.sh
# =============================================================================
set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
WORKSPACE="/workspace"
VENV="$WORKSPACE/venv"
BACKEND="$WORKSPACE/babyloon-mvp/backend"
LOG="$WORKSPACE/startup.log"
PORT="${PORT:-8000}"
SKIP_INSTALL="${1:-}"

# ── Tee all output to log ─────────────────────────────────────────────────────
exec > >(tee -a "$LOG") 2>&1
echo ""
echo "════════════════════════════════════════════════════════════"
echo " babyloon.ai startup  —  $(date)"
echo "════════════════════════════════════════════════════════════"

# ── Workspace directories (all on 50 GB network volume) ──────────────────────
mkdir -p \
  "$WORKSPACE/tmp" \
  "$WORKSPACE/pip-cache" \
  "$WORKSPACE/hf-cache" \
  "$WORKSPACE/torch-cache" \
  "$WORKSPACE/babyloon-manifests"

# ── Step 1: Virtual environment ───────────────────────────────────────────────
echo "[1/5] Virtual environment …"
if [ ! -f "$VENV/bin/activate" ]; then
  echo "      Creating venv with --system-site-packages …"
  # --system-site-packages: inherit CUDA-enabled torch from RunPod base image.
  # Without this flag, pip would install the CPU-only torch from PyPI (~3 GB
  # download, no CUDA). The flag is safe — pip-installed packages in the venv
  # always shadow system packages, so there is no version bleed-through for
  # anything we install explicitly.
  python3 -m venv --system-site-packages "$VENV"
  echo "      Venv created ✓"
else
  echo "      Venv exists — skipping create"
fi

# shellcheck source=/dev/null
source "$VENV/bin/activate"
echo "      Python : $(python --version)"
echo "      Binary : $(which python)"

# ── Step 2: pip install ───────────────────────────────────────────────────────
if [ "$SKIP_INSTALL" = "--skip-install" ]; then
  echo "[2/5] --skip-install — skipping pip"
else
  echo "[2/5] Upgrading pip + wheel …"
  TMPDIR="$WORKSPACE/tmp" pip install \
    --cache-dir="$WORKSPACE/pip-cache" \
    --upgrade pip wheel setuptools \
    --quiet

  # ── Torch: validate CUDA build; install CUDA wheel only if needed ──────────
  echo "      Checking torch + CUDA …"
  TORCH_OK=$(python - <<'PYEOF'
try:
    import torch
    print("ok" if torch.cuda.is_available() else "nocuda")
except ImportError:
    print("missing")
PYEOF
)
  if [ "$TORCH_OK" = "ok" ]; then
    echo "      torch CUDA already available via system-site-packages ✓"
  else
    echo "      torch CUDA not found — installing from PyTorch wheel index …"
    # Detect CUDA version to pick the right index URL
    CUDA_VER=$(python3 -c "
import subprocess, re
out = subprocess.check_output(['nvcc','--version'], stderr=subprocess.STDOUT).decode()
m = re.search(r'release (\d+)\.(\d+)', out)
print(f'cu{m.group(1)}{m.group(2)}' if m else 'cu121')
" 2>/dev/null || echo "cu121")
    echo "      CUDA version tag: $CUDA_VER"
    TMPDIR="$WORKSPACE/tmp" pip install \
      --cache-dir="$WORKSPACE/pip-cache" \
      --index-url "https://download.pytorch.org/whl/${CUDA_VER}" \
      "torch>=2.4.0" \
      --quiet
    echo "      torch installed from PyTorch index ✓"
  fi

  # ── Main requirements (torch is excluded from requirements.txt) ────────────
  echo "      Installing requirements.txt …"
  TMPDIR="$WORKSPACE/tmp" pip install \
    --cache-dir="$WORKSPACE/pip-cache" \
    -r "$BACKEND/requirements.txt" \
    --quiet

  echo "      Dependencies ready ✓"
fi

# ── Step 3: Environment variables ─────────────────────────────────────────────
echo "[3/5] Environment …"

export CUDA_VISIBLE_DEVICES=0

# Hugging Face — model weights go to /workspace, never touch the 5 GB root disk
export HF_TOKEN="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"
export HF_HOME="$WORKSPACE/hf-cache"
export HUGGINGFACE_HUB_CACHE="$WORKSPACE/hf-cache"
export TRANSFORMERS_CACHE="$WORKSPACE/hf-cache"

# Build / scratch dirs — off root disk
export TMPDIR="$WORKSPACE/tmp"
export TORCH_HOME="$WORKSPACE/torch-cache"

# App
export LOAD_MODEL=1
export MANIFEST_DIR="$WORKSPACE/babyloon-manifests"

# Suppress harmless warnings
export TOKENIZERS_PARALLELISM=false

echo "      HF_HOME      : $HF_HOME"
echo "      MANIFEST_DIR : $MANIFEST_DIR"
echo "      CUDA devices : $CUDA_VISIBLE_DEVICES"

# ── Step 4: GPU + library sanity check ───────────────────────────────────────
echo "[4/5] GPU check …"
python - <<'PYEOF'
import sys
try:
    import torch
    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        print(f"      GPU  : {name}")
        print(f"      VRAM : {vram:.1f} GB  ({'A40 ✓' if vram > 40 else 'check'})")
        print(f"      CUDA : {torch.version.cuda}")
    else:
        print("      WARNING: CUDA not available — model will run on CPU (very slow)", file=sys.stderr)
except Exception as e:
    print(f"      WARNING: torch check failed: {e}", file=sys.stderr)
PYEOF

# ── Step 5: Launch ────────────────────────────────────────────────────────────
echo "[5/5] Starting uvicorn on 0.0.0.0:$PORT …"
echo ""
cd "$BACKEND"

# exec replaces the shell process so uvicorn receives SIGTERM/SIGINT directly
exec python -m uvicorn main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --workers 1 \
  --log-level info \
  --access-log
