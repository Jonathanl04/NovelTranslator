import json
import urllib.error
import urllib.request
from typing import Any

from . import settings
from .errors import AppError


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
        "temperature": 0.3,
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
        raise AppError(f"DeepSeek request failed: HTTP {exc.code} {detail}", 502) from exc
    except urllib.error.URLError as exc:
        raise AppError(f"DeepSeek request failed: {exc.reason}", 502) from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError("DeepSeek returned invalid API JSON.", 502) from exc
