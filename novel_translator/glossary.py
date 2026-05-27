import re
from pathlib import Path
from typing import Any

from . import settings
from .chapters import safe_segment
from .config import safe_file_stem
from .errors import AppError
from .json_store import read_json, write_json
from .source_language import contains_source_language_text


def glossary_path(novel: str, glossary_root: Path | None = None) -> Path:
    glossary_root = glossary_root or settings.GLOSSARY_ROOT
    safe_novel = safe_file_stem(safe_segment(novel, "novel"))
    return glossary_root / safe_novel / "glossary" / "glossary.json"


def load_glossary(novel: str | None = None) -> list[dict[str, str]]:
    path = glossary_path(novel) if novel else settings.GLOSSARY_PATH
    data = read_json(path, [])
    if not isinstance(data, list):
        raise AppError(f"{path.name} must contain a JSON array.", 500)
    return [normalize_glossary_entry(item) for item in data if isinstance(item, dict)]


def save_glossary(entries: list[dict[str, Any]], novel: str | None = None) -> list[dict[str, str]]:
    normalized = [entry for entry in (normalize_glossary_entry(item) for item in entries) if entry]
    write_json(glossary_path(novel) if novel else settings.GLOSSARY_PATH, normalized)
    return normalized


def normalize_glossary_entry(entry: dict[str, Any]) -> dict[str, str]:
    source_term = str(entry.get("source_term", "")).strip()
    english_term = str(entry.get("english_term", "")).strip()
    category = re.sub(r"\s+", "_", str(entry.get("category", "")).strip().lower())
    gender = str(entry.get("gender_or_pronoun", "")).strip().lower()

    if not source_term or not english_term:
        return {}
    if contains_source_language_text(english_term):
        return {}
    if gender not in settings.ALLOWED_GENDERS:
        gender = ""

    return {
        "source_term": source_term,
        "english_term": english_term,
        "category": category,
        "gender_or_pronoun": gender,
    }


def merge_glossary_entries(
    existing: list[dict[str, Any]], updates: list[dict[str, Any]]
) -> list[dict[str, str]]:
    merged = [entry for entry in (normalize_glossary_entry(item) for item in existing) if entry]
    by_source = {entry["source_term"]: entry for entry in merged}

    for raw_update in updates:
        if not isinstance(raw_update, dict):
            continue
        update = normalize_glossary_entry(raw_update)
        if not update:
            continue
        current = by_source.get(update["source_term"])
        if current is None:
            merged.append(update)
            by_source[update["source_term"]] = update
            continue
        for key, value in update.items():
            if key != "source_term" and not current.get(key) and value:
                current[key] = value

    return merged


def glossary_prompt(glossary: list[dict[str, Any]]) -> str:
    if not glossary:
        return "No established glossary entries yet."
    lines = []
    for entry in glossary:
        gender = entry.get("gender_or_pronoun", "")
        detail = f"{entry['source_term']} => {entry['english_term']}"
        if gender:
            detail += f" pronoun={gender}"
        lines.append(detail)
    return "\n".join(lines)
