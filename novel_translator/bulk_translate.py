from __future__ import annotations

from threading import Event, Lock, Thread, current_thread
from typing import Any

from . import settings
from .chapters import source_path
from .config import load_config, safe_file_stem
from .errors import AppError
from .glossary import glossary_path, load_glossary, merge_glossary_entries
from .glossary_strategy import (
    ROLLING_GLOSSARY_REFRESH_INTERVAL,
    finish_rolling_glossary_chapter,
    normalize_rolling_glossary_state,
    prepare_rolling_glossary_prompt,
)
from .json_store import read_json, write_json
from .novel_names import ensure_translated_novel_name, needs_translated_novel_name
from .translation import translate_chapter

ALLOWED_BULK_STATUSES = {"pending", "translating", "done", "failed", "aborted"}
ALLOWED_BULK_MODES = {"full", "only", "name"}
NOVEL_NAME_TRANSLATION_FILENAME = "__novel_name__"
BULK_TRANSLATION_ABORTED_MESSAGE = "Bulk translation aborted."

_bulk_lock = Lock()
_bulk_workers: dict[str, Thread] = {}
_bulk_abort_events: dict[str, Event] = {}


def bulk_state_path(novel: str):
    return settings.DATA_ROOT / "bulk" / f"{safe_file_stem(novel)}.json"


def empty_bulk_state(novel: str) -> dict[str, Any]:
    return {"novel": novel, "running": False, "aborted": False, "items": []}


def public_bulk_state(state: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in state.items() if key != "rolling_glossary"}


def flush_pending_glossary_updates(
    novel: str, pending_updates: list[dict[str, Any]]
) -> None:
    if not pending_updates:
        return
    merged = merge_glossary_entries(load_glossary(novel), pending_updates)
    write_json(glossary_path(novel), merged)
    pending_updates.clear()


def normalize_bulk_item(item: dict[str, Any]) -> dict[str, str]:
    filename = str(item.get("filename", "")).strip()
    if not filename:
        raise AppError("Bulk translation items require filename.")
    title = str(item.get("title", "")).strip() or filename
    status = str(item.get("status", "pending")).strip() or "pending"
    if status not in ALLOWED_BULK_STATUSES:
        raise AppError("Invalid bulk translation status.", 500)
    message = str(item.get("message", "")).strip()
    mode = str(item.get("mode", "full")).strip() or "full"
    if mode not in ALLOWED_BULK_MODES:
        raise AppError("Invalid bulk translation mode.", 500)
    normalized = {"filename": filename, "title": title, "status": status, "mode": mode}
    if message:
        normalized["message"] = message
    return normalized


def load_bulk_state(novel: str) -> dict[str, Any]:
    safe_novel = novel.strip()
    if not safe_novel:
        return empty_bulk_state("")
    raw = read_json(bulk_state_path(safe_novel), empty_bulk_state(safe_novel))
    if not isinstance(raw, dict):
        raise AppError("Bulk translation state must be a JSON object.", 500)
    items = raw.get("items", [])
    if not isinstance(items, list):
        raise AppError("Bulk translation items must be a list.", 500)
    running = bool(raw.get("running", False))
    aborted = bool(raw.get("aborted", False))
    state = {
        "novel": safe_novel,
        "running": running,
        "aborted": aborted,
        "items": [normalize_bulk_item(item) for item in items if isinstance(item, dict)],
    }
    rolling_glossary = normalize_rolling_glossary_state(raw.get("rolling_glossary"))
    if rolling_glossary is not None:
        state["rolling_glossary"] = rolling_glossary
    return state


def save_bulk_state(novel: str, state: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "novel": novel,
        "running": bool(state.get("running", False)),
        "aborted": bool(state.get("aborted", False)),
        "items": [
            normalize_bulk_item(item)
            for item in state.get("items", [])
            if isinstance(item, dict)
        ],
    }
    rolling_glossary = normalize_rolling_glossary_state(state.get("rolling_glossary"))
    if rolling_glossary is not None:
        normalized["rolling_glossary"] = rolling_glossary
    write_json(bulk_state_path(novel), normalized)
    return normalized


def get_bulk_state(novel: str) -> dict[str, Any]:
    with _bulk_lock:
        state = load_bulk_state(novel)
        if _should_resume(state, novel):
            state = _prepare_state_for_resume(state)
            save_bulk_state(novel, state)
            _start_worker(novel)
            state["running"] = True
            save_bulk_state(novel, state)
        return state


def enqueue_novel_name_translation(novel: str) -> dict[str, Any]:
    safe_novel = novel.strip()
    if not safe_novel:
        return empty_bulk_state("")
    with _bulk_lock:
        state = load_bulk_state(safe_novel)
        if not needs_translated_novel_name(safe_novel):
            return state
        existing = next(
            (
                item
                for item in state["items"]
                if item["mode"] == "name"
                and item["filename"] == NOVEL_NAME_TRANSLATION_FILENAME
                and item["status"] in {"pending", "translating", "done"}
            ),
            None,
        )
        if existing:
            if _should_resume(state, safe_novel):
                state = _prepare_state_for_resume(state)
                save_bulk_state(safe_novel, state)
                _start_worker(safe_novel)
                state["running"] = True
                save_bulk_state(safe_novel, state)
            return state

        state["items"] = [
            {
                "filename": NOVEL_NAME_TRANSLATION_FILENAME,
                "title": "Novel title",
                "status": "pending",
                "mode": "name",
                "message": "Queued for title translation",
            },
            *state["items"],
        ]
        state["running"] = True
        save_bulk_state(safe_novel, state)
        if not _is_worker_alive(safe_novel):
            _start_worker(safe_novel)
        return state


def start_bulk_translation(novel: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    safe_novel = novel.strip()
    if not safe_novel:
        raise AppError("Novel is required.")
    normalized_items = [normalize_bulk_item(item) for item in items if isinstance(item, dict)]
    if not normalized_items:
        raise AppError("Select at least one chapter for bulk translation.")
    with _bulk_lock:
        if _is_worker_alive(safe_novel):
            raise AppError("Bulk translation is already running.", 409)
        state = save_bulk_state(
            safe_novel,
            {"novel": safe_novel, "running": True, "items": normalized_items},
        )
        _start_worker(safe_novel)
        return state


def abort_bulk_translation(novel: str) -> dict[str, Any]:
    safe_novel = novel.strip()
    if not safe_novel:
        return empty_bulk_state("")
    with _bulk_lock:
        abort_event = _bulk_abort_events.get(safe_novel)
        if abort_event is not None:
            abort_event.set()
        state = load_bulk_state(safe_novel)
        state["running"] = False
        state["aborted"] = True
        save_bulk_state(safe_novel, state)
        return state


def is_bulk_translation_aborted(novel: str) -> bool:
    safe_novel = novel.strip()
    if not safe_novel:
        return False
    with _bulk_lock:
        return bool(load_bulk_state(safe_novel).get("aborted", False))


def _prepare_state_for_resume(state: dict[str, Any]) -> dict[str, Any]:
    return {
        **state,
        "running": True,
        "items": [
            {
                **item,
                "status": "pending" if item["status"] == "translating" else item["status"],
                "message": "Queued" if item["status"] == "translating" else item.get("message", ""),
            }
            for item in state["items"]
        ],
    }


def _should_resume(state: dict[str, Any], novel: str) -> bool:
    if state.get("aborted", False):
        return False
    if _is_worker_alive(novel):
        return False
    return any(item["status"] in {"pending", "translating"} for item in state["items"])


def _is_worker_alive(novel: str) -> bool:
    worker = _bulk_workers.get(novel)
    abort_event = _bulk_abort_events.get(novel)
    return bool(worker and worker.is_alive() and abort_event and not abort_event.is_set())


def _start_worker(novel: str) -> None:
    abort_event = Event()
    worker = Thread(
        target=_process_bulk_translation_queue,
        args=(novel, abort_event),
        daemon=True,
    )
    _bulk_workers[novel] = worker
    _bulk_abort_events[novel] = abort_event
    worker.start()


def _process_bulk_translation_queue(novel: str, abort_event: Event) -> None:
    pending_existing_glossary_updates: list[dict[str, Any]] = []
    try:
        while True:
            with _bulk_lock:
                state = load_bulk_state(novel)
                if abort_event.is_set() or state.get("aborted", False):
                    state["running"] = False
                    save_bulk_state(novel, state)
                    return
                current = next(
                    (item for item in state["items"] if item["status"] == "pending"),
                    None,
                )
                if current is None:
                    break
                for item in state["items"]:
                    if item["filename"] == current["filename"]:
                        item["status"] = "translating"
                        if current["mode"] == "name":
                            item["message"] = "Translating novel title..."
                        elif current["mode"] == "full":
                            item["message"] = "Populating glossary and translating..."
                        else:
                            item["message"] = "Translating with current glossary..."
                        break
                save_bulk_state(novel, state)

            try:
                rolling_state = None
                rolling_prompt = None
                glossary_before: list[dict[str, Any]] = []
                chapter_text = ""
                if (
                    current["mode"] == "full"
                    and load_config().get("glossary_strategy", "full") == "rolling"
                ):
                    saved_rolling_state = normalize_rolling_glossary_state(
                        state.get("rolling_glossary")
                    )
                    if (
                        saved_rolling_state is not None
                        and saved_rolling_state["processed"]
                        >= ROLLING_GLOSSARY_REFRESH_INTERVAL
                    ):
                        flush_pending_glossary_updates(
                            novel, pending_existing_glossary_updates
                        )
                    glossary_before = load_glossary(novel)
                    chapter_text = source_path(novel, current["filename"]).read_text(
                        encoding="utf-8"
                    )
                    rolling_state, rolling_prompt = prepare_rolling_glossary_prompt(
                        novel,
                        current["filename"],
                        chapter_text,
                        glossary_before,
                        state.get("rolling_glossary"),
                    )
                    with _bulk_lock:
                        prepared_state = load_bulk_state(novel)
                        prepared_state["rolling_glossary"] = rolling_state
                        save_bulk_state(novel, prepared_state)
                if current["mode"] == "name":
                    ensure_translated_novel_name(novel, should_abort=abort_event.is_set)
                    if needs_translated_novel_name(novel):
                        raise AppError("Translation backend did not return a translated title.")
                else:
                    prompt_kwargs = (
                        {"glossary_prompt_entries": rolling_prompt}
                        if rolling_prompt is not None
                        else {}
                    )
                    translate_chapter(
                        novel,
                        current["filename"],
                        populate_glossary=current["mode"] == "full",
                        should_abort=abort_event.is_set,
                        defer_existing_glossary_updates=current["mode"] == "full",
                        deferred_existing_glossary_updates=(
                            pending_existing_glossary_updates if current["mode"] == "full" else None
                        ),
                        **prompt_kwargs,
                    )
                    if rolling_state is not None:
                        rolling_state = finish_rolling_glossary_chapter(
                            rolling_state,
                            chapter_text,
                            glossary_before,
                            load_glossary(novel),
                        )
            except Exception as exc:
                with _bulk_lock:
                    if _bulk_abort_events.get(novel) is not abort_event:
                        return
                    state = load_bulk_state(novel)
                    for item in state["items"]:
                        if item["filename"] == current["filename"]:
                            if isinstance(exc, AppError) and str(exc) == BULK_TRANSLATION_ABORTED_MESSAGE:
                                item["status"] = "aborted"
                                item["message"] = "Aborted by user"
                            else:
                                item["status"] = "failed"
                                item["message"] = str(exc)
                            break
                    state["aborted"] = True
                    save_bulk_state(novel, state)
                return

            with _bulk_lock:
                if _bulk_abort_events.get(novel) is not abort_event:
                    return
                state = load_bulk_state(novel)
                if rolling_state is not None:
                    state["rolling_glossary"] = rolling_state
                elif current["mode"] == "full":
                    state.pop("rolling_glossary", None)
                for item in state["items"]:
                    if item["filename"] == current["filename"]:
                        item["status"] = "done"
                        item["message"] = "Saved"
                        break
                save_bulk_state(novel, state)
    finally:
        with _bulk_lock:
            flush_pending_glossary_updates(novel, pending_existing_glossary_updates)
            if _bulk_workers.get(novel) is current_thread():
                state = load_bulk_state(novel)
                state["running"] = False
                save_bulk_state(novel, state)
                _bulk_workers.pop(novel, None)
                _bulk_abort_events.pop(novel, None)
