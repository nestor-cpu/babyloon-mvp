"""
Tests for E2: AgentVerifier + E6: Fallback Authorization
Run: pytest backend/tests/test_identity.py -v
"""

import pytest

from modules.identity import AgentVerifier, LEVEL_PERMISSIONS


@pytest.fixture
def verifier(tmp_path):
    path = str(tmp_path / "agents.json")
    return AgentVerifier(registry_path=path)


# ------------------------------------------------------------------ #
# Agent registration
# ------------------------------------------------------------------ #

def test_register_l0_agent(verifier):
    record, token = verifier.register_agent("TestAgentL0", "L0", ttl_days=30)
    assert record.authorization_level == "L0"
    assert record.is_active is True
    assert len(record.agent_id) == 36
    assert token  # non-empty JWT


def test_register_l1_agent(verifier):
    record, token = verifier.register_agent("TestAgentL1", "L1", ttl_days=90)
    assert record.authorization_level == "L1"
    assert "generate" in record.allowed_operations
    assert "admin" not in record.allowed_operations


def test_register_l2_agent(verifier):
    record, token = verifier.register_agent("TestAgentL2", "L2")
    assert record.authorization_level == "L2"
    assert record.allowed_operations == ["generate", "manifest"]


def test_register_invalid_level(verifier):
    with pytest.raises(ValueError, match="Invalid level"):
        verifier.register_agent("Bad", "L99")


# ------------------------------------------------------------------ #
# Verification — valid tokens
# ------------------------------------------------------------------ #

def test_verify_l0_token(verifier):
    record, token = verifier.register_agent("L0Agent", "L0")
    result = verifier.verify_agent(token)
    assert result.is_valid is True
    assert result.level == "L0"
    assert result.agent_id == record.agent_id
    assert result.corpus_access == "full"
    assert result.attention_layers == "all"


def test_verify_l1_token(verifier):
    record, token = verifier.register_agent("L1Agent", "L1")
    result = verifier.verify_agent(token)
    assert result.is_valid is True
    assert result.level == "L1"
    assert result.corpus_access == "verified"
    assert result.attention_layers == "upper_half"


def test_verify_l2_token(verifier):
    record, token = verifier.register_agent("L2Agent", "L2")
    result = verifier.verify_agent(token)
    assert result.is_valid is True
    assert result.level == "L2"
    assert result.corpus_access == "public"
    assert result.attention_layers == "last_only"


# ------------------------------------------------------------------ #
# E6: Fallback — invalid/missing tokens
# ------------------------------------------------------------------ #

def test_fallback_empty_token(verifier):
    result = verifier.verify_agent("")
    assert result.is_valid is False
    assert result.level == "L2"
    assert result.agent_id is None
    assert "no token" in result.reason


def test_fallback_malformed_token(verifier):
    result = verifier.verify_agent("not.a.jwt")
    assert result.is_valid is False
    assert result.level == "L2"


def test_fallback_random_string(verifier):
    result = verifier.verify_agent("eyJhbGciOiJFUzI1NiJ9.garbage.signature")
    assert result.is_valid is False
    assert result.level == "L2"


def test_fallback_unknown_agent_id(verifier):
    # Valid JWT structure but agent not in registry
    import uuid
    from datetime import datetime, timedelta, timezone
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from jose import jwt as jose_jwt

    # Generate a fresh key not registered anywhere
    key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()

    claims = {
        "sub": str(uuid.uuid4()),
        "name": "ghost",
        "authorization_level": "L0",
        "allowed_operations": ["generate", "admin"],
        "iss": "attacker.com",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(days=1)).timestamp()),
    }
    forged_token = jose_jwt.encode(claims, pem, algorithm="ES256")

    result = verifier.verify_agent(forged_token)
    assert result.is_valid is False
    assert result.level == "L2"  # fallback, not L0 escalation


def test_fallback_level_permissions():
    """E6: L2 fallback always has minimum permissions."""
    perms = LEVEL_PERMISSIONS["L2"]
    assert perms["corpus_access"] == "public"
    assert perms["attention_layers"] == "last_only"
    assert "admin" not in perms["allowed_operations"]
    assert "registry" not in perms["allowed_operations"]


# ------------------------------------------------------------------ #
# Agent registry persistence
# ------------------------------------------------------------------ #

def test_get_agent(verifier):
    record, _ = verifier.register_agent("MyAgent", "L1")
    fetched = verifier.get_agent(record.agent_id)
    assert fetched is not None
    assert fetched.name == "MyAgent"
    assert fetched.authorization_level == "L1"


def test_get_nonexistent_agent(verifier):
    result = verifier.get_agent("00000000-0000-0000-0000-000000000000")
    assert result is None


def test_list_agents(verifier):
    verifier.register_agent("A1", "L0")
    verifier.register_agent("A2", "L1")
    verifier.register_agent("A3", "L2")
    agents = verifier.list_agents()
    assert len(agents) == 3
    names = {a.name for a in agents}
    assert names == {"A1", "A2", "A3"}


def test_deactivate_agent(verifier):
    record, token = verifier.register_agent("ToDeactivate", "L1")
    ok = verifier.deactivate_agent(record.agent_id)
    assert ok is True
    # Token should now fail verification
    result = verifier.verify_agent(token)
    assert result.is_valid is False
    assert result.level == "L2"


def test_persistence_across_instances(tmp_path):
    path = str(tmp_path / "agents.json")
    v1 = AgentVerifier(registry_path=path)
    record, token = v1.register_agent("PersistAgent", "L1")

    v2 = AgentVerifier(registry_path=path)
    result = v2.verify_agent(token)
    assert result.is_valid is True
    assert result.level == "L1"


# ------------------------------------------------------------------ #
# Three canonical test agents (as per TZ milestone week 4)
# ------------------------------------------------------------------ #

def test_three_canonical_agents(tmp_path):
    path = str(tmp_path / "canonical.json")
    v = AgentVerifier(registry_path=path)

    l0_rec, l0_tok = v.register_agent("BabyloonAdmin", "L0", ttl_days=365)
    l1_rec, l1_tok = v.register_agent("BabyloonPartner", "L1", ttl_days=90)
    l2_rec, l2_tok = v.register_agent("BabyloonPublic", "L2", ttl_days=30)

    # L0 — full access
    r0 = v.verify_agent(l0_tok)
    assert r0.is_valid and r0.level == "L0" and r0.corpus_access == "full"

    # L1 — verified access
    r1 = v.verify_agent(l1_tok)
    assert r1.is_valid and r1.level == "L1" and r1.corpus_access == "verified"

    # L2 — public access
    r2 = v.verify_agent(l2_tok)
    assert r2.is_valid and r2.level == "L2" and r2.corpus_access == "public"

    # No token → fallback L2
    r_fallback = v.verify_agent("")
    assert not r_fallback.is_valid and r_fallback.level == "L2"
