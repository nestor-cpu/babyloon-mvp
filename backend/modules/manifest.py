"""
E4: ManifestGenerator — live JSONL provenance manifest per inference session.
One record per output token:
  {session_id, token_position, token_text, attribution, agent_id, agent_level,
   trust_distribution, model_backend, thinking_mode, timestamp}
Session summary includes:
  {reasoning_trace, reasoning_hash, model_backend, thinking_mode, …}
Aggregate metrics after session + auto-write to E5 registry.
Patent claim: machine-readable audit trail per inference, verifiable chain.
PCT/IB2026/053131
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Optional

from modules.attribution import TokenProvenance
from modules.registry import ProvenanceRegistry

logger = logging.getLogger(__name__)


class ManifestGenerator:
    """
    Streams per-token provenance records to a JSONL manifest file.
    Computes aggregate metrics at session end.
    Writes final inference record to E5 registry.
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_level: str = "L2",
        manifests_dir: str = "data/manifests",
        registry: Optional[ProvenanceRegistry] = None,
        model_backend: str = "mistral-7b",
        thinking_mode: bool = False,
    ):
        self.session_id = session_id or str(uuid.uuid4())
        self.agent_id = agent_id or "anonymous"
        self.agent_level = agent_level
        self.manifests_dir = Path(manifests_dir)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)
        self.registry = registry
        self.model_backend = model_backend
        self.thinking_mode = thinking_mode

        self.manifest_path = self.manifests_dir / f"{self.session_id}.jsonl"
        self._token_records: list[dict] = []
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._finalized = False

        # Session-level thinking data (set once per inference)
        self._reasoning_trace: Optional[str] = None
        self._reasoning_hash: Optional[str] = None

    # ---- Thinking mode helpers ------------------------------------ #

    def set_reasoning_trace(self, trace: Optional[str]) -> None:
        """
        Store the Gemma 4 thinking trace for this session.
        Computes SHA-256 hash of the trace for integrity verification.
        Call once before finalize(); idempotent if trace is None.
        """
        if not trace:
            return
        self._reasoning_trace = trace
        self._reasoning_hash = hashlib.sha256(
            trace.encode("utf-8")
        ).hexdigest()

    # ---- Streaming ------------------------------------------------ #

    def append_token(
        self,
        provenance: TokenProvenance,
        trust_distribution: Optional[list[dict]] = None,
    ) -> dict:
        """
        Append one token provenance record to the manifest JSONL.
        Returns the record dict (for streaming to client).
        """
        token_dict = provenance.to_dict()
        record = {
            "session_id": self.session_id,
            "token_position": provenance.position,
            "token_text": provenance.token_text,
            "token_id": provenance.token_id,
            "attribution": token_dict.get("attribution", []),
            "agent_id": self.agent_id,
            "agent_level": self.agent_level,
            "trust_distribution": trust_distribution or [],
            "average_trust": token_dict.get("trust_avg", 0.0),  # canonical key
            "license_purity": token_dict.get("license_purity", 0.0),
            "model_backend": self.model_backend,
            "thinking_mode": self.thinking_mode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self._token_records.append(record)

        with open(self.manifest_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return record

    async def stream_tokens(
        self, token_provenances: list[TokenProvenance]
    ) -> AsyncIterator[str]:
        """Async generator for FastAPI StreamingResponse."""
        for prov in token_provenances:
            record = self.append_token(prov)
            yield json.dumps(record, ensure_ascii=False) + "\n"

    # ---- Finalize ------------------------------------------------- #

    def finalize(self) -> dict:
        """
        Compute session metrics and write inference record to E5 registry.
        Returns summary dict including manifest_hash and registry_record_id.
        """
        if self._finalized:
            return self.get_summary()

        summary = self.get_summary()

        manifest_content = (
            self.manifest_path.read_bytes() if self.manifest_path.exists() else b""
        )
        manifest_hash = hashlib.sha256(manifest_content).hexdigest()

        registry_record_id = None
        if self.registry is not None:
            try:
                rec = self.registry.append_inference(
                    session_id=self.session_id,
                    requester_agent_id=self.agent_id,
                    manifest_hash=manifest_hash,
                    token_count=summary["total_tokens"],
                    license_purity=summary["license_purity"],
                    high_trust_ratio=summary["high_trust_ratio"],
                )
                registry_record_id = rec["id"]
                logger.info(
                    f"Session {self.session_id} → registry record {registry_record_id}"
                )
            except Exception as e:
                logger.error(f"Failed to write to registry: {e}")

        self._finalized = True
        summary["manifest_hash"] = manifest_hash
        summary["registry_record_id"] = registry_record_id
        return summary

    # ---- Metrics -------------------------------------------------- #

    def get_summary(self) -> dict:
        records = self._token_records
        total = len(records)

        if total == 0:
            return {
                "session_id": self.session_id,
                "agent_id": self.agent_id,
                "agent_level": self.agent_level,
                "total_tokens": 0,
                "license_purity": 0.0,
                "high_trust_ratio": 0.0,
                "dominant_sources": [],
                "model_backend": self.model_backend,
                "thinking_mode": self.thinking_mode,
                "reasoning_trace": self._reasoning_trace,
                "reasoning_hash": self._reasoning_hash,
                "started_at": self._started_at,
                "finalized_at": datetime.now(timezone.utc).isoformat(),
                "manifest_hash": None,
                "registry_record_id": None,
            }

        license_purity = sum(r.get("license_purity", 0.0) for r in records) / total
        high_trust_count = sum(
            1 for r in records if r.get("average_trust", 0.0) >= 0.8
        )
        high_trust_ratio = high_trust_count / total

        source_weights: dict[str, float] = {}
        source_meta: dict[str, dict] = {}
        for record in records:
            for attr in record.get("attribution", []):
                sid = attr.get("segment_id", "")
                if not sid:
                    continue
                w = attr.get("weight", 0.0)
                source_weights[sid] = source_weights.get(sid, 0.0) + w
                if sid not in source_meta:
                    source_meta[sid] = {
                        "source_name": attr.get("source_name", "unknown"),
                        "license_class": attr.get("license_class", "unknown"),
                        "trust_score": attr.get("trust_score", 0.5),
                    }

        top5 = sorted(source_weights.items(), key=lambda x: x[1], reverse=True)[:5]
        dominant_sources = [
            {
                "segment_id": sid,
                "total_weight": round(w, 4),
                **source_meta.get(sid, {}),
            }
            for sid, w in top5
        ]

        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "agent_level": self.agent_level,
            "total_tokens": total,
            "license_purity": round(license_purity, 4),
            "high_trust_ratio": round(high_trust_ratio, 4),
            "dominant_sources": dominant_sources,
            "model_backend": self.model_backend,
            "thinking_mode": self.thinking_mode,
            "reasoning_trace": self._reasoning_trace,
            "reasoning_hash": self._reasoning_hash,
            "started_at": self._started_at,
            "finalized_at": datetime.now(timezone.utc).isoformat(),
            "manifest_hash": None,
            "registry_record_id": None,
        }

    # ---- Load / list --------------------------------------------- #

    @classmethod
    def load(
        cls, session_id: str, manifests_dir: str = "data/manifests"
    ) -> Optional["ManifestGenerator"]:
        path = Path(manifests_dir) / f"{session_id}.jsonl"
        if not path.exists():
            return None

        instance = cls(session_id=session_id, manifests_dir=manifests_dir)
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    instance._token_records.append(json.loads(line))
        if instance._token_records:
            first = instance._token_records[0]
            instance.agent_level   = first.get("agent_level",   "L2")
            instance.agent_id      = first.get("agent_id",      "anonymous")
            instance.model_backend = first.get("model_backend", "mistral-7b")
            instance.thinking_mode = first.get("thinking_mode", False)
        instance._finalized = True
        return instance

    @staticmethod
    def list_sessions(manifests_dir: str = "data/manifests") -> list[str]:
        d = Path(manifests_dir)
        if not d.exists():
            return []
        return [p.stem for p in d.glob("*.jsonl")]
