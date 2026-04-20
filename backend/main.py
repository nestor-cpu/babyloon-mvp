"""
babyloon.ai — FastAPI application
All six patent mechanisms: E1–E6
MOCK_GENERATE=1 enables testing without GPU.
PCT/IB2026/053131
"""

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from modules.fallback import AgentAuthMiddleware, get_current_agent
from modules.identity import VerificationResult, get_verifier
from modules.manifest import ManifestGenerator
from modules.registry import ProvenanceRegistry, get_registry
from modules.trust import TrustScoreStore, get_trust_store, reset_trust_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("DATA_DIR", "data")
MANIFESTS_DIR = os.path.join(DATA_DIR, "manifests")
REGISTRY_PATH = os.path.join(DATA_DIR, "corpus_registry.jsonl")
AGENT_REGISTRY_PATH = os.path.join(DATA_DIR, "agent_registry.json")
TRUST_SCORES_PATH = os.path.join(DATA_DIR, "trust_scores.json")


# ------------------------------------------------------------------ #
# Trust color helper
# ------------------------------------------------------------------ #

def _trust_color(trust: float) -> str:
    if trust >= 0.8:
        return "green"
    if trust >= 0.5:
        return "yellow"
    return "red"


# ------------------------------------------------------------------ #
# Lifespan
# ------------------------------------------------------------------ #

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("babyloon.ai starting…")

    get_registry(REGISTRY_PATH)
    get_verifier(AGENT_REGISTRY_PATH)
    reset_trust_store()
    get_trust_store(TRUST_SCORES_PATH, use_corpus=True)

    # Register demo corpus in E5 on startup
    try:
        from modules.corpus_loader import register_corpus_in_registry
        registry = get_registry(REGISTRY_PATH)
        n = register_corpus_in_registry(registry)
        if n:
            logger.info(f"Registered {n} new corpus segments in E5 registry")
    except Exception as e:
        logger.warning(f"Corpus registration skipped: {e}")

    if os.environ.get("LOAD_MODEL", "0") == "1":
        logger.info("LOAD_MODEL=1 — loading Mistral 7B…")
        from models.loader import load_model
        load_model()

    yield
    logger.info("babyloon.ai shutting down.")


# ------------------------------------------------------------------ #
# App
# ------------------------------------------------------------------ #

app = FastAPI(
    title="babyloon.ai",
    description="LLM Provenance Attribution System — PCT/IB2026/053131",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AgentAuthMiddleware)


# ================================================================== #
# Health
# ================================================================== #

@app.get("/health", tags=["system"])
def health():
    from models.loader import is_loaded
    return {
        "status": "ok",
        "model_loaded": is_loaded(),
        "mock_mode": os.environ.get("MOCK_GENERATE", "0") == "1",
        "patent": "PCT/IB2026/053131",
    }


# ================================================================== #
# E5 — Registry
# ================================================================== #

class RegistryAppendRequest(BaseModel):
    record_type: str
    payload: dict


@app.post("/registry/append", tags=["E5-registry"])
def registry_append(
    body: RegistryAppendRequest,
    agent: VerificationResult = Depends(get_current_agent),
):
    if "admin" not in agent.allowed_operations:
        raise HTTPException(403, "Registry write requires L0 access")
    registry = get_registry(REGISTRY_PATH)
    return registry.append(body.record_type, body.payload)


@app.get("/registry/verify", tags=["E5-registry"])
def registry_verify():
    registry = get_registry(REGISTRY_PATH)
    ok = registry.verify_chain()
    return {"valid": ok, "message": "chain intact" if ok else "TAMPER DETECTED"}


@app.get("/registry/{record_id}", tags=["E5-registry"])
def registry_get(record_id: str):
    registry = get_registry(REGISTRY_PATH)
    record = registry.get(record_id)
    if record is None:
        raise HTTPException(404, f"Record {record_id} not found")
    return record


@app.get("/registry/session/{session_id}", tags=["E5-registry"])
def registry_session(session_id: str):
    return get_registry(REGISTRY_PATH).get_by_session(session_id)


@app.get("/registry", tags=["E5-registry"])
def registry_list(agent: VerificationResult = Depends(get_current_agent)):
    if agent.level not in ("L0", "L1"):
        raise HTTPException(403, "Registry listing requires L1+ access")
    return get_registry(REGISTRY_PATH).get_all()


# ================================================================== #
# E2 + E6 — Agent Identity
# ================================================================== #

class RegisterAgentRequest(BaseModel):
    name: str
    level: str
    ttl_days: int = 90


@app.post("/agent/register", tags=["E2-identity"])
def agent_register(body: RegisterAgentRequest):
    verifier = get_verifier(AGENT_REGISTRY_PATH)
    try:
        record, token = verifier.register_agent(body.name, body.level, body.ttl_days)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"agent": record.model_dump(), "token": token}


@app.post("/agent/verify", tags=["E2-identity"])
def agent_verify(request: Request):
    return request.state.agent.model_dump()


@app.get("/agent/{agent_id}", tags=["E2-identity"])
def agent_get(agent_id: str):
    verifier = get_verifier(AGENT_REGISTRY_PATH)
    record = verifier.get_agent(agent_id)
    if record is None:
        raise HTTPException(404, f"Agent {agent_id} not found")
    return record.model_dump()


@app.get("/agents", tags=["E2-identity"])
def agents_list(agent: VerificationResult = Depends(get_current_agent)):
    if agent.level != "L0":
        raise HTTPException(403, "Agent listing requires L0 access")
    return [a.model_dump() for a in get_verifier(AGENT_REGISTRY_PATH).list_agents()]


# ================================================================== #
# E3 — Trust
# ================================================================== #

@app.get("/trust/scores", tags=["E3-trust"])
def trust_scores(agent: VerificationResult = Depends(get_current_agent)):
    store = get_trust_store(TRUST_SCORES_PATH)
    if agent.level == "L0":
        return store.get_all()
    return store.get_active_segments(agent.level)


@app.get("/trust/top", tags=["E3-trust"])
def trust_top(k: int = 5, agent: VerificationResult = Depends(get_current_agent)):
    store = get_trust_store(TRUST_SCORES_PATH)
    return [
        {"segment_id": sid, "trust_score": score}
        for sid, score in store.top_k(k, agent.level)
    ]


class TrustUpdateRequest(BaseModel):
    segment_id: str
    trust_score: float


@app.post("/trust/update", tags=["E3-trust"])
def trust_update(
    body: TrustUpdateRequest,
    agent: VerificationResult = Depends(get_current_agent),
):
    if agent.level != "L0":
        raise HTTPException(403, "Trust update requires L0 access")
    store = get_trust_store(TRUST_SCORES_PATH)
    try:
        store.set(body.segment_id, body.trust_score)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"segment_id": body.segment_id, "trust_score": body.trust_score}


@app.post("/trust/reload", tags=["E3-trust"])
def trust_reload(agent: VerificationResult = Depends(get_current_agent)):
    if agent.level != "L0":
        raise HTTPException(403, "Trust reload requires L0 access")
    get_trust_store(TRUST_SCORES_PATH).reload()
    return {"status": "reloaded"}


# ================================================================== #
# E4 — Manifest
# ================================================================== #

@app.get("/manifest/{session_id}/summary", tags=["E4-manifest"])
def manifest_summary(session_id: str):
    mgen = ManifestGenerator.load(session_id, MANIFESTS_DIR)
    if mgen is None:
        raise HTTPException(404, f"Manifest for session {session_id} not found")
    return mgen.get_summary()


@app.get("/manifest/{session_id}", tags=["E4-manifest"])
def manifest_get(session_id: str):
    mgen = ManifestGenerator.load(session_id, MANIFESTS_DIR)
    if mgen is None:
        raise HTTPException(404, f"Manifest for session {session_id} not found")
    return mgen._token_records


@app.get("/manifest", tags=["E4-manifest"])
def manifest_list():
    return ManifestGenerator.list_sessions(MANIFESTS_DIR)


# ================================================================== #
# E1+E2+E3+E4+E5+E6 — /generate (full pipeline)
# ================================================================== #

_VALID_MODELS = {"mistral-7b", "gemma-4-12b", "gemma-4-e4b"}
_VALID_MODES  = {"dev", "enterprise", "sovereign"}


class GenerateRequest(BaseModel):
    prompt: str
    agent_token: Optional[str] = None   # alternative to Authorization header
    max_new_tokens: int = 256
    temperature: float = 0.7
    stream: bool = False
    session_id: Optional[str] = None
    mode_override: Optional[str] = None   # "dev" | "enterprise" | "sovereign"
    model_override: Optional[str] = None  # "mistral-7b" | "gemma-4-12b" | "gemma-4-e4b"


@app.post("/generate", tags=["pipeline"])
async def generate(
    body: GenerateRequest,
    request: Request,
    agent: VerificationResult = Depends(get_current_agent),
):
    """
    Full babyloon.ai pipeline — all 6 mechanisms:
    E2+E6 → agent verified (middleware)
    E3    → trust-weighted attention during generation
    E1    → per-token attribution vector
    E4    → JSONL manifest built token by token (includes thinking mode fields)
    E5    → inference record written to registry
    """
    from modules.attribution import ProvenanceAttribution, SegmentMetaStore
    from modules.corpus_loader import (
        load_corpus,
        build_token_segment_map,
        filter_by_level,
    )
    from modules.trust import TrustSession, get_trust_store, reset_trust_store

    # ---- Validate optional overrides --------------------------------
    if body.model_override and body.model_override not in _VALID_MODELS:
        raise HTTPException(400, f"model_override must be one of {sorted(_VALID_MODELS)}")
    if body.mode_override and body.mode_override not in _VALID_MODES:
        raise HTTPException(400, f"mode_override must be one of {sorted(_VALID_MODES)}")

    # ---- Setup -------------------------------------------------------
    session_id = body.session_id or str(uuid.uuid4())
    registry = get_registry(REGISTRY_PATH)

    # ---- E3: prepare trust store ------------------------------------
    reset_trust_store()
    trust_store = get_trust_store(TRUST_SCORES_PATH, use_corpus=True)

    # ---- Determine model key ----------------------------------------
    from models.manager import make_adapter, _MODEL_REGISTRY  # type: ignore

    model_key = body.model_override or os.environ.get("BABYLOON_MODEL", "mistral-7b")
    _real_key = model_key if model_key in _MODEL_REGISTRY else "mistral-7b"

    # ---- E3+E1: generate --------------------------------------------
    #
    # TWO explicit paths to avoid double-loading on GPU:
    #
    #   mistral-7b  → models.loader singleton (already loaded at startup,
    #                  or mock-generates without loading). Never calls
    #                  make_adapter() which would instantiate a second copy.
    #
    #   gemma-4-*   → make_adapter() fresh instance (Gemma is never in the
    #                  loader singleton; safe to create on demand).

    if _real_key == "mistral-7b":
        # ── Mistral path: use the pre-loaded loader singleton ──────
        from models.loader import (
            is_loaded, load_model, get_model, get_tokenizer,
            generate as _loader_generate,
        )
        # In real mode, load if not yet loaded (idempotent).
        # In mock mode, loader.generate() handles it internally via _is_mock().
        if not is_loaded() and os.environ.get("MOCK_GENERATE", "0") != "1":
            try:
                load_model()
            except Exception as e:
                raise HTTPException(503, f"Model not available: {e}")

        _raw = _loader_generate(
            prompt=body.prompt,
            max_new_tokens=body.max_new_tokens,
            temperature=body.temperature,
        )
        generated_text, prompt_token_ids, output_token_ids = _raw
        reasoning_trace      = None   # Mistral has no thinking mode
        thinking_mode        = False
        thinking_token_count = 0

        model     = get_model() if is_loaded() else None
        tokenizer = get_tokenizer() if is_loaded() else None

    else:
        # ── Gemma path: fresh adapter loaded on demand ─────────────
        adapter = make_adapter(_real_key)

        gen_result = adapter.generate(body.prompt, max_tokens=body.max_new_tokens)
        generated_text       = gen_result["text"]
        reasoning_trace      = gen_result["reasoning_trace"]
        prompt_token_ids     = gen_result["prompt_token_ids"]
        output_token_ids     = gen_result["output_token_ids"]
        thinking_mode        = adapter.supports_thinking()

        thinking_token_count = 0
        if reasoning_trace and thinking_mode:
            thinking_token_count = max(
                0,
                len(output_token_ids) - len(adapter.tokenize(generated_text)),
            )

        # Expose adapter's real model/tokenizer for E1 attention hooks
        model     = getattr(adapter, "_model",     None)
        tokenizer = getattr(adapter, "_tokenizer", None)

    # Mock trust session (real GPU: register hooks on model)
    with TrustSession(
        model=model,
        trust_store=trust_store,
        segment_mapping={},
        layer_filter=agent.attention_layers,
        level=agent.level,
        model_name=_real_key,
    ) as ts:
        trust_distribution = ts.get_distribution(top_k=5)
        avg_trust          = ts.get_average_trust()

    # ---- Build corpus segment mapping per agent level ---------------
    corpus = load_corpus()
    accessible_corpus = filter_by_level(corpus, agent.level)

    # ---- E1: build token-level attribution --------------------------
    meta_store = SegmentMetaStore.from_corpus()
    attributor = ProvenanceAttribution(
        model=model,
        tokenizer=tokenizer,
        segment_meta_store=meta_store,
        top_k=5,
        level=agent.level,
        model_name=_real_key,
    )

    segment_token_map = build_token_segment_map(
        prompt_token_ids, accessible_corpus, level=agent.level
    )
    provenances = attributor.attribute(
        prompt_tokens=prompt_token_ids,
        output_tokens=output_token_ids,
        segment_token_map=segment_token_map,
        layer_filter=agent.attention_layers,
        thinking_token_count=thinking_token_count,
        reasoning_trace=reasoning_trace,
    )

    # ---- E4: build manifest ----------------------------------------
    mgen = ManifestGenerator(
        session_id=session_id,
        agent_id=agent.agent_id or "anonymous",
        agent_level=agent.level,
        manifests_dir=MANIFESTS_DIR,
        registry=registry,
        model_backend=_real_key,
        thinking_mode=thinking_mode,
    )
    mgen.set_reasoning_trace(reasoning_trace)

    tokens_out = []
    for prov in provenances:
        mgen.append_token(prov, trust_distribution)
        d = prov.to_dict()
        t_avg = d.get("trust_avg", avg_trust if avg_trust else 0.0)
        tokens_out.append({
            "position":    prov.position,
            "text":        prov.token_text,
            "attribution": d.get("attribution", []),
            "trust_avg":   t_avg,
            "trust_color": _trust_color(t_avg),
        })

    # ---- E5: finalize → registry record ----------------------------
    summary = mgen.finalize()

    # ---- Streaming mode --------------------------------------------
    if body.stream:
        import json as _json

        async def _event_stream():
            for tok in tokens_out:
                yield _json.dumps(tok, ensure_ascii=False) + "\n"
            yield _json.dumps({"__summary__": summary}, ensure_ascii=False) + "\n"

        return StreamingResponse(_event_stream(), media_type="application/x-ndjson")

    # ---- Normal response -------------------------------------------
    return {
        "session_id":   session_id,
        "agent_id":     agent.agent_id or "anonymous",
        "agent_level":  agent.level,
        "model_backend": _real_key,
        "thinking_mode": thinking_mode,
        "reasoning_trace": reasoning_trace,
        "output_text":  generated_text,
        "tokens":       tokens_out,
        "summary": {
            "license_purity":      summary["license_purity"],
            "high_trust_ratio":    summary["high_trust_ratio"],
            "dominant_sources":    summary["dominant_sources"],
            "total_tokens":        summary["total_tokens"],
            "model_backend":       summary["model_backend"],
            "thinking_mode":       summary["thinking_mode"],
            "reasoning_hash":      summary["reasoning_hash"],
            "registry_record_id":  summary.get("registry_record_id"),
        },
    }


# ================================================================== #
# /compare — side-by-side model or quantization comparison
# ================================================================== #

class CompareRequest(BaseModel):
    prompt: str
    agent_token: Optional[str] = None
    compare_type: str = "quantization"  # "quantization" | "models"


def _text_similarity(a: str, b: str) -> float:
    """Jaccard similarity of word sets (case-insensitive)."""
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return round(len(wa & wb) / len(wa | wb), 4)


def _attribution_overlap(tokens_a: list[dict], tokens_b: list[dict]) -> float:
    """
    Overlap of dominant source segment_ids across two token lists.
    Jaccard over sets of segment_ids that appear in at least one attribution.
    """
    def _seg_ids(tokens: list[dict]) -> set:
        ids: set[str] = set()
        for tok in tokens:
            for attr in tok.get("attribution", []):
                sid = attr.get("segment_id")
                if sid:
                    ids.add(sid)
        return ids

    sa = _seg_ids(tokens_a)
    sb = _seg_ids(tokens_b)
    if not sa or not sb:
        return 0.0
    return round(len(sa & sb) / len(sa | sb), 4)


def _run_model(
    prompt: str,
    model_key: str,
    agent,
    max_new_tokens: int = 200,
) -> tuple[dict, float]:
    """
    Run a single model adapter and return (response_dict, elapsed_ms).
    response_dict contains text, reasoning_trace, tokens.
    """
    from models.manager import make_adapter, _MODEL_REGISTRY  # type: ignore
    from modules.attribution import ProvenanceAttribution, SegmentMetaStore
    from modules.corpus_loader import load_corpus, build_token_segment_map, filter_by_level

    real_key = model_key if model_key in _MODEL_REGISTRY else "mistral-7b"

    # Same two-path logic as /generate: loader singleton for mistral, fresh
    # make_adapter() for Gemma. Avoids double-loading on GPU servers.
    t0 = time.perf_counter()

    if real_key == "mistral-7b":
        from models.loader import (
            is_loaded, load_model, get_model, get_tokenizer,
            generate as _loader_generate,
        )
        if not is_loaded() and os.environ.get("MOCK_GENERATE", "0") != "1":
            load_model()

        _raw = _loader_generate(prompt=prompt, max_new_tokens=max_new_tokens)
        gen = {
            "text":             _raw[0],
            "reasoning_trace":  None,
            "prompt_token_ids": _raw[1],
            "output_token_ids": _raw[2],
        }
        thinking_token_count = 0
        _thinking_mode  = False
        _attn_model     = get_model() if is_loaded() else None
        _attn_tokenizer = get_tokenizer() if is_loaded() else None

    else:
        adapter = make_adapter(real_key)
        gen = adapter.generate(prompt, max_tokens=max_new_tokens)
        _thinking_mode  = adapter.supports_thinking()
        _attn_model     = getattr(adapter, "_model",     None)
        _attn_tokenizer = getattr(adapter, "_tokenizer", None)
        thinking_token_count = 0
        if gen["reasoning_trace"] and _thinking_mode:
            thinking_token_count = max(
                0,
                len(gen["output_token_ids"]) - len(adapter.tokenize(gen["text"])),
            )

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    # Attribution
    corpus = load_corpus()
    accessible = filter_by_level(corpus, agent.level)
    meta_store = SegmentMetaStore.from_corpus()
    attributor = ProvenanceAttribution(
        model=_attn_model, tokenizer=_attn_tokenizer,
        segment_meta_store=meta_store,
        top_k=5, level=agent.level, model_name=real_key,
    )
    seg_map = build_token_segment_map(
        gen["prompt_token_ids"], accessible, level=agent.level
    )
    provenances = attributor.attribute(
        prompt_tokens=gen["prompt_token_ids"],
        output_tokens=gen["output_token_ids"],
        segment_token_map=seg_map,
        thinking_token_count=thinking_token_count,
        reasoning_trace=gen["reasoning_trace"],
    )

    tokens_out = [
        {
            "position":    p.position,
            "text":        p.token_text,
            "attribution": p.to_dict().get("attribution", []),
            "trust_avg":   p.to_dict().get("trust_avg", 0.5),
            "trust_color": _trust_color(p.to_dict().get("trust_avg", 0.5)),
        }
        for p in provenances
    ]

    return {
        "model":           real_key,
        "thinking_mode":   _thinking_mode,
        "output_text":     gen["text"],
        "reasoning_trace": gen["reasoning_trace"],
        "tokens":          tokens_out,
        "token_count":     len(tokens_out),
    }, elapsed_ms


@app.post("/compare", tags=["pipeline"])
async def compare(
    body: CompareRequest,
    request: Request,
    agent: VerificationResult = Depends(get_current_agent),
):
    """
    Compare two inference runs side by side.

    compare_type="quantization":
        Same model (env default) run twice — demonstrates determinism / variance.

    compare_type="models":
        Mistral 7B vs Gemma 4 12B on the same prompt.
        Returns per-model results plus similarity / overlap metrics.
    """
    if body.compare_type not in ("quantization", "models"):
        raise HTTPException(
            400, "compare_type must be 'quantization' or 'models'"
        )

    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(400, "prompt must not be empty")

    if body.compare_type == "models":
        # ── Mistral 7B vs Gemma 4 12B ──────────────────────────────
        result_m, ms_m = _run_model(prompt, "mistral-7b",    agent)
        result_g, ms_g = _run_model(prompt, "gemma-4-12b",   agent)

        similarity    = _text_similarity(result_m["output_text"], result_g["output_text"])
        attr_overlap  = _attribution_overlap(result_m["tokens"],  result_g["tokens"])
        latency_diff  = round(abs(ms_m - ms_g), 1)

        return {
            "compare_type": "models",
            "prompt":        prompt,
            "mistral-7b":    result_m,
            "gemma-4-12b":   result_g,
            "comparison": {
                "output_similarity":   similarity,
                "attribution_overlap": attr_overlap,
                "latency_mistral_ms":  ms_m,
                "latency_gemma_ms":    ms_g,
                "latency_diff_ms":     latency_diff,
                "thinking_advantage":  result_g["reasoning_trace"] is not None,
            },
        }

    # ── Quantization: same model, two runs ─────────────────────────
    default_key = os.environ.get("BABYLOON_MODEL", "mistral-7b")
    result_1, ms_1 = _run_model(prompt, default_key, agent)
    result_2, ms_2 = _run_model(prompt, default_key, agent)

    return {
        "compare_type": "quantization",
        "prompt":  prompt,
        "run_1":   result_1,
        "run_2":   result_2,
        "comparison": {
            "output_similarity":   _text_similarity(result_1["output_text"], result_2["output_text"]),
            "attribution_overlap": _attribution_overlap(result_1["tokens"],  result_2["tokens"]),
            "latency_run1_ms":     ms_1,
            "latency_run2_ms":     ms_2,
            "latency_diff_ms":     round(abs(ms_1 - ms_2), 1),
        },
    }
