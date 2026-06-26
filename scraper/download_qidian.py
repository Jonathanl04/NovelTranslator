from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from scraper.qidian_auth import UA, load_cookies

DATA_ROOT = Path(os.environ.get("NOVEL_TRANSLATOR_DATA_DIR", "data"))
OUTPUT_ROOT = Path(os.environ.get("NOVEL_TRANSLATOR_OUTPUT_ROOT", DATA_ROOT))

ProgressCallback = Callable[[dict[str, object]], None]


class ChapterAccessError(RuntimeError):
    """Raised when a chapter is locked or requires VIP/subscription access."""


def infer_book_id(url: str) -> str:
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    if netloc not in {"qidian.com", "www.qidian.com"}:
        raise ValueError("This scraper only supports qidian.com URLs.")
    match = re.search(r"/book/(\d+)/?", parsed.path)
    if not match:
        raise ValueError(f"Could not infer book id from URL: {url}")
    return match.group(1)


def safe_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name).strip(" .")


def clean_lines(text: str) -> list[str]:
    lines = []
    for raw in text.replace("\r", "").split("\n"):
        line = raw.replace("　", " ").strip()
        lines.append(line)
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _page_fetch(ctx, url: str, wait_selector: str | None = None, wait_ms: int = 2_000) -> str:
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=10_000)
            except Exception:
                pass
        page.wait_for_timeout(wait_ms)
        return page.content()
    finally:
        page.close()


def _fetch_catalog(ctx, book_id: str) -> list[tuple[str, str, bool]]:
    """Returns list of (chapter_id, title, is_locked) in catalog order."""
    page = ctx.new_page()
    try:
        page.goto(f"https://www.qidian.com/book/{book_id}/", wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(2_000)

        csrf_token = ""
        for cookie in ctx.cookies():
            if cookie["name"] == "_csrfToken":
                csrf_token = cookie["value"]
                break

        chapters: list[tuple[str, str, bool]] = []

        if csrf_token:
            result = page.evaluate(
                f"""async () => {{
                    try {{
                        const r = await fetch(
                            '/ajax/book/category?_csrfToken={csrf_token}&bookId={book_id}',
                            {{ headers: {{ 'X-Requested-With': 'XMLHttpRequest' }}, credentials: 'include' }}
                        );
                        return await r.text();
                    }} catch (e) {{ return ''; }}
                }}"""
            )
            try:
                data = json.loads(result)
                if data.get("code") == 0:
                    for vol in data.get("data", {}).get("vs", []):
                        for ch in vol.get("cs", []):
                            chapter_id = str(ch.get("id", ""))
                            title = ch.get("cN", "") or ch.get("name", "")
                            if chapter_id and title:
                                # cv=1 means VIP chapter; isAuth=1 means user has access
                                is_vip = bool(ch.get("cv", 0))
                                is_auth = bool(ch.get("isAuth", 0) or ch.get("isAudition", 0))
                                is_locked = is_vip and not is_auth
                                chapters.append((chapter_id, title, is_locked))
            except Exception:
                pass

        if not chapters:
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            seen: set[str] = set()
            for anchor in soup.select(f"a[href*='/chapter/{book_id}/']"):
                href = str(anchor.get("href", ""))
                m = re.search(rf"/chapter/{book_id}/(\d+)/?", href)
                if m:
                    cid = m.group(1)
                    if cid not in seen:
                        seen.add(cid)
                        # HTML fallback can't determine lock status
                        chapters.append((cid, anchor.get_text(strip=True), False))

        return chapters
    finally:
        page.close()


def extract_book_info(html: str) -> tuple[str, str | None]:
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = str(og_title["content"]).strip()
    if not title:
        for sel in [".book-info h1 em", ".book-info h1", "h1.title", "h1"]:
            node = soup.select_one(sel)
            if node:
                title = node.get_text(" ", strip=True)
                break
    if not title:
        raise RuntimeError("Could not determine book name from index page.")

    cover_url: str | None = None
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        src = str(og_image["content"])
        cover_url = src if src.startswith("http") else f"https:{src}"
    if not cover_url:
        for sel in [".book-img-box img", ".book-img img", ".bookimg img"]:
            img = soup.select_one(sel)
            if img:
                src = str(img.get("src", "") or img.get("data-src", ""))
                if src:
                    cover_url = src if src.startswith("http") else f"https:{src}"
                    break

    return title, cover_url


def _assert_chapter_accessible(soup: BeautifulSoup, fallback_title: str) -> None:
    """Raise ChapterAccessError if the page shows a VIP/lock gate."""
    # Explicit lock/auth gate elements Qidian renders for inaccessible chapters
    lock_selectors = [
        ".chapter-authenticate",
        ".chapter-authenticate-tips",
        ".chapter-lock",
        ".lock-tips",
        ".j_locked",
        ".nologin-tips",
        ".no-auth-tips",
    ]
    for sel in lock_selectors:
        if soup.select_one(sel):
            raise ChapterAccessError(
                f"Chapter '{fallback_title}' is locked – VIP or subscription required."
            )

    # Check embedded Next.js page data for VIP/auth flags
    next_data_tag = soup.find("script", id="__NEXT_DATA__")
    if next_data_tag and next_data_tag.string:
        try:
            data = json.loads(next_data_tag.string)
            chapter_info = (
                data.get("props", {}).get("pageProps", {}).get("chapterInfo", {})
            )
            if chapter_info.get("isVip") and not chapter_info.get("isAuth"):
                raise ChapterAccessError(
                    f"Chapter '{fallback_title}' requires VIP access."
                )
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass


def extract_chapter_text(html: str, fallback_title: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")

    _assert_chapter_accessible(soup, fallback_title)

    # The print div contains the canonical title and content
    print_div = soup.select_one(".chapter-wrapper .relative .print")

    title = fallback_title
    title_node = print_div.select_one("h1.title") if print_div else None
    if title_node:
        # Use only direct text nodes to exclude inline comment-count badges
        direct_text = "".join(title_node.find_all(string=True, recursive=False)).strip()
        title = direct_text or title_node.get_text(" ", strip=True)

    content_node = print_div.select_one("main.content") if print_div else None
    if content_node is None:
        raise RuntimeError(f"Could not find chapter content for: {fallback_title}")

    for tag in content_node.find_all(["script", "style", "aside"]):
        tag.decompose()

    lines = clean_lines(content_node.get_text("\n"))
    # Drop the title echo and bare numbers (inline paragraph-comment counts)
    lines = [line for line in lines if line != title and not re.fullmatch(r"\d+", line)]

    content = "\n".join(lines).strip()
    if not content:
        raise RuntimeError(f"Empty chapter page for {fallback_title}")
    return title, content


def download_cover(cover_url: str | None, output_dir: Path) -> None:
    if not cover_url:
        print("No cover image found.")
        return
    try:
        resp = requests.get(
            cover_url,
            headers={"User-Agent": UA, "Referer": "https://www.qidian.com/"},
            timeout=30,
        )
        resp.raise_for_status()
        suffix = Path(urlparse(cover_url).path).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            suffix = ".jpg"
        cover_path = output_dir / f"cover{suffix}"
        for existing in output_dir.glob("cover.*"):
            existing.unlink()
        cover_path.write_bytes(resp.content)
        print(f"Saved cover: {cover_path.name}")
    except Exception as exc:
        print(f"Could not download cover: {exc}")


def save_source_url(output_dir: Path, novel: str, source_url: str) -> None:
    metadata_path = output_dir.parent / "metadata.json"
    metadata: dict[str, object] = {}
    if metadata_path.exists():
        try:
            loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                metadata = loaded
        except json.JSONDecodeError:
            metadata = {}
    metadata["name"] = novel
    metadata["source_url"] = source_url
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def remove_existing_chapter_files(output_dir: Path, chapter_number: int) -> None:
    for existing in output_dir.glob(f"{chapter_number:03d}_*.txt"):
        existing.unlink()


def download_range(
    url: str,
    start: int,
    end: int,
    output_root: Path = OUTPUT_ROOT,
    progress: ProgressCallback | None = None,
) -> dict[str, object]:
    if start < 1 or end < start:
        raise ValueError("Invalid chapter range: start must be >= 1 and end must be >= start.")

    book_id = infer_book_id(url)
    cookies = load_cookies()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(user_agent=UA, locale="zh-CN")
        if cookies:
            ctx.add_cookies(cookies)

        try:
            if progress:
                progress({"stage": "fetching", "current": 0, "total": 0, "message": "Fetching book page..."})

            book_html = _page_fetch(ctx, url, wait_ms=2_000)
            book_name_raw, cover_url = extract_book_info(book_html)
            book_name = safe_name(book_name_raw)

            if progress:
                progress({"stage": "fetching", "current": 0, "total": 0, "message": "Fetching chapter list..."})

            all_chapters = _fetch_catalog(ctx, book_id)
            if not all_chapters:
                raise RuntimeError("No chapters found. The book catalog may not be accessible.")

            selected = [
                (i, cid, ctitle, locked)
                for i, (cid, ctitle, locked) in enumerate(all_chapters, 1)
                if start <= i <= end
            ]
            if not selected:
                raise RuntimeError(
                    f"No chapters in range {start}-{end}. Book has {len(all_chapters)} chapters total."
                )

            locked_chapters = [(i, ctitle) for i, _, ctitle, locked in selected if locked]
            if locked_chapters:
                names = ", ".join(f"#{i} {t}" for i, t in locked_chapters[:5])
                extra = f" (and {len(locked_chapters) - 5} more)" if len(locked_chapters) > 5 else ""
                raise ChapterAccessError(
                    f"{len(locked_chapters)} chapter(s) in the requested range require VIP access: {names}{extra}"
                )

            book_output_dir = output_root / book_name / "source"
            book_output_dir.mkdir(parents=True, exist_ok=True)
            save_source_url(book_output_dir, book_name, url)

            if progress:
                progress(
                    {
                        "stage": "downloading",
                        "current": 0,
                        "total": len(selected),
                        "message": f"Downloading {len(selected)} chapters...",
                        "novel": book_name,
                    }
                )

            download_cover(cover_url, book_output_dir)

            files: list[str] = []
            for idx, (chapter_number, chapter_id, fallback_title, _locked) in enumerate(selected, 1):
                chapter_url = f"https://www.qidian.com/chapter/{book_id}/{chapter_id}/"

                if progress:
                    progress(
                        {
                            "stage": "downloading",
                            "current": idx - 1,
                            "total": len(selected),
                            "message": f"Downloading chapter {chapter_number}: {fallback_title}",
                            "novel": book_name,
                        }
                    )

                page_html = _page_fetch(
                    ctx,
                    chapter_url,
                    wait_selector="#j-readContent, .j_readContent, .read-content",
                    wait_ms=2_000,
                )
                title, content = extract_chapter_text(page_html, fallback_title)
                file_name = f"{chapter_number:03d}_{safe_name(title)}.txt"
                remove_existing_chapter_files(book_output_dir, chapter_number)
                (book_output_dir / file_name).write_text(f"{title}\n\n{content}\n", encoding="utf-8")
                files.append(file_name)
                print(f"Saved {chapter_number}: {file_name}")

                if progress:
                    progress(
                        {
                            "stage": "downloading",
                            "current": idx,
                            "total": len(selected),
                            "message": f"Saved chapter {chapter_number}: {title}",
                            "novel": book_name,
                        }
                    )

        finally:
            browser.close()

    return {
        "novel": book_name,
        "source_url": url,
        "output_dir": str(book_output_dir),
        "chapter_count": len(files),
        "files": files,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a chapter range from a 起点中文网 novel.")
    parser.add_argument("url", help="Qidian book URL, e.g. https://www.qidian.com/book/1034669943/")
    parser.add_argument("start", type=int, help="First chapter number to download, inclusive.")
    parser.add_argument("end", type=int, help="Last chapter number to download, inclusive.")
    return parser.parse_args()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    download_range(args.url, args.start, args.end)


if __name__ == "__main__":
    main()
