from fastapi import Header

from app.core.config import get_settings
from app.core.errors import api_error


def enforce_optional_auth(
    x_staff_id: str | None = Header(default=None, alias="X-STAFF-ID"),
    x_api_token: str | None = Header(default=None, alias="X-API-TOKEN"),
) -> None:
    settings = get_settings()
    if not settings.enable_simple_auth:
        return

    if x_staff_id:
        return

    if settings.simple_auth_token and x_api_token == settings.simple_auth_token:
        return

    raise api_error(401, "UNAUTHORIZED", "Authentication required")
