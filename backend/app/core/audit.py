import json
import logging
import time

logger = logging.getLogger("app.audit")


def audit_log(action: str, staff_id: str | None, detail: dict | None = None) -> None:
    entry = {
        "audit": True,
        "action": action,
        "staff_id": staff_id or "anonymous",
        "timestamp": int(time.time()),
        "detail": detail or {},
    }
    logger.info(json.dumps(entry, ensure_ascii=False))
