from __future__ import annotations

import json
import os
from pathlib import Path

DATA_ROOT = Path(os.environ.get("NOVEL_TRANSLATOR_DATA_DIR", "data"))
COOKIES_PATH = DATA_ROOT / "qidian_cookies.json"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_AUTH_COOKIE_NAMES = {"ywguid", "ywkey"}


def load_cookies() -> list[dict]:
    if not COOKIES_PATH.exists():
        return []
    try:
        data = json.loads(COOKIES_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, IOError):
        pass
    return []


def save_cookies(cookies: list[dict]) -> None:
    COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    COOKIES_PATH.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")


def _has_auth_cookies(cookies: list[dict]) -> bool:
    return any(c.get("name") in _AUTH_COOKIE_NAMES and c.get("value") for c in cookies)


def is_logged_in() -> bool:
    return _has_auth_cookies(load_cookies())


def get_state() -> dict[str, object]:
    return {"logged_in": is_logged_in()}


def set_cookies_from_string(cookie_str: str) -> dict[str, object]:
    """Parse a cookie header string and save it. Raises ValueError on bad input."""
    cookies = []
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, value = part.partition("=")
        name = name.strip()
        value = value.strip()
        if name and value:
            cookies.append({
                "name": name,
                "value": value,
                "domain": ".qidian.com",
                "path": "/",
            })

    if not cookies:
        raise ValueError("No valid cookies found in the provided string.")

    if not _has_auth_cookies(cookies):
        raise ValueError(
            "Required auth cookies (ywguid, ywkey) were not found. "
            "Make sure you are logged in to Qidian before copying cookies."
        )

    save_cookies(cookies)
    return get_state()


def clear_login() -> dict[str, object]:
    if COOKIES_PATH.exists():
        COOKIES_PATH.unlink()
    return get_state()
