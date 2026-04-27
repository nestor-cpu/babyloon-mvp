"""
E1: ProvenanceAttribution — token-level provenance attribution
Per output token: attribution vector across corpus segments.
Collects attention weights from the last attention layer (or more).
Top-K=5 sources, normalized to 1.0. License filtering by agent level.
Patent claim: per-token attribution to specific corpus segments.
PCT/IB2026/053131
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy torch import
try:
    import torch
    _TORCH_AVAILABLE = True
except ImportError:
    torch = None  # type: ignore
    _TORCH_AVAILABLE = False

TOP_K = 5

# License classes visible per agent level
_LICENSE_BY_LEVEL: dict[str, Optional[set]] = {
    "L0": None,
    "L1": {"CC0", "CC-BY", "CC-BY-SA", "Apache-2.0", "MIT", "CC-BY-NC-SA"},
    "L2": {"CC0", "public-domain"},
}


# ================================================================== #
# Data structures
# ================================================================== #

@dataclass
class SourceAttribution:
    segment_id: str
    source_name: str
    weight: float
    license_class: str
    trust_score: float

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "source_name": self.source_name,
            "weight": round(self.weight, 6),
            "license_class": self.license_class,
            "trust_score": round(self.trust_score, 4),
        }


@dataclass
class TokenProvenance:
    token_id: int
    token_text: str
    position: int
    attribution: list[SourceAttribution] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            # Primary fields (frontend canonical names)
            "token_id":   self.token_id,
            "text":       self.token_text,   # frontend: token.text
            "position":   self.position,
            "attribution": [a.to_dict() for a in self.attribution],
            "dominant_source": self.attribution[0].to_dict() if self.attribution else None,
            "trust_avg":  self._average_trust(),   # frontend: token.trust_avg
            "license_purity": self._license_purity(),
            # Extra metadata (model-specific, e.g. reasoning_trace for Gemma 4)
            **({"metadata": self.metadata} if self.metadata else {}),
        }

    def _average_trust(self) -> float:
        if not self.attribution:
            return 0.0
        total_w = sum(a.weight for a in self.attribution)
        if total_w == 0:
            return 0.0
        return round(
            sum(a.trust_score * a.weight for a in self.attribution) / total_w, 4
        )

    def _license_purity(self) -> float:
        clean = {"CC0", "public-domain", "Apache-2.0", "MIT", "CC-BY", "CC-BY-SA"}
        total_w = sum(a.weight for a in self.attribution)
        if total_w == 0:
            return 0.0
        clean_w = sum(a.weight for a in self.attribution if a.license_class in clean)
        return round(clean_w / total_w, 4)


# ================================================================== #
# SegmentMetaStore — metadata about corpus segments
# ================================================================== #

class SegmentMetaStore:
    """
    Metadata store for corpus segments.
    Populated from corpus_loader (primary) or manually in tests.
    """

    def __init__(self, segments: Optional[dict] = None):
        self._segments: dict[str, dict] = segments or {}

    def add(self, segment_id: str, meta: dict) -> None:
        self._segments[segment_id] = meta

    def get(self, segment_id: str) -> dict:
        return self._segments.get(segment_id, {
            "source_name": "unknown",
            "license_class": "unknown",
            "trust_score": 0.5,
            "language": "en",
        })

    def all_ids(self) -> list[str]:
        return list(self._segments.keys())

    @classmethod
    def from_corpus(cls) -> "SegmentMetaStore":
        """Build SegmentMetaStore from demo corpus."""
        try:
            from modules.corpus_loader import load_corpus
            store = cls()
            for seg in load_corpus():
                store.add(seg.segment_id, {
                    "source_name": seg.source_name,
                    "license_class": seg.license_class,
                    "trust_score": seg.trust_score,
                    "language": seg.language,
                })
            return store
        except Exception as e:
            logger.warning(f"Could not build SegmentMetaStore from corpus: {e}")
            return cls()


# ================================================================== #
# ProvenanceAttribution
# ================================================================== #

class ProvenanceAttribution:
    """
    Computes token-level provenance via attention weight aggregation.

    For each output token t:
      For each corpus segment s:
        weight[t][s] = Σ attention_weight[t → prompt_pos] for all positions mapped to s

    Then normalize across segments and return top-K.

    When torch is not available (tests without GPU): returns uniform attribution
    across the active corpus segments.
    """

    def __init__(
        self,
        model,
        tokenizer,
        segment_meta_store: Optional[SegmentMetaStore] = None,
        top_k: int = TOP_K,
        level: str = "L0",
        model_name: str = "mistral-7b",
    ):
        self.model = model
        self.tokenizer = tokenizer
        self.meta_store = segment_meta_store or SegmentMetaStore.from_corpus()
        self.top_k = top_k
        self.level = level
        self.model_name = model_name
        self._attention_cache: list = []
        self._hooks: list = []
        # Set after each attribute() call — accessible for manifest serialisation
        self.reasoning_trace: Optional[str] = None

    # ---- License filter ------------------------------------------ #

    def _filter_by_level(self, segment_id: str) -> bool:
        """Return True if segment is accessible at self.level."""
        allowed = _LICENSE_BY_LEVEL.get(self.level)
        if allowed is None:
            return True
        meta = self.meta_store.get(segment_id)
        return meta.get("license_class", "unknown") in allowed

    # ---- Attention hook registration ----------------------------- #

    def _register_hooks(self, layer_filter: str = "last_only") -> None:
        self._attention_cache.clear()

        def make_hook(layer_idx):
            def hook_fn(module, inp, output):
                if isinstance(output, tuple) and len(output) > 1:
                    attn_weights = output[1]
                    if attn_weights is not None:
                        self._attention_cache.append(attn_weights.detach().cpu())
            return hook_fn

        layers = self._get_layers()
        if layers is None:
            return

        n = len(layers)
        if layer_filter == "last_only":
            indices = [n - 1]
        elif layer_filter == "upper_half":
            indices = list(range(n // 2, n))
        else:
            indices = list(range(n))

        for idx in indices:
            layer = layers[idx]
            attn = getattr(layer, "self_attn", None)
            if attn is not None:
                h = attn.register_forward_hook(make_hook(idx))
                self._hooks.append(h)

    def _remove_hooks(self) -> None:
        for h in self._hooks:
            h.remove()
        self._hooks.clear()

    def _get_layers(self):
        if self.model is None:
            return None
        if hasattr(self.model, "model") and hasattr(self.model.model, "layers"):
            return self.model.model.layers
        if hasattr(self.model, "layers"):
            return self.model.layers
        return None

    # ---- Core attribution ---------------------------------------- #

    def attribute(
        self,
        prompt_tokens: list[int],
        output_tokens: list[int],
        segment_token_map: dict[int, str],
        layer_filter: str = "last_only",
        thinking_token_count: int = 0,
        reasoning_trace: Optional[str] = None,
    ) -> list[TokenProvenance]:
        """
        Compute token provenance for each output token.
        Falls back to uniform distribution when torch is unavailable.

        Args:
            prompt_tokens:        Token IDs of the formatted prompt.
            output_tokens:        All output token IDs (including thinking block).
            segment_token_map:    prompt position → corpus segment_id.
            layer_filter:         "last_only" | "upper_half" | "all".
            thinking_token_count: Number of leading output tokens that belong to
                                  the Gemma 4 <|think|>…<|/think|> block.
                                  These tokens are skipped — attribution is
                                  computed only for visible output tokens.
                                  Always 0 for Mistral.
            reasoning_trace:      Extracted thinking text (already stripped of
                                  tags). Stored as self.reasoning_trace and
                                  injected as metadata on every TokenProvenance
                                  so callers can include it in JSONL manifests.

        Returns:
            List of TokenProvenance — one entry per *visible* output token.
        """
        # Store reasoning trace for caller access (manifest serialisation)
        self.reasoning_trace = reasoning_trace

        # Skip the thinking block — attribute only the visible output
        visible_tokens = output_tokens[thinking_token_count:]

        if not _TORCH_AVAILABLE or self.model is None:
            return self._uniform_attribution(
                visible_tokens, segment_token_map, reasoning_trace
            )

        self._register_hooks(layer_filter)

        try:
            with torch.no_grad():
                full_ids = torch.tensor([prompt_tokens + output_tokens], dtype=torch.long)
                if hasattr(next(self.model.parameters()), "device"):
                    try:
                        dev = next(self.model.parameters()).device
                        full_ids = full_ids.to(dev)
                    except Exception:
                        pass

                self.model(full_ids, output_attentions=True)

        except Exception as e:
            logger.error(f"Forward pass for attribution failed: {e}")
            self._remove_hooks()
            return self._uniform_attribution(
                visible_tokens, segment_token_map, reasoning_trace
            )
        finally:
            self._remove_hooks()

        return self._compute_from_cache(
            prompt_tokens, output_tokens, segment_token_map,
            thinking_token_count=thinking_token_count,
            reasoning_trace=reasoning_trace,
        )

    def _compute_from_cache(
        self,
        prompt_tokens: list[int],
        output_tokens: list[int],
        segment_token_map: dict[int, str],
        thinking_token_count: int = 0,
        reasoning_trace: Optional[str] = None,
    ) -> list[TokenProvenance]:
        n_prompt = len(prompt_tokens)
        # Only attribute visible tokens (skip Gemma thinking block)
        visible_tokens = output_tokens[thinking_token_count:]
        # The actual sequence offset for the first visible output token
        visible_start = n_prompt + thinking_token_count
        results = []

        meta_extra = {"reasoning_trace": reasoning_trace} if reasoning_trace else {}

        for out_idx, token_id in enumerate(visible_tokens):
            out_pos = visible_start + out_idx
            token_text = self._decode(token_id)

            seg_weights: dict[str, float] = {}

            for attn in self._attention_cache:
                # attn shape: [batch, heads, q_len, kv_len]
                # For Gemma 4 sliding-window layers: kv_len = window_size < full_seq
                if attn is None or out_pos >= attn.shape[2]:
                    continue

                # kv_len may be smaller than n_prompt for sliding-window layers
                kv_len = attn.shape[3]
                n_prompt_vis = min(n_prompt, kv_len)

                # Average over heads: result shape [kv_len]
                row = attn[0, :, out_pos, :n_prompt_vis].mean(dim=0)

                for prompt_pos in range(n_prompt_vis):
                    seg_id = segment_token_map.get(prompt_pos)
                    if seg_id is None or not self._filter_by_level(seg_id):
                        continue
                    w = float(row[prompt_pos]) if prompt_pos < len(row) else 0.0
                    seg_weights[seg_id] = seg_weights.get(seg_id, 0.0) + w

            results.append(
                self._build_provenance(
                    token_id, token_text, out_idx, seg_weights, metadata=meta_extra
                )
            )

        return results

    def _uniform_attribution(
        self,
        output_tokens: list[int],
        segment_token_map: dict[int, str],
        reasoning_trace: Optional[str] = None,
    ) -> list[TokenProvenance]:
        """
        No torch → uniform weight across accessible corpus segments.
        Used in mock/test mode.
        output_tokens here already has thinking tokens stripped by attribute().
        """
        all_segs = list({
            sid for sid in segment_token_map.values()
            if sid and self._filter_by_level(sid)
        })
        n = len(all_segs)
        uniform_w = 1.0 / n if n > 0 else 0.0

        meta_extra = {"reasoning_trace": reasoning_trace} if reasoning_trace else {}

        results = []
        for idx, token_id in enumerate(output_tokens):
            token_text = self._decode(token_id)
            seg_weights = {sid: uniform_w for sid in all_segs}
            results.append(
                self._build_provenance(
                    token_id, token_text, idx, seg_weights, metadata=meta_extra
                )
            )
        return results

    def _build_provenance(
        self,
        token_id: int,
        token_text: str,
        position: int,
        seg_weights: dict[str, float],
        metadata: Optional[dict] = None,
    ) -> TokenProvenance:
        total = sum(seg_weights.values())
        if total > 0:
            seg_weights = {k: v / total for k, v in seg_weights.items()}

        top = sorted(seg_weights.items(), key=lambda x: x[1], reverse=True)[: self.top_k]
        attribution = []
        for seg_id, weight in top:
            meta = self.meta_store.get(seg_id)
            attribution.append(SourceAttribution(
                segment_id=seg_id,
                source_name=meta.get("source_name", "unknown"),
                weight=weight,
                license_class=meta.get("license_class", "unknown"),
                trust_score=meta.get("trust_score", 0.5),
            ))

        return TokenProvenance(
            token_id=token_id,
            token_text=token_text,
            position=position,
            attribution=attribution,
            metadata=metadata or {},
        )

    def _decode(self, token_id: int) -> str:
        if self.tokenizer is None:
            return f"[{token_id}]"
        try:
            tok = self.tokenizer.convert_ids_to_tokens([token_id])[0] or ""; tok = tok.replace("▁", " "); return "" if tok in {"</s>", "<s>", "<unk>", "<pad>", "<0x0A>"} else (tok if not tok.startswith("<") else self.tokenizer.decode([token_id]))
        except Exception:
            return f"[{token_id}]"
