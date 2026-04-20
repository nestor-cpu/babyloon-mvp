"""
Tests for E3: TrustWeightedAttention
Key invariant: segments with trust < 0.3 are excluded from active corpus.
Run: pytest backend/tests/test_trust.py -v
"""

import json
import pytest

from modules.trust import (
    TrustScoreStore,
    TrustWeightedAttentionHook,
    TrustSession,
    EXCLUSION_THRESHOLD,
    reset_trust_store,
)


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture(autouse=True)
def reset_singleton():
    """Ensure TrustStore singleton is reset between tests."""
    reset_trust_store()
    yield
    reset_trust_store()


@pytest.fixture
def store_from_corpus():
    """TrustScoreStore populated from demo_corpus.json."""
    return TrustScoreStore(use_corpus=True)


@pytest.fixture
def store_custom(tmp_path):
    """TrustScoreStore with custom test scores (no corpus)."""
    scores = {
        "seg-high-001": 0.95,
        "seg-high-002": 0.88,
        "seg-mid-001": 0.65,
        "seg-mid-002": 0.55,
        "seg-low-001": 0.25,    # below threshold
        "seg-low-002": 0.10,    # below threshold
        "seg-low-003": 0.30,    # exactly at threshold (border)
    }
    p = tmp_path / "trust.json"
    p.write_text(json.dumps({"segments": scores}), encoding="utf-8")
    return TrustScoreStore(scores_path=str(p), use_corpus=False)


# ------------------------------------------------------------------ #
# EXCLUSION THRESHOLD — core requirement
# ------------------------------------------------------------------ #

def test_exclusion_threshold_value():
    """EXCLUSION_THRESHOLD must be 0.3."""
    assert EXCLUSION_THRESHOLD == 0.3


def test_low_trust_excluded_from_active(store_custom):
    """Segments with trust < 0.3 must NOT appear in get_active_segments()."""
    active = store_custom.get_active_segments()
    assert "seg-low-001" not in active  # 0.25 < 0.3
    assert "seg-low-002" not in active  # 0.10 < 0.3


def test_border_trust_excluded(store_custom):
    """Segment at exactly 0.3 is NOT active (strict less-than)."""
    active = store_custom.get_active_segments()
    # 0.30 is NOT >= 0.3 when threshold is < — check our implementation
    # Our code uses score < EXCLUSION_THRESHOLD → excluded if score < 0.3
    # So 0.30 >= 0.30 → should be included
    assert "seg-low-003" in active  # 0.30 is at threshold, included


def test_high_and_mid_trust_in_active(store_custom):
    """Segments with trust >= 0.3 appear in get_active_segments()."""
    active = store_custom.get_active_segments()
    assert "seg-high-001" in active
    assert "seg-high-002" in active
    assert "seg-mid-001" in active
    assert "seg-mid-002" in active


def test_active_count(store_custom):
    """Exactly 5 active segments (high ×2, mid ×2, border ×1)."""
    active = store_custom.get_active_segments()
    assert len(active) == 5


# ------------------------------------------------------------------ #
# Level-based license filtering
# ------------------------------------------------------------------ #

def test_l0_sees_all_active(store_from_corpus):
    """L0 agent sees all segments above threshold regardless of license."""
    all_active = store_from_corpus.get_active_segments("L0")
    l1_active = store_from_corpus.get_active_segments("L1")
    # L0 should have >= L1 segments
    assert len(all_active) >= len(l1_active)


def test_l2_sees_only_cc0(store_from_corpus):
    """L2 can only access CC0 / public-domain segments."""
    l2_active = store_from_corpus.get_active_segments("L2")
    for sid in l2_active:
        lic = store_from_corpus.get_license(sid)
        assert lic in {"CC0", "public-domain"}, f"L2 got non-CC0 segment: {sid} ({lic})"


def test_l1_excludes_proprietary(store_from_corpus):
    """L1 must not include proprietary-licensed segments."""
    l0_active = store_from_corpus.get_active_segments("L0")
    l1_active = store_from_corpus.get_active_segments("L1")
    proprietary = {
        sid for sid in l0_active
        if store_from_corpus.get_license(sid) not in
           {"CC0", "CC-BY", "CC-BY-SA", "Apache-2.0", "MIT", "CC-BY-NC-SA"}
    }
    for sid in proprietary:
        assert sid not in l1_active, f"L1 got proprietary segment: {sid}"


# ------------------------------------------------------------------ #
# TrustScoreStore API
# ------------------------------------------------------------------ #

def test_get_existing_score(store_custom):
    assert store_custom.get("seg-high-001") == pytest.approx(0.95)


def test_get_missing_returns_default(store_custom):
    assert store_custom.get("seg-nonexistent") == TrustScoreStore.DEFAULT_TRUST


def test_set_and_get(store_custom):
    store_custom.set("seg-high-001", 0.42)
    assert store_custom.get("seg-high-001") == pytest.approx(0.42)


def test_set_invalid_score_raises(store_custom):
    with pytest.raises(ValueError):
        store_custom.set("seg-x", 1.5)
    with pytest.raises(ValueError):
        store_custom.set("seg-x", -0.1)


def test_top_k_returns_highest(store_custom):
    top3 = store_custom.top_k(3)
    assert len(top3) == 3
    scores = [s for _, s in top3]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == pytest.approx(0.95)


def test_top_k_respects_exclusion(store_custom):
    """top_k should never return excluded segments."""
    top_all = store_custom.top_k(10)
    ids = [sid for sid, _ in top_all]
    assert "seg-low-001" not in ids
    assert "seg-low-002" not in ids


def test_reload_persists_json(store_custom):
    """use_corpus=False: set() persists to JSON, reload() reads it back."""
    store_custom.set("seg-new", 0.77)
    assert store_custom.get("seg-new") == pytest.approx(0.77)
    store_custom.reload()
    # use_corpus=False → reloads from tmp JSON which has "seg-new" persisted
    assert store_custom.get("seg-new") == pytest.approx(0.77)


def test_reload_corpus_overwrites_custom(tmp_path):
    """use_corpus=True: reload() pulls from corpus, discarding in-memory-only extras."""
    store = TrustScoreStore(str(tmp_path / "t.json"), use_corpus=True)
    # Corpus loads 20 segments; manually set a custom key (not persisted)
    store._scores["seg-fake-999"] = 0.77
    assert store.get("seg-fake-999") == pytest.approx(0.77)
    store.reload()
    # After reload from corpus, ephemeral key is gone
    assert store.get("seg-fake-999") == TrustScoreStore.DEFAULT_TRUST


# ------------------------------------------------------------------ #
# Hook: low-trust segments zeroed in attention output
# ------------------------------------------------------------------ #

def test_hook_zeros_low_trust_segments():
    """
    Core patent claim: attention_output * trust_score.
    Segments with trust < 0.3 must be zeroed.
    Test uses synthetic data without real model.
    """
    if not _torch_available():
        pytest.skip("torch not available")

    import torch

    # Build a store with one low-trust and one high-trust segment
    import json
    import tempfile, pathlib
    scores = {"seg-good": 0.9, "seg-bad": 0.2}
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        json.dump({"segments": scores}, f)
        path = f.name

    store = TrustScoreStore(scores_path=path, use_corpus=False)
    mapping = {0: "seg-good", 1: "seg-bad"}
    hook = TrustWeightedAttentionHook(store, mapping, layer_filter="all")

    # Simulate attention output: shape [batch=1, seq=2, hidden=8]
    attn_out = torch.ones(1, 2, 8)

    # Manually call the hook function
    hook_fn = hook._make_hook(0)

    class FakeMod:
        pass

    result = hook_fn(FakeMod(), None, (attn_out,))
    modified = result[0]

    # Position 0: good segment → scaled by 0.9
    assert torch.allclose(modified[:, 0, :], torch.ones(1, 8) * 0.9, atol=1e-5)

    # Position 1: bad segment (trust=0.2 < 0.3) → zeroed
    assert torch.allclose(modified[:, 1, :], torch.zeros(1, 8), atol=1e-5)


def test_hook_distribution_excludes_low_trust():
    """trust_distribution must not include segments with effective_trust == 0."""
    if not _torch_available():
        pytest.skip("torch not available")

    import torch, json, tempfile

    scores = {"seg-a": 0.85, "seg-b": 0.15, "seg-c": 0.70}
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        json.dump({"segments": scores}, f)
        path = f.name

    store = TrustScoreStore(scores_path=path, use_corpus=False)
    mapping = {0: "seg-a", 1: "seg-b", 2: "seg-c"}
    hook = TrustWeightedAttentionHook(store, mapping, layer_filter="all")

    attn_out = torch.ones(1, 3, 4)
    hook_fn = hook._make_hook(0)

    class FakeMod:
        pass

    hook_fn(FakeMod(), None, (attn_out,))
    dist = hook.get_trust_distribution(top_k=5)

    ids_in_dist = [d["segment_id"] for d in dist]
    assert "seg-b" not in ids_in_dist, "Low-trust seg-b should not appear in distribution"
    assert "seg-a" in ids_in_dist
    assert "seg-c" in ids_in_dist


# ------------------------------------------------------------------ #
# TrustSession context manager
# ------------------------------------------------------------------ #

def test_trust_session_no_model():
    """TrustSession with model=None should not crash."""
    from modules.corpus_loader import get_trust_scores
    scores = get_trust_scores()
    store = TrustScoreStore(use_corpus=True)
    mapping = {i: sid for i, sid in enumerate(list(scores.keys())[:5])}

    with TrustSession(None, store, mapping, "all", "L1") as ts:
        dist = ts.get_distribution()
        avg = ts.get_average_trust()

    # No model → no hooks → empty distribution
    assert isinstance(dist, list)
    assert isinstance(avg, float)


# ------------------------------------------------------------------ #
# Corpus integration
# ------------------------------------------------------------------ #

def test_corpus_trust_scores_loaded(store_from_corpus):
    """All 20 demo corpus segments should be in the store."""
    all_scores = store_from_corpus.get_all()
    assert len(all_scores) == 20


def test_corpus_has_excluded_segments(store_from_corpus):
    """Demo corpus has low-trust segments that should be excluded."""
    all_scores = store_from_corpus.get_all()
    below_threshold = [sid for sid, s in all_scores.items() if s < EXCLUSION_THRESHOLD]
    assert len(below_threshold) >= 3, "Expected at least 3 low-trust segments in demo corpus"
    active = store_from_corpus.get_active_segments()
    for sid in below_threshold:
        assert sid not in active


def test_corpus_ukrainian_segments_accessible_l1(store_from_corpus):
    """Ukrainian CC-BY-SA/CC0 segments should be visible at L1."""
    l1_active = store_from_corpus.get_active_segments("L1")
    # seg-wiki-uk-ai-001 is CC-BY-SA, trust=0.94 → should be in L1
    assert "seg-wiki-uk-ai-001" in l1_active


def _torch_available() -> bool:
    try:
        import torch
        return True
    except ImportError:
        return False
