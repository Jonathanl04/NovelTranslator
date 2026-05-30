from __future__ import annotations

import argparse
import mimetypes
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from scrapling.fetchers import StealthyFetcher

DATA_ROOT = Path(os.environ.get("NOVEL_TRANSLATOR_DATA_DIR", "data"))
OUTPUT_ROOT = Path(os.environ.get("NOVEL_TRANSLATOR_OUTPUT_ROOT", DATA_ROOT))
FETCH_OPTIONS = {
    "headless": True,
    "disable_resources": True,
    "timeout": 60_000,
    "wait": 3_000,
    "locale": "zh-CN",
}
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "○": 0,
    "一": 1,
    "壹": 1,
    "二": 2,
    "兩": 2,
    "两": 2,
    "貳": 2,
    "贰": 2,
    "三": 3,
    "參": 3,
    "叁": 3,
    "四": 4,
    "肆": 4,
    "五": 5,
    "伍": 5,
    "六": 6,
    "陸": 6,
    "陆": 6,
    "七": 7,
    "柒": 7,
    "八": 8,
    "捌": 8,
    "九": 9,
    "玖": 9,
}

CHINESE_SMALL_UNITS = {
    "十": 10,
    "拾": 10,
    "百": 100,
    "佰": 100,
    "千": 1000,
    "仟": 1000,
}

CHINESE_LARGE_UNITS = {
    "萬": 10_000,
    "万": 10_000,
    "億": 100_000_000,
    "亿": 100_000_000,
}


def jina_reader_url(url: str) -> str:
    return f"https://r.jina.ai/{url}"


def fetch_text(url: str) -> str:
    try:
        response = StealthyFetcher.fetch(url, **FETCH_OPTIONS)
        if response.status < 400 and response.html_content.strip():
            return response.html_content
        failure = f"HTTP {response.status}"
    except Exception as exc:
        failure = str(exc)

    reader_response = requests.get(jina_reader_url(url), headers=REQUEST_HEADERS, timeout=60)
    if reader_response.status_code >= 400:
        raise RuntimeError(
            f"Failed to fetch {url}: {failure}; r.jina.ai fallback returned HTTP {reader_response.status_code}"
        )
    if not reader_response.text.strip():
        raise RuntimeError(f"Failed to fetch {url}: {failure}; r.jina.ai fallback returned an empty page")
    return reader_response.text


def markdown_content(page_text: str) -> str:
    marker = "Markdown Content:\n"
    if marker in page_text:
        return page_text.split(marker, 1)[1]
    return page_text


def clean_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.replace("\r", "").split("\n"):
        line = raw_line.replace("\u3000", " ").strip()
        if line.startswith("# "):
            line = line[2:].strip()
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

    response = requests.get(
        cover_url,
        headers={
            **REQUEST_HEADERS,
            "Referer": referer,
        },
        timeout=30,
    )
    response.raise_for_status()

    extension = image_extension(cover_url, response.headers.get("content-type"))
    cover_path = output_dir / f"cover{extension}"
    for existing_cover in output_dir.glob("cover.*"):
        existing_cover.unlink()
    cover_path.write_bytes(response.content)
    print(f"Saved cover: {cover_path.name}")


def remove_existing_chapter_files(output_dir: Path, chapter_number: int) -> None:
    for existing in output_dir.glob(f"{chapter_number:03d}_*.txt"):
        existing.unlink()


def chinese_numeral_to_int(text: str) -> int:
    total = 0
    section = 0
    number = 0

    for char in text:
        if char in CHINESE_DIGITS:
            number = CHINESE_DIGITS[char]
            continue

        if char in CHINESE_SMALL_UNITS:
            unit = CHINESE_SMALL_UNITS[char]
            section += (number or 1) * unit
            number = 0
            continue

        if char in CHINESE_LARGE_UNITS:
            unit = CHINESE_LARGE_UNITS[char]
            total += (section + number or 1) * unit
            section = 0
            number = 0
            continue

        raise ValueError(f"Unsupported chapter numeral: {text}")

    return total + section + number


def parse_chapter_number(title: str) -> int | None:
    match = re.search(r"第([0-9零〇○一壹二兩两貳贰三參叁四肆五伍六陸陆七柒八捌九玖十拾百佰千仟萬万億亿]+)章", title)
    if not match:
        return None

    raw_number = match.group(1)
    if raw_number.isdigit():
        return int(raw_number)
    try:
        return chinese_numeral_to_int(raw_number)
    except ValueError:
        return None


def infer_book_id(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc not in {"69shuba.com", "www.69shuba.com"}:
        raise ValueError("This scraper only supports 69shuba.com URLs.")

    match = re.search(r"/book/(\d+)(?:\.htm|/)?", parsed.path)
    if not match:
        raise ValueError(f"Could not infer book id from URL: {url}")
    return match.group(1)


def chapter_index_url(book_id: str) -> str:
    return f"https://www.69shuba.com/book/{book_id}/"


def extract_book_name(index_text: str) -> str:
    if "Markdown Content:" in index_text:
        title_match = re.search(r"^Title:\s*(.+?)(?:最新章节|无弹窗|txt|全集|阅读|列表|广告)", index_text, re.MULTILINE)
        if title_match:
            return title_match.group(1).strip(" ,-")

        markdown = markdown_content(index_text)
        heading_match = re.search(r"^#\s+(?:\[)?(.+?)(?:最新章节|无弹窗|txt|全集|阅读|列表|广告)", markdown, re.MULTILINE)
        if heading_match:
            return heading_match.group(1).strip(" []")

    soup = BeautifulSoup(index_text, "html.parser")
    title_node = soup.select_one("h1") or soup.select_one("title")
    if title_node is None:
        raise RuntimeError("Could not determine book name from index page.")
    return re.split(r"最新章节|无弹窗|txt|全集|阅读|列表|广告", title_node.get_text(" ", strip=True), 1)[0].strip()


def extract_cover_url(index_text: str, base_url: str) -> str | None:
    if "Markdown Content:" in index_text:
        markdown = markdown_content(index_text)
        match = re.search(r"!\[[^\]]*\]\((https?://cdn\.cdnshu\.com/files/article/image/[^\s)]+)", markdown)
        return match.group(1) if match else None

    soup = BeautifulSoup(index_text, "html.parser")
    image = soup.select_one('img[src*="/files/article/image/"][src]') or soup.select_one("img[alt][title][src]")
    if image is None:
        return None
    return urljoin(base_url, image.get("src", ""))


def extract_chapter_links(index_text: str, book_id: str) -> list[tuple[int, str, str]]:
    links: list[tuple[int, str, str]] = []
    seen: set[str] = set()

    if "Markdown Content:" in index_text:
        markdown = markdown_content(index_text)
        link_re = re.compile(
            rf"\[([^\]]+)\]\((https?://(?:www\.)?69shuba\.com/txt/{book_id}/\d+)(?:\s+\"[^\"]*\")?\)"
        )

        for title, url in link_re.findall(markdown):
            chapter_number = parse_chapter_number(title)
            if chapter_number is None or url in seen:
                continue
            seen.add(url)
            links.append((chapter_number, title.strip(), url))
    else:
        soup = BeautifulSoup(index_text, "html.parser")
        for anchor in soup.select("a[href]"):
            title = anchor.get_text(" ", strip=True)
            href = anchor.get("href", "")
            chapter_number = parse_chapter_number(title)
            if chapter_number is None:
                continue

            url = urljoin("https://www.69shuba.com", href)
            if f"/txt/{book_id}/" not in url or url in seen:
                continue
            seen.add(url)
            links.append((chapter_number, title, url))

    if not links:
        raise RuntimeError("No chapter links were found on the index page.")

    links.sort(key=lambda item: item[0])
    return links


def extract_chapter_text(page_text: str, fallback_title: str) -> tuple[str, str]:
    if "Markdown Content:" in page_text:
        metadata, markdown = page_text.split("Markdown Content:\n", 1)
        title = fallback_title
        title_match = re.search(r"^Title:\s*.+?-(.+?)-69书吧", metadata, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()

        lines = clean_lines(markdown)
        if lines and re.match(r"^\d{4}-\d{2}-\d{2}\s+作者：", lines[0]):
            lines.pop(0)
        while lines and not lines[0]:
            lines.pop(0)
        while lines and lines[0] == title:
            lines.pop(0)
        while lines and not lines[0]:
            lines.pop(0)

        content = "\n".join(lines).strip()
        if not content:
            raise RuntimeError(f"Empty chapter page for {fallback_title}")
        return title, content

    soup = BeautifulSoup(page_text, "html.parser")
    title_node = soup.select_one("h1") or soup.select_one(".txtnav h1")
    body_node = soup.select_one("#content") or soup.select_one(".txtnav")
    if body_node is None:
        raise RuntimeError(f"Could not find chapter content for: {fallback_title}")

    for node in body_node.select("script, style, .page1, .bottom-ad, .adsbygoogle"):
        node.decompose()

    title = title_node.get_text(" ", strip=True) if title_node is not None else fallback_title
    lines = clean_lines(body_node.get_text("\n"))
    lines = [
        line
        for line in lines
        if line != title and not line.startswith("作者：") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", line)
    ]

    content = "\n".join(lines).strip()
    if not content:
        raise RuntimeError(f"Empty chapter page for {fallback_title}")
    return title, content


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a chapter range from a 69书吧 novel.")
    parser.add_argument("url", help="69书吧 book URL, for example https://www.69shuba.com/book/77582.htm")
    parser.add_argument("start", type=int, help="First chapter number to download, inclusive.")
    parser.add_argument("end", type=int, help="Last chapter number to download, inclusive.")
    return parser.parse_args()


def download_range(url: str, start: int, end: int, output_root: Path = OUTPUT_ROOT) -> dict[str, object]:
    if start < 1 or end < start:
        raise ValueError("Invalid chapter range: start must be >= 1 and end must be >= start.")

    book_id = infer_book_id(url)
    book_page_text = fetch_text(url)
    index_text = fetch_text(chapter_index_url(book_id))
    book_name = safe_name(extract_book_name(book_page_text))
    cover_url = extract_cover_url(book_page_text, url)
    chapters = extract_chapter_links(index_text, book_id)

    selected = [item for item in chapters if start <= item[0] <= end]
    if not selected:
        raise RuntimeError("No chapters matched the requested range.")

    book_output_dir = output_root / book_name / "source"
    book_output_dir.mkdir(parents=True, exist_ok=True)
    download_cover(cover_url, book_output_dir, url)

    files: list[str] = []
    for chapter_number, fallback_title, url in selected:
        page_text = fetch_text(url)
        title, content = extract_chapter_text(page_text, fallback_title)
        file_name = f"{chapter_number:03d}_{safe_name(title)}.txt"
        remove_existing_chapter_files(book_output_dir, chapter_number)
        (book_output_dir / file_name).write_text(f"{title}\n\n{content}\n", encoding="utf-8")
        files.append(file_name)
        print(f"Saved {chapter_number}: {file_name}")

    return {
        "novel": book_name,
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
