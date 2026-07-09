import threading
from copy import deepcopy
from typing import Any


_empty_usage = {
    "prompt_cache_hit_tokens": 0,
    "prompt_cache_miss_tokens": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "cost_usd": 0.0,
}
_usage = {}
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

    cost = usage_cost(usage)

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
    for bucket in by_model.values():
        for key in total:
            total[key] += bucket[key]
        bucket["cost_usd"] = round(float(bucket["cost_usd"]), 8)
    total["cost_usd"] = round(float(total["cost_usd"]), 8)
    return {"total": total, "by_model": by_model}


def reset_usage() -> dict[str, Any]:
    with _usage_lock:
        _usage.clear()
    return current_usage()


def int_token(value: Any) -> int:
    return value if isinstance(value, int) and value > 0 else 0


def usage_cost(usage: dict[str, Any]) -> float:
    cost = number(usage.get("cost"))
    details = usage.get("cost_details")
    upstream_cost = number(details.get("upstream_inference_cost")) if isinstance(details, dict) else None
    if cost is not None:
        if upstream_cost is not None and cost <= upstream_cost * 0.1:
            return cost + upstream_cost
        return cost
    return 0.0


def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return float(value)
    return None
