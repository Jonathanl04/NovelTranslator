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
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from scrapling.fetchers import StealthySession

DATA_ROOT = Path(os.environ.get("NOVEL_TRANSLATOR_DATA_DIR", "data"))
OUTPUT_ROOT = Path(os.environ.get("NOVEL_TRANSLATOR_OUTPUT_ROOT", DATA_ROOT))
PROFILE_DIR = Path(os.environ.get("NOVEL_TRANSLATOR_BOOKTO_PROFILE_DIR", DATA_ROOT / ".bookto-profile"))
BOOKTO_STATE_PATH = DATA_ROOT / ".bookto-domain.json"
BOOKTO_HOST_PATTERN = re.compile(r"(?:www\.)?bookto(?P<number>\d+)\.com", re.IGNORECASE)
BOOKTO_MAX_SUCCESSOR_CHECKS = 10
BOOKTO_PROBE_TIMEOUT = 10
CHAPTER_DELAY = 1.0
FETCH_OPTIONS = {
    "headless": True,
    "solve_cloudflare": False,
    "load_dom": True,
    "network_idle": False,
    "google_search": False,
    "timeout": 90_000,
    "wait": 0,
}
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}
_CLOUDFLARE_MARKERS = (
    "Just a moment...",
    "Performing security verification",
    "잠시만 기다리십시오",
)

ProgressCallback = Callable[[dict[str, object]], None]


def bookto_real_chrome_enabled() -> bool:
    configured = os.environ.get("NOVEL_TRANSLATOR_BOOKTO_REAL_CHROME")
    if configured is None:
        return os.name == "nt"
    return configured.strip().lower() in {"1", "true", "yes", "on"}


def bookto_headless_enabled() -> bool:
    configured = os.environ.get("NOVEL_TRANSLATOR_BOOKTO_HEADLESS")
    if configured is None:
        return os.name != "nt"
    return configured.strip().lower() in {"1", "true", "yes", "on"}


FETCH_OPTIONS["real_chrome"] = bookto_real_chrome_enabled()
FETCH_OPTIONS["headless"] = bookto_headless_enabled()


def is_bookto_host(host: str) -> bool:
    return BOOKTO_HOST_PATTERN.fullmatch(host.lower()) is not None


def bookto_host_number(host: str) -> int:
    match = BOOKTO_HOST_PATTERN.fullmatch(host.lower())
    if match is None:
        raise ValueError(f"Not a numbered Bookto host: {host}")
    return int(match.group("number"))


def point_bookto_url_at_host(url: str, host: str) -> str:
    parsed = urlparse(url)
    if not is_bookto_host(parsed.netloc):
        raise ValueError("This scraper only supports numbered bookto.com URLs.")
    if not is_bookto_host(host):
        raise ValueError(f"Not a numbered Bookto host: {host}")
    return parsed._replace(netloc=host.lower()).geturl()


def load_saved_bookto_host(state_path: Path | None = None) -> str | None:
    path = state_path or BOOKTO_STATE_PATH
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    host = state.get("host") if isinstance(state, dict) else None
    return host.lower() if isinstance(host, str) and is_bookto_host(host) else None


def save_bookto_host(host: str, state_path: Path | None = None) -> None:
    if not is_bookto_host(host):
        raise ValueError(f"Not a numbered Bookto host: {host}")
    path = state_path or BOOKTO_STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps({"host": host.lower()}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def migrate_saved_bookto_urls(host: str, library_root: Path | None = None) -> int:
    if not is_bookto_host(host):
        raise ValueError(f"Not a numbered Bookto host: {host}")

    root = library_root or OUTPUT_ROOT
    current_number = bookto_host_number(host)
    updated_count = 0
    for metadata_path in root.glob("*/metadata.json"):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(metadata, dict):
            continue

        source_url = metadata.get("source_url")
        if not isinstance(source_url, str):
            continue
        parsed = urlparse(source_url)
        if not is_bookto_host(parsed.netloc):
            continue
        if bookto_host_number(parsed.netloc) >= current_number:
            continue

        metadata["source_url"] = point_bookto_url_at_host(source_url, host)
        temporary_path = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
        try:
            temporary_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(metadata_path)
        except OSError:
            continue
        updated_count += 1
    return updated_count


def bookto_candidate_hosts(url: str, state_path: Path | None = None) -> list[str]:
    supplied_number = bookto_host_number(urlparse(url).netloc)
    saved_host = load_saved_bookto_host(state_path)
    saved_number = bookto_host_number(saved_host) if saved_host else supplied_number
    start_number = max(supplied_number, saved_number)
    return [
        f"bookto{number}.com"
        for number in range(start_number, start_number + BOOKTO_MAX_SUCCESSOR_CHECKS)
    ]


def bookto_candidate_is_viable(url: str) -> bool:
    try:
        response = requests.get(
            url,
            headers=REQUEST_HEADERS,
            timeout=BOOKTO_PROBE_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException:
        return False

    try:
        if 300 <= response.status_code < 400:
            location = response.headers.get("location", "")
            if not location:
                return False
            original_host = urlparse(url).netloc
            redirect_host = urlparse(urljoin(url, location)).netloc
            return (
                is_bookto_host(redirect_host)
                and bookto_host_number(redirect_host) == bookto_host_number(original_host)
            )
        return response.status_code not in {404, 410, 421, 451} and response.status_code < 500
    finally:
        response.close()


def fetch_text(
    session: StealthySession,
    url: str,
    wait_selector: str,
    retry_challenge: bool = True,
) -> str:
    attempts = 2 if retry_challenge else 1
    for _attempt in range(attempts):
        response = session.fetch(
            url,
            load_dom=True,
            network_idle=False,
            google_search=False,
            # Bookto31 uses a managed Turnstile challenge. Solve it on the initial
            # page; later chapter requests reuse the clearance from this session.
            solve_cloudflare=retry_challenge,
            wait_selector=wait_selector,
            wait_selector_state="attached",
            timeout=30_000 if retry_challenge else 15_000,
            wait=0,
        )
        text = response.html_content
        blocked = response.status >= 400 or any(
            marker in text for marker in _CLOUDFLARE_MARKERS
        )
        if not blocked:
            if not text.strip():
                raise RuntimeError(f"Failed to fetch {url}: empty page")
            return text

    raise RuntimeError(
        f"Failed to pass Bookto security verification for {url}. "
        "Try again later or from a network that can open the page normally."
    )


def clean_lines(text: str) -> list[str]:
    lines = [
        line.replace("\u3000", " ").strip()
        for line in text.replace("\r", "").split("\n")
    ]
    return [line for line in lines if line]


def safe_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name).strip(" .")


def infer_book_id(url: str) -> str:
    parsed = urlparse(url)
    if not is_bookto_host(parsed.netloc):
        raise ValueError("This scraper only supports numbered bookto.com URLs.")

    query = parse_qs(parsed.query)
    book_ids = query.get("wr_id", [])
    if parsed.path != "/bbs/board.php" or query.get("bo_table") != ["novel"]:
        raise ValueError(f"Could not infer novel id from URL: {url}")
    if not book_ids or not book_ids[0].isdigit():
        raise ValueError(f"Could not infer novel id from URL: {url}")
    return book_ids[0]


def extract_book_name(index_text: str) -> str:
    soup = BeautifulSoup(index_text, "html.parser")
    selectors = (
        ".page-title .page-desc",
        "div.col-sm-8 div.view-content span b",
        "div.col-sm-8 div.view-content b",
        ".view-title",
        "h1",
    )
    for selector in selectors:
        node = soup.select_one(selector)
        if node and node.get_text(" ", strip=True):
            return node.get_text(" ", strip=True)

    if soup.title:
        title = soup.title.get_text(" ", strip=True)
        return re.split(r"\s*[>|-]\s*(?:북토끼|BOOKTO)", title, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    raise RuntimeError("Could not determine book name from index page.")


def extract_cover_url(index_text: str, base_url: str) -> str | None:
    soup = BeautifulSoup(index_text, "html.parser")
    image = (
        soup.select_one("div.view-img img[src]")
        or soup.select_one("div.view-content1 img[src]")
        or soup.select_one("div.col-sm-4 img[src]")
    )
    if image is None:
        return None
    return urljoin(base_url, str(image.get("src", "")))


def extract_chapter_links(index_text: str, base_url: str) -> list[tuple[int, str, str]]:
    soup = BeautifulSoup(index_text, "html.parser")
    links: list[tuple[int, str, str]] = []
    seen: set[str] = set()

    for row in soup.select(".list-body li"):
        number_node = row.select_one(".wr-num")
        if number_node is None:
            continue
        match = re.search(r"\d+", number_node.get_text(" ", strip=True).replace(",", ""))
        if match is None:
            continue

        anchor = row.select_one('a[href*="bo_table=novel"]') or row.select_one('a[href*="/novel/"]')
        if anchor is None:
            continue
        url = urljoin(base_url, str(anchor.get("href", "")))
        if url in seen:
            continue
        seen.add(url)
        links.append((int(match.group()), anchor.get_text(" ", strip=True), url))

    if not links:
        raise RuntimeError("No chapter links were found on the book page.")
    links.sort(key=lambda item: item[0])
    return links


def resolve_bookto_index(
    session: StealthySession,
    source_url: str,
    state_path: Path | None = None,
    library_root: Path | None = None,
) -> tuple[str, str]:
    failures: list[tuple[str, Exception]] = []
    for host in bookto_candidate_hosts(source_url, state_path):
        candidate_url = point_bookto_url_at_host(source_url, host)
        if not bookto_candidate_is_viable(candidate_url):
            failures.append((host, RuntimeError("Domain is retired or unreachable.")))
            continue
        try:
            index_text = fetch_text(session, spage_url(candidate_url, 1), ".list-body")
            extract_chapter_links(index_text, candidate_url)
        except Exception as exc:
            failures.append((host, exc))
            continue
        save_bookto_host(host, state_path)
        migrate_saved_bookto_urls(host, library_root)
        return candidate_url, index_text

    attempted = ", ".join(host for host, _exc in failures)
    last_error = failures[-1][1]
    raise RuntimeError(
        f"Could not find a working Bookto domain after checking: {attempted}"
    ) from last_error


def spage_url(url: str, page_number: int) -> str:
    parsed = urlparse(url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    query = [(name, str(page_number) if name == "spage" else value) for name, value in query]
    if not any(name == "spage" for name, _value in query):
        query.append(("spage", str(page_number)))
    return parsed._replace(query=urlencode(query)).geturl()


def extract_last_spage(index_text: str, base_url: str, book_id: str) -> int:
    soup = BeautifulSoup(index_text, "html.parser")
    pages = [1]
    for anchor in soup.select('a[href*="spage="]'):
        parsed = urlparse(urljoin(base_url, str(anchor.get("href", ""))))
        query = parse_qs(parsed.query)
        if query.get("bo_table") != ["novel"] or query.get("wr_id") != [book_id]:
            continue
        raw_page = query.get("spage", [""])[0]
        if raw_page.isdigit():
            pages.append(int(raw_page))
    return max(pages)


def collect_chapters_for_range(
    session: StealthySession,
    source_url: str,
    first_page_text: str,
    start: int,
    end: int,
) -> list[tuple[int, str, str]]:
    book_id = infer_book_id(source_url)
    chapters = extract_chapter_links(first_page_text, source_url)
    page_size = len(chapters)
    highest_chapter = max(item[0] for item in chapters)
    last_spage = extract_last_spage(first_page_text, source_url, book_id)

    first_target_page = max(1, (highest_chapter - min(end, highest_chapter)) // page_size + 1)
    last_target_page = (
        max(1, (highest_chapter - start) // page_size + 1)
        if start <= highest_chapter
        else 1
    )
    first_target_page = min(first_target_page, last_spage)
    last_target_page = min(last_target_page, last_spage)

    seen = {item[2] for item in chapters}
    for page_number in range(first_target_page, last_target_page + 1):
        if page_number == 1:
            continue
        page_url = spage_url(source_url, page_number)
        page_text = fetch_text(session, page_url, ".list-body", retry_challenge=False)
        for chapter in extract_chapter_links(page_text, page_url):
            if chapter[2] not in seen:
                seen.add(chapter[2])
                chapters.append(chapter)

    chapters.sort(key=lambda item: item[0])
    return chapters


def extract_chapter_text(page_text: str, fallback_title: str) -> tuple[str, str]:
    soup = BeautifulSoup(page_text, "html.parser")
    title_node = soup.select_one("h1") or soup.select_one(".view-title") or soup.select_one(".page-title")
    title = title_node.get_text(" ", strip=True) if title_node else fallback_title

    content_node = soup.select_one("#novel_content") or soup.select_one(".book-text-viewer")
    if content_node is None:
        candidates = soup.select("article div")
        content_node = max(candidates, key=lambda node: len(node.select("p")), default=None)
        if content_node is None or len(content_node.select("p")) < 2:
            raise RuntimeError(f"Could not find chapter content for: {fallback_title}")

    for node in content_node.select("script, style, iframe, ins, .adsbygoogle"):
        node.decompose()
    lines = [line for line in clean_lines(content_node.get_text("\n")) if line != title]
    content = "\n".join(lines).strip()
    if not content:
        raise RuntimeError(f"Empty chapter page for {fallback_title}")
    return title, content


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

    try:
        response = requests.get(
            cover_url,
            headers={**REQUEST_HEADERS, "Referer": referer},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Could not download cover: {exc}")
        return
    extension = image_extension(cover_url, response.headers.get("content-type"))
    for existing_cover in output_dir.glob("cover.*"):
        existing_cover.unlink()
    (output_dir / f"cover{extension}").write_bytes(response.content)


def remove_existing_chapter_files(output_dir: Path, chapter_number: int) -> None:
    for existing in output_dir.glob(f"{chapter_number:03d}_*.txt"):
        existing.unlink()


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
    infer_book_id(url)

    if progress:
        progress(
            {
                "stage": "fetching",
                "current": 0,
                "total": 0,
                "message": "Finding current Bookto domain...",
            }
        )
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with StealthySession(**FETCH_OPTIONS, user_data_dir=str(PROFILE_DIR)) as session:
        url, index_text = resolve_bookto_index(
            session,
            url,
            state_path=output_root / BOOKTO_STATE_PATH.name,
            library_root=output_root,
        )
        book_name = safe_name(extract_book_name(index_text))
        cover_url = extract_cover_url(index_text, url)
        chapters = collect_chapters_for_range(session, url, index_text, start, end)
        selected = [item for item in chapters if start <= item[0] <= end]
        if not selected:
            raise RuntimeError("No chapters matched the requested range.")

        book_output_dir = output_root / book_name / "source"
        book_output_dir.mkdir(parents=True, exist_ok=True)
        save_source_url(book_output_dir, book_name, url)
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
            page_text = fetch_text(
                session,
                chapter_url,
                ".book-text-viewer, #novel_content",
                retry_challenge=False,
            )
            title, content = extract_chapter_text(page_text, fallback_title)
            file_name = f"{chapter_number:03d}_{safe_name(title)}.txt"
            remove_existing_chapter_files(book_output_dir, chapter_number)
            (book_output_dir / file_name).write_text(f"{title}\n\n{content}\n", encoding="utf-8")
            files.append(file_name)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a chapter range from a Bookto novel.")
    parser.add_argument("url", help="Numbered bookto.com novel URL")
    parser.add_argument("start", type=int, help="First chapter number to download, inclusive.")
    parser.add_argument("end", type=int, help="Last chapter number to download, inclusive.")
    return parser.parse_args()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    download_range(args.url, args.start, args.end)


if __name__ == "__main__":
    main()
