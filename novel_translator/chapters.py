import shutil
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


def delete_novel(
    novel: str,
    output_root: Path | None = None,
    translated_root: Path | None = None,
    glossary_root: Path | None = None,
) -> dict[str, str]:
    output_root = output_root or settings.OUTPUT_ROOT
    translated_root = translated_root or settings.TRANSLATED_ROOT
    glossary_root = glossary_root or settings.GLOSSARY_ROOT
    safe_novel = safe_segment(novel, "novel")
    from .config import safe_file_stem

    safe_stem = safe_file_stem(safe_novel)
    source_root = output_root / safe_novel
    if not (source_root / "source").is_dir():
        raise AppError("Novel not found.", 404)

    targets = [
        source_root,
        translated_root / safe_novel,
        glossary_root / safe_stem,
    ]
    for target in unique_paths(targets):
        remove_tree(target)

    try:
        from .bulk_translate import bulk_state_path
        remove_file(settings.DATA_ROOT / "bulk" / f"{safe_stem}.json")
        remove_file(bulk_state_path(safe_novel))
    except AppError:
        raise
    except Exception:
        pass
    return {"deleted": safe_novel}


def unique_paths(paths: list[Path]) -> list[Path]:
    seen = set()
    unique = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def remove_tree(path: Path) -> None:
    if not path.exists():
        return
    ensure_safe_delete_path(path)
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def remove_file(path: Path) -> None:
    if not path.exists():
        return
    ensure_safe_delete_path(path)
    if path.is_file():
        path.unlink()


def ensure_safe_delete_path(path: Path) -> None:
    resolved = path.resolve()
    allowed_roots = [
        settings.OUTPUT_ROOT.resolve(),
        settings.TRANSLATED_ROOT.resolve(),
        settings.GLOSSARY_ROOT.resolve(),
        (settings.DATA_ROOT / "bulk").resolve(),
    ]
    if not any(resolved == root or resolved.is_relative_to(root) for root in allowed_roots):
        raise AppError("Refusing to delete outside app data roots.", 500)


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


def _latest_mtime(*paths: Path) -> float:
    latest = 0.0
    for path in paths:
        if not path.exists():
            continue
        try:
            latest = max(latest, path.stat().st_mtime)
            if path.is_dir():
                for child in path.iterdir():
                    latest = max(latest, child.stat().st_mtime)
        except OSError:
            continue
    return latest


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
    updated_at = _latest_mtime(
        output_root / safe_novel / "source",
        settings.TRANSLATED_ROOT / safe_novel / "translated",
    )
    return {
        "name": safe_novel,
        "translated_name": translated_name,
        "cover_url": f"/api/cover?novel={quote(safe_novel)}" if path else None,
        "source_url": source_url or None,
        "updated_at": updated_at,
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
    for path in sorted(novel_dir.glob("*.txt"), key=_chapter_sort_key):
        target = translated_path(novel, path.name, translated_root)
        translated_exists = target.exists()
        chapters.append(
            {
                "filename": path.name,
                "title": chapter_label(path.name, target),
                "translated": translated_exists,
                "source_size": path.stat().st_size,
                "translated_size": target.stat().st_size if translated_exists else 0,
            }
        )
    return chapters


def _chapter_sort_key(path: Path) -> tuple[int, int | str, str]:
    stem = path.stem
    prefix = stem.split("_", 1)[0]
    if prefix.isdigit():
        return (0, int(prefix), path.name)
    return (1, stem, path.name)


def chapter_label(filename: str, translated_file: Path | None = None) -> str:
    prefix = Path(filename).stem.split("_", 1)[0]
    if translated_file and translated_file.exists():
        try:
            with translated_file.open(encoding="utf-8") as file:
                title = file.readline().strip()
            if title and not contains_source_language_text(title):
                return f"{prefix} {title}" if prefix and not title.startswith(prefix) else title
        except OSError:
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
