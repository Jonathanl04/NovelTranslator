from __future__ import annotations

from threading import Lock, Thread
from typing import Any

from . import settings
from .config import safe_file_stem
from .errors import AppError
from .json_store import read_json, write_json
from .translation import translate_chapter

ALLOWED_BULK_STATUSES = {"pending", "translating", "done", "failed"}
ALLOWED_BULK_MODES = {"full", "only"}

_bulk_lock = Lock()
_bulk_workers: dict[str, Thread] = {}


def bulk_state_path(novel: str):
    return settings.DATA_ROOT / "bulk" / f"{safe_file_stem(novel)}.json"


def empty_bulk_state(novel: str) -> dict[str, Any]:
    return {"novel": novel, "running": False, "items": []}


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
    return {
        "novel": safe_novel,
        "running": running,
        "items": [normalize_bulk_item(item) for item in items if isinstance(item, dict)],
    }


def save_bulk_state(novel: str, state: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "novel": novel,
        "running": bool(state.get("running", False)),
        "items": [
            normalize_bulk_item(item)
            for item in state.get("items", [])
            if isinstance(item, dict)
        ],
    }
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
    if _is_worker_alive(novel):
        return False
    return any(item["status"] in {"pending", "translating"} for item in state["items"])


def _is_worker_alive(novel: str) -> bool:
    worker = _bulk_workers.get(novel)
    return bool(worker and worker.is_alive())


def _start_worker(novel: str) -> None:
    worker = Thread(target=_process_bulk_translation_queue, args=(novel,), daemon=True)
    _bulk_workers[novel] = worker
    worker.start()


def _process_bulk_translation_queue(novel: str) -> None:
    try:
        while True:
            with _bulk_lock:
                state = load_bulk_state(novel)
                current = next(
                    (item for item in state["items"] if item["status"] == "pending"),
                    None,
                )
                if current is None:
                    state["running"] = False
                    save_bulk_state(novel, state)
                    return
                for item in state["items"]:
                    if item["filename"] == current["filename"]:
                        item["status"] = "translating"
                        item["message"] = (
                            "Populating glossary and translating..."
                            if current["mode"] == "full"
                            else "Translating with current glossary..."
                        )
                        break
                save_bulk_state(novel, state)

            try:
                translate_chapter(
                    novel,
                    current["filename"],
                    populate_glossary=current["mode"] == "full",
                )
            except Exception as exc:
                with _bulk_lock:
                    state = load_bulk_state(novel)
                    for item in state["items"]:
                        if item["filename"] == current["filename"]:
                            item["status"] = "failed"
                            item["message"] = str(exc)
                            break
                    state["running"] = False
                    save_bulk_state(novel, state)
                return

            with _bulk_lock:
                state = load_bulk_state(novel)
                for item in state["items"]:
                    if item["filename"] == current["filename"]:
                        item["status"] = "done"
                        item["message"] = "Saved"
                        break
                save_bulk_state(novel, state)
    finally:
        with _bulk_lock:
            worker = _bulk_workers.get(novel)
            if worker is not None and worker is _bulk_workers.get(novel):
                _bulk_workers.pop(novel, None)
