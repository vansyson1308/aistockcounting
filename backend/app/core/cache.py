import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_redis_client: Any = None
_available = False


def _get_redis() -> Any:
    global _redis_client, _available
    if _redis_client is not None:
        return _redis_client
    try:
        import redis

        from app.core.config import get_settings

        settings = get_settings()
        _redis_client = redis.Redis.from_url(
            settings.redis_url, decode_responses=True, socket_connect_timeout=2
        )
        _redis_client.ping()
        _available = True
        logger.info("Redis connected: %s", settings.redis_url)
    except Exception:
        _available = False
        logger.info("Redis unavailable; caching disabled")
    return _redis_client


def cache_key(*parts: str) -> str:
    raw = ":".join(parts)
    return f"vjsc:{hashlib.md5(raw.encode()).hexdigest()}"


def get_cached(key: str) -> dict | None:
    try:
        client = _get_redis()
        if not _available or client is None:
            return None
        data = client.get(key)
        if data is None:
            return None
        return json.loads(data)
    except Exception:
        return None


def set_cached(key: str, value: Any, ttl: int = 300) -> None:
    try:
        client = _get_redis()
        if not _available or client is None:
            return
        client.setex(key, ttl, json.dumps(value, default=str))
    except Exception:
        pass


def invalidate(pattern: str = "vjsc:*") -> None:
    try:
        client = _get_redis()
        if not _available or client is None:
            return
        keys = client.keys(pattern)
        if keys:
            client.delete(*keys)
    except Exception:
        pass
