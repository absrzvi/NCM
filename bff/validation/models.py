from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class GateResult(BaseModel):
    passed: bool
    code: str | None = None
    message: str | None = None
    warning: str | None = None
    data: Any = None
