import json
import threading
from pathlib import Path
from typing import Any, Callable

from . import settings
from .chapters import safe_segment
from .config import load_config
from .deepseek import call_deepseek
from .errors import AppError
from .json_store import read_json, write_json
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
    if not api_key:
        return safe_novel

    call_api = call_api or call_deepseek
    if should_abort and should_abort():
        raise AppError("Bulk translation aborted.", 409)
    messages = build_novel_name_messages(safe_novel)
    if call_api is call_deepseek:
        response = call_api(api_key, config["translation_model"], messages, config["translation_provider"])
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
            raise AppError("DeepSeek response did not include novel title content.", 502) from exc
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AppError("DeepSeek message was not valid novel title JSON.", 502) from exc

    translated_name = data.get("translated_name")
    if not isinstance(translated_name, str) or not translated_name.strip():
        raise AppError("Novel title JSON is missing translated_name.", 502)
    translated_name = translated_name.strip()
    if contains_source_language_text(translated_name):
        raise AppError("Translated novel title still contains source-language text.", 502)
    return translated_name
