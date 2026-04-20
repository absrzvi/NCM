"""FastAPI BFF entry point."""
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg
from fastapi import Depends, FastAPI

from bff.clients.keycloak_jwks import close_keycloak_client
from bff.clients.puppetdb_client import close_puppetdb_client
from bff.clients.puppet_server_client import close_puppet_server_client
from bff.dependencies import get_current_user
from bff.middleware.idempotency import IdempotencyMiddleware
from bff.middleware.rate_limit import RateLimitMiddleware
from bff.models.user import CurrentUser
from bff.routers.health import router as health_router


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise and tear down shared resources: asyncpg pool and httpx clients."""
    dsn = os.environ.get("POSTGRES_DSN", "")
    pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=10)
    application.state.db_pool = pool
    try:
        yield
    finally:
        await pool.close()
        await close_keycloak_client()
        await close_puppetdb_client()
        await close_puppet_server_client()


app = FastAPI(title="NMS+ Config BFF", lifespan=lifespan)

# Middleware is applied in reverse-registration order (last registered = outermost).
# Effective request stack: RateLimitMiddleware → IdempotencyMiddleware → route handler.
app.add_middleware(IdempotencyMiddleware)
# Rate limit health probes at 10 req/s per IP (STORY-01 / FR8)
app.add_middleware(RateLimitMiddleware, paths=["/healthz", "/readyz"])

# Health probes at root — no /api/ prefix (FR8)
app.include_router(health_router)


@app.get("/api/ping")
async def ping(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Minimal authenticated endpoint used in tests (D3)."""
    return {"sub": user.sub, "roles": user.roles}
