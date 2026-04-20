"""
Integration tests for the full babyloon.ai pipeline.
Tests E5 + E2 + E3 + E4 integration WITHOUT model (mock generation).
Run: pytest backend/tests/test_pipeline.py -v
"""

import hashlib
import json
import uuid

import pytest

from modules.registry import ProvenanceRegistry
from modules.identity import AgentVerifier
from modules.trust import TrustScoreStore
from modules.attribution import (
    ProvenanceAttribution,
    SegmentMetaStore,
    TokenProvenance,
    SourceAttribution,
)
from modules.manifest import ManifestGenerator


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def tmp_registry(tmp_path):
    return ProvenanceRegistry(str(tmp_path / "registry.jsonl"))


@pytest.fixture
def tmp_verifier(tmp_path):
    return AgentVerifier(str(tmp_path / "agents.json"))


@pytest.fixture
def tmp_trust(tmp_path):
    # use_corpus=False → isolated custom scores, no demo corpus interference
    store = TrustScoreStore(str(tmp_path / "trust.json"), use_corpus=False)
    store.set("seg-wikipedia", 0.95)
    store.set("seg-arxiv", 0.88)
    store.set("seg-gutenberg", 0.72)
    store.set("seg-lowquality", 0.15)  # below exclusion threshold
    return store


@pytest.fixture
def meta_store():
    ms = SegmentMetaStore()
    ms.add("seg-wikipedia", {"source_name": "Wikipedia EN", "license_class": "CC-BY-SA", "trust_score": 0.95})
    ms.add("seg-arxiv", {"source_name": "arXiv", "license_class": "CC-BY", "trust_score": 0.88})
    ms.add("seg-gutenberg", {"source_name": "Project Gutenberg", "license_class": "CC0", "trust_score": 0.72})
    ms.add("seg-lowquality", {"source_name": "LowQ Source", "license_class": "unknown", "trust_score": 0.15})
    return ms


# ------------------------------------------------------------------ #
# Trust store tests
# ------------------------------------------------------------------ #

def test_trust_active_segments(tmp_trust):
    active = tmp_trust.get_active_segments()
    assert "seg-wikipedia" in active
    assert "seg-arxiv" in active
    assert "seg-gutenberg" in active
    assert "seg-lowquality" not in active  # below threshold 0.3


def test_trust_top_k(tmp_trust):
    top3 = tmp_trust.top_k(3)
    assert len(top3) == 3
    assert top3[0][0] == "seg-wikipedia"
    assert top3[0][1] == 0.95


def test_trust_hot_reload(tmp_trust):
    tmp_trust.set("seg-new", 0.99)
    assert tmp_trust.get("seg-new") == 0.99
    tmp_trust.reload()
    assert tmp_trust.get("seg-new") == 0.99


# ------------------------------------------------------------------ #
# Attribution data structures
# ------------------------------------------------------------------ #

def test_source_attribution_to_dict(meta_store):
    attr = SourceAttribution(
        segment_id="seg-wikipedia",
        source_name="Wikipedia EN",
        weight=0.65,
        license_class="CC-BY-SA",
        trust_score=0.95,
    )
    d = attr.to_dict()
    assert d["segment_id"] == "seg-wikipedia"
    assert d["weight"] == 0.65
    assert d["trust_score"] == 0.95


def test_token_provenance_to_dict():
    prov = TokenProvenance(
        token_id=1234,
        token_text=" Paris",
        position=5,
        attribution=[
            SourceAttribution("seg-wiki", "Wikipedia", 0.7, "CC-BY-SA", 0.95),
            SourceAttribution("seg-arxiv", "arXiv", 0.3, "CC-BY", 0.88),
        ],
    )
    d = prov.to_dict()
    assert d["text"] == " Paris"
    assert d["position"] == 5
    assert len(d["attribution"]) == 2
    assert d["dominant_source"]["segment_id"] == "seg-wiki"
    # weighted average: (0.7*0.95 + 0.3*0.88) / 1.0 = 0.929
    assert d["trust_avg"] == pytest.approx(0.929, abs=0.01)


def test_license_purity_clean():
    prov = TokenProvenance(
        token_id=1, token_text=" x", position=0,
        attribution=[
            SourceAttribution("s1", "S1", 0.6, "CC0", 0.9),
            SourceAttribution("s2", "S2", 0.4, "Apache-2.0", 0.8),
        ],
    )
    assert prov._license_purity() == 1.0


def test_license_purity_mixed():
    prov = TokenProvenance(
        token_id=1, token_text=" x", position=0,
        attribution=[
            SourceAttribution("s1", "S1", 0.5, "CC0", 0.9),
            SourceAttribution("s2", "S2", 0.5, "proprietary", 0.4),
        ],
    )
    assert prov._license_purity() == 0.5


# ------------------------------------------------------------------ #
# Manifest generation
# ------------------------------------------------------------------ #

def test_manifest_append_and_summary(tmp_path, tmp_registry):
    mgen = ManifestGenerator(
        session_id="test-sess-001",
        agent_id="agent-001",
        agent_level="L1",
        manifests_dir=str(tmp_path / "manifests"),
        registry=tmp_registry,
    )

    for i in range(5):
        prov = TokenProvenance(
            token_id=100 + i,
            token_text=f" word{i}",
            position=i,
            attribution=[
                SourceAttribution("seg-wikipedia", "Wikipedia", 0.7, "CC-BY-SA", 0.95),
                SourceAttribution("seg-arxiv", "arXiv", 0.3, "CC-BY", 0.88),
            ],
        )
        mgen.append_token(prov)

    summary = mgen.finalize()
    assert summary["total_tokens"] == 5
    assert summary["session_id"] == "test-sess-001"
    assert 0.0 <= summary["license_purity"] <= 1.0
    assert 0.0 <= summary["high_trust_ratio"] <= 1.0
    assert len(summary["dominant_sources"]) <= 5
    assert "manifest_hash" in summary


def test_manifest_writes_to_registry(tmp_path, tmp_registry):
    mgen = ManifestGenerator(
        session_id="reg-test-sess",
        agent_id="agent-xyz",
        agent_level="L0",
        manifests_dir=str(tmp_path / "manifests"),
        registry=tmp_registry,
    )

    prov = TokenProvenance(1, " hello", 0, [
        SourceAttribution("seg-wikipedia", "Wiki", 0.8, "CC-BY-SA", 0.95)
    ])
    mgen.append_token(prov)
    mgen.finalize()

    # Check that inference record was written to E5 registry
    records = tmp_registry.get_by_session("reg-test-sess")
    assert len(records) == 1
    assert records[0]["type"] == "inference"
    assert records[0]["payload"]["requester_agent_id"] == "agent-xyz"
    assert records[0]["payload"]["token_count"] == 1

    # Chain should still be valid
    assert tmp_registry.verify_chain() is True


def test_manifest_persistence(tmp_path, tmp_registry):
    manifests_dir = str(tmp_path / "manifests")
    sid = "persist-sess"

    mgen = ManifestGenerator(sid, "agent-1", "L1", manifests_dir, tmp_registry)
    prov = TokenProvenance(42, " test", 0, [
        SourceAttribution("seg-gutenberg", "Gutenberg", 0.9, "CC0", 0.72)
    ])
    mgen.append_token(prov)
    mgen.finalize()

    # Load from disk
    loaded = ManifestGenerator.load(sid, manifests_dir)
    assert loaded is not None
    assert len(loaded._token_records) == 1
    assert loaded._token_records[0]["token_text"] == " test"


def test_manifest_list_sessions(tmp_path):
    manifests_dir = str(tmp_path / "manifests")
    for i in range(3):
        mgen = ManifestGenerator(f"sess-{i}", "a", "L2", manifests_dir)
        prov = TokenProvenance(i, f" t{i}", 0, [])
        mgen.append_token(prov)

    sessions = ManifestGenerator.list_sessions(manifests_dir)
    assert len(sessions) == 3
    assert "sess-0" in sessions


# ------------------------------------------------------------------ #
# Full mini-pipeline: E2 → E5 → E4 (no model)
# ------------------------------------------------------------------ #

def test_full_pipeline_no_model(tmp_path, tmp_registry, tmp_verifier, tmp_trust):
    """
    Simulate a full session without loading a real LLM.
    Verifies that all components integrate correctly.
    """
    manifests_dir = str(tmp_path / "manifests")

    # E2: Register and verify agent
    l1_record, l1_token = tmp_verifier.register_agent("TestPartner", "L1")
    result = tmp_verifier.verify_agent(l1_token)
    assert result.is_valid is True
    assert result.level == "L1"

    # E3: Get active segments respecting agent level
    active = tmp_trust.get_active_segments()
    assert len(active) >= 3

    # E1: Build mock token provenances (simulating model output)
    session_id = str(uuid.uuid4())
    mgen = ManifestGenerator(session_id, result.agent_id, result.level, manifests_dir, tmp_registry)

    output_words = ["The", " capital", " of", " France", " is", " Paris", "."]
    for i, word in enumerate(output_words):
        prov = TokenProvenance(
            token_id=1000 + i,
            token_text=word,
            position=i,
            attribution=[
                SourceAttribution("seg-wikipedia", "Wikipedia EN", 0.75, "CC-BY-SA", 0.95),
                SourceAttribution("seg-arxiv", "arXiv", 0.15, "CC-BY", 0.88),
                SourceAttribution("seg-gutenberg", "Gutenberg", 0.10, "CC0", 0.72),
            ],
        )
        mgen.append_token(prov)

    # E4: Finalize → writes to E5 registry
    summary = mgen.finalize()
    assert summary["total_tokens"] == 7
    assert summary["dominant_sources"][0]["segment_id"] == "seg-wikipedia"

    # E5: Chain integrity
    assert tmp_registry.verify_chain() is True
    inference_records = tmp_registry.get_by_session(session_id)
    assert len(inference_records) == 1
    assert inference_records[0]["payload"]["token_count"] == 7

    # E6: No token → fallback L2
    fallback = tmp_verifier.verify_agent("")
    assert fallback.level == "L2"
    assert fallback.is_valid is False


# ================================================================== #
# E2E test via FastAPI TestClient (MOCK_GENERATE=1, no GPU)
# ================================================================== #

def test_full_e2e_generate_mock(tmp_path, monkeypatch):
    """
    End-to-end test: all 6 mechanisms through the HTTP API.
    Uses MOCK_GENERATE=1 and isolated tmp data directories.
    """
    import os
    from fastapi.testclient import TestClient

    # Point all data to tmp dir so tests don't pollute real data
    monkeypatch.setenv("MOCK_GENERATE", "1")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    # Reset all module-level singletons so they pick up the new DATA_DIR
    import models.loader as loader_mod
    loader_mod._model = None
    loader_mod._tokenizer = None

    import modules.registry as reg_mod
    reg_mod._registry = None

    import modules.identity as id_mod
    id_mod._verifier = None

    from modules.trust import reset_trust_store
    reset_trust_store()

    import modules.corpus_loader as cl_mod
    cl_mod._corpus_cache = None
    cl_mod._segment_index = {}

    # Now import app (after env vars set)
    from main import app

    client = TestClient(app, raise_server_exceptions=True)

    # ---- 1. Register an L1 agent (E2) --------------------------------
    resp = client.post("/agent/register", json={
        "name": "E2E-Test-Agent",
        "level": "L1",
        "ttl_days": 1,
    })
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    agent_id = resp.json()["agent"]["agent_id"]

    # ---- 2. Verify health --------------------------------------------
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["mock_mode"] is True

    # ---- 3. POST /generate (E1+E2+E3+E4+E5) -------------------------
    resp = client.post(
        "/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "prompt": "What is the capital of France?",
            "max_new_tokens": 50,
        },
    )
    assert resp.status_code == 200, f"Generate failed: {resp.text}"
    data = resp.json()

    # ---- 4. Verify response structure --------------------------------
    assert "session_id" in data
    assert data["agent_level"] == "L1"
    assert data["agent_id"] == agent_id
    assert isinstance(data["output_text"], str)
    assert len(data["output_text"]) > 0

    # tokens structure
    tokens = data["tokens"]
    assert len(tokens) > 0
    for i, tok in enumerate(tokens):
        assert "position" in tok
        assert "text" in tok
        assert "trust_avg" in tok
        assert tok["trust_color"] in {"green", "yellow", "red"}
        assert isinstance(tok["attribution"], list)

    # summary structure
    summary = data["summary"]
    assert "license_purity" in summary
    assert "high_trust_ratio" in summary
    assert "dominant_sources" in summary
    assert "total_tokens" in summary
    assert summary["total_tokens"] == len(tokens)
    assert 0.0 <= summary["license_purity"] <= 1.0
    assert 0.0 <= summary["high_trust_ratio"] <= 1.0

    # ---- 5. Verify manifest was written (E4) -------------------------
    session_id = data["session_id"]
    resp = client.get(f"/manifest/{session_id}/summary")
    assert resp.status_code == 200
    manifest_summary = resp.json()
    assert manifest_summary["agent_level"] == "L1"
    assert manifest_summary["total_tokens"] == len(tokens)

    # ---- 6. Verify registry was written (E5) -------------------------
    resp = client.get(f"/registry/session/{session_id}")
    assert resp.status_code == 200
    registry_records = resp.json()
    assert len(registry_records) >= 1
    assert registry_records[0]["type"] == "inference"
    assert registry_records[0]["payload"]["requester_agent_id"] == agent_id

    # Chain integrity
    resp = client.get("/registry/verify")
    assert resp.status_code == 200
    assert resp.json()["valid"] is True

    # ---- 7. E6 fallback: no token → L2 response ----------------------
    resp = client.post(
        "/generate",
        json={"prompt": "Test fallback", "max_new_tokens": 20},
        # No Authorization header
    )
    assert resp.status_code == 200
    fallback_data = resp.json()
    assert fallback_data["agent_level"] == "L2"  # E6 fallback

    # ---- 8. L2 license filtering: only CC0 in attribution ------------
    for tok in fallback_data["tokens"]:
        for attr in tok["attribution"]:
            assert attr["license_class"] in {"CC0", "public-domain"}, \
                f"L2 got non-CC0 segment: {attr['segment_id']} ({attr['license_class']})"
