from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import generate_latest
from pydantic import ValidationError

from app.api.routes import count, export, history, save, stats
from app.core.auth import enforce_optional_auth
from app.core.config import get_settings
from app.core.logging import RequestContextMiddleware, setup_logging
from app.core.metrics_middleware import PrometheusMiddleware
from app.core.rate_limit import InMemoryRateLimitMiddleware
from app.db.database import engine
from app.services.inference import InferenceService
from app.services.storage import StorageService

settings = get_settings()
logger = setup_logging()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    openapi_tags=[
        {"name": "Counting", "description": "Image upload and AI item counting."},
        {"name": "Records", "description": "Persisted count records and history."},
        {"name": "Analytics", "description": "Aggregated statistics for staff."},
        {"name": "System", "description": "Health checks and system endpoints."},
    ],
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(PrometheusMiddleware)
app.add_middleware(InMemoryRateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.cors_origins.split(",") if x.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exc_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = (
        exc.detail
        if isinstance(exc.detail, dict)
        else {"code": "HTTP_ERROR", "message": "Request failed."}
    )
    logger.warning(
        "http_exception",
        extra={"request_id": getattr(request.state, "request_id", "n/a")},
    )
    return JSONResponse(
        status_code=exc.status_code, content={"success": False, "error": detail}
    )


@app.exception_handler(ValidationError)
async def validation_exc_handler(request: Request, _: ValidationError) -> JSONResponse:
    logger.warning(
        "validation_exception",
        extra={"request_id": getattr(request.state, "request_id", "n/a")},
    )
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {"code": "VALIDATION_ERROR", "message": "Invalid request."},
        },
    )


@app.exception_handler(Exception)
async def unhandled_exc_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled_exception",
        extra={"request_id": getattr(request.state, "request_id", "n/a")},
    )
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Unexpected server error.",
            },
        },
    )


@app.get("/health", tags=["System"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", tags=["System"])
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest(), media_type="text/plain; version=0.0.4")


@app.get("/api/health", tags=["System"])
async def api_health() -> dict[str, object]:
    checks = {"db": False, "minio": False}
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
        checks["db"] = True
    except Exception:
        logger.warning("health_db_check_failed")

    try:
        StorageService().ensure_bucket()
        checks["minio"] = True
    except Exception:
        logger.warning("health_minio_check_failed")

    status = "ok" if all(checks.values()) else "degraded"
    return {
        "status": status,
        "checks": checks,
        "model": {
            "loaded": InferenceService.is_model_loaded(),
            "version": settings.model_version,
        },
    }


app.include_router(
    count.router,
    prefix=settings.api_prefix,
    dependencies=[Depends(enforce_optional_auth)],
)
app.include_router(
    save.router,
    prefix=settings.api_prefix,
    dependencies=[Depends(enforce_optional_auth)],
)
app.include_router(
    history.router,
    prefix=settings.api_prefix,
    dependencies=[Depends(enforce_optional_auth)],
)
app.include_router(
    stats.router,
    prefix=settings.api_prefix,
    dependencies=[Depends(enforce_optional_auth)],
)
app.include_router(
    export.router,
    prefix=settings.api_prefix,
    dependencies=[Depends(enforce_optional_auth)],
)
