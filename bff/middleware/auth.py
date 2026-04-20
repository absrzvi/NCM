"""JWT RS256 verification using Keycloak JWKS (D2)."""
import logging

from fastapi import HTTPException
from jose import ExpiredSignatureError, JWTError, jwt
from jose.exceptions import JWKError

from bff.clients.keycloak_jwks import get_jwks, invalidate_jwks_cache
from bff.config import settings

logger = logging.getLogger(__name__)


async def verify_jwt(token: str) -> dict:
    """Verify RS256 JWT signature and claims; return decoded payload.

    Raises HTTPException(401) on any failure.
    """
    try:
        payload = await _decode(token)
    except ExpiredSignatureError:
        logger.warning("JWT expired")
        raise HTTPException(status_code=401, detail="Not authenticated")
    except (JWTError, JWKError, Exception) as exc:
        # On key-not-found, invalidate cache once and retry with fresh JWKS.
        logger.warning("JWT verification failed (%s); refreshing JWKS cache", type(exc).__name__)
        invalidate_jwks_cache()
        try:
            payload = await _decode(token)
        except ExpiredSignatureError:
            logger.warning("JWT expired (after cache refresh)")
            raise HTTPException(status_code=401, detail="Not authenticated")
        except Exception:
            logger.warning("JWT verification failed after JWKS refresh")
            raise HTTPException(status_code=401, detail="Not authenticated")

    issuer = payload.get("iss", "")
    if settings.keycloak_realm_url and issuer != settings.keycloak_realm_url:
        logger.warning("JWT issuer mismatch: %s", issuer)
        raise HTTPException(status_code=401, detail="Not authenticated")

    return payload


async def _decode(token: str) -> dict:
    jwks = await get_jwks()
    return jwt.decode(
        token,
        jwks,
        algorithms=["RS256"],
        options={"verify_aud": False},
    )
