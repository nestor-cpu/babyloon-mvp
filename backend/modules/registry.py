"""
E5: ProvenanceRegistry — незмінний криптографічний реєстр
Patent claim: SHA-256 hash-chain, JSONL append-only, tamper detection
PCT/IB2026/053131
"""

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


ZERO_HASH = hashlib.sha256(b"\x00" * 32).hexdigest()


class ProvenanceRegistry:
    def __init__(self, registry_path: str = "data/corpus_registry.jsonl"):
        self.registry_path = Path(registry_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.registry_path.exists():
            self.registry_path.touch()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _last_hash(self) -> str:
        """Return hash of the last record, or ZERO_HASH if registry is empty."""
        last = None
        if self.registry_path.exists():
            with open(self.registry_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        last = line
        if last is None:
            return ZERO_HASH
        record = json.loads(last)
        return record["record_hash"]

    @staticmethod
    def _compute_record_hash(record: dict) -> str:
        """SHA-256 over canonical JSON of all fields except record_hash itself."""
        fields = {k: v for k, v in record.items() if k != "record_hash"}
        canonical = json.dumps(fields, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def append(self, record_type: str, payload: dict) -> dict:
        """
        Append a new record to the JSONL registry.
        record_type: "corpus_segment" | "inference"
        Returns the full record including hashes.
        """
        if record_type not in ("corpus_segment", "inference"):
            raise ValueError(f"Unknown record type: {record_type}")

        prev_hash = self._last_hash()
        record = {
            "id": str(uuid.uuid4()),
            "type": record_type,
            "payload": payload,
            "prev_hash": prev_hash,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "record_hash": "",  # placeholder
        }
        record["record_hash"] = self._compute_record_hash(record)

        with open(self.registry_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return record

    def get(self, record_id: str) -> Optional[dict]:
        """Retrieve a single record by UUID."""
        if not self.registry_path.exists():
            return None
        with open(self.registry_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if record["id"] == record_id:
                    return record
        return None

    def get_by_session(self, session_id: str) -> list[dict]:
        """Return all 'inference' records whose payload.session_id matches."""
        results = []
        if not self.registry_path.exists():
            return results
        with open(self.registry_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if (
                    record["type"] == "inference"
                    and record.get("payload", {}).get("session_id") == session_id
                ):
                    results.append(record)
        return results

    def get_all(self) -> list[dict]:
        """Return all records."""
        records = []
        if not self.registry_path.exists():
            return records
        with open(self.registry_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def verify_chain(self) -> bool:
        """
        Traverse the entire chain and verify hash integrity.
        Returns True only if every record's hashes are consistent.
        Tamper detection: any modification to any record breaks the chain.
        """
        prev_hash = ZERO_HASH
        if not self.registry_path.exists():
            return True
        with open(self.registry_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    return False

                # Verify prev_hash linkage
                if record["prev_hash"] != prev_hash:
                    return False

                # Verify record_hash integrity
                expected_hash = self._compute_record_hash(record)
                if record["record_hash"] != expected_hash:
                    return False

                prev_hash = record["record_hash"]

        return True

    def append_corpus_segment(
        self,
        segment_id: str,
        source_name: str,
        source_url: str,
        license_class: str,
        content_hash: str,
        trust_score: float,
        session_id: Optional[str] = None,
    ) -> dict:
        """Convenience wrapper for corpus_segment records."""
        payload = {
            "segment_id": segment_id,
            "source_name": source_name,
            "source_url": source_url,
            "license_class": license_class,
            "content_hash": content_hash,
            "trust_score": trust_score,
        }
        if session_id:
            payload["session_id"] = session_id
        return self.append("corpus_segment", payload)

    def append_inference(
        self,
        session_id: str,
        requester_agent_id: str,
        manifest_hash: str,
        token_count: int,
        license_purity: float,
        high_trust_ratio: float,
    ) -> dict:
        """Convenience wrapper for inference records."""
        payload = {
            "session_id": session_id,
            "requester_agent_id": requester_agent_id,
            "manifest_hash": manifest_hash,
            "token_count": token_count,
            "license_purity": license_purity,
            "high_trust_ratio": high_trust_ratio,
        }
        return self.append("inference", payload)


# Module-level singleton (lazy init)
_registry: Optional[ProvenanceRegistry] = None


def get_registry(path: str = "data/corpus_registry.jsonl") -> ProvenanceRegistry:
    global _registry
    if _registry is None:
        _registry = ProvenanceRegistry(path)
    return _registry
