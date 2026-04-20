"""
ModelAdapter — unified multi-model interface for babyloon.ai.
Supports Mistral 7B Instruct v0.3 and Gemma 4 (12B / e4B).

Controlled by env variable BABYLOON_MODEL:
  mistral-7b   → mistralai/Mistral-7B-Instruct-v0.3  (32K ctx,  no thinking)
  gemma-4-12b  → google/gemma-4-12b-it               (128K ctx, thinking ✓)
  gemma-4-e4b  → google/gemma-4-e4b-it               (128K ctx, thinking ✓)

Stable public interface (never changes across model variants):
  generate(prompt, max_tokens, temperature, return_attention) → dict
  tokenize(text)      → list[int]
  detokenize(ids)     → str
  get_model_name()    → str
  get_max_context()   → int
  supports_thinking() → bool

generate() always returns:
  {
    "text":             str,        # visible output (thinking stripped for Gemma)
    "reasoning_trace":  str | None, # <|think|>…<|/think|> content (Gemma only)
    "prompt_token_ids": list[int],
    "output_token_ids": list[int],
    "model_name":       str,
  }

Patent: PCT/IB2026/053131
"""

import logging
import os
import re
import time
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)

# ── Model registry ─────────────────────────────────────────────────── #

_MODEL_REGISTRY: dict[str, dict] = {
    "mistral-7b": {
        "hf_id":       "mistralai/Mistral-7B-Instruct-v0.3",
        "max_context": 32_768,
        "thinking":    False,
        "family":      "mistral",
    },
    "gemma-4-12b": {
        "hf_id":       "google/gemma-4-12b-it",
        "max_context": 131_072,
        "thinking":    True,
        "family":      "gemma4",
    },
    "gemma-4-e4b": {
        "hf_id":       "google/gemma-4-e4b-it",
        "max_context": 131_072,
        "thinking":    True,
        "family":      "gemma4",
    },
}

_DEFAULT_MODEL_KEY = "mistral-7b"

# Regex for Gemma thinking block — escaped pipes required
_THINK_RE = re.compile(r"<\|think\|>(.*?)<\|/think\|>", re.DOTALL)


def _resolve_model_key() -> str:
    """Read BABYLOON_MODEL at runtime (allows tests to override after import)."""
    key = os.environ.get("BABYLOON_MODEL", _DEFAULT_MODEL_KEY).strip().lower()
    if key not in _MODEL_REGISTRY:
        logger.warning(
            f"Unknown BABYLOON_MODEL={key!r} — falling back to {_DEFAULT_MODEL_KEY!r}"
        )
        return _DEFAULT_MODEL_KEY
    return key


def _is_mock() -> bool:
    return os.environ.get("MOCK_GENERATE", "0") == "1"


def _extract_thinking(text: str) -> tuple[str, Optional[str]]:
    """
    Strip <|think|>…<|/think|> from Gemma output.
    Returns (visible_text, reasoning_trace).
    """
    m = _THINK_RE.search(text)
    if m:
        reasoning = m.group(1).strip()
        visible = (text[: m.start()] + text[m.end() :]).strip()
        return visible, reasoning
    return text.strip(), None


# ── Abstract base ──────────────────────────────────────────────────── #

class ModelAdapter(ABC):
    """
    Model-agnostic interface.  Concrete subclasses: MistralAdapter,
    Gemma4Adapter, _MockMistralAdapter, _MockGemma4Adapter.
    """

    @abstractmethod
    def generate(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        return_attention: bool = True,
    ) -> dict:
        """
        Generate a response.

        Returns a dict with keys:
          text              str          visible output
          reasoning_trace   str | None   thinking trace (Gemma 4 only)
          prompt_token_ids  list[int]
          output_token_ids  list[int]
          model_name        str
        """

    @abstractmethod
    def tokenize(self, text: str) -> list[int]:
        """Encode text → token IDs."""

    @abstractmethod
    def detokenize(self, token_ids: list[int]) -> str:
        """Decode token IDs → text."""

    @abstractmethod
    def get_model_name(self) -> str:
        """Human-readable model identifier (e.g. 'mistral-7b')."""

    @abstractmethod
    def get_max_context(self) -> int:
        """Maximum context window in tokens."""

    @abstractmethod
    def supports_thinking(self) -> bool:
        """True when model generates <|think|>…<|/think|> blocks."""

    # ── shared helpers ──────────────────────────────────────────────── #

    def _make_result(
        self,
        text: str,
        reasoning_trace: Optional[str],
        prompt_token_ids: list[int],
        output_token_ids: list[int],
    ) -> dict:
        return {
            "text":             text,
            "reasoning_trace":  reasoning_trace,
            "prompt_token_ids": prompt_token_ids,
            "output_token_ids": output_token_ids,
            "model_name":       self.get_model_name(),
        }


# ── Mistral 7B ─────────────────────────────────────────────────────── #

class MistralAdapter(ModelAdapter):
    """
    Mistral-7B-Instruct-v0.3.
    Chat format: [INST] … [/INST]
    Context: 32 768 tokens | Thinking: no
    Flash Attention 2 enabled when torch+GPU available.
    """

    _CFG = _MODEL_REGISTRY["mistral-7b"]

    def __init__(self) -> None:
        self._model = None
        self._tokenizer = None
        self._device = "cpu"
        self._load()

    def _load(self) -> None:
        hf_id = self._CFG["hf_id"]
        hf_token = os.environ.get("HF_TOKEN")
        logger.info(f"[MistralAdapter] Loading {hf_id}…")
        t0 = time.time()

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

            has_gpu = torch.cuda.is_available()
            self._device = "cuda" if has_gpu else "cpu"

            self._tokenizer = AutoTokenizer.from_pretrained(
                hf_id, use_fast=True, token=hf_token
            )
            if self._tokenizer.pad_token is None:
                self._tokenizer.pad_token = self._tokenizer.eos_token

            if has_gpu:
                quant = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                )
                self._model = AutoModelForCausalLM.from_pretrained(
                    hf_id,
                    quantization_config=quant,
                    device_map="auto",
                    torch_dtype=torch.float16,
                    attn_implementation="flash_attention_2",
                    token=hf_token,
                )
            else:
                self._model = AutoModelForCausalLM.from_pretrained(
                    hf_id,
                    device_map="cpu",
                    torch_dtype=torch.float32,
                    token=hf_token,
                )

            self._model.eval()
            logger.info(f"[MistralAdapter] Ready in {time.time() - t0:.1f}s on {self._device}")

        except Exception as e:
            raise RuntimeError(f"[MistralAdapter] Failed to load {hf_id}: {e}") from e

    def _format_prompt(self, prompt: str) -> str:
        return f"[INST] {prompt} [/INST]"

    def generate(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        return_attention: bool = True,
    ) -> dict:
        import torch

        formatted = self._format_prompt(prompt)
        inputs = self._tokenizer(formatted, return_tensors="pt")
        input_ids = inputs["input_ids"]
        if self._device == "cuda":
            input_ids = input_ids.cuda()

        with torch.no_grad():
            output_ids = self._model.generate(
                input_ids,
                max_new_tokens=max_tokens,
                temperature=temperature,
                do_sample=temperature > 0,
                pad_token_id=self._tokenizer.eos_token_id,
            )

        prompt_len = input_ids.shape[1]
        new_ids = output_ids[0][prompt_len:].tolist()
        text = self._tokenizer.decode(new_ids, skip_special_tokens=True).strip()

        return self._make_result(
            text=text,
            reasoning_trace=None,
            prompt_token_ids=input_ids[0].tolist(),
            output_token_ids=new_ids,
        )

    def tokenize(self, text: str) -> list[int]:
        return self._tokenizer(text, add_special_tokens=False)["input_ids"]

    def detokenize(self, token_ids: list[int]) -> str:
        return self._tokenizer.decode(token_ids, skip_special_tokens=True)

    def get_model_name(self) -> str:
        return "mistral-7b"

    def get_max_context(self) -> int:
        return self._CFG["max_context"]

    def supports_thinking(self) -> bool:
        return False


# ── Gemma 4 ────────────────────────────────────────────────────────── #

class Gemma4Adapter(ModelAdapter):
    """
    Gemma 4 (12B-IT or e4B-IT).
    Chat format: <start_of_turn>user\\n…<end_of_turn>\\n<start_of_turn>model\\n
    Mandatory BOS token prepended by tokenizer.
    Context: 131 072 tokens | Thinking: yes — strips <|think|>…<|/think|>
    Flash Attention 2 enabled.
    """

    def __init__(self, model_key: str) -> None:
        if model_key not in ("gemma-4-12b", "gemma-4-e4b"):
            raise ValueError(f"Unknown Gemma 4 key: {model_key!r}")
        self._key = model_key
        self._cfg = _MODEL_REGISTRY[model_key]
        self._model = None
        self._tokenizer = None
        self._device = "cpu"
        self._load()

    def _load(self) -> None:
        hf_id = self._cfg["hf_id"]
        hf_token = os.environ.get("HF_TOKEN")
        logger.info(f"[Gemma4Adapter] Loading {hf_id}…")
        t0 = time.time()

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

            has_gpu = torch.cuda.is_available()
            self._device = "cuda" if has_gpu else "cpu"

            # Gemma 4: GemmaTokenizer via AutoTokenizer
            self._tokenizer = AutoTokenizer.from_pretrained(
                hf_id,
                use_fast=True,
                token=hf_token,
                add_bos_token=True,   # mandatory BOS for Gemma
            )
            if self._tokenizer.pad_token is None:
                self._tokenizer.pad_token = self._tokenizer.eos_token

            if has_gpu:
                quant = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.bfloat16,
                    bnb_4bit_use_double_quant=True,
                )
                self._model = AutoModelForCausalLM.from_pretrained(
                    hf_id,
                    quantization_config=quant,
                    device_map="auto",
                    torch_dtype=torch.bfloat16,
                    attn_implementation="flash_attention_2",
                    token=hf_token,
                )
            else:
                self._model = AutoModelForCausalLM.from_pretrained(
                    hf_id,
                    device_map="cpu",
                    torch_dtype=torch.float32,
                    token=hf_token,
                )

            self._model.eval()
            logger.info(f"[Gemma4Adapter] Ready in {time.time() - t0:.1f}s on {self._device}")

        except Exception as e:
            raise RuntimeError(f"[Gemma4Adapter] Failed to load {hf_id}: {e}") from e

    def _format_prompt(self, prompt: str) -> str:
        """Gemma 4 instruct chat template."""
        return (
            f"<start_of_turn>user\n"
            f"{prompt}<end_of_turn>\n"
            f"<start_of_turn>model\n"
        )

    def generate(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        return_attention: bool = True,
    ) -> dict:
        import torch

        formatted = self._format_prompt(prompt)
        inputs = self._tokenizer(formatted, return_tensors="pt")
        input_ids = inputs["input_ids"]
        if self._device == "cuda":
            input_ids = input_ids.cuda()

        with torch.no_grad():
            output_ids = self._model.generate(
                input_ids,
                max_new_tokens=max_tokens,
                temperature=temperature,
                do_sample=temperature > 0,
                pad_token_id=self._tokenizer.eos_token_id,
            )

        prompt_len = input_ids.shape[1]
        new_ids = output_ids[0][prompt_len:].tolist()
        raw_text = self._tokenizer.decode(new_ids, skip_special_tokens=True)

        # E1: extract thinking block before returning
        visible_text, reasoning_trace = _extract_thinking(raw_text)

        return self._make_result(
            text=visible_text,
            reasoning_trace=reasoning_trace,
            prompt_token_ids=input_ids[0].tolist(),
            output_token_ids=new_ids,
        )

    def tokenize(self, text: str) -> list[int]:
        return self._tokenizer(text, add_special_tokens=False)["input_ids"]

    def detokenize(self, token_ids: list[int]) -> str:
        return self._tokenizer.decode(token_ids, skip_special_tokens=True)

    def get_model_name(self) -> str:
        return self._key

    def get_max_context(self) -> int:
        return self._cfg["max_context"]

    def supports_thinking(self) -> bool:
        return True


# ── Mock adapters (MOCK_GENERATE=1, no GPU required) ───────────────── #

_MOCK_VOCAB = {
    100: "The", 101: " capital", 102: " of", 103: " France",
    104: " is", 105: " Paris", 106: ".", 107: " Neural",
    108: " networks", 109: " learn", 110: " through",
    111: " gradient", 112: " descent", 113: " Machine",
    114: " learning", 115: " uses", 116: " data", 117: " to",
    118: " make", 119: " predictions", 120: " This", 121: " is",
    122: " a", 123: " demonstration", 124: " of", 125: " babyloon",
    126: ".", 127: " Artificial", 128: " intelligence",
    129: " Штучний", 130: " інтелект", 131: " це", 132: " галузь",
}

_MOCK_RESPONSES = {
    "france":  "The capital of France is Paris.",
    "neural":  "Neural networks learn through gradient descent.",
    "ml":      "Machine learning uses data to make predictions.",
    "ukraine": "Штучний інтелект — це галузь інформатики.",
    "default": "This is a demonstration of babyloon.ai provenance attribution.",
}

_GEMMA_THINKING = (
    "<|think|>Let me reason about this step by step. "
    "Based on my training data, I can identify the relevant sources.<|/think|>"
)


def _pick_mock_response(prompt: str) -> str:
    p = prompt.lower()
    if "france" in p or "capital" in p:
        return _MOCK_RESPONSES["france"]
    if "neural" in p or "network" in p:
        return _MOCK_RESPONSES["neural"]
    if "machine learning" in p or " ml " in p:
        return _MOCK_RESPONSES["ml"]
    if "штучний" in p or "ukraine" in p or "syaivo" in p or "pilot" in p:
        return _MOCK_RESPONSES["ukraine"]
    return _MOCK_RESPONSES["default"]


def _mock_token_ids(text: str) -> list[int]:
    return [(abs(hash(w)) % 900) + 100 for w in text.split()]


class _MockMistralAdapter(ModelAdapter):
    """Mock Mistral — no GPU, deterministic output."""

    def generate(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        return_attention: bool = True,
    ) -> dict:
        text = _pick_mock_response(prompt)
        return self._make_result(
            text=text,
            reasoning_trace=None,
            prompt_token_ids=_mock_token_ids(self._format_prompt(prompt)),
            output_token_ids=_mock_token_ids(text),
        )

    def _format_prompt(self, prompt: str) -> str:
        return f"[INST] {prompt} [/INST]"

    def tokenize(self, text: str) -> list[int]:
        return _mock_token_ids(text)

    def detokenize(self, token_ids: list[int]) -> str:
        return " ".join(_MOCK_VOCAB.get(i, f"[{i}]") for i in token_ids)

    def get_model_name(self) -> str:
        return "mistral-7b"

    def get_max_context(self) -> int:
        return _MODEL_REGISTRY["mistral-7b"]["max_context"]

    def supports_thinking(self) -> bool:
        return False


class _MockGemma4Adapter(ModelAdapter):
    """Mock Gemma 4 — generates a thinking block, then the answer."""

    def __init__(self, model_key: str) -> None:
        self._key = model_key

    def generate(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        return_attention: bool = True,
    ) -> dict:
        answer = _pick_mock_response(prompt)
        raw = _GEMMA_THINKING + answer
        visible, trace = _extract_thinking(raw)
        return self._make_result(
            text=visible,
            reasoning_trace=trace,
            prompt_token_ids=_mock_token_ids(self._format_prompt(prompt)),
            output_token_ids=_mock_token_ids(raw),
        )

    def _format_prompt(self, prompt: str) -> str:
        return (
            f"<start_of_turn>user\n"
            f"{prompt}<end_of_turn>\n"
            f"<start_of_turn>model\n"
        )

    def tokenize(self, text: str) -> list[int]:
        return _mock_token_ids(text)

    def detokenize(self, token_ids: list[int]) -> str:
        return " ".join(_MOCK_VOCAB.get(i, f"[{i}]") for i in token_ids)

    def get_model_name(self) -> str:
        return self._key

    def get_max_context(self) -> int:
        return _MODEL_REGISTRY[self._key]["max_context"]

    def supports_thinking(self) -> bool:
        return True


# ── Singleton ──────────────────────────────────────────────────────── #

_adapter: Optional[ModelAdapter] = None


def get_adapter() -> ModelAdapter:
    """
    Return the singleton ModelAdapter for the current BABYLOON_MODEL.
    In MOCK_GENERATE=1 mode never loads real weights.
    """
    global _adapter
    if _adapter is not None:
        return _adapter

    key = _resolve_model_key()
    cfg = _MODEL_REGISTRY[key]

    if _is_mock():
        logger.info(f"[manager] MOCK_GENERATE=1 — mock adapter for {key!r}")
        if cfg["family"] == "gemma4":
            _adapter = _MockGemma4Adapter(key)
        else:
            _adapter = _MockMistralAdapter()
        return _adapter

    # Real model — may take minutes and require GPU
    logger.info(f"[manager] Loading real model {key!r} ({cfg['hf_id']})…")
    if cfg["family"] == "gemma4":
        _adapter = Gemma4Adapter(key)
    else:
        _adapter = MistralAdapter()

    return _adapter


def reset_adapter() -> None:
    """Force recreation of the singleton. Required between tests."""
    global _adapter
    _adapter = None


def make_adapter(key: str) -> ModelAdapter:
    """
    Create a *fresh* (non-singleton) adapter for a given model key.
    Useful when a request needs a specific model independent of the
    global BABYLOON_MODEL env variable (e.g. model_override in /generate).

    Falls back to mistral-7b if key is unknown.
    Respects MOCK_GENERATE — never loads real weights in mock mode.
    """
    real_key = key if key in _MODEL_REGISTRY else _DEFAULT_MODEL_KEY
    cfg = _MODEL_REGISTRY[real_key]

    if _is_mock():
        if cfg["family"] == "gemma4":
            return _MockGemma4Adapter(real_key)
        return _MockMistralAdapter()

    # Real weights path
    if cfg["family"] == "gemma4":
        return Gemma4Adapter(real_key)
    return MistralAdapter()
