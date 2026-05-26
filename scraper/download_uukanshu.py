from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

MIRROR_PREFIX = "https://r.jina.ai/http://"
OUTPUT_ROOT = Path("output")

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


def fetch_text(url: str) -> str:
    response = requests.get(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        },
        timeout=30,
    )

    if response.ok:
        return response.text

    mirror_url = f"{MIRROR_PREFIX}{url.removeprefix('https://').removeprefix('http://')}"
    mirror_response = requests.get(mirror_url, timeout=30)
    mirror_response.raise_for_status()
    return mirror_response.text


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
    match = re.search(r"第(.+?)章", title)
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
    if parsed.netloc not in {"uukanshu.cc", "www.uukanshu.cc"}:
        raise ValueError("This scraper only supports uukanshu.cc URLs.")

    match = re.search(r"/book/(\d+)/?", url)
    if not match:
        raise ValueError(f"Could not infer book id from URL: {url}")
    return match.group(1)


def extract_book_name(index_text: str) -> str:
    if "Markdown Content:" in index_text:
        markdown = markdown_content(index_text)
        match = re.search(r"^#\s+(.+?)最新章節", markdown, re.MULTILINE)
        if match:
            return match.group(1).strip()

    soup = BeautifulSoup(index_text, "html.parser")
    title_node = soup.select_one(".content h1") or soup.select_one("h1") or soup.select_one("title")
    if title_node is None:
        raise RuntimeError("Could not determine book name from index page.")
    return title_node.get_text(" ", strip=True).replace(" - UU看書", "").strip()


def extract_chapter_links(index_text: str, book_id: str) -> list[tuple[int, str, str]]:
    links: list[tuple[int, str, str]] = []
    seen: set[str] = set()

    if "Markdown Content:" in index_text:
        markdown = markdown_content(index_text)
        link_re = re.compile(
            rf"\[([^\]]+)\]\(((?:https?://(?:www\.)?uukanshu\.cc)?/book/{book_id}/\d+\.html)(?:\s+\"[^\"]*\")?\)"
        )

        for title, url in link_re.findall(markdown):
            chapter_number = parse_chapter_number(title)
            if chapter_number is None:
                continue
            if url in seen:
                continue
            seen.add(url)
            links.append((chapter_number, title.strip(), url if url.startswith("http") else urljoin("https://uukanshu.cc", url)))
    else:
        soup = BeautifulSoup(index_text, "html.parser")
        content = soup.select_one(".content")
        if content is None:
            raise RuntimeError("Could not find the chapter index container.")

        for anchor in content.select("a[href]"):
            title = anchor.get_text(strip=True)
            href = anchor.get("href", "")
            chapter_number = parse_chapter_number(title)
            if chapter_number is None:
                continue
            if f"/book/{book_id}/" not in href or not href.endswith(".html"):
                continue
            url = urljoin("https://uukanshu.cc", href)
            if url in seen:
                continue
            seen.add(url)
            links.append((chapter_number, title, url))

    if not links:
        raise RuntimeError("No chapter links were found on the index page.")

    links.sort(key=lambda item: item[0])
    return links


def extract_chapter_text(page_text: str, fallback_title: str) -> tuple[str, str]:
    if "Markdown Content:" in page_text:
        markdown = markdown_content(page_text)
        lines = clean_lines(markdown)
        if not lines:
            raise RuntimeError(f"Empty chapter page for {fallback_title}")

        title = lines[0] if lines[0].startswith("第") else fallback_title
        body_lines = lines[1:] if lines[0] == title else lines

        while body_lines and not body_lines[0]:
            body_lines.pop(0)

        return title, "\n".join(body_lines).strip()

    soup = BeautifulSoup(page_text, "html.parser")
    title_node = soup.select_one(".content h1.pt10") or soup.select_one("h1.pt10")
    body_node = soup.select_one(".readcotent")
    if title_node is None or body_node is None:
        raise RuntimeError(f"Could not find chapter content for: {fallback_title}")

    title = title_node.get_text(" ", strip=True)
    for script in body_node.find_all("script"):
        script.decompose()

    lines = clean_lines(body_node.get_text("\n"))
    while lines and lines[0] == title:
        lines.pop(0)

    return title, "\n".join(lines).strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a chapter range from a UU看書 novel.")
    parser.add_argument("url", help="UU看書 book index URL, for example https://uukanshu.cc/book/25771/")
    parser.add_argument("start", type=int, help="First chapter number to download, inclusive.")
    parser.add_argument("end", type=int, help="Last chapter number to download, inclusive.")
    return parser.parse_args()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    if args.start < 1 or args.end < args.start:
        raise ValueError("Invalid chapter range: start must be >= 1 and end must be >= start.")

    book_id = infer_book_id(args.url)
    index_text = fetch_text(args.url)
    book_name = safe_name(extract_book_name(index_text))
    chapters = extract_chapter_links(index_text, book_id)

    selected = [item for item in chapters if args.start <= item[0] <= args.end]
    if not selected:
        raise RuntimeError("No chapters matched the requested range.")

    book_output_dir = OUTPUT_ROOT / book_name
    book_output_dir.mkdir(parents=True, exist_ok=True)
    for existing in book_output_dir.glob("*.txt"):
        existing.unlink()

    for chapter_number, fallback_title, url in selected:
        page_text = fetch_text(url)
        title, content = extract_chapter_text(page_text, fallback_title)
        file_name = f"{chapter_number:03d}_{safe_name(title)}.txt"
        (book_output_dir / file_name).write_text(f"{title}\n\n{content}\n", encoding="utf-8")
        print(f"Saved {chapter_number}: {file_name}")


if __name__ == "__main__":
    main()
