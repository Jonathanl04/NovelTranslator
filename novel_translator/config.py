import re
from typing import Any

from . import settings
from .errors import AppError
from .json_store import read_json, write_json


def load_config() -> dict[str, Any]:
    config = read_json(settings.CONFIG_PATH, {})
    if not isinstance(config, dict):
        raise AppError("translator_config.json must contain a JSON object.", 500)
    old_model = str(config.get("model", "")).strip()
    openrouter_api_key = str(config.get("openrouter_api_key", config.get("api_key", "")))
    translation_model = str(
        config.get("translation_model", old_model or settings.DEFAULT_TRANSLATION_MODEL)
    ).strip()
    glossary_model = str(config.get("glossary_model", settings.DEFAULT_GLOSSARY_MODEL)).strip()
    translation_model = translation_model or settings.DEFAULT_TRANSLATION_MODEL
    glossary_model = glossary_model or settings.DEFAULT_GLOSSARY_MODEL
    translation_provider = provider_for_config(
        config, "translation_provider", settings.DEFAULT_TRANSLATION_PROVIDER
    )
    glossary_provider = provider_for_config(
        config, "glossary_provider", settings.DEFAULT_GLOSSARY_PROVIDER
    )
    translation_model, translation_provider = normalize_preset_model(
        translation_model, translation_provider
    )
    glossary_model, glossary_provider = normalize_preset_model(glossary_model, glossary_provider)
    return {
        "openrouter_api_key": openrouter_api_key,
        "translation_model": translation_model,
        "translation_provider": translation_provider,
        "glossary_model": glossary_model,
        "glossary_provider": glossary_provider,
        "added_models": normalize_models(config.get("added_models", config.get("favorite_models", []))),
    }


def save_config(config: dict[str, Any]) -> dict[str, Any]:
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
    translation_provider = selected_provider(
        config, "translation_provider", translation_model, current["translation_provider"]
    )
    glossary_model = str(
        config.get("glossary_model", current["glossary_model"])
        or current["glossary_model"]
    ).strip()
    glossary_provider = selected_provider(
        config, "glossary_provider", glossary_model, current["glossary_provider"]
    )
    if not translation_model or not glossary_model:
        raise AppError("Models are required.")
    if not translation_provider or not glossary_provider:
        raise AppError("Model providers are required.")
    translation_model, translation_provider = normalize_preset_model(
        translation_model, translation_provider
    )
    glossary_model, glossary_provider = normalize_preset_model(glossary_model, glossary_provider)
    saved = {
        "openrouter_api_key": openrouter_api_key,
        "translation_model": translation_model,
        "translation_provider": translation_provider,
        "glossary_model": glossary_model,
        "glossary_provider": glossary_provider,
        "added_models": normalize_models(
            config.get("added_models", config.get("favorite_models", current["added_models"]))
        ),
    }
    write_json(settings.CONFIG_PATH, saved)
    return saved


def public_config() -> dict[str, Any]:
    config = load_config()
    return {
        "has_openrouter_api_key": bool(config["openrouter_api_key"]),
        "openrouter_api_key_mask": mask_key(config["openrouter_api_key"]),
        "translation_model": config["translation_model"],
        "translation_provider": config["translation_provider"],
        "glossary_model": config["glossary_model"],
        "glossary_provider": config["glossary_provider"],
        "added_models": config["added_models"],
        "model_presets": settings.DEFAULT_MODEL_PRESETS,
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


def provider_for_config(config: dict[str, Any], key: str, default_provider: str) -> str:
    provider = str(config.get(key, "")).strip()
    return provider or default_provider


def selected_provider(config: dict[str, Any], key: str, model: str, current_provider: str) -> str:
    if key not in config:
        return current_provider
    return str(config.get(key, "")).strip()


def normalize_models(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    models = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        model = str(item.get("model", "")).strip()
        provider = str(item.get("provider", "")).strip()
        key = (model, provider)
        if not model or not provider or key in seen:
            continue
        seen.add(key)
        models.append({"model": model, "provider": provider})
    return models


def normalize_preset_model(model: str, provider: str) -> tuple[str, str]:
    suffix_matches = [
        preset
        for preset in settings.DEFAULT_MODEL_PRESETS
        if model == preset["model"].rsplit("/", 1)[-1]
    ]
    if len(suffix_matches) == 1:
        preset = suffix_matches[0]
        return preset["model"], preset["provider"]
    for preset in settings.DEFAULT_MODEL_PRESETS:
        preset_model = preset["model"]
        preset_provider = preset["provider"]
        if model == preset_model:
            return model, provider or preset_provider
    return model, provider
