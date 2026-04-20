# Babylon∞n.ai

## LLM Provenance Attribution System

**Patent PCT/IB2026/053131 · 150+ countries · 28 claims**

> *"Where every token knows its origin."*

Babylon∞n.ai is model-agnostic infrastructure that makes any LLM output cryptographically auditable. Every output token is traced to its training-data source, trust-weighted at inference time, and written to a tamper-proof manifest — without retraining, fine-tuning, or model modification.

---

## Supported Models

| Model | License | Context | Thinking Mode | VRAM (4-bit) |
|-------|---------|---------|--------------|-------------|
| **Mistral 7B Instruct v0.3** | Apache 2.0 | 32 768 tok | — | 6–8 GB |
| **Google Gemma 4 12B** | Apache 2.0 | 131 072 tok | ✓ | 8–12 GB |
| **Google Gemma 4 E4B** | Apache 2.0 | 131 072 tok | ✓ | 3–5 GB |

Select model at runtime — no code changes required:

```bash
BABYLOON_MODEL=gemma-4-12b uvicorn main:app --reload
```

Or per-request via `model_override` in the `/generate` payload.

---

## Deployment Modes

| Mode | Backend | Quantization | VRAM | Use Case |
|------|---------|-------------|------|----------|
| **dev** | HuggingFace Transformers | BitsAndBytes NF4 4-bit | 8–12 GB | Development, CI, demos |
| **enterprise** | llama.cpp GGUF | Q8\_0 (near-lossless) | 10–14 GB | Regulated sectors, audit trail |
| **sovereign** | llama.cpp GGUF | Q4\_K\_L (balanced) | 5–7 GB | Air-gapped, local, edge |

```bash
# dev (default — BitsAndBytes 4-bit via HuggingFace)
LOAD_MODEL=1 BABYLOON_MODEL=mistral-7b docker-compose up api

# enterprise — GGUF Q8_0 on CPU or GPU
MODE=enterprise GGUF_PATH=/models/mistral-7b-q8.gguf docker-compose up api

# sovereign — GGUF Q4_K_L, fully local, no internet
MODE=sovereign GGUF_PATH=/models/mistral-7b-q4kl.gguf docker-compose up api
```

---

## Quick Start

### Without GPU (mock mode — all six mechanisms except real inference)

```bash
git clone https://github.com/babyloon-ai/babyloon-mvp
cd babyloon-mvp

# Backend
cd backend
pip install -r requirements.txt
MOCK_GENERATE=1 uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev        # → http://localhost:5173
```

### Docker Compose (GPU server)

```bash
# 1. Set your HuggingFace token (for model download)
export HF_TOKEN=hf_...

# 2. Start API — no GPU (mock mode)
docker-compose up api

# 3. Start API — with GPU (Mistral 7B, dev mode)
LOAD_MODEL=1 BABYLOON_MODEL=mistral-7b docker-compose up api

# 4. Start API — Gemma 4 12B with thinking mode
LOAD_MODEL=1 BABYLOON_MODEL=gemma-4-12b docker-compose up api

# 5. Full stack (API + frontend)
docker-compose up

# 6. Run test suite
docker-compose --profile test run tests
```

### Test Suite

```bash
cd backend
MOCK_GENERATE=1 pytest tests/ -v
# Expected: 141 passed, 2 skipped (GPU-only hooks)
```

---

## Six Mechanisms

| # | Mechanism | Module | Description | Patent Claims |
|---|-----------|--------|-------------|---------------|
| **E1** | Token Attribution | `attribution.py` | Per-token attention-weight provenance vector. Top-K=5 corpus sources, normalized to 1.0. Supports Gemma GQA/sliding-window attention. | 1–6 |
| **E2** | Agent Identity | `identity.py` | ECDSA-signed JWT. Three access tiers: L0 (full), L1 (verified partner), L2 (public). | 7–10 |
| **E3** | Trust-Weighted Attention | `trust.py` | Forward hook scales attention outputs by per-segment trust score. Segments below 0.3 threshold are zeroed. License filtering per agent level. | 11–16 |
| **E4** | Live Manifest | `manifest.py` | Streaming JSONL record per output token. Includes `reasoning_trace`, `reasoning_hash` (SHA-256), `model_backend`, `thinking_mode`. | 17–20 |
| **E5** | Hash-Chain Registry | `registry.py` | Append-only JSONL with SHA-256 chain. Tamper detection via `GET /registry/verify`. | 21–24 |
| **E6** | Fallback Authorization | `fallback.py` | Unknown agents fall back to L2 (public-domain only). No 401 — system stays available. | 25–28 |

---

## API Reference

### Core Pipeline

```http
POST /generate
Content-Type: application/json
Authorization: Bearer <agent_jwt>

{
  "prompt":         "What causes climate change?",
  "max_new_tokens": 256,
  "model_override": "gemma-4-12b",     # optional: mistral-7b | gemma-4-12b | gemma-4-e4b
  "mode_override":  "enterprise",       # optional: dev | enterprise | sovereign
  "stream":         false,
  "session_id":     "uuid-optional"
}
```

**Response:**

```json
{
  "session_id":      "...",
  "model_backend":   "gemma-4-12b",
  "thinking_mode":   true,
  "reasoning_trace": "Let me reason about this...",
  "output_text":     "Climate change is caused by...",
  "tokens": [
    {
      "position":    0,
      "text":        "Climate",
      "trust_avg":   0.87,
      "trust_color": "green",
      "attribution": [
        { "segment_id": "seg-wiki", "source_name": "Wikipedia",
          "weight": 0.62, "license_class": "CC-BY-SA", "trust_score": 0.91 }
      ]
    }
  ],
  "summary": {
    "license_purity":   1.0,
    "high_trust_ratio": 0.94,
    "total_tokens":     128,
    "model_backend":    "gemma-4-12b",
    "thinking_mode":    true,
    "reasoning_hash":   "sha256-of-thinking-block"
  }
}
```

### Side-by-Side Comparison

```http
POST /compare
{
  "prompt":       "Explain quantum entanglement.",
  "compare_type": "models"     # "models" | "quantization"
}
```

`compare_type=models` runs **Mistral 7B vs Gemma 4 12B** in parallel and returns:

```json
{
  "mistral-7b":  { "output_text": "...", "tokens": [...] },
  "gemma-4-12b": { "output_text": "...", "reasoning_trace": "...", "tokens": [...] },
  "comparison": {
    "output_similarity":   0.74,
    "attribution_overlap": 0.81,
    "latency_mistral_ms":  312,
    "latency_gemma_ms":    489,
    "latency_diff_ms":     177,
    "thinking_advantage":  true
  }
}
```

### Other Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service status, mock mode flag |
| `POST` | `/agent/register` | Create agent, receive JWT |
| `POST` | `/agent/verify` | Verify JWT from header |
| `GET` | `/trust/top?k=5` | Top-K trusted corpus segments |
| `POST` | `/trust/update` | Update segment trust score (L0 only) |
| `GET` | `/manifest/{session_id}` | Full JSONL token records |
| `GET` | `/manifest/{session_id}/summary` | Session metrics |
| `GET` | `/registry/verify` | SHA-256 chain integrity check |
| `GET` | `/registry/{record_id}` | Fetch single registry record |

Full API reference: [`docs/API.md`](docs/API.md)

---

## Project Structure

```
babyloon-mvp/
├── backend/
│   ├── main.py                    # FastAPI app — all six mechanisms
│   ├── requirements.txt
│   ├── modules/
│   │   ├── attribution.py         # E1: token-level provenance (attention hooks)
│   │   ├── identity.py            # E2: ECDSA JWT agent identity
│   │   ├── fallback.py            # E6: L2 fallback middleware
│   │   ├── trust.py               # E3: trust-weighted attention + get_attention_class()
│   │   ├── manifest.py            # E4: streaming JSONL manifest (thinking mode aware)
│   │   ├── registry.py            # E5: SHA-256 append-only hash-chain
│   │   └── corpus_loader.py       # Demo corpus with provenance metadata
│   ├── models/
│   │   ├── manager.py             # ModelAdapter: Mistral + Gemma 4 + make_adapter()
│   │   └── loader.py              # Legacy loader (Mistral 7B, backward compat)
│   ├── data/
│   │   ├── corpus_registry.jsonl  # Corpus segment registry
│   │   ├── trust_scores.json      # Per-segment trust scores
│   │   └── agent_registry.json    # Registered agents
│   └── tests/
│       ├── test_registry.py       # E5: tamper detection, hash chain (19 tests)
│       ├── test_identity.py       # E2+E6: JWT, fallback (18 tests)
│       ├── test_trust.py          # E3: trust store, hooks (21 tests)
│       ├── test_attribution.py    # E1: provenance, sliding-window fix (19 tests)
│       ├── test_pipeline.py       # Integration: all mechanisms (14 tests)
│       └── test_manager.py        # ModelAdapter: Mistral + Gemma 4 (57 tests)
├── frontend/
│   └── src/
│       ├── App.jsx                # Router: / /demo /pilot
│       ├── components/
│       │   ├── DemoPage.jsx       # Main demo — model selector, reasoning panel
│       │   ├── TokenViewer.jsx    # Hover → provenance popup
│       │   ├── ManifestPanel.jsx  # Live session metrics
│       │   ├── ChainViewer.jsx    # Registry chain visualization
│       │   └── CompareView.jsx    # Black box vs babyloon split-screen
│       └── pages/
│           ├── Home.jsx           # Landing page
│           ├── Demo.jsx           # Demo redirect
│           └── Pilot.jsx          # Pilot program (ex Syaivo)
├── docs/
│   ├── API.md                     # Full REST API reference
│   └── benchmark_report.md        # Latency/quality benchmarks per mode
├── Dockerfile
└── docker-compose.yml
```

---

## Infrastructure

| Component | Service | Notes |
|-----------|---------|-------|
| GPU Server | RunPod / Lambda Labs (RTX 4090 or A100) | LOAD\_MODEL=1 |
| Frontend | Vercel | Auto-deploy from `main` branch |
| DNS | Cloudflare | `babyloon.ai` → Vercel · `api.babyloon.ai` → GPU |
| Registry | Append-only JSONL | Persistent Docker volume |
| Agent DB | JSON file | `/data/agent_registry.json` |

---

## Development Timeline

| Weeks | Phase | Milestone | Status |
|-------|-------|-----------|--------|
| 1–2 | E5 Registry | Hash-chain tamper detection | ✅ Done |
| 3–4 | E2+E6 Identity | JWT + L0/L1/L2 fallback | ✅ Done |
| 4 | E3 Trust | Attention hooks + license filter | ✅ Done |
| 5–6 | E1 Attribution | Per-token provenance, Gemma fix | ✅ Done |
| 7–8 | E4 Manifest | Streaming JSONL, thinking mode | ✅ Done |
| 8 | БЛОК 2 | ModelAdapter (Mistral + Gemma 4) | ✅ Done |
| 9 | БЛОК 3 | Gemma GQA/sliding-window fix | ✅ Done |
| 10 | БЛОК 4 | Model selector UI, /compare | ✅ Done |
| 11 | Frontend | Brand, logo, pilot page | ✅ Done |
| 12 | Polish + EIC | Benchmarks, README, EIC ready | ✅ Done |

---

## Brand & Design

Colors: Deep Azure `#1B3A5C` · Babylonian Gold `#C5963A` · Ink `#0C1824` · Silver `#E0E8F0`

Fonts: Cormorant Garamond (headings) · Inter (UI) · JetBrains Mono (code/tokens)

---

## Patent

All code implements patent **PCT/IB2026/053131** (filed April 2026, 150+ countries, 28 claims).
Each module corresponds to specific patent claims — see the table under **Six Mechanisms**.

Do not modify the architectural boundaries of E1–E6 without cross-referencing the patent specification.

**CONFIDENTIAL** · Babylon∞n.ai · April 2026
