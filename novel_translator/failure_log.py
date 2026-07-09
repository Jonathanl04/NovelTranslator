import json
import threading
from datetime import datetime, timezone
from typing import Any

from . import settings


_log_lock = threading.Lock()


def log_llm_failure(
    event: str,
    request_payload: dict[str, Any],
    error: str,
    response: Any = None,
    raw_response: str | None = None,
) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "error": error,
        "request": sanitize_request(request_payload),
        "response": response,
        "raw_response": raw_response,
    }
    settings.LLM_FAILURE_LOG.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False, default=str)
    with _log_lock:
        with settings.LLM_FAILURE_LOG.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def sanitize_request(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(payload)
    if "api_key" in sanitized:
        sanitized["api_key"] = "[redacted]"
    headers = sanitized.get("headers")
    if isinstance(headers, dict) and "Authorization" in headers:
        sanitized["headers"] = {**headers, "Authorization": "[redacted]"}
    return sanitized
