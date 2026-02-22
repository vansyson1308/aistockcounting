import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.settings = get_settings()
        self.window_s = 60
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        client = request.client.host if request.client else "unknown"
        key = f"{client}:{request.url.path}"
        now = time.time()
        q = self.hits[key]

        while q and now - q[0] > self.window_s:
            q.popleft()

        if len(q) >= self.settings.rate_limit_per_minute:
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "Too many requests. Please retry later.",
                    },
                },
            )

        q.append(now)
        return await call_next(request)
