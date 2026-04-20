"""
Model loader — Mistral 7B Instruct v0.3 with 4-bit quantization.
Singleton pattern: load once, reuse forever.
CPU fallback + MOCK_GENERATE mode for testing without GPU.
Patent: PCT/IB2026/053131
"""

import logging
import os
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

MODEL_ID = os.environ.get("MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.3")


def _is_mock() -> bool:
    """Runtime check — allows tests to set MOCK_GENERATE=1 after import."""
    return os.environ.get("MOCK_GENERATE", "0") == "1"

_model = None
_tokenizer = None
_device: str = "cpu"


# ------------------------------------------------------------------ #
# GPU detection
# ------------------------------------------------------------------ #

def _has_gpu() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def _log_vram(prefix: str = "") -> None:
    try:
        import torch
        if torch.cuda.is_available():
            used = torch.cuda.memory_allocated(0) / 1024 ** 3
            total = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
            logger.info(f"{prefix}VRAM: {used:.2f} / {total:.1f} GB")
    except Exception:
        pass


# ------------------------------------------------------------------ #
# Load
# ------------------------------------------------------------------ #

def load_model(
    model_id: str = MODEL_ID,
    load_in_4bit: bool = True,
    force_cpu: bool = False,
) -> Tuple:
    """
    Load Mistral 7B with 4-bit quantization (NF4, float16).
    Falls back to CPU fp32 with a warning if no CUDA GPU is detected.
    Returns (model, tokenizer).
    """
    global _model, _tokenizer, _device

    if _model is not None and _tokenizer is not None:
        return _model, _tokenizer

    # ---- Mock mode (testing without GPU) -------------------------
    if _is_mock():
        logger.info("MOCK_GENERATE=1 — skipping real model load, using mock")
        _model = _MockModel()
        _tokenizer = _MockTokenizer()
        _device = "mock"
        return _model, _tokenizer

    # ---- Real model load -----------------------------------------
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    except ImportError as e:
        raise RuntimeError(
            f"Missing dependency: {e}. "
            "Run: pip install torch transformers accelerate bitsandbytes"
        )

    has_gpu = _has_gpu() and not force_cpu

    if has_gpu:
        gpu_name = torch.cuda.get_device_name(0)
        vram_total = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
        logger.info(f"GPU detected: {gpu_name} | Total VRAM: {vram_total:.1f} GB")
        _device = "cuda"
    else:
        logger.warning(
            "⚠️  No CUDA GPU detected — falling back to CPU. "
            "Inference will be very slow. Set MOCK_GENERATE=1 for testing."
        )
        _device = "cpu"

    hf_token = os.environ.get("HF_TOKEN")
    logger.info(
        f"Loading {model_id} "
        f"({'4-bit NF4 on GPU' if has_gpu and load_in_4bit else 'fp32 on CPU'})…"
    )
    t0 = time.time()

    _tokenizer = AutoTokenizer.from_pretrained(
        model_id,
        use_fast=True,
        token=hf_token,
    )
    if _tokenizer.pad_token is None:
        _tokenizer.pad_token = _tokenizer.eos_token

    if has_gpu and load_in_4bit:
        quant_cfg = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )
        _model = AutoModelForCausalLM.from_pretrained(
            model_id,
            quantization_config=quant_cfg,
            device_map="auto",
            torch_dtype=torch.float16,
            token=hf_token,
        )
    else:
        _model = AutoModelForCausalLM.from_pretrained(
            model_id,
            device_map="cpu",
            torch_dtype=torch.float32,
            token=hf_token,
        )

    _model.eval()
    elapsed = time.time() - t0
    logger.info(f"Model ready in {elapsed:.1f}s on {_device}")
    _log_vram("Post-load ")
    return _model, _tokenizer


# ------------------------------------------------------------------ #
# Accessors
# ------------------------------------------------------------------ #

def get_model():
    """Return loaded model (raises if not loaded)."""
    if _model is None:
        raise RuntimeError(
            "Model not loaded. Call load_model() first, or set MOCK_GENERATE=1."
        )
    return _model


def get_tokenizer():
    """Return loaded tokenizer (raises if not loaded)."""
    if _tokenizer is None:
        raise RuntimeError(
            "Tokenizer not loaded. Call load_model() first, or set MOCK_GENERATE=1."
        )
    return _tokenizer


def is_loaded() -> bool:
    return _model is not None and _tokenizer is not None


def get_device() -> str:
    return _device


# ------------------------------------------------------------------ #
# Generate
# ------------------------------------------------------------------ #

def generate(
    prompt: str,
    max_new_tokens: int = 256,
    temperature: float = 0.7,
    top_p: float = 0.9,
    do_sample: bool = True,
) -> Tuple[str, list, list]:
    """
    Generate text from prompt.
    Returns (generated_text, prompt_token_ids, output_token_ids).
    """
    if _is_mock() or isinstance(_model, _MockModel):
        return _mock_generate(prompt)

    import torch

    model = get_model()
    tokenizer = get_tokenizer()

    messages = [{"role": "user", "content": prompt}]
    formatted = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(formatted, return_tensors="pt")
    input_ids = inputs["input_ids"]

    if _device == "cuda":
        input_ids = input_ids.cuda()

    with torch.no_grad():
        output_ids = model.generate(
            input_ids,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            do_sample=do_sample,
            pad_token_id=tokenizer.eos_token_id,
        )

    prompt_len = input_ids.shape[1]
    new_ids = output_ids[0][prompt_len:].tolist()
    text = tokenizer.decode(new_ids, skip_special_tokens=True)
    _log_vram("Post-generate ")
    return text, input_ids[0].tolist(), new_ids


def unload_model() -> None:
    global _model, _tokenizer, _device
    import gc
    _model = None
    _tokenizer = None
    _device = "cpu"
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
    logger.info("Model unloaded and GPU memory freed.")


# ================================================================== #
# Mock implementations for MOCK_GENERATE=1 (no GPU testing)
# ================================================================== #

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


def _mock_generate(prompt: str) -> Tuple[str, list, list]:
    p = prompt.lower()
    if "france" in p or "capital" in p:
        text = _MOCK_RESPONSES["france"]
    elif "neural" in p or "network" in p:
        text = _MOCK_RESPONSES["neural"]
    elif "machine learning" in p or "ml" in p:
        text = _MOCK_RESPONSES["ml"]
    elif "штучний" in p or "ukraine" in p or "syaivo" in p:
        text = _MOCK_RESPONSES["ukraine"]
    else:
        text = _MOCK_RESPONSES["default"]

    words = text.split()
    # Fake but deterministic token IDs
    prompt_ids = [(abs(hash(w)) % 900) + 100 for w in prompt.split()]
    output_ids = [(abs(hash(w)) % 32) + 100 for w in words]
    return text, prompt_ids, output_ids


class _MockModel:
    """Minimal mock — satisfies isinstance checks and attribute access."""

    def eval(self):
        return self

    def parameters(self):
        class _FakeParam:
            device = "cpu"
            is_cuda = False
        yield _FakeParam()

    @property
    def hf_device_map(self):
        return {}

    # Mistral architecture stub for hook registration
    class _MockLayers:
        def __len__(self):
            return 32

        def __iter__(self):
            for _ in range(32):
                yield _MockAttentionLayer()

    class model:
        layers = None  # filled below

    def __init__(self):
        self.model = type("_M", (), {"layers": [_MockAttentionLayer() for _ in range(32)]})()


class _MockAttentionLayer:
    def __init__(self):
        self.self_attn = _MockSelfAttn()


class _MockSelfAttn:
    def register_forward_hook(self, fn):
        class _Handle:
            def remove(self):
                pass
        return _Handle()


class _MockTokenizer:
    eos_token_id = 2
    pad_token = "<pad>"
    pad_token_id = 0

    def __call__(self, text, return_tensors=None, **kwargs):
        words = text.split()
        ids = [(abs(hash(w)) % 900) + 100 for w in words]

        class _Enc:
            pass
        enc = _Enc()
        if return_tensors == "pt":
            try:
                import torch
                enc.input_ids = torch.tensor([ids])
                enc.attention_mask = torch.ones(1, len(ids), dtype=torch.long)
            except ImportError:
                enc.input_ids = [ids]
                enc.attention_mask = [[1] * len(ids)]
        else:
            enc.input_ids = [ids]
            enc.attention_mask = [[1] * len(ids)]
        return enc

    def decode(self, ids, skip_special_tokens=True):
        return " ".join(_MOCK_VOCAB.get(i, f"[{i}]") for i in ids)

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False):
        content = messages[0].get("content", "") if messages else ""
        return f"[INST] {content} [/INST]"
