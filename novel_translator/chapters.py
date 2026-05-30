from pathlib import Path
from typing import Any
from urllib.parse import quote

from . import settings
from .errors import AppError
from .json_store import read_json
from .source_language import contains_source_language_text


def safe_segment(value: str, label: str) -> str:
    value = value.strip()
    if not value or "/" in value or "\\" in value or value in {".", ".."}:
        raise AppError(f"Invalid {label}.")
    return value


def list_novels(output_root: Path | None = None) -> list[str]:
    output_root = output_root or settings.OUTPUT_ROOT
    if not output_root.exists():
        return []
    novels = sorted(
        item.name
        for item in output_root.iterdir()
        if item.is_dir() and (item / "source").is_dir()
    )
    for novel in novels:
        try:
            from .bulk_translate import enqueue_novel_name_translation

            enqueue_novel_name_translation(novel)
        except AppError:
            pass
    return novels


def cover_path(novel: str, output_root: Path | None = None) -> Path | None:
    output_root = output_root or settings.OUTPUT_ROOT
    novel = safe_segment(novel, "novel")
    novel_dir = output_root / novel / "source"
    if not novel_dir.exists() or not novel_dir.is_dir():
        raise AppError("Novel not found.", 404)

    for pattern in ("cover.jpg", "cover.jpeg", "cover.png", "cover.webp", "cover.gif"):
        path = novel_dir / pattern
        if path.exists() and path.is_file():
            return path
    return None


def novel_metadata(novel: str, output_root: Path | None = None) -> dict[str, Any]:
    output_root = output_root or settings.OUTPUT_ROOT
    safe_novel = safe_segment(novel, "novel")
    try:
        from .bulk_translate import enqueue_novel_name_translation
        from .novel_names import load_novel_display_name

        enqueue_novel_name_translation(safe_novel)
        translated_name = load_novel_display_name(safe_novel, output_root)
    except AppError:
        from .novel_names import load_novel_display_name

        translated_name = load_novel_display_name(safe_novel, output_root)
    path = cover_path(safe_novel, output_root)
    metadata = read_json(output_root / safe_novel / "metadata.json", {})
    source_url = str(metadata.get("source_url", "")).strip() if isinstance(metadata, dict) else ""
    return {
        "name": safe_novel,
        "translated_name": translated_name,
        "cover_url": f"/api/cover?novel={quote(safe_novel)}" if path else None,
        "source_url": source_url or None,
    }


def source_path(novel: str, filename: str, output_root: Path | None = None) -> Path:
    output_root = output_root or settings.OUTPUT_ROOT
    novel = safe_segment(novel, "novel")
    filename = safe_segment(filename, "chapter")
    if not filename.lower().endswith(".txt"):
        raise AppError("Chapter must be a .txt file.")
    path = output_root / novel / "source" / filename
    if not path.exists() or not path.is_file():
        raise AppError("Chapter not found.", 404)
    return path


def translated_path(
    novel: str, filename: str, translated_root: Path | None = None
) -> Path:
    translated_root = translated_root or settings.TRANSLATED_ROOT
    novel = safe_segment(novel, "novel")
    filename = safe_segment(filename, "chapter")
    return translated_root / novel / "translated" / filename


def list_chapters(
    novel: str,
    output_root: Path | None = None,
    translated_root: Path | None = None,
) -> list[dict[str, Any]]:
    output_root = output_root or settings.OUTPUT_ROOT
    translated_root = translated_root or settings.TRANSLATED_ROOT
    novel = safe_segment(novel, "novel")
    novel_dir = output_root / novel / "source"
    if not novel_dir.exists() or not novel_dir.is_dir():
        raise AppError("Novel not found.", 404)

    chapters = []
    for path in sorted(novel_dir.glob("*.txt")):
        target = translated_path(novel, path.name, translated_root)
        chapters.append(
            {
                "filename": path.name,
                "title": chapter_label(path.name, target),
                "translated": target.exists(),
                "source_size": path.stat().st_size,
                "translated_size": target.stat().st_size if target.exists() else 0,
            }
        )
    return chapters


def chapter_label(filename: str, translated_file: Path | None = None) -> str:
    prefix = Path(filename).stem.split("_", 1)[0]
    if translated_file and translated_file.exists():
        try:
            title, _ = split_chapter(translated_file.read_text(encoding="utf-8"))
            if title and not contains_source_language_text(title):
                return f"{prefix} {title}" if prefix and not title.startswith(prefix) else title
        except AppError:
            pass
    return Path(filename).stem.replace("_", " ", 1)


def read_chapter(novel: str, filename: str) -> dict[str, Any]:
    source = source_path(novel, filename)
    target = translated_path(novel, filename)
    return {
        "filename": filename,
        "source": source.read_text(encoding="utf-8"),
        "translated": target.read_text(encoding="utf-8") if target.exists() else "",
        "translated_exists": target.exists(),
    }


def split_chapter(text: str) -> tuple[str, str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise AppError("Chapter is empty.")
    if "\n" not in normalized:
        return normalized, ""
    title, body = normalized.split("\n", 1)
    return title.strip(), body.strip()


def write_translation(novel: str, filename: str, title: str, body: str) -> Path:
    target = translated_path(novel, filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{title}\n\n{body}\n", encoding="utf-8")
    return target
