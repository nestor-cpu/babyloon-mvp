"""
E2: AgentVerifier — identity-conditioned routing via JWT/ECDSA
E6: Fallback authorization — unknown agents get L2 (minimum) access
Patent claims: agent identity verification, authorization levels, fallback
PCT/IB2026/053131
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
from jose import jwt, JWTError
from pydantic import BaseModel


# ------------------------------------------------------------------ #
# Constants
# ------------------------------------------------------------------ #

ALGORITHM = "ES256"  # ECDSA P-256

LEVEL_PERMISSIONS = {
    "L0": {
        "description": "Full access — entire corpus + all attention layers",
        "corpus_access": "full",
        "attention_layers": "all",
        "allowed_operations": ["generate", "manifest", "registry", "admin"],
    },
    "L1": {
        "description": "Verified subcorpus (CC0, CC BY, Apache 2.0) + upper half of layers",
        "corpus_access": "verified",
        "attention_layers": "upper_half",
        "allowed_operations": ["generate", "manifest", "registry"],
    },
    "L2": {
        "description": "Public subcorpus (CC0, Public Domain) + last attention layer only",
        "corpus_access": "public",
        "attention_layers": "last_only",
        "allowed_operations": ["generate", "manifest"],
    },
}

LICENSE_CLASSES_BY_LEVEL = {
    "L0": ["CC0", "CC-BY", "CC-BY-SA", "Apache-2.0", "MIT", "proprietary"],
    "L1": ["CC0", "CC-BY", "Apache-2.0", "MIT"],
    "L2": ["CC0", "public-domain"],
}


# ------------------------------------------------------------------ #
# Pydantic models
# ------------------------------------------------------------------ #

class AgentRecord(BaseModel):
    agent_id: str
    name: str
    authorization_level: str
    allowed_operations: list[str]
    created_at: str
    expires_at: str
    is_active: bool = True
    public_key_pem: str


class VerificationResult(BaseModel):
    agent_id: Optional[str]
    name: Optional[str]
    level: str
    is_valid: bool
    reason: str
    allowed_operations: list[str]
    corpus_access: str
    attention_layers: str


# ------------------------------------------------------------------ #
# AgentVerifier
# ------------------------------------------------------------------ #

class AgentVerifier:
    def __init__(self, registry_path: str = "data/agent_registry.json"):
        self.registry_path = Path(registry_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.registry_path.exists():
            self.registry_path.write_text(json.dumps({"agents": []}, indent=2))

    # ---- Registry helpers ----------------------------------------- #

    def _load_registry(self) -> dict:
        return json.loads(self.registry_path.read_text(encoding="utf-8"))

    def _save_registry(self, data: dict) -> None:
        self.registry_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ---- Key generation ------------------------------------------- #

    @staticmethod
    def _generate_keypair() -> tuple[str, str]:
        """Generate ECDSA P-256 keypair. Returns (private_pem, public_pem)."""
        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        return private_pem, public_pem

    # ---- Public API ----------------------------------------------- #

    def register_agent(
        self,
        name: str,
        level: str,
        ttl_days: int = 90,
    ) -> tuple[AgentRecord, str]:
        """
        Register a new agent. Returns (AgentRecord, jwt_token).
        Generates fresh ECDSA P-256 keypair per agent.
        """
        if level not in LEVEL_PERMISSIONS:
            raise ValueError(f"Invalid level: {level}. Must be L0, L1, or L2.")

        agent_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=ttl_days)

        private_pem, public_pem = self._generate_keypair()

        allowed_ops = LEVEL_PERMISSIONS[level]["allowed_operations"]

        record = AgentRecord(
            agent_id=agent_id,
            name=name,
            authorization_level=level,
            allowed_operations=allowed_ops,
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
            is_active=True,
            public_key_pem=public_pem,
        )

        # Persist to registry (without private key)
        data = self._load_registry()
        data["agents"].append(record.model_dump())
        self._save_registry(data)

        # Issue JWT signed with private key
        claims = {
            "sub": agent_id,
            "name": name,
            "authorization_level": level,
            "allowed_operations": allowed_ops,
            "iss": "babyloon.ai",
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = jwt.encode(claims, private_pem, algorithm=ALGORITHM)

        return record, token

    def verify_agent(self, token: str) -> VerificationResult:
        """
        Verify a JWT and return VerificationResult.
        Invalid/missing/expired token → fallback L2 (E6).
        """
        if not token:
            return self._fallback("no token provided")

        # Decode header to get agent_id (sub) without verification first
        try:
            unverified = jwt.get_unverified_claims(token)
            agent_id = unverified.get("sub")
        except JWTError:
            return self._fallback("malformed token")

        # Look up agent record to get public key
        record_data = self._get_agent_data(agent_id)
        if record_data is None:
            return self._fallback(f"agent {agent_id} not found in registry")

        if not record_data.get("is_active", False):
            return self._fallback(f"agent {agent_id} is deactivated")

        # Verify signature with agent's public key
        try:
            claims = jwt.decode(
                token,
                record_data["public_key_pem"],
                algorithms=[ALGORITHM],
                options={"verify_aud": False},
            )
        except JWTError as e:
            return self._fallback(f"token verification failed: {e}")

        # Check expiry (python-jose handles this but we double-check)
        exp = claims.get("exp", 0)
        if datetime.now(timezone.utc).timestamp() > exp:
            return self._fallback("token expired")

        level = claims.get("authorization_level", "L2")
        perms = LEVEL_PERMISSIONS.get(level, LEVEL_PERMISSIONS["L2"])

        return VerificationResult(
            agent_id=agent_id,
            name=claims.get("name"),
            level=level,
            is_valid=True,
            reason="ok",
            allowed_operations=claims.get("allowed_operations", []),
            corpus_access=perms["corpus_access"],
            attention_layers=perms["attention_layers"],
        )

    def get_agent(self, agent_id: str) -> Optional[AgentRecord]:
        data = self._get_agent_data(agent_id)
        if data is None:
            return None
        return AgentRecord(**data)

    def list_agents(self) -> list[AgentRecord]:
        data = self._load_registry()
        return [AgentRecord(**a) for a in data["agents"]]

    def deactivate_agent(self, agent_id: str) -> bool:
        data = self._load_registry()
        for agent in data["agents"]:
            if agent["agent_id"] == agent_id:
                agent["is_active"] = False
                self._save_registry(data)
                return True
        return False

    # ---- Internal helpers ----------------------------------------- #

    def _get_agent_data(self, agent_id: str) -> Optional[dict]:
        data = self._load_registry()
        for agent in data["agents"]:
            if agent["agent_id"] == agent_id:
                return agent
        return None

    @staticmethod
    def _fallback(reason: str) -> VerificationResult:
        """E6: unknown/invalid agent → minimum L2 access."""
        perms = LEVEL_PERMISSIONS["L2"]
        return VerificationResult(
            agent_id=None,
            name=None,
            level="L2",
            is_valid=False,
            reason=reason,
            allowed_operations=perms["allowed_operations"],
            corpus_access=perms["corpus_access"],
            attention_layers=perms["attention_layers"],
        )


# Module-level singleton
_verifier: Optional[AgentVerifier] = None


def get_verifier(path: str = "data/agent_registry.json") -> AgentVerifier:
    global _verifier
    if _verifier is None:
        _verifier = AgentVerifier(path)
    return _verifier


def get_allowed_license_classes(level: str) -> list[str]:
    return LICENSE_CLASSES_BY_LEVEL.get(level, LICENSE_CLASSES_BY_LEVEL["L2"])
