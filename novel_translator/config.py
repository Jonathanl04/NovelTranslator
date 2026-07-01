import re
from typing import Any

from . import settings
from .errors import AppError
from .json_store import read_json, write_json


def load_config() -> dict[str, str]:
    config = read_json(settings.CONFIG_PATH, {})
    if not isinstance(config, dict):
        raise AppError("translator_config.json must contain a JSON object.", 500)
    old_model = str(config.get("model", "")).strip()
    openrouter_api_key = str(config.get("openrouter_api_key", config.get("api_key", "")))
    translation_model = str(
        config.get("translation_model", old_model or settings.DEFAULT_TRANSLATION_MODEL)
    ).strip()
    glossary_model = str(config.get("glossary_model", settings.DEFAULT_GLOSSARY_MODEL)).strip()
    return {
        "openrouter_api_key": openrouter_api_key,
        "translation_model": translation_model if translation_model in settings.MODELS else settings.DEFAULT_TRANSLATION_MODEL,
        "glossary_model": glossary_model if glossary_model in settings.MODELS else settings.DEFAULT_GLOSSARY_MODEL,
    }


def save_config(config: dict[str, Any]) -> dict[str, str]:
    current = load_config()
    keep_openrouter_key = (
        config.get("keep_existing_openrouter_key")
        or ("openrouter_api_key" not in config and "api_key" not in config)
    )
    openrouter_api_key = str(
        current["openrouter_api_key"]
        if keep_openrouter_key
        else config.get("openrouter_api_key", config.get("api_key", ""))
    ).strip()
    translation_model = str(
        config.get("translation_model", current["translation_model"])
        or current["translation_model"]
    ).strip()
    glossary_model = str(
        config.get("glossary_model", current["glossary_model"])
        or current["glossary_model"]
    ).strip()
    if translation_model not in settings.MODELS or glossary_model not in settings.MODELS:
        raise AppError(f"Models must be one of: {', '.join(sorted(settings.MODELS))}.")
    saved = {
        "openrouter_api_key": openrouter_api_key,
        "translation_model": translation_model,
        "glossary_model": glossary_model,
    }
    write_json(settings.CONFIG_PATH, saved)
    return saved


def public_config() -> dict[str, Any]:
    config = load_config()
    return {
        "has_openrouter_api_key": bool(config["openrouter_api_key"]),
        "openrouter_api_key_mask": mask_key(config["openrouter_api_key"]),
        "translation_model": config["translation_model"],
        "glossary_model": config["glossary_model"],
    }


def mask_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "********"
    return f"{api_key[:4]}...{api_key[-4:]}"


def safe_file_stem(value: str) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", value).strip(" .")
    if not stem:
        raise AppError("Invalid novel.")
    return stem
