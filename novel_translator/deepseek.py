import json
import urllib.error
import urllib.request
from typing import Any

from . import settings
from .errors import AppError
from .failure_log import log_deepseek_failure
from .usage import record_deepseek_usage


DEEPSEEK_TIMEOUT_SECONDS = 300
DEEPSEEK_TIMEOUT_MESSAGE = "DeepSeek request timed out."


def call_deepseek(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    opener: Any = urllib.request.urlopen,
) -> dict[str, Any]:
    provider = settings.MODEL_PROVIDER_IDS.get(model)
    payload = {
        "model": settings.MODEL_API_IDS.get(model, model),
        "messages": messages,
        "temperature": 1,
        "stream": False,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "reasoning": {"effort": "none", "exclude": True},
    }
    if provider:
        payload["provider"] = {
            "only": [provider],
            "allow_fallbacks": False,
        }
    request = urllib.request.Request(
        settings.OPENROUTER_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=DEEPSEEK_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
    except TimeoutError as exc:
        log_deepseek_failure("timeout", payload, str(exc) or DEEPSEEK_TIMEOUT_MESSAGE)
        raise AppError(DEEPSEEK_TIMEOUT_MESSAGE, 502) from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        log_deepseek_failure("http_error", payload, f"HTTP {exc.code}", raw_response=detail)
        raise AppError(f"DeepSeek request failed: HTTP {exc.code} {detail}", 502) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            log_deepseek_failure("timeout", payload, str(exc.reason) or DEEPSEEK_TIMEOUT_MESSAGE)
            raise AppError(DEEPSEEK_TIMEOUT_MESSAGE, 502) from exc
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
