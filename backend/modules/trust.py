"""
E3: TrustWeightedAttention — trust-conditioned attention modification
Modifies attention layer outputs using per-segment trust scores.
Segments with trust < 0.3 are masked (zeroed). L0/L1/L2 license filtering.
Patent claim: trust score × attention_weight per source segment, no retraining.
PCT/IB2026/053131

Model support:
  - Mistral 7B  : MHA, 32 layers, attention class "MistralAttention"
  - Gemma 4 12B : GQA + sliding window, 26 layers, "GemmaAttention"
  - Gemma 4 e4b : GQA + sliding window, 18 layers, "GemmaAttention"

Hook registration is identical for all — model.layers[i].self_attn.
The hook receives the *output* tensor (post-projection), not the raw
attention weight matrix, so GQA/sliding-window shape differences are
transparent here. Shape differences matter only in ProvenanceAttribution
(_compute_from_cache), which captures the raw attention weight matrix.

GGUF post-processing note:
  When running llama.cpp GGUF models the HuggingFace forward hooks are not
  available. Attention weights must be extracted from llama_get_logits()
  and post-processed into the same [batch, heads, seq, seq] tensor format
  before being passed to _compute_from_cache(). TrustWeightedAttentionHook
  cannot be used with GGUF models directly; trust weighting must be applied
  as a logit-processor instead.
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy torch import — only needed on GPU server
try:
    import torch
    _TORCH_AVAILABLE = True
except ImportError:
    torch = None  # type: ignore
    _TORCH_AVAILABLE = False

EXCLUSION_THRESHOLD = 0.3  # segments below this are zeroed out

# ── Attention class registry ───────────────────────────────────────── #

_ATTENTION_CLASS_MAP: dict[str, str] = {
    "mistral":  "MistralAttention",
    "gemma4":   "GemmaAttention",
    "gemma":    "GemmaAttention",   # generic alias
}


def get_attention_class(model_name: str) -> str:
    """
    Return the HuggingFace attention class name for a given model key.

    Used when selectively registering hooks only on specific layer types,
    e.g. to skip non-attention modules during model inspection.

    Args:
        model_name: Model key from _MODEL_REGISTRY (e.g. "gemma-4-12b")
                    or any string containing a recognisable family token.

    Returns:
        Attention class name string, e.g. "GemmaAttention".
        Falls back to "MistralAttention" for unknown families.

    Examples:
        >>> get_attention_class("gemma-4-12b")
        'GemmaAttention'
        >>> get_attention_class("gemma-4-e4b")
        'GemmaAttention'
        >>> get_attention_class("mistral-7b")
        'MistralAttention'
        >>> get_attention_class("unknown-model")
        'MistralAttention'
    """
    name_lower = model_name.lower()
    for family, cls in _ATTENTION_CLASS_MAP.items():
        if family in name_lower:
            return cls
    return "MistralAttention"


# License classes visible per level (for attention filtering)
_LICENSE_BY_LEVEL: dict[str, Optional[set]] = {
    "L0": None,                                           # all
    "L1": {"CC0", "CC-BY", "CC-BY-SA", "Apache-2.0", "MIT", "CC-BY-NC-SA"},
    "L2": {"CC0", "public-domain"},
}


# ================================================================== #
# TrustScoreStore
# ================================================================== #

class TrustScoreStore:
    """
    In-memory trust score table. Populated from:
      1. corpus_loader.get_trust_scores()  (primary, live corpus)
      2. trust_scores.json fallback        (legacy / static)
    Updated without retraining.
    """

    DEFAULT_TRUST = 0.5

    def __init__(
        self,
        scores_path: str = "data/trust_scores.json",
        use_corpus: bool = True,
    ):
        self.scores_path = Path(scores_path)
        self._scores: dict[str, float] = {}
        self._license_map: dict[str, str] = {}  # segment_id → license_class
        self._use_corpus = use_corpus
        self._load(use_corpus)

    # ---- Load ---------------------------------------------------- #

    def _load(self, use_corpus: bool = True) -> None:
        """Load trust scores — corpus takes precedence over JSON file."""
        if use_corpus:
            try:
                from modules.corpus_loader import get_trust_scores, load_corpus
                self._scores = get_trust_scores()
                for seg in load_corpus():
                    self._license_map[seg.segment_id] = seg.license_class
                logger.info(f"Trust store: {len(self._scores)} segments from demo corpus")
                return
            except Exception as e:
                logger.warning(f"corpus_loader unavailable ({e}), falling back to JSON")

        if self.scores_path.exists():
            data = json.loads(self.scores_path.read_text(encoding="utf-8"))
            self._scores = data.get("segments", {})
            logger.info(f"Trust store: {len(self._scores)} segments from {self.scores_path}")
        else:
            logger.warning(f"Trust scores file not found: {self.scores_path}")
            self._scores = {}

    def reload(self) -> None:
        """Hot-reload without restarting the model. Respects original use_corpus setting."""
        self._scores.clear()
        self._license_map.clear()
        self._load(use_corpus=self._use_corpus)

    # ---- Accessors ----------------------------------------------- #

    def get(self, segment_id: str) -> float:
        return self._scores.get(segment_id, self.DEFAULT_TRUST)

    def set(self, segment_id: str, score: float) -> None:
        if not (0.0 <= score <= 1.0):
            raise ValueError(f"Trust score must be 0.0–1.0, got {score}")
        self._scores[segment_id] = score
        self._persist()

    def get_all(self) -> dict[str, float]:
        return dict(self._scores)

    def get_active_segments(self, level: str = "L0") -> dict[str, float]:
        """
        Return segments above EXCLUSION_THRESHOLD filtered by agent level.
        L0 → all, L1 → verified licenses, L2 → CC0 only
        """
        allowed = _LICENSE_BY_LEVEL.get(level)
        result = {}
        for sid, score in self._scores.items():
            if score < EXCLUSION_THRESHOLD:
                continue
            if allowed is not None:
                lic = self._license_map.get(sid, "unknown")
                if lic not in allowed:
                    continue
            result[sid] = score
        return result

    def top_k(self, k: int = 5, level: str = "L0") -> list[tuple[str, float]]:
        active = self.get_active_segments(level)
        return sorted(active.items(), key=lambda x: x[1], reverse=True)[:k]

    def get_license(self, segment_id: str) -> str:
        return self._license_map.get(segment_id, "unknown")

    def _persist(self) -> None:
        data = {"segments": self._scores}
        self.scores_path.parent.mkdir(parents=True, exist_ok=True)
        self.scores_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )


# ================================================================== #
# TrustWeightedAttentionHook
# ================================================================== #

class TrustWeightedAttentionHook:
    """
    PyTorch forward hook that scales attention outputs by trust score.

    Per output position p, per corpus segment s:
        attention_output[:, p, :] *= trust_score[s]

    Segments with trust < EXCLUSION_THRESHOLD → zeroed (masked).
    Only token positions in segment_mapping are modified.

    Usage:
        hook = TrustWeightedAttentionHook(store, mapping, layer_filter)
        handles = hook.register(model)
        output = model.generate(...)
        distribution = hook.get_trust_distribution()
        hook.remove(handles)
    """

    def __init__(
        self,
        trust_store: TrustScoreStore,
        segment_mapping: Optional[dict[int, str]] = None,
        layer_filter: str = "all",  # "all" | "upper_half" | "last_only"
        level: str = "L0",
        model_name: str = "mistral-7b",
    ):
        self.trust_store = trust_store
        self.segment_mapping = segment_mapping or {}
        self.layer_filter = layer_filter
        self.level = level
        self.model_name = model_name
        self._hook_data: list[dict] = []
        self._total_layers: int = 32  # overwritten by register() from actual model depth

    def _should_hook(self, layer_idx: int) -> bool:
        if self.layer_filter == "all":
            return True
        if self.layer_filter == "last_only":
            return layer_idx == self._total_layers - 1
        if self.layer_filter == "upper_half":
            return layer_idx >= self._total_layers // 2
        return True

    def _make_hook(self, layer_idx: int):
        def hook_fn(module, inp, output):
            if not _TORCH_AVAILABLE or not self._should_hook(layer_idx):
                return output

            attn_out = output[0] if isinstance(output, tuple) else output
            if not isinstance(attn_out, torch.Tensor):
                return output

            modified = attn_out.clone()
            seq_len = attn_out.shape[1] if attn_out.dim() >= 2 else 1

            # Get allowed segments for this agent level
            allowed = _LICENSE_BY_LEVEL.get(self.level)

            for pos in range(seq_len):
                seg_id = self.segment_mapping.get(pos)
                if seg_id is None:
                    continue

                # License-level filter
                if allowed is not None:
                    lic = self.trust_store.get_license(seg_id)
                    if lic not in allowed:
                        if attn_out.dim() >= 2:
                            modified[:, pos, :] = 0.0
                        continue

                trust = self.trust_store.get(seg_id)

                if trust < EXCLUSION_THRESHOLD:
                    # Mask: zero out contribution
                    if attn_out.dim() >= 2:
                        modified[:, pos, :] = 0.0
                    effective_trust = 0.0
                else:
                    # Scale by trust score
                    if attn_out.dim() >= 2:
                        modified[:, pos, :] = modified[:, pos, :] * trust
                    effective_trust = trust

                if attn_out.dim() >= 2:
                    attn_weight = float(attn_out[:, pos, :].abs().mean())
                else:
                    attn_weight = 0.0

                self._hook_data.append({
                    "position": pos,
                    "segment_id": seg_id,
                    "trust_score": effective_trust,
                    "attention_weight": attn_weight,
                    "layer": layer_idx,
                })

            if isinstance(output, tuple):
                return (modified,) + output[1:]
            return modified

        return hook_fn

    def register(self, model) -> list:
        """Register hooks on all attention layers. Returns handles list."""
        if not _TORCH_AVAILABLE:
            logger.warning("torch not available — hooks not registered")
            return []

        handles = []
        layers = self._get_layers(model)
        if layers is None:
            logger.warning("Could not find attention layers — hooks not registered")
            return handles

        self._total_layers = len(layers)
        for idx, layer in enumerate(layers):
            attn = getattr(layer, "self_attn", None)
            if attn is not None:
                h = attn.register_forward_hook(self._make_hook(idx))
                handles.append(h)

        logger.info(
            f"Registered trust hooks on {len(handles)} layers "
            f"(filter={self.layer_filter}, level={self.level})"
        )
        return handles

    def remove(self, handles: list) -> None:
        for h in handles:
            h.remove()
        self._hook_data.clear()

    def get_trust_distribution(self, top_k: int = 5) -> list[dict]:
        """
        Return [{segment_id, trust_score, attention_weight}] sorted by weight.
        """
        if not self._hook_data:
            return []
        sorted_data = sorted(
            self._hook_data, key=lambda x: x["attention_weight"], reverse=True
        )
        # Deduplicate by segment_id, keeping highest weight entry
        seen: set[str] = set()
        result = []
        for d in sorted_data:
            if d["trust_score"] == 0.0:   # skip masked / below-threshold segments
                continue
            sid = d["segment_id"]
            if sid not in seen:
                seen.add(sid)
                result.append({
                    "segment_id": sid,
                    "trust_score": d["trust_score"],
                    "attention_weight": round(d["attention_weight"], 6),
                })
            if len(result) >= top_k:
                break
        return result

    def get_average_trust(self) -> float:
        if not self._hook_data:
            return 0.0
        active = [d for d in self._hook_data if d["trust_score"] > 0]
        if not active:
            return 0.0
        return sum(d["trust_score"] for d in active) / len(active)

    def clear(self) -> None:
        self._hook_data.clear()

    @staticmethod
    def _get_layers(model):
        if hasattr(model, "model") and hasattr(model.model, "layers"):
            return model.model.layers
        if hasattr(model, "layers"):
            return model.layers
        return None


# ================================================================== #
# TrustSession — context manager for a single inference
# ================================================================== #

class TrustSession:
    """
    Context manager: registers hooks before generate, removes after.

    with TrustSession(model, store, mapping, layer_filter, level) as ts:
        output = model.generate(...)
        dist = ts.get_distribution()
        avg  = ts.get_average_trust()
    """

    def __init__(
        self,
        model,
        trust_store: TrustScoreStore,
        segment_mapping: dict[int, str],
        layer_filter: str = "all",
        level: str = "L0",
        model_name: str = "mistral-7b",
    ):
        self.model = model
        self.hook = TrustWeightedAttentionHook(
            trust_store, segment_mapping, layer_filter, level, model_name
        )
        self._handles: list = []

    def __enter__(self):
        if self.model is not None:
            self._handles = self.hook.register(self.model)
        return self

    def __exit__(self, *args):
        self.hook.remove(self._handles)

    def get_distribution(self, top_k: int = 5) -> list[dict]:
        return self.hook.get_trust_distribution(top_k)

    def get_average_trust(self) -> float:
        return self.hook.get_average_trust()


# ================================================================== #
# Singleton helpers
# ================================================================== #

_trust_store: Optional[TrustScoreStore] = None


def get_trust_store(
    path: str = "data/trust_scores.json",
    use_corpus: bool = True,
) -> TrustScoreStore:
    global _trust_store
    if _trust_store is None:
        _trust_store = TrustScoreStore(path, use_corpus=use_corpus)
    return _trust_store


def reset_trust_store() -> None:
    """Force recreation of singleton (useful in tests)."""
    global _trust_store
    _trust_store = None
