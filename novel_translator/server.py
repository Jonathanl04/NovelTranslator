import argparse
import json
import mimetypes
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import settings
from .bulk_translate import get_bulk_state, start_bulk_translation
from .chapters import cover_path, list_chapters, list_novels, novel_metadata, read_chapter
from .config import load_config, mask_key, public_config, save_config
from .errors import AppError
from .epub import build_translated_epub
from .glossary import load_glossary, save_glossary
from .translation import populate_glossary_for_chapter, translate_chapter
from .usage import current_usage, reset_usage


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.route("GET")

    def do_POST(self) -> None:
        self.route("POST")

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
            if method == "GET" and parsed.path == "/api/novels":
                self.json(list_novels())
                return
            if method == "GET" and parsed.path == "/api/novel":
                query = urllib.parse.parse_qs(parsed.query)
                self.json(novel_metadata(first(query, "novel")))
                return
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
            data["api_key"] = current["api_key"]
        saved = save_config(data)
        self.json(
            {
                "has_api_key": bool(saved["api_key"]),
                "api_key_mask": mask_key(saved["api_key"]),
                "translation_model": saved["translation_model"],
                "glossary_model": saved["glossary_model"],
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
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Novel Translator running at http://{host}:{port}")
    server.serve_forever()
