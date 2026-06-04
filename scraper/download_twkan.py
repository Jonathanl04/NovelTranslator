from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests as cf_requests

DATA_ROOT = Path(os.environ.get("NOVEL_TRANSLATOR_DATA_DIR", "data"))
OUTPUT_ROOT = Path(os.environ.get("NOVEL_TRANSLATOR_OUTPUT_ROOT", DATA_ROOT))
IMPERSONATE = "chrome124"
CHAPTER_DELAY = 3.0
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}
_CF_CHALLENGE_MARKERS = ("Just a moment...", "請稍候", "Performing security verification")

ProgressCallback = Callable[[dict[str, object]], None]


def _is_cloudflare_challenge(text: str) -> bool:
    return any(marker in text for marker in _CF_CHALLENGE_MARKERS)


def fetch_text(url: str, retries: int = 2) -> str:
    failure = "unknown error"
    for attempt in range(retries):
        if attempt > 0:
            time.sleep(3)
        try:
            response = cf_requests.get(url, impersonate=IMPERSONATE, timeout=30)
            if response.status_code < 400 and response.text.strip():
                if not _is_cloudflare_challenge(response.text):
                    return response.text
                failure = "Cloudflare challenge"
                continue
            failure = f"HTTP {response.status_code}"
        except Exception as exc:
            failure = str(exc)

    raise RuntimeError(f"Failed to fetch {url}: {failure} (after {retries} attempts)")


def clean_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.replace("\r", "").split("\n"):
        line = raw_line.replace("　", " ").strip()
        lines.append(line)
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def safe_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name).strip(" .")


def image_extension(url: str, content_type: str | None) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return suffix
    if content_type:
        extension = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
        if extension in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            return extension
    return ".jpg"


def download_cover(cover_url: str | None, output_dir: Path, referer: str) -> None:
    if not cover_url:
        print("No cover image found.")
        return

    response = cf_requests.get(cover_url, impersonate=IMPERSONATE, timeout=30)
    if response.status_code >= 400:
        print(f"Could not download cover: HTTP {response.status_code}")
        return

    extension = image_extension(cover_url, response.headers.get("content-type"))
    cover_path = output_dir / f"cover{extension}"
    for existing_cover in output_dir.glob("cover.*"):
        existing_cover.unlink()
    cover_path.write_bytes(response.content)
    print(f"Saved cover: {cover_path.name}")


def remove_existing_chapter_files(output_dir: Path, chapter_number: int) -> None:
    for existing in output_dir.glob(f"{chapter_number:03d}_*.txt"):
        existing.unlink()


def infer_book_id(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc not in {"twkan.com", "www.twkan.com"}:
        raise ValueError("This scraper only supports twkan.com URLs.")

    match = re.search(r"/book/(\d+)(?:\.html|/)?", parsed.path)
    if not match:
        raise ValueError(f"Could not infer book id from URL: {url}")
    return match.group(1)


def chapter_list_url(book_id: str) -> str:
    return f"https://twkan.com/ajax_novels/chapterlist/{book_id}.html"


def extract_book_name(index_text: str) -> str:
    soup = BeautifulSoup(index_text, "html.parser")

    og_title = soup.find("meta", property="og:novel:book_name")
    if og_title and og_title.get("content"):
        return str(og_title["content"]).strip()

    h1 = soup.select_one(".booknav2 h1") or soup.select_one("h1")
    if h1:
        return h1.get_text(" ", strip=True)

    raise RuntimeError("Could not determine book name from index page.")


def extract_cover_url(index_text: str) -> str | None:
    soup = BeautifulSoup(index_text, "html.parser")
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        return str(og_image["content"]).strip()
    img = soup.select_one(".bookimg2 img[src]")
    if img:
        return str(img["src"])
    return None


def extract_chapter_links(chapter_list_text: str, book_id: str) -> list[tuple[int, str, str]]:
    soup = BeautifulSoup(chapter_list_text, "html.parser")
    links: list[tuple[int, str, str]] = []
    seen: set[str] = set()

    for li in soup.find_all("li", attrs={"data-num": True}):
        anchor = li.find("a", href=True)
        if not anchor:
            continue

        try:
            chapter_number = int(li["data-num"])
        except (ValueError, KeyError):
            continue

        title = anchor.get_text(strip=True)
        url = str(anchor["href"])
        if not url.startswith("http"):
            url = f"https://twkan.com{url}"

        if url in seen:
            continue
        seen.add(url)
        links.append((chapter_number, title, url))

    if not links:
        raise RuntimeError("No chapter links were found on the index page.")

    links.sort(key=lambda item: item[0])
    return links


def extract_chapter_text(page_text: str, fallback_title: str) -> tuple[str, str]:
    soup = BeautifulSoup(page_text, "html.parser")

    title_node = soup.select_one("h1")
    title = title_node.get_text(" ", strip=True) if title_node else fallback_title

    content_node = soup.find(id="txtcontent0")
    if content_node is None:
        raise RuntimeError(f"Could not find chapter content for: {fallback_title}")

    for node in content_node.find_all(["script", "style"]):
        node.decompose()

    lines = clean_lines(content_node.get_text("\n"))
    lines = [line for line in lines if line != title]

    content = "\n".join(lines).strip()
    if not content:
        raise RuntimeError(f"Empty chapter page for {fallback_title}")
    return title, content


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a chapter range from a 台灣小說網 novel.")
    parser.add_argument("url", help="twkan.com book URL, for example https://twkan.com/book/92274.html")
    parser.add_argument("start", type=int, help="First chapter number to download, inclusive.")
    parser.add_argument("end", type=int, help="Last chapter number to download, inclusive.")
    return parser.parse_args()


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


def download_range(
    url: str,
    start: int,
    end: int,
    output_root: Path = OUTPUT_ROOT,
    progress: ProgressCallback | None = None,
) -> dict[str, object]:
    if start < 1 or end < start:
        raise ValueError("Invalid chapter range: start must be >= 1 and end must be >= start.")

    if progress:
        progress({"stage": "fetching", "current": 0, "total": 0, "message": "Fetching book page..."})
    book_id = infer_book_id(url)
    index_text = fetch_text(url)
    book_name = safe_name(extract_book_name(index_text))
    cover_url = extract_cover_url(index_text)

    if progress:
        progress({"stage": "fetching", "current": 0, "total": 0, "message": "Fetching chapter list..."})
    chapter_list_text = fetch_text(chapter_list_url(book_id))
    chapters = extract_chapter_links(chapter_list_text, book_id)

    selected = [item for item in chapters if start <= item[0] <= end]
    if not selected:
        raise RuntimeError("No chapters matched the requested range.")

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
    download_cover(cover_url, book_output_dir, url)

    files: list[str] = []
    for index, (chapter_number, fallback_title, chapter_url) in enumerate(selected, start=1):
        if progress:
            progress(
                {
                    "stage": "downloading",
                    "current": index - 1,
                    "total": len(selected),
                    "message": f"Downloading chapter {chapter_number}: {fallback_title}",
                    "novel": book_name,
                }
            )
        if index > 1:
            time.sleep(CHAPTER_DELAY)
        page_text = fetch_text(chapter_url)
        title, content = extract_chapter_text(page_text, fallback_title)
        file_name = f"{chapter_number:03d}_{safe_name(title)}.txt"
        remove_existing_chapter_files(book_output_dir, chapter_number)
        (book_output_dir / file_name).write_text(f"{title}\n\n{content}\n", encoding="utf-8")
        files.append(file_name)
        print(f"Saved {chapter_number}: {file_name}")
        if progress:
            progress(
                {
                    "stage": "downloading",
                    "current": index,
                    "total": len(selected),
                    "message": f"Saved chapter {chapter_number}: {title}",
                    "novel": book_name,
                }
            )

    return {
        "novel": book_name,
        "source_url": url,
        "output_dir": str(book_output_dir),
        "chapter_count": len(files),
        "files": files,
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    download_range(args.url, args.start, args.end)


if __name__ == "__main__":
    main()
