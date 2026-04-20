"""
E6: FallbackAuthorization — default L2 access for unknown/invalid agents
This module provides FastAPI middleware and helper utilities for fallback logic.
The core fallback decision is made in identity.py (AgentVerifier._fallback).
PCT/IB2026/053131
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from modules.identity import get_verifier, VerificationResult, LEVEL_PERMISSIONS


FALLBACK_LEVEL = "L2"


class AgentAuthMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that:
    1. Extracts JWT from Authorization header (Bearer token)
    2. Verifies agent identity via AgentVerifier
    3. Injects VerificationResult into request.state
    4. Falls back to L2 for any missing/invalid token (E6)

    All downstream handlers read request.state.agent to know:
      - who is calling
      - what level of access they have
      - which corpus segments they may access
    """

    SKIP_PATHS = {"/", "/docs", "/openapi.json", "/redoc", "/health"}

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.SKIP_PATHS:
            # Public endpoints — inject anonymous L2 anyway
            request.state.agent = _anonymous_l2()
            return await call_next(request)

        token = _extract_token(request)
        verifier = get_verifier()
        result = verifier.verify_agent(token)

        # Always set state — handlers never need to handle missing agent
        request.state.agent = result

        response = await call_next(request)
        # Attach agent level to response header for transparency
        response.headers["X-Babyloon-Agent-Level"] = result.level
        response.headers["X-Babyloon-Agent-Valid"] = str(result.is_valid).lower()
        return response


def _extract_token(request: Request) -> str:
    """Extract Bearer token from Authorization header. Returns empty string if absent."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return ""


def _anonymous_l2() -> VerificationResult:
    perms = LEVEL_PERMISSIONS[FALLBACK_LEVEL]
    return VerificationResult(
        agent_id=None,
        name="anonymous",
        level=FALLBACK_LEVEL,
        is_valid=False,
        reason="no authentication (public endpoint)",
        allowed_operations=perms["allowed_operations"],
        corpus_access=perms["corpus_access"],
        attention_layers=perms["attention_layers"],
    )


def require_level(required_level: str):
    """
    Dependency factory for FastAPI routes.
    Usage:
        @router.get("/admin")
        def admin(agent=Depends(require_level("L0"))):
            ...
    """
    level_rank = {"L0": 0, "L1": 1, "L2": 2}

    def _check(request: Request) -> VerificationResult:
        agent: VerificationResult = request.state.agent
        if level_rank.get(agent.level, 99) > level_rank.get(required_level, 99):
            # Return 403 via exception — caller must handle
            from fastapi import HTTPException
            raise HTTPException(
                status_code=403,
                detail=f"Requires {required_level}, agent has {agent.level}",
            )
        return agent

    return _check


def get_current_agent(request: Request) -> VerificationResult:
    """FastAPI dependency: get current agent from request state."""
    return request.state.agent
