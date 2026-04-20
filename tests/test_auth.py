"""Unit tests for JWT verification and get_current_user (STORY-02).

All JWKS calls are mocked — no real Keycloak requests.
"""
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jose import jwt

from bff.clients.keycloak_jwks import invalidate_jwks_cache
from bff.dependencies import get_current_user
from bff.middleware.auth import verify_jwt
from bff.models.user import CurrentUser


# ---------------------------------------------------------------------------
# RSA key fixture helpers
# ---------------------------------------------------------------------------


def _generate_rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _private_pem(key: rsa.RSAPrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )


def _make_jwks(key: rsa.RSAPrivateKey) -> dict:
    """Return a minimal JWKS dict containing the public key of *key*."""
    from jose.backends import RSAKey

    pub = key.public_key()
    pub_pem = pub.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    rsa_key = RSAKey(pub_pem.decode(), "RS256")
    return {"keys": [rsa_key.public_key().to_dict()]}  # type: ignore[attr-defined]


def _make_token(
    key: rsa.RSAPrivateKey,
    *,
    sub: str = "user123",
    roles: list[str] | None = None,
    exp_offset: int = 3600,
    issuer: str = "http://keycloak/realms/nmsplus",
) -> str:
    payload: dict[str, Any] = {
        "sub": sub,
        "iss": issuer,
        "exp": int(time.time()) + exp_offset,
        "iat": int(time.time()),
    }
    if roles is not None:
        payload["realm_access"] = {"roles": roles}
    pem = _private_pem(key)
    return jwt.encode(payload, pem, algorithm="RS256")


# ---------------------------------------------------------------------------
# verify_jwt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_jwt_valid_token() -> None:
    key = _generate_rsa_key()
    jwks = _make_jwks(key)
    token = _make_token(key, roles=["viewer"])

    with patch("bff.middleware.auth.get_jwks", new=AsyncMock(return_value=jwks)), patch(
        "bff.middleware.auth.settings"
    ) as mock_settings:
        mock_settings.keycloak_realm_url = ""
        payload = await verify_jwt(token)

    assert payload["sub"] == "user123"
    assert payload["realm_access"]["roles"] == ["viewer"]


@pytest.mark.asyncio
async def test_verify_jwt_expired_token() -> None:
    key = _generate_rsa_key()
    jwks = _make_jwks(key)
    token = _make_token(key, exp_offset=-3600)  # expired 1h ago

    with patch("bff.middleware.auth.get_jwks", new=AsyncMock(return_value=jwks)), patch(
        "bff.middleware.auth.settings"
    ) as mock_settings:
        mock_settings.keycloak_realm_url = ""
        with pytest.raises(HTTPException) as exc_info:
            await verify_jwt(token)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Not authenticated"


@pytest.mark.asyncio
async def test_verify_jwt_malformed_token() -> None:
    with patch("bff.middleware.auth.get_jwks", new=AsyncMock(return_value={"keys": []})), patch(
        "bff.middleware.auth.settings"
    ) as mock_settings, patch(
        "bff.clients.keycloak_jwks.invalidate_jwks_cache"
    ):
        mock_settings.keycloak_realm_url = ""
        with pytest.raises(HTTPException) as exc_info:
            await verify_jwt("not-a-jwt")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_jwt_signature_mismatch() -> None:
    signing_key = _generate_rsa_key()
    wrong_key = _generate_rsa_key()
    wrong_jwks = _make_jwks(wrong_key)  # JWKS has wrong_key's public key
    token = _make_token(signing_key)  # signed with signing_key

    with patch("bff.middleware.auth.get_jwks", new=AsyncMock(return_value=wrong_jwks)), patch(
        "bff.middleware.auth.settings"
    ) as mock_settings:
        mock_settings.keycloak_realm_url = ""
        with pytest.raises(HTTPException) as exc_info:
            await verify_jwt(token)

    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# get_current_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_current_user_extracts_sub_and_roles() -> None:
    key = _generate_rsa_key()
    jwks = _make_jwks(key)
    token = _make_token(key, sub="user123", roles=["viewer"])

    with patch("bff.middleware.auth.get_jwks", new=AsyncMock(return_value=jwks)), patch(
        "bff.middleware.auth.settings"
    ) as mock_settings:
        mock_settings.keycloak_realm_url = ""
        user = await get_current_user(authorization=f"Bearer {token}")

    assert user.sub == "user123"
    assert user.roles == ["viewer"]


@pytest.mark.asyncio
async def test_get_current_user_missing_authorization_header() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(authorization=None)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Not authenticated"


@pytest.mark.asyncio
async def test_get_current_user_no_customer_id_field() -> None:
    user = CurrentUser(sub="x", roles=[])
    assert not hasattr(user, "customer_id"), "D3 violation: customer_id must not exist on CurrentUser"


@pytest.mark.asyncio
async def test_get_current_user_no_realm_access_defaults_to_empty_roles() -> None:
    key = _generate_rsa_key()
    jwks = _make_jwks(key)
    token = _make_token(key, roles=None)  # no realm_access claim

    with patch("bff.middleware.auth.get_jwks", new=AsyncMock(return_value=jwks)), patch(
        "bff.middleware.auth.settings"
    ) as mock_settings:
        mock_settings.keycloak_realm_url = ""
        user = await get_current_user(authorization=f"Bearer {token}")

    assert user.roles == []
