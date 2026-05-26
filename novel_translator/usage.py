import threading
from copy import deepcopy
from typing import Any


DEEPSEEK_PRICING_PER_MILLION = {
    "deepseek-v4-flash": {
        "input_cache_hit": 0.0028,
        "input_cache_miss": 0.14,
        "output": 0.28,
    },
    "deepseek-v4-pro": {
        "input_cache_hit": 0.003625,
        "input_cache_miss": 0.435,
        "output": 0.87,
    },
}

_empty_usage = {
    "prompt_cache_hit_tokens": 0,
    "prompt_cache_miss_tokens": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "cost_usd": 0.0,
}
_usage = {model: deepcopy(_empty_usage) for model in DEEPSEEK_PRICING_PER_MILLION}
_usage_lock = threading.Lock()


def record_deepseek_usage(model: str, response: dict[str, Any]) -> None:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return

    prompt_tokens = int_token(usage.get("prompt_tokens"))
    completion_tokens = int_token(usage.get("completion_tokens"))
    total_tokens = int_token(usage.get("total_tokens")) or prompt_tokens + completion_tokens
    hit_tokens = int_token(usage.get("prompt_cache_hit_tokens"))
    miss_tokens = int_token(usage.get("prompt_cache_miss_tokens"))

    details = usage.get("prompt_tokens_details")
    if not hit_tokens and isinstance(details, dict):
        hit_tokens = int_token(details.get("cached_tokens"))
    if not miss_tokens:
        miss_tokens = max(prompt_tokens - hit_tokens, 0)

    rates = DEEPSEEK_PRICING_PER_MILLION.get(model, {})
    cost = (
        hit_tokens * float(rates.get("input_cache_hit", 0))
        + miss_tokens * float(rates.get("input_cache_miss", 0))
        + completion_tokens * float(rates.get("output", 0))
    ) / 1_000_000

    with _usage_lock:
        bucket = _usage.setdefault(model, deepcopy(_empty_usage))
        bucket["prompt_cache_hit_tokens"] += hit_tokens
        bucket["prompt_cache_miss_tokens"] += miss_tokens
        bucket["prompt_tokens"] += prompt_tokens
        bucket["completion_tokens"] += completion_tokens
        bucket["total_tokens"] += total_tokens
        bucket["cost_usd"] += cost


def current_usage() -> dict[str, Any]:
    with _usage_lock:
        by_model = deepcopy(_usage)
    total = deepcopy(_empty_usage)
    for model in DEEPSEEK_PRICING_PER_MILLION:
        by_model.setdefault(model, deepcopy(_empty_usage))
    for bucket in by_model.values():
        for key in total:
            total[key] += bucket[key]
        bucket["cost_usd"] = round(float(bucket["cost_usd"]), 8)
    total["cost_usd"] = round(float(total["cost_usd"]), 8)
    return {"total": total, "by_model": by_model}


def reset_usage() -> dict[str, Any]:
    with _usage_lock:
        _usage.clear()
        _usage.update({model: deepcopy(_empty_usage) for model in DEEPSEEK_PRICING_PER_MILLION})
    return current_usage()


def int_token(value: Any) -> int:
    return value if isinstance(value, int) and value > 0 else 0
