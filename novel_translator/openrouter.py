import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import settings
from .errors import AppError
from .failure_log import log_llm_failure
from .usage import record_llm_usage


OPENROUTER_TIMEOUT_SECONDS = 300
OPENROUTER_TIMEOUT_MESSAGE = "OpenRouter request timed out."
_json_object_unsupported: set[tuple[str, str]] = set()
_json_schema_unsupported: set[tuple[str, str]] = set()
_response_format_lock = threading.Lock()


def call_openrouter(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    provider: str = "",
    opener: Any = urllib.request.urlopen,
    output_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if callable(provider):
        opener = provider
        provider = ""
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 1,
        "stream": False,
        "thinking": {"type": "disabled"},
        "reasoning": {"effort": "none", "exclude": True},
    }
    if output_schema is not None and json_schema_supported(model, provider):
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "novel_translator_response",
                "strict": False,
                "schema": output_schema,
            },
        }
    elif json_object_supported(model, provider):
        payload["response_format"] = {"type": "json_object"}
    if provider:
        payload["provider"] = {
            "only": [provider],
            "allow_fallbacks": False,
        }
    return post_openrouter(api_key, model, payload, opener)


def post_openrouter(api_key: str, usage_model: str, payload: dict[str, Any], opener: Any) -> dict[str, Any]:
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
        with opener(request, timeout=OPENROUTER_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
    except TimeoutError as exc:
        log_llm_failure("timeout", payload, str(exc) or OPENROUTER_TIMEOUT_MESSAGE)
        raise AppError(OPENROUTER_TIMEOUT_MESSAGE, 502) from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if should_retry_without_json_schema(payload, detail):
            payload_provider = provider_from_payload(payload)
            remember_json_schema_unsupported(usage_model, payload_provider)
            retry_payload = dict(payload)
            if json_object_supported(usage_model, payload_provider):
                retry_payload["response_format"] = {"type": "json_object"}
            else:
                retry_payload.pop("response_format", None)
            return post_openrouter(api_key, usage_model, retry_payload, opener)
        if should_retry_without_json_object(payload, detail):
            remember_json_object_unsupported(usage_model, provider_from_payload(payload))
            retry_payload = dict(payload)
            retry_payload.pop("response_format", None)
            return post_openrouter(api_key, usage_model, retry_payload, opener)
        log_llm_failure("http_error", payload, f"HTTP {exc.code}", raw_response=detail)
        raise AppError(f"OpenRouter request failed: HTTP {exc.code} {detail}", 502) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            log_llm_failure("timeout", payload, str(exc.reason) or OPENROUTER_TIMEOUT_MESSAGE)
            raise AppError(OPENROUTER_TIMEOUT_MESSAGE, 502) from exc
        log_llm_failure("url_error", payload, str(exc.reason))
        raise AppError(f"OpenRouter request failed: {exc.reason}", 502) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        log_llm_failure("invalid_api_json", payload, str(exc), raw_response=raw)
        raise AppError("OpenRouter returned invalid API JSON.", 502) from exc

    if isinstance(data, dict):
        record_llm_usage(usage_model, data)
    return data


def should_retry_without_json_object(payload: dict[str, Any], detail: str) -> bool:
    response_format = payload.get("response_format")
    if not isinstance(response_format, dict) or response_format.get("type") != "json_object":
        return False
    detail_lower = detail.lower()
    return "json_object" in detail_lower and (
        "response format" in detail_lower or "response_format" in detail_lower
    )


def should_retry_without_json_schema(payload: dict[str, Any], detail: str) -> bool:
    response_format = payload.get("response_format")
    if not isinstance(response_format, dict) or response_format.get("type") != "json_schema":
        return False
    detail_lower = detail.lower()
    format_mentioned = (
        "json_schema" in detail_lower
        or "structured output" in detail_lower
        or ("response_format" in detail_lower and "json_object" in detail_lower)
    )
    return format_mentioned and (
        "response format" in detail_lower
        or "response_format" in detail_lower
        or "not support" in detail_lower
        or "unsupported" in detail_lower
    )


def json_object_supported(model: str, provider: str) -> bool:
    with _response_format_lock:
        return (model, provider) not in _json_object_unsupported


def json_schema_supported(model: str, provider: str) -> bool:
    with _response_format_lock:
        return (model, provider) not in _json_schema_unsupported


def remember_json_object_unsupported(model: str, provider: str) -> None:
    with _response_format_lock:
        _json_object_unsupported.add((model, provider))


def remember_json_schema_unsupported(model: str, provider: str) -> None:
    with _response_format_lock:
        _json_schema_unsupported.add((model, provider))


def provider_from_payload(payload: dict[str, Any]) -> str:
    provider = payload.get("provider")
    if not isinstance(provider, dict):
        return ""
    only = provider.get("only")
    if isinstance(only, list) and only:
        return str(only[0])
    return ""


def openrouter_model_providers(
    model: str,
    api_key: str = "",
    opener: Any = urllib.request.urlopen,
) -> list[dict[str, str]]:
    model = model.strip()
    if not model:
        raise AppError("model is required.")
    encoded_model = urllib.parse.quote(model, safe="/")
    request = urllib.request.Request(
        f"https://openrouter.ai/api/v1/models/{encoded_model}/endpoints",
        headers=openrouter_headers(api_key),
        method="GET",
    )
    try:
        with opener(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AppError(f"OpenRouter providers failed: HTTP {exc.code} {detail}", 502) from exc
    except urllib.error.URLError as exc:
        raise AppError(f"OpenRouter providers failed: {exc.reason}", 502) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError("OpenRouter returned invalid provider JSON.", 502) from exc

    endpoints = endpoint_items(data)
    providers = []
    seen = set()
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue
        provider = str(endpoint.get("tag") or endpoint.get("provider") or "").strip()
        name = str(endpoint.get("provider_name") or endpoint.get("name") or provider).strip()
        if not provider or provider in seen:
            continue
        seen.add(provider)
        providers.append({"provider": provider, "name": name or provider})
    return providers


def openrouter_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def endpoint_items(data: Any) -> list[Any]:
    if isinstance(data, dict):
        nested = data.get("data")
        if isinstance(nested, dict) and isinstance(nested.get("endpoints"), list):
            return nested["endpoints"]
        if isinstance(nested, list):
            return nested
        if isinstance(data.get("endpoints"), list):
            return data["endpoints"]
    return []
