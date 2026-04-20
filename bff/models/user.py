"""CurrentUser Pydantic model (D3 — single-tenant, no customer_id)."""
from pydantic import BaseModel


class CurrentUser(BaseModel):
    sub: str
    roles: list[str]
