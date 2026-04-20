"""
corpus_loader.py — Demo corpus management for babyloon.ai
Loads demo_corpus.json, registers segments in E5, builds token→segment maps.
PCT/IB2026/053131
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CORPUS_PATH = Path(__file__).parent.parent / "data" / "demo_corpus.json"

# License classes allowed per authorization level (E2 filtering)
LICENSE_BY_LEVEL: dict[str, Optional[set]] = {
    "L0": None,  # no filter — all licenses
    "L1": {"CC0", "CC-BY", "CC-BY-SA", "Apache-2.0", "MIT", "CC-BY-NC-SA", "CC-BY-NC"},
    "L2": {"CC0", "public-domain"},
}


@dataclass
class CorpusSegment:
    segment_id: str
    source_name: str
    source_url: str
    license_class: str
    language: str
    trust_score: float
    content: str

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "license_class": self.license_class,
            "language": self.language,
            "trust_score": self.trust_score,
            "content_hash": self.content_hash,
        }


# ------------------------------------------------------------------ #
# Module-level cache
# ------------------------------------------------------------------ #

_corpus_cache: Optional[list[CorpusSegment]] = None
_segment_index: dict[str, CorpusSegment] = {}


def load_corpus(path: Optional[str] = None) -> list[CorpusSegment]:
    """
    Load corpus from JSON file. Cached after first load.
    Returns list of CorpusSegment.
    """
    global _corpus_cache, _segment_index

    if _corpus_cache is not None:
        return _corpus_cache

    corpus_path = Path(path) if path else CORPUS_PATH
    if not corpus_path.exists():
        logger.warning(f"Corpus not found at {corpus_path} — returning empty corpus")
        _corpus_cache = []
        return _corpus_cache

    data = json.loads(corpus_path.read_text(encoding="utf-8"))
    segments = []
    for raw in data.get("segments", []):
        seg = CorpusSegment(
            segment_id=raw["segment_id"],
            source_name=raw["source_name"],
            source_url=raw["source_url"],
            license_class=raw["license_class"],
            language=raw.get("language", "en"),
            trust_score=float(raw["trust_score"]),
            content=raw["content"],
        )
        segments.append(seg)
        _segment_index[seg.segment_id] = seg

    _corpus_cache = segments
    logger.info(f"Loaded {len(segments)} corpus segments from {corpus_path}")
    return _corpus_cache


def get_segment_by_id(segment_id: str) -> Optional[CorpusSegment]:
    """Return a single segment by ID (loads corpus if not yet loaded)."""
    if not _segment_index:
        load_corpus()
    return _segment_index.get(segment_id)


def get_trust_scores(path: Optional[str] = None) -> dict[str, float]:
    """
    Return {segment_id: trust_score} for all corpus segments.
    Used by trust.TrustScoreStore.
    """
    corpus = load_corpus(path)
    return {seg.segment_id: seg.trust_score for seg in corpus}


def register_corpus_in_registry(registry, path: Optional[str] = None) -> int:
    """
    Register all corpus segments as corpus_segment records in E5 registry.
    Idempotent: skips segments already registered (checks by content_hash).
    Returns number of newly registered segments.
    """
    corpus = load_corpus(path)
    if not corpus:
        return 0

    # Get existing content hashes to avoid duplicates
    existing_hashes: set[str] = set()
    for record in registry.get_all():
        if record["type"] == "corpus_segment":
            ch = record.get("payload", {}).get("content_hash")
            if ch:
                existing_hashes.add(ch)

    registered = 0
    for seg in corpus:
        if seg.content_hash in existing_hashes:
            continue
        registry.append_corpus_segment(
            segment_id=seg.segment_id,
            source_name=seg.source_name,
            source_url=seg.source_url,
            license_class=seg.license_class,
            content_hash=seg.content_hash,
            trust_score=seg.trust_score,
        )
        registered += 1

    logger.info(f"Registered {registered} new corpus segments in E5 registry")
    return registered


def filter_by_level(
    corpus: list[CorpusSegment], level: str
) -> list[CorpusSegment]:
    """
    Filter corpus segments by agent authorization level.
    L0: all   L1: verified licenses   L2: CC0/public-domain only
    """
    allowed = LICENSE_BY_LEVEL.get(level)
    if allowed is None:
        return corpus
    return [seg for seg in corpus if seg.license_class in allowed]


def build_token_segment_map(
    token_ids: list[int],
    corpus: Optional[list[CorpusSegment]] = None,
    level: str = "L0",
) -> dict[int, str]:
    """
    Map each token position to a corpus segment_id.

    Strategy for MVP: round-robin assignment across active (trust ≥ 0.3)
    filtered corpus segments. On a GPU server this would use vector search
    to find which corpus passage each token position most likely came from.

    Returns {position: segment_id}
    """
    if corpus is None:
        corpus = load_corpus()

    # Filter by level and exclude low-trust segments
    active = [
        seg for seg in filter_by_level(corpus, level)
        if seg.trust_score >= 0.3
    ]

    if not active:
        return {}

    mapping: dict[int, str] = {}
    for pos in range(len(token_ids)):
        seg = active[pos % len(active)]
        mapping[pos] = seg.segment_id

    return mapping


def get_segment_meta(segment_id: str) -> dict:
    """Return metadata dict for use by attribution module."""
    seg = get_segment_by_id(segment_id)
    if seg is None:
        return {
            "source_name": "unknown",
            "license_class": "unknown",
            "trust_score": 0.5,
            "language": "en",
        }
    return {
        "source_name": seg.source_name,
        "license_class": seg.license_class,
        "trust_score": seg.trust_score,
        "language": seg.language,
    }


def reload_corpus() -> None:
    """Force reload from disk (useful for hot-updates)."""
    global _corpus_cache, _segment_index
    _corpus_cache = None
    _segment_index = {}
    load_corpus()
    logger.info("Corpus reloaded")
