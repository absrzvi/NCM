"""Sliding-window, memory-backed rate limiter — 10 req/s per IP.

No Redis required in MVP (D8: single BFF container).
"""
import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

_RATE_LIMIT = 10  # requests per window
_WINDOW_SECONDS = 1.0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter applied to all routes."""

    def __init__(self, app: Callable, paths: list[str] | None = None) -> None:
        super().__init__(app)
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._paths = paths  # if None, applies to all

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if self._paths is not None and request.url.path not in self._paths:
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = self._windows[ip]

        # Evict timestamps outside the sliding window
        cutoff = now - _WINDOW_SECONDS
        while window and window[0] <= cutoff:
            window.popleft()

        if len(window) >= _RATE_LIMIT:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
            )

        window.append(now)
        return await call_next(request)
