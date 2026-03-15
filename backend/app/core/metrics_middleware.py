import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.metrics import request_count, request_duration_seconds


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip metrics endpoint to avoid self-referencing
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        path = request.url.path

        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        request_count.labels(
            method=method, path=path, status=response.status_code
        ).inc()
        request_duration_seconds.labels(method=method, path=path).observe(duration)

        return response
