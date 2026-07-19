import argparse
import json
import mimetypes
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from scraper import qidian_auth
from scraper.download_69shuba import download_range as download_69shuba_range
from scraper.download_qidian import download_range as download_qidian_range
from scraper.download_twkan import download_range as download_twkan_range
from scraper.download_uukanshu import download_range as download_uukanshu_range

from . import settings
from .bulk_translate import abort_bulk_translation, get_bulk_state, start_bulk_translation
from .chapters import (
    cover_path,
    delete_novel,
    library_metadata,
    list_chapters,
    list_novels,
    novel_metadata,
    read_chapter,
    rebuild_chapter_manifest,
)
from .config import load_config, mask_key, public_config, save_config
from .codex_backend import (
    close_codex,
    codex_auth_state,
    codex_models,
    codex_remaining_usage,
    logout_codex,
    start_codex_login,
)
from .openrouter import openrouter_model_providers
from .errors import AppError
from .epub import build_translated_epub
from .glossary import load_glossary, save_glossary
from .translation import populate_glossary_for_chapter, translate_chapter
from .usage import current_usage, reset_usage


scrape_lock = threading.Lock()
scrape_state: dict[str, Any] = {
    "running": False,
    "stage": "idle",
    "current": 0,
    "total": 0,
    "message": "",
    "novel": "",
    "result": None,
    "error": "",
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.route("GET")

    def do_POST(self) -> None:
        self.route("POST")

    def do_DELETE(self) -> None:
        self.route("DELETE")

    def log_message(self, format: str, *args: Any) -> None:
        return

    def route(self, method: str) -> None:
        parsed = urllib.parse.urlparse(self.path)
        try:
            if method == "GET" and not parsed.path.startswith("/api/"):
                self.serve_frontend(parsed.path)
                return
            if parsed.path == "/api/config":
                self.handle_config(method)
                return
            if parsed.path == "/api/usage":
                self.handle_usage(method)
                return
            if parsed.path == "/api/codex/auth":
                if method != "GET":
                    raise AppError("Method not allowed.", 405)
                self.json(codex_auth_state())
                return
            if parsed.path == "/api/codex/auth/login":
                if method != "POST":
                    raise AppError("Method not allowed.", 405)
                self.json(start_codex_login())
                return
            if parsed.path == "/api/codex/auth/logout":
                if method != "POST":
                    raise AppError("Method not allowed.", 405)
                self.json(logout_codex())
                return
            if method == "GET" and parsed.path == "/api/codex/models":
                query = urllib.parse.parse_qs(parsed.query)
                self.json(codex_models(first(query, "refresh").lower() == "true"))
                return
            if method == "GET" and parsed.path == "/api/codex/usage":
                query = urllib.parse.parse_qs(parsed.query)
                self.json(codex_remaining_usage(first(query, "refresh").lower() == "true"))
                return
            if method == "GET" and parsed.path == "/api/openrouter/providers":
                query = urllib.parse.parse_qs(parsed.query)
                config = load_config()
                self.json(openrouter_model_providers(first(query, "model"), config["openrouter_api_key"]))
                return
            if method == "GET" and parsed.path == "/api/novels":
                self.json(list_novels())
                return
            if method == "GET" and parsed.path == "/api/novels/metadata":
                self.json(library_metadata())
                return
            if parsed.path == "/api/novel":
                query = urllib.parse.parse_qs(parsed.query)
                if method == "GET":
                    self.json(novel_metadata(first(query, "novel")))
                    return
                if method == "DELETE":
                    self.json(delete_novel(first(query, "novel")))
                    return
                raise AppError("Method not allowed.", 405)
            if method == "GET" and parsed.path == "/api/cover":
                query = urllib.parse.parse_qs(parsed.query)
                path = cover_path(first(query, "novel"))
                if path is None:
                    raise AppError("Cover not found.", 404)
                self.static_file(path)
                return
            if method == "GET" and parsed.path == "/api/export/epub":
                query = urllib.parse.parse_qs(parsed.query)
                raw, filename = build_translated_epub(first(query, "novel"))
                self.download(
                    raw,
                    filename,
                    "application/epub+zip",
                )
                return
            if method == "GET" and parsed.path == "/api/chapters":
                query = urllib.parse.parse_qs(parsed.query)
                self.json(list_chapters(first(query, "novel")))
                return
            if parsed.path == "/api/scrape":
                self.handle_scrape(method)
                return
            if parsed.path == "/api/qidian-auth":
                self.handle_qidian_auth(method)
                return
            if method == "GET" and parsed.path == "/api/chapter":
                query = urllib.parse.parse_qs(parsed.query)
                self.json(read_chapter(first(query, "novel"), first(query, "file")))
                return
            if parsed.path == "/api/glossary":
                query = urllib.parse.parse_qs(parsed.query)
                self.handle_glossary(method, first(query, "novel") if method == "GET" else "")
                return
            if method == "POST" and parsed.path == "/api/populate-glossary":
                data = self.body_json()
                self.json(
                    populate_glossary_for_chapter(
                        str(data.get("novel", "")), str(data.get("file", ""))
                    )
                )
                return
            if method == "POST" and parsed.path == "/api/translate":
                data = self.body_json()
                self.json(translate_chapter(str(data.get("novel", "")), str(data.get("file", ""))))
                return
            if method == "POST" and parsed.path == "/api/translate-only":
                data = self.body_json()
                self.json(
                    translate_chapter(
                        str(data.get("novel", "")),
                        str(data.get("file", "")),
                        populate_glossary=False,
                    )
                )
                return
            if parsed.path == "/api/bulk-translate":
                query = urllib.parse.parse_qs(parsed.query)
                self.handle_bulk_translate(
                    method,
                    first(query, "novel") if method == "GET" else "",
                )
                return
            if method == "POST" and parsed.path == "/api/bulk-translate/abort":
                data = self.body_json()
                self.json(abort_bulk_translation(str(data.get("novel", ""))))
                return
            raise AppError("Not found.", 404)
        except AppError as exc:
            self.json({"error": str(exc)}, exc.status)
        except Exception as exc:
            self.json({"error": f"Unexpected error: {exc}"}, 500)

    def handle_config(self, method: str) -> None:
        if method == "GET":
            self.json(public_config())
            return
        if method != "POST":
            raise AppError("Method not allowed.", 405)
        data = self.body_json()
        if data.get("keep_existing_key"):
            current = load_config()
            data["openrouter_api_key"] = current["openrouter_api_key"]
        if data.get("keep_existing_openrouter_key"):
            data["openrouter_api_key"] = load_config()["openrouter_api_key"]
        saved = save_config(data)
        self.json(
            {
                "has_openrouter_api_key": bool(saved["openrouter_api_key"]),
                "openrouter_api_key_mask": mask_key(saved["openrouter_api_key"]),
                "translation_backend": saved["translation_backend"],
                "glossary_backend": saved["glossary_backend"],
                "translation_reasoning_effort": saved["translation_reasoning_effort"],
                "glossary_reasoning_effort": saved["glossary_reasoning_effort"],
                "codex_translation_model": saved["codex_translation_model"],
                "codex_glossary_model": saved["codex_glossary_model"],
                "translation_model": saved["translation_model"],
                "translation_provider": saved["translation_provider"],
                "glossary_model": saved["glossary_model"],
                "glossary_provider": saved["glossary_provider"],
                "added_models": saved["added_models"],
                "model_presets": settings.DEFAULT_MODEL_PRESETS,
            }
        )

    def handle_glossary(self, method: str, novel: str) -> None:
        if method == "GET":
            self.json(load_glossary(novel))
            return
        if method != "POST":
            raise AppError("Method not allowed.", 405)
        data = self.body_json()
        if not novel:
            novel = str(data.get("novel", ""))
        entries = data.get("entries", [])
        if not isinstance(entries, list):
            raise AppError("entries must be a list.")
        self.json(save_glossary(entries, novel))

    def handle_usage(self, method: str) -> None:
        if method == "GET":
            self.json(current_usage())
            return
        if method == "POST":
            self.json(reset_usage())
            return
        raise AppError("Method not allowed.", 405)

    def handle_bulk_translate(self, method: str, novel: str) -> None:
        if method == "GET":
            self.json(get_bulk_state(novel))
            return
        if method != "POST":
            raise AppError("Method not allowed.", 405)
        data = self.body_json()
        if not novel:
            novel = str(data.get("novel", ""))
        items = data.get("items", [])
        if not isinstance(items, list):
            raise AppError("items must be a list.")
        self.json(start_bulk_translation(novel, items))

    def handle_qidian_auth(self, method: str) -> None:
        if method == "GET":
            self.json(qidian_auth.get_state())
            return
        if method != "POST":
            raise AppError("Method not allowed.", 405)
        data = self.body_json()
        action = str(data.get("action", ""))
        if action == "set_cookies":
            cookie_str = str(data.get("cookies", "")).strip()
            if not cookie_str:
                raise AppError("cookies string is required.")
            try:
                self.json(qidian_auth.set_cookies_from_string(cookie_str))
            except ValueError as exc:
                raise AppError(str(exc)) from exc
        elif action == "logout":
            self.json(qidian_auth.clear_login())
        else:
            raise AppError("action must be 'set_cookies' or 'logout'.")

    def handle_scrape(self, method: str) -> None:
        if method == "GET":
            with scrape_lock:
                self.json(dict(scrape_state))
            return
        if method != "POST":
            raise AppError("Method not allowed.", 405)

        data = self.body_json()
        url = str(data.get("url", "")).strip()
        try:
            start = int(data.get("start", 0))
            end = int(data.get("end", 0))
        except (TypeError, ValueError) as exc:
            raise AppError("start and end must be chapter numbers.") from exc
        if not url:
            raise AppError("url is required.")
        if start < 1 or end < start:
            raise AppError("Invalid chapter range: start must be >= 1 and end must be >= start.")

        host = urllib.parse.urlparse(url).netloc.lower()
        if host in {"69shuba.com", "www.69shuba.com"}:
            downloader = download_69shuba_range
        elif host in {"uukanshu.cc", "www.uukanshu.cc"}:
            downloader = download_uukanshu_range
        elif host in {"twkan.com", "www.twkan.com"}:
            downloader = download_twkan_range
        elif host in {"qidian.com", "www.qidian.com"}:
            downloader = download_qidian_range
        else:
            raise AppError("Supported scraper URLs are 69shuba.com, uukanshu.cc, twkan.com, and qidian.com.")

        with scrape_lock:
            if scrape_state["running"]:
                raise AppError("A scrape is already running.", 409)
            scrape_state.update(
                {
                    "running": True,
                    "stage": "queued",
                    "current": 0,
                    "total": max(0, end - start + 1),
                    "message": "Starting scrape...",
                    "novel": "",
                    "result": None,
                    "error": "",
                }
            )

        def update_progress(progress: dict[str, object]) -> None:
            with scrape_lock:
                scrape_state.update(progress)
                scrape_state["running"] = True
                scrape_state["error"] = ""

        def worker() -> None:
            try:
                result = downloader(url, start, end, settings.OUTPUT_ROOT, update_progress)
                rebuild_chapter_manifest(result["novel"])
                with scrape_lock:
                    scrape_state.update(
                        {
                            "running": False,
                            "stage": "done",
                            "current": result["chapter_count"],
                            "total": result["chapter_count"],
                            "message": f"Downloaded {result['chapter_count']} chapters for {result['novel']}.",
                            "novel": result["novel"],
                            "result": result,
                            "error": "",
                        }
                    )
            except Exception as exc:
                with scrape_lock:
                    scrape_state.update(
                        {
                            "running": False,
                            "stage": "failed",
                            "message": f"Scrape failed: {exc}",
                            "result": None,
                            "error": str(exc),
                        }
                    )

        threading.Thread(target=worker, daemon=True).start()
        with scrape_lock:
            self.json(dict(scrape_state))

    def body_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AppError("Request body must be valid JSON.") from exc
        if not isinstance(data, dict):
            raise AppError("Request body must be a JSON object.")
        return data

    def json(self, data: Any, status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.no_cache_headers()
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def serve_frontend(self, path: str) -> None:
        if not settings.FRONTEND_DIST.exists():
            raise AppError("Frontend build not found. Run npm run build in frontend.", 500)
        relative = path.lstrip("/") or "index.html"
        target = settings.FRONTEND_DIST / relative
        if not target.exists() or not target.is_file():
            target = settings.FRONTEND_DIST / "index.html"
        if not target.resolve().is_relative_to(settings.FRONTEND_DIST.resolve()):
            raise AppError("Not found.", 404)
        self.static_file(target)

    def static_file(self, path: Path) -> None:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        raw = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.no_cache_headers()
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def download(self, raw: bytes, filename: str, content_type: str) -> None:
        encoded = urllib.parse.quote(filename)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header(
            "Content-Disposition",
            f"attachment; filename*=UTF-8''{encoded}",
        )
        self.no_cache_headers()
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def no_cache_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")


def first(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key)
    return values[0] if values else ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local novel translator app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run_server(args.host, args.port)


def run_server(host: str, port: int) -> None:
    settings.TRANSLATED_ROOT.mkdir(exist_ok=True)
    instance_lock = acquire_server_lock(port)
    server = None
    try:
        server = ThreadingHTTPServer((host, port), Handler)
        print(f"Novel Translator running at http://{host}:{port}")
        server.serve_forever()
    finally:
        if server is not None:
            server.server_close()
        close_codex()
        release_server_lock(instance_lock)


def acquire_server_lock(port: int):
    path = settings.DATA_ROOT / f".server-{port}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    if path.stat().st_size == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise OSError(f"Another Novel Translator instance is already using port {port}.") from None
    return handle


def release_server_lock(handle) -> None:
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()
