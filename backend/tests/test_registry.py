"""
Tests for E5: ProvenanceRegistry
Run: pytest backend/tests/test_registry.py -v
"""

import hashlib
import json
import os
import tempfile

import pytest

from modules.registry import ProvenanceRegistry, ZERO_HASH


@pytest.fixture
def tmp_registry(tmp_path):
    path = str(tmp_path / "test_registry.jsonl")
    return ProvenanceRegistry(registry_path=path)


# ------------------------------------------------------------------ #
# Basic append & get
# ------------------------------------------------------------------ #

def test_append_corpus_segment(tmp_registry):
    record = tmp_registry.append_corpus_segment(
        segment_id="seg-001",
        source_name="Wikipedia EN",
        source_url="https://en.wikipedia.org",
        license_class="CC-BY-SA",
        content_hash="abc123",
        trust_score=0.9,
    )
    assert record["type"] == "corpus_segment"
    assert record["payload"]["segment_id"] == "seg-001"
    assert record["payload"]["trust_score"] == 0.9
    assert len(record["id"]) == 36  # UUID v4
    assert record["prev_hash"] == ZERO_HASH
    assert len(record["record_hash"]) == 64  # SHA-256 hex


def test_append_inference(tmp_registry):
    record = tmp_registry.append_inference(
        session_id="sess-abc",
        requester_agent_id="agent-001",
        manifest_hash="deadbeef" * 8,
        token_count=128,
        license_purity=0.95,
        high_trust_ratio=0.85,
    )
    assert record["type"] == "inference"
    assert record["payload"]["session_id"] == "sess-abc"
    assert record["payload"]["token_count"] == 128


def test_get_existing_record(tmp_registry):
    appended = tmp_registry.append("corpus_segment", {
        "segment_id": "s1", "source_name": "Test", "source_url": "http://x",
        "license_class": "CC0", "content_hash": "h1", "trust_score": 0.7,
    })
    fetched = tmp_registry.get(appended["id"])
    assert fetched is not None
    assert fetched["id"] == appended["id"]


def test_get_nonexistent_record(tmp_registry):
    result = tmp_registry.get("00000000-0000-0000-0000-000000000000")
    assert result is None


def test_get_by_session(tmp_registry):
    tmp_registry.append_inference("sess-X", "a1", "h1" * 32, 50, 0.9, 0.8)
    tmp_registry.append_inference("sess-X", "a1", "h2" * 32, 60, 0.85, 0.75)
    tmp_registry.append_inference("sess-Y", "a2", "h3" * 32, 70, 0.7, 0.6)

    sess_x = tmp_registry.get_by_session("sess-X")
    assert len(sess_x) == 2
    assert all(r["payload"]["session_id"] == "sess-X" for r in sess_x)

    sess_y = tmp_registry.get_by_session("sess-Y")
    assert len(sess_y) == 1


# ------------------------------------------------------------------ #
# Chain integrity
# ------------------------------------------------------------------ #

def test_empty_registry_verifies(tmp_registry):
    assert tmp_registry.verify_chain() is True


def test_single_record_verifies(tmp_registry):
    tmp_registry.append_corpus_segment("s1", "Src", "http://x", "CC0", "h", 0.8)
    assert tmp_registry.verify_chain() is True


def test_chain_verifies_multiple_records(tmp_registry):
    for i in range(5):
        tmp_registry.append_corpus_segment(
            f"seg-{i:03d}", f"Source {i}", "http://x", "CC0", f"hash{i}", 0.7 + i * 0.05
        )
    assert tmp_registry.verify_chain() is True


def test_chain_links_prev_hash(tmp_registry):
    r1 = tmp_registry.append_corpus_segment("s1", "S1", "http://1", "CC0", "h1", 0.8)
    r2 = tmp_registry.append_corpus_segment("s2", "S2", "http://2", "CC0", "h2", 0.9)
    assert r2["prev_hash"] == r1["record_hash"]
    assert r1["prev_hash"] == ZERO_HASH


# ------------------------------------------------------------------ #
# Tamper detection
# ------------------------------------------------------------------ #

def test_tamper_detection_modified_payload(tmp_registry):
    tmp_registry.append_corpus_segment("s1", "Safe", "http://x", "CC0", "h1", 0.9)
    tmp_registry.append_corpus_segment("s2", "Safe2", "http://y", "CC0", "h2", 0.8)

    # Tamper: manually modify the first record in the file
    path = tmp_registry.registry_path
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    first = json.loads(lines[0])
    first["payload"]["trust_score"] = 0.1  # Evil modification
    lines[0] = json.dumps(first)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert tmp_registry.verify_chain() is False


def test_tamper_detection_deleted_record(tmp_registry):
    for i in range(3):
        tmp_registry.append_corpus_segment(f"s{i}", "S", "http://x", "CC0", "h", 0.8)

    # Delete middle record
    path = tmp_registry.registry_path
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    lines.pop(1)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert tmp_registry.verify_chain() is False


def test_tamper_detection_hash_spoofing(tmp_registry):
    # Build a legitimate 2-record chain first
    tmp_registry.append_corpus_segment("s1", "S1", "http://x", "CC0", "h1", 0.9)
    tmp_registry.append_corpus_segment("s2", "S2", "http://y", "CC0", "h2", 0.8)
    assert tmp_registry.verify_chain() is True  # baseline OK

    path = tmp_registry.registry_path
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2

    # Attacker tampers s1: changes payload AND recomputes its record_hash
    # BUT s2.prev_hash still points to the ORIGINAL s1.record_hash → chain breaks
    record = json.loads(lines[0])
    original_s1_hash = record["record_hash"]
    record["payload"]["trust_score"] = 0.1  # evil modification
    fields = {k: v for k, v in record.items() if k != "record_hash"}
    record["record_hash"] = hashlib.sha256(
        json.dumps(fields, sort_keys=True).encode()
    ).hexdigest()
    assert record["record_hash"] != original_s1_hash  # hash changed
    lines[0] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # s2.prev_hash still has original_s1_hash → verify_chain must detect mismatch
    assert tmp_registry.verify_chain() is False


# ------------------------------------------------------------------ #
# Persistence
# ------------------------------------------------------------------ #

def test_persistence_across_instances(tmp_path):
    path = str(tmp_path / "persist.jsonl")

    reg1 = ProvenanceRegistry(registry_path=path)
    r1 = reg1.append_corpus_segment("s1", "S1", "http://x", "CC0", "h1", 0.8)

    # New instance reads same file
    reg2 = ProvenanceRegistry(registry_path=path)
    assert reg2.verify_chain() is True
    r2 = reg2.append_corpus_segment("s2", "S2", "http://y", "CC0", "h2", 0.9)
    assert r2["prev_hash"] == r1["record_hash"]


def test_invalid_record_type(tmp_registry):
    with pytest.raises(ValueError, match="Unknown record type"):
        tmp_registry.append("INVALID_TYPE", {"foo": "bar"})
