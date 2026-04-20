# Keycloak Authentication Reference

> Read-only reference for all agents. Do not change without platform team approval.

## JWT Claims Structure (RS256)
```json
{
  "sub": "user-uuid",
  "roles": ["viewer", "editor", "admin"],
  "preferred_username": "first.last",
  "email": "first.last@example.com",
  "iss": "https://keycloak.example.com/realms/nmsplus",
  "exp": 1234567890
}
```

> Note: MVP is single-tenant. There is no `customer_id` claim. When multi-tenancy is added later (phase-3), this reference will be updated along with a new ADR and an Iron Rule 3 restoration.

## BFF Auth Pattern
Every endpoint must use the `get_current_user` dependency:

```python
# bff/auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from pydantic import BaseModel

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class User(BaseModel):
    sub: str
    roles: list[str]
    username: str | None = None

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    try:
        payload = jwt.decode(
            token,
            KEYCLOAK_PUBLIC_KEY,      # JWKS-resolved
            algorithms=["RS256"],
            audience=EXPECTED_AUDIENCE,
            issuer=EXPECTED_ISSUER,   # must match configured realm
        )
        return User(
            sub=payload["sub"],
            roles=payload.get("roles", []),
            username=payload.get("preferred_username"),
        )
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
```

## Role-based Authorisation Rule
Every write endpoint must assert role before touching downstream:
```python
if "editor" not in user.roles and "admin" not in user.roles:
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
```
Force-run (`/api/deployments/force-run`) requires `admin` AND must use the D13 envelope helper.

## Frontend keycloak-js Pattern
See `docs/STACK.md` — `<KeycloakProvider>` wraps `<App>`; components consume via `useKeycloak()` and `useAuthedFetch()`. Tokens are refreshed 60s before expiry; on refresh failure the user is redirected to login with draft state preserved in Zustand+localStorage.
