import hmac
import re

from fastapi import Header

from app.core.audit import audit_log
from app.core.config import get_settings
from app.core.errors import api_error

_STAFF_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,50}$")


def enforce_optional_auth(
    x_staff_id: str | None = Header(default=None, alias="X-STAFF-ID"),
    x_api_token: str | None = Header(default=None, alias="X-API-TOKEN"),
) -> None:
    settings = get_settings()
    if not settings.enable_simple_auth:
        return

    if x_staff_id:
        if not _STAFF_ID_RE.match(x_staff_id):
            raise api_error(
                400,
                "INVALID_STAFF_ID",
                "Staff ID must be alphanumeric with hyphens/underscores, max 50 chars",
            )
        return

    if settings.simple_auth_token and hmac.compare_digest(
        x_api_token or "", settings.simple_auth_token
    ):
        return

    audit_log("AUTH_FAIL", x_staff_id, {"reason": "no_valid_credentials"})
    raise api_error(401, "UNAUTHORIZED", "Authentication required")
