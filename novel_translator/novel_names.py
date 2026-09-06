import json
import threading
from pathlib import Path
from typing import Any, Callable

from . import settings
from .chapters import safe_segment
from .config import load_config
from .codex_backend import call_codex
from .openrouter import call_openrouter
from .errors import AppError
from .json_store import read_json, write_json
from .novel_activity import novel_work
from .llm_schemas import NOVEL_NAME_SCHEMA
from .source_language import contains_source_language_text


state_lock = threading.Lock()


def novel_metadata_path(novel: str, output_root: Path | None = None) -> Path:
    output_root = output_root or settings.OUTPUT_ROOT
    safe_novel = safe_segment(novel, "novel")
    return output_root / safe_novel / "metadata.json"


def load_novel_display_name(novel: str, output_root: Path | None = None) -> str:
    safe_novel = safe_segment(novel, "novel")
    metadata = read_json(novel_metadata_path(safe_novel, output_root), {})
    if isinstance(metadata, dict):
        translated_name = str(metadata.get("translated_name", "")).strip()
        if translated_name and not contains_source_language_text(translated_name):
            return translated_name
    return safe_novel


def needs_translated_novel_name(novel: str, output_root: Path | None = None) -> bool:
    safe_novel = safe_segment(novel, "novel")
    return (
        contains_source_language_text(safe_novel)
        and load_novel_display_name(safe_novel, output_root) == safe_novel
    )


@novel_work
def ensure_translated_novel_name(
    novel: str,
    output_root: Path | None = None,
    call_api: Any = None,
    should_abort: Callable[[], bool] | None = None,
) -> str:
    safe_novel = safe_segment(novel, "novel")
    existing = load_novel_display_name(safe_novel, output_root)
    if existing != safe_novel or not contains_source_language_text(safe_novel):
        return existing

    config = load_config()
    api_key = config["openrouter_api_key"]
    backend = config["translation_backend"]
    if backend == "openrouter":
        if not api_key:
            raise AppError("OpenRouter API key is not configured.")
        if not config["translation_model"] or not config["translation_provider"]:
            raise AppError("Select an OpenRouter translation model.")
    if backend == "codex" and not config["codex_translation_model"]:
        raise AppError("Codex translation model is not configured.")

    call_api = call_api or call_openrouter
    if should_abort and should_abort():
        raise AppError("Bulk translation aborted.", 409)
    messages = build_novel_name_messages(safe_novel)
    if call_api is call_openrouter and backend == "codex":
        response = call_codex(
            config["codex_translation_model"],
            messages,
            NOVEL_NAME_SCHEMA,
            reasoning_effort=config["translation_reasoning_effort"],
            fast_mode=config["codex_fast_mode"],
        )
    elif call_api is call_openrouter:
        response = call_api(
            api_key,
            config["translation_model"],
            messages,
            config["translation_provider"],
            output_schema=NOVEL_NAME_SCHEMA,
            reasoning_effort=config["translation_reasoning_effort"],
        )
    else:
        response = call_api(api_key, config["translation_model"], messages)
    translated_name = parse_novel_name_response(response)
    if should_abort and should_abort():
        raise AppError("Bulk translation aborted.", 409)
    with state_lock:
        metadata = read_json(novel_metadata_path(safe_novel, output_root), {})
        if not isinstance(metadata, dict):
            metadata = {}
        metadata["name"] = safe_novel
        metadata["translated_name"] = translated_name
        write_json(novel_metadata_path(safe_novel, output_root), metadata)
    return translated_name


def build_novel_name_messages(novel: str) -> list[dict[str, str]]:
    user = f"""
Translate this web novel title into concise, natural English.
Preserve meaning and genre flavor. Translate objects, powers, and concepts;
romanize character names only if the title is clearly a personal name.
Do not include Chinese or Korean source-language text.

Return only valid JSON with:
{{
  "translated_name": "English novel title"
}}

Novel title:
{novel}
""".strip()
    return [
        {"role": "system", "content": "You translate web novel titles into English."},
        {"role": "user", "content": user},
    ]


def parse_novel_name_response(data: dict[str, Any]) -> str:
    if "choices" in data:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AppError("Model response did not include novel title content.", 502) from exc
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AppError("Model message was not valid novel title JSON.", 502) from exc

    translated_name = data.get("translated_name")
    if not isinstance(translated_name, str) or not translated_name.strip():
        raise AppError("Novel title JSON is missing translated_name.", 502)
    translated_name = translated_name.strip()
    if contains_source_language_text(translated_name):
        raise AppError("Translated novel title still contains source-language text.", 502)
    return translated_name
