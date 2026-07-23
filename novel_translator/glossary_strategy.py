from __future__ import annotations

from typing import Any

from .chapters import list_chapters, source_path
from .glossary import normalize_glossary_entry


ROLLING_GLOSSARY_WINDOW = 100
ROLLING_GLOSSARY_REFRESH_INTERVAL = 50


def entries_in_chapter_order(
    entries: list[dict[str, Any]],
    chapter_text: str,
    excluded_sources: set[str] | None = None,
) -> list[dict[str, str]]:
    excluded_sources = excluded_sources or set()
    matches: list[tuple[int, int, str, dict[str, str]]] = []
    for raw_entry in entries:
        entry = normalize_glossary_entry(raw_entry)
        source_term = entry.get("source_term", "")
        if not source_term or source_term in excluded_sources:
            continue
        position = chapter_text.find(source_term)
        if position < 0:
            continue
        matches.append((position, -len(source_term), source_term, entry))
    matches.sort(key=lambda item: item[:3])
    return [entry for _, _, _, entry in matches]


def rolling_glossary_snapshot(
    novel: str,
    filename: str,
    glossary: list[dict[str, Any]],
    window: int = ROLLING_GLOSSARY_WINDOW,
) -> list[dict[str, str]]:
    chapters = list_chapters(novel)
    current_index = next(
        (index for index, chapter in enumerate(chapters) if chapter["filename"] == filename),
        None,
    )
    if current_index is None:
        return []
    prior_chapters = chapters[max(0, current_index - window) : current_index]
    lookback_text = "\n".join(
        source_path(novel, chapter["filename"]).read_text(encoding="utf-8")
        for chapter in prior_chapters
    )
    return [
        entry
        for raw_entry in glossary
        if (entry := normalize_glossary_entry(raw_entry))
        and entry["source_term"] in lookback_text
    ]


def new_rolling_glossary_state(
    novel: str, filename: str, glossary: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "epoch_start_filename": filename,
        "processed": 0,
        "snapshot": rolling_glossary_snapshot(novel, filename, glossary),
        "additions": [],
    }


def normalize_rolling_glossary_state(raw_state: Any) -> dict[str, Any] | None:
    if not isinstance(raw_state, dict):
        return None
    epoch_start_filename = str(raw_state.get("epoch_start_filename", "")).strip()
    if not epoch_start_filename:
        return None
    try:
        processed = max(0, int(raw_state.get("processed", 0)))
    except (TypeError, ValueError):
        processed = 0
    snapshot = _normalize_unique_entries(raw_state.get("snapshot", []))
    snapshot_sources = {entry["source_term"] for entry in snapshot}
    additions = _normalize_unique_entries(
        raw_state.get("additions", []), excluded_sources=snapshot_sources
    )
    return {
        "epoch_start_filename": epoch_start_filename,
        "processed": processed,
        "snapshot": snapshot,
        "additions": additions,
    }


def prepare_rolling_glossary_prompt(
    novel: str,
    filename: str,
    chapter_text: str,
    glossary: list[dict[str, Any]],
    raw_state: Any,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    state = normalize_rolling_glossary_state(raw_state)
    if state is None or state["processed"] >= ROLLING_GLOSSARY_REFRESH_INTERVAL:
        state = new_rolling_glossary_state(novel, filename, glossary)

    known_sources = {
        entry["source_term"] for entry in [*state["snapshot"], *state["additions"]]
    }
    reactivated = entries_in_chapter_order(glossary, chapter_text, known_sources)
    state["additions"].extend(reactivated)
    return state, [*state["snapshot"], *state["additions"]]


def finish_rolling_glossary_chapter(
    raw_state: Any,
    chapter_text: str,
    glossary_before: list[dict[str, Any]],
    glossary_after: list[dict[str, Any]],
) -> dict[str, Any] | None:
    state = normalize_rolling_glossary_state(raw_state)
    if state is None:
        return None
    before_sources = {
        entry["source_term"]
        for raw_entry in glossary_before
        if (entry := normalize_glossary_entry(raw_entry))
    }
    known_sources = {
        entry["source_term"] for entry in [*state["snapshot"], *state["additions"]]
    }
    newly_created = [
        entry
        for entry in entries_in_chapter_order(glossary_after, chapter_text, known_sources)
        if entry["source_term"] not in before_sources
    ]
    state["additions"].extend(newly_created)
    state["processed"] += 1
    return state


def recent_glossary_for_chapter(
    novel: str,
    filename: str,
    chapter_text: str,
    glossary: list[dict[str, Any]],
) -> list[dict[str, str]]:
    snapshot = rolling_glossary_snapshot(novel, filename, glossary)
    snapshot_sources = {entry["source_term"] for entry in snapshot}
    return [
        *snapshot,
        *entries_in_chapter_order(glossary, chapter_text, snapshot_sources),
    ]


def _normalize_unique_entries(
    raw_entries: Any, excluded_sources: set[str] | None = None
) -> list[dict[str, str]]:
    if not isinstance(raw_entries, list):
        return []
    seen = set(excluded_sources or set())
    entries = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue
        entry = normalize_glossary_entry(raw_entry)
        source_term = entry.get("source_term", "")
        if not source_term or source_term in seen:
            continue
        seen.add(source_term)
        entries.append(entry)
    return entries
