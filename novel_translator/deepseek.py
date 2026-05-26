import json
import urllib.error
import urllib.request
from typing import Any

from . import settings
from .errors import AppError
from .failure_log import log_deepseek_failure
from .usage import record_deepseek_usage


def call_deepseek(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    opener: Any = urllib.request.urlopen,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "thinking": {"type": "disabled"},
        "temperature": 0.6,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        settings.DEEPSEEK_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=180) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        log_deepseek_failure("http_error", payload, f"HTTP {exc.code}", raw_response=detail)
        raise AppError(f"DeepSeek request failed: HTTP {exc.code} {detail}", 502) from exc
    except urllib.error.URLError as exc:
        log_deepseek_failure("url_error", payload, str(exc.reason))
        raise AppError(f"DeepSeek request failed: {exc.reason}", 502) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        log_deepseek_failure("invalid_api_json", payload, str(exc), raw_response=raw)
        raise AppError("DeepSeek returned invalid API JSON.", 502) from exc

    if isinstance(data, dict):
        record_deepseek_usage(model, data)
    return data
