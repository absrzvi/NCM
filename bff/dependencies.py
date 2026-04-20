"""FastAPI dependencies (D3 — get_current_user, no customer_id)."""
import logging

from fastapi import Header, HTTPException

from bff.middleware.auth import verify_jwt
from bff.models.user import CurrentUser

logger = logging.getLogger(__name__)


async def get_current_user(authorization: str = Header(default=None)) -> CurrentUser:
    """Extract and validate Bearer JWT; return CurrentUser(sub, roles).

    Raises 401 if the header is missing, malformed, or the token is invalid.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = parts[1]
    payload = await verify_jwt(token)

    sub = payload.get("sub", "")
    if not sub:
        logger.warning("JWT missing sub claim")
        raise HTTPException(status_code=401, detail="Not authenticated")

    realm_access = payload.get("realm_access") or {}
    roles: list[str] = realm_access.get("roles") or []

    return CurrentUser(sub=sub, roles=roles)
