"""
Tests for ModelAdapter (backend/models/manager.py).
All tests run without GPU — MOCK_GENERATE=1 is set per test via monkeypatch.

Coverage:
  - Interface compliance for all 3 model variants
  - Thinking extraction (Gemma 4 only)
  - Chat prompt formatting (Mistral vs Gemma)
  - Context length constants
  - supports_thinking() per family
  - tokenize / detokenize round-trips
  - generate() return-dict schema
  - Singleton + reset
  - Invalid BABYLOON_MODEL key graceful fallback
  - _extract_thinking helper directly

Run: pytest backend/tests/test_manager.py -v
"""

import os
import pytest

# ── Isolate singleton between every test ──────────────────────────── #

@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    """Reset adapter singleton and ensure mock mode for every test."""
    monkeypatch.setenv("MOCK_GENERATE", "1")
    from models import manager
    manager.reset_adapter()
    yield
    manager.reset_adapter()


# ── Helpers ───────────────────────────────────────────────────────── #

def _get(model_key: str):
    """Return a fresh mock adapter for the given model key."""
    from models import manager
    manager.reset_adapter()
    os.environ["BABYLOON_MODEL"] = model_key
    adapter = manager.get_adapter()
    return adapter


# ================================================================== #
# 1. _extract_thinking helper
# ================================================================== #

def test_extract_thinking_present():
    from models.manager import _extract_thinking
    raw = "<|think|>step 1\nstep 2<|/think|>Final answer."
    text, trace = _extract_thinking(raw)
    assert text == "Final answer."
    assert trace == "step 1\nstep 2"


def test_extract_thinking_absent():
    from models.manager import _extract_thinking
    text, trace = _extract_thinking("No thinking here.")
    assert text == "No thinking here."
    assert trace is None


def test_extract_thinking_multiline():
    from models.manager import _extract_thinking
    raw = "<|think|>\n  - reason A\n  - reason B\n<|/think|>Answer."
    _, trace = _extract_thinking(raw)
    assert "reason A" in trace
    assert "reason B" in trace


def test_extract_thinking_strips_whitespace():
    from models.manager import _extract_thinking
    raw = "  <|think|>  thoughts  <|/think|>  answer  "
    text, trace = _extract_thinking(raw)
    assert text == "answer"
    assert trace == "thoughts"


# ================================================================== #
# 2. Model metadata
# ================================================================== #

@pytest.mark.parametrize("key,expected_ctx", [
    ("mistral-7b",   32_768),
    ("gemma-4-12b", 131_072),
    ("gemma-4-e4b", 131_072),
])
def test_max_context(key, expected_ctx, monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", key)
    adapter = _get(key)
    assert adapter.get_max_context() == expected_ctx


@pytest.mark.parametrize("key,expected", [
    ("mistral-7b",  False),
    ("gemma-4-12b", True),
    ("gemma-4-e4b", True),
])
def test_supports_thinking(key, expected, monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", key)
    adapter = _get(key)
    assert adapter.supports_thinking() is expected


@pytest.mark.parametrize("key", ["mistral-7b", "gemma-4-12b", "gemma-4-e4b"])
def test_get_model_name_matches_key(key, monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", key)
    adapter = _get(key)
    assert adapter.get_model_name() == key


# ================================================================== #
# 3. generate() — return dict schema
# ================================================================== #

_REQUIRED_KEYS = {"text", "reasoning_trace", "prompt_token_ids", "output_token_ids", "model_name"}

@pytest.mark.parametrize("key", ["mistral-7b", "gemma-4-12b", "gemma-4-e4b"])
def test_generate_returns_required_keys(key, monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", key)
    adapter = _get(key)
    result = adapter.generate("What is the capital of France?")
    assert _REQUIRED_KEYS == set(result.keys()), (
        f"Missing keys: {_REQUIRED_KEYS - set(result.keys())}"
    )


@pytest.mark.parametrize("key", ["mistral-7b", "gemma-4-12b", "gemma-4-e4b"])
def test_generate_text_is_nonempty_string(key, monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", key)
    result = _get(key).generate("Explain neural networks.")
    assert isinstance(result["text"], str)
    assert len(result["text"]) > 0


@pytest.mark.parametrize("key", ["mistral-7b", "gemma-4-12b", "gemma-4-e4b"])
def test_generate_token_ids_are_lists_of_ints(key, monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", key)
    result = _get(key).generate("Test prompt.")
    for field in ("prompt_token_ids", "output_token_ids"):
        assert isinstance(result[field], list), f"{field} must be list"
        assert all(isinstance(i, int) for i in result[field]), f"{field} must contain ints"


@pytest.mark.parametrize("key", ["mistral-7b", "gemma-4-12b", "gemma-4-e4b"])
def test_generate_model_name_in_result(key, monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", key)
    result = _get(key).generate("Hello.")
    assert result["model_name"] == key


# ================================================================== #
# 4. Thinking mode
# ================================================================== #

def test_gemma_generate_has_reasoning_trace(monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", "gemma-4-12b")
    result = _get("gemma-4-12b").generate("What is machine learning?")
    assert result["reasoning_trace"] is not None
    assert isinstance(result["reasoning_trace"], str)
    assert len(result["reasoning_trace"]) > 0


def test_gemma_visible_text_has_no_think_tags(monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", "gemma-4-12b")
    result = _get("gemma-4-12b").generate("Explain gradient descent.")
    assert "<|think|>" not in result["text"]
    assert "<|/think|>" not in result["text"]


def test_gemma_e4b_has_reasoning_trace(monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", "gemma-4-e4b")
    result = _get("gemma-4-e4b").generate("What is AI?")
    assert result["reasoning_trace"] is not None


def test_mistral_reasoning_trace_is_none(monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", "mistral-7b")
    result = _get("mistral-7b").generate("What is France's capital?")
    assert result["reasoning_trace"] is None


def test_gemma_text_contains_actual_answer(monkeypatch):
    """After stripping thinking, visible text must be the real answer."""
    monkeypatch.setenv("BABYLOON_MODEL", "gemma-4-12b")
    result = _get("gemma-4-12b").generate("What is the capital of France?")
    # Mock response for 'france' is 'The capital of France is Paris.'
    assert "Paris" in result["text"]


# ================================================================== #
# 5. Chat prompt format
# ================================================================== #

def test_mistral_prompt_format(monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", "mistral-7b")
    adapter = _get("mistral-7b")
    formatted = adapter._format_prompt("Hello world")
    assert "[INST]" in formatted
    assert "[/INST]" in formatted
    assert "Hello world" in formatted


def test_gemma_prompt_format(monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", "gemma-4-12b")
    adapter = _get("gemma-4-12b")
    formatted = adapter._format_prompt("Hello world")
    assert "<start_of_turn>user" in formatted
    assert "<end_of_turn>" in formatted
    assert "<start_of_turn>model" in formatted
    assert "Hello world" in formatted


def test_gemma_prompt_bos_ordering(monkeypatch):
    """user turn must come before model turn."""
    monkeypatch.setenv("BABYLOON_MODEL", "gemma-4-12b")
    formatted = _get("gemma-4-12b")._format_prompt("test")
    user_pos  = formatted.index("<start_of_turn>user")
    model_pos = formatted.index("<start_of_turn>model")
    assert user_pos < model_pos


def test_mistral_vs_gemma_format_differ(monkeypatch):
    prompt = "Tell me about Paris."
    monkeypatch.setenv("BABYLOON_MODEL", "mistral-7b")
    m_fmt = _get("mistral-7b")._format_prompt(prompt)
    monkeypatch.setenv("BABYLOON_MODEL", "gemma-4-12b")
    g_fmt = _get("gemma-4-12b")._format_prompt(prompt)
    assert m_fmt != g_fmt


# ================================================================== #
# 6. tokenize / detokenize
# ================================================================== #

@pytest.mark.parametrize("key", ["mistral-7b", "gemma-4-12b", "gemma-4-e4b"])
def test_tokenize_returns_list_of_ints(key, monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", key)
    ids = _get(key).tokenize("Hello babyloon")
    assert isinstance(ids, list)
    assert len(ids) > 0
    assert all(isinstance(i, int) for i in ids)


@pytest.mark.parametrize("key", ["mistral-7b", "gemma-4-12b", "gemma-4-e4b"])
def test_detokenize_returns_str(key, monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", key)
    adapter = _get(key)
    ids = adapter.tokenize("The capital of France")
    text = adapter.detokenize(ids)
    assert isinstance(text, str)


@pytest.mark.parametrize("key", ["mistral-7b", "gemma-4-12b", "gemma-4-e4b"])
def test_tokenize_detokenize_nonempty(key, monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", key)
    adapter = _get(key)
    ids = adapter.tokenize("babyloon provenance")
    assert len(ids) > 0
    decoded = adapter.detokenize(ids)
    assert len(decoded) > 0


# ================================================================== #
# 7. Singleton behaviour
# ================================================================== #

def test_singleton_returns_same_instance(monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", "mistral-7b")
    from models import manager
    a1 = manager.get_adapter()
    a2 = manager.get_adapter()
    assert a1 is a2


def test_reset_adapter_creates_new_instance(monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", "mistral-7b")
    from models import manager
    a1 = manager.get_adapter()
    manager.reset_adapter()
    a2 = manager.get_adapter()
    assert a1 is not a2


def test_model_switch_after_reset(monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", "mistral-7b")
    from models import manager
    a1 = manager.get_adapter()
    assert a1.get_model_name() == "mistral-7b"

    manager.reset_adapter()
    monkeypatch.setenv("BABYLOON_MODEL", "gemma-4-12b")
    a2 = manager.get_adapter()
    assert a2.get_model_name() == "gemma-4-12b"


# ================================================================== #
# 8. Invalid key fallback
# ================================================================== #

def test_invalid_model_key_falls_back_to_mistral(monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", "gpt-999-turbo")
    from models import manager
    manager.reset_adapter()
    adapter = manager.get_adapter()
    # Fallback → mistral-7b
    assert adapter.get_model_name() == "mistral-7b"
    assert adapter.get_max_context() == 32_768
    assert adapter.supports_thinking() is False


def test_empty_model_key_falls_back(monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", "")
    from models import manager
    manager.reset_adapter()
    adapter = manager.get_adapter()
    assert adapter.get_model_name() == "mistral-7b"


# ================================================================== #
# 9. generate() determinism & content routing
# ================================================================== #

@pytest.mark.parametrize("prompt,expected_word", [
    ("What is the capital of France?",   "Paris"),
    ("Explain how neural networks work.", "gradient"),
    ("What is machine learning?",         "learning"),
    ("Штучний інтелект — це що?",         "інтелект"),
])
def test_mock_response_routing(prompt, expected_word, monkeypatch):
    monkeypatch.setenv("BABYLOON_MODEL", "mistral-7b")
    result = _get("mistral-7b").generate(prompt)
    assert expected_word.lower() in result["text"].lower()


def test_gemma_same_routing_as_mistral(monkeypatch):
    """Both adapters route to same answer (thinking stripped in Gemma)."""
    prompt = "What is the capital of France?"
    monkeypatch.setenv("BABYLOON_MODEL", "mistral-7b")
    m_text = _get("mistral-7b").generate(prompt)["text"]
    monkeypatch.setenv("BABYLOON_MODEL", "gemma-4-12b")
    g_text = _get("gemma-4-12b").generate(prompt)["text"]
    assert "Paris" in m_text
    assert "Paris" in g_text


# ================================================================== #
# 10. _MODEL_REGISTRY completeness
# ================================================================== #

def test_registry_contains_all_keys():
    from models.manager import _MODEL_REGISTRY
    assert "mistral-7b"   in _MODEL_REGISTRY
    assert "gemma-4-12b"  in _MODEL_REGISTRY
    assert "gemma-4-e4b"  in _MODEL_REGISTRY


def test_registry_schema():
    from models.manager import _MODEL_REGISTRY
    required = {"hf_id", "max_context", "thinking", "family"}
    for key, cfg in _MODEL_REGISTRY.items():
        missing = required - set(cfg.keys())
        assert not missing, f"{key} missing fields: {missing}"


def test_registry_gemma4_thinking_flag():
    from models.manager import _MODEL_REGISTRY
    assert _MODEL_REGISTRY["gemma-4-12b"]["thinking"] is True
    assert _MODEL_REGISTRY["gemma-4-e4b"]["thinking"] is True
    assert _MODEL_REGISTRY["mistral-7b"]["thinking"]  is False


def test_registry_context_lengths():
    from models.manager import _MODEL_REGISTRY
    assert _MODEL_REGISTRY["mistral-7b"]["max_context"]  == 32_768
    assert _MODEL_REGISTRY["gemma-4-12b"]["max_context"] == 131_072
    assert _MODEL_REGISTRY["gemma-4-e4b"]["max_context"] == 131_072
