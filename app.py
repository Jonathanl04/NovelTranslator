from __future__ import annotations

import argparse
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT / "output"
TRANSLATED_ROOT = ROOT / "translated"
CONFIG_PATH = ROOT / "translator_config.json"
GLOSSARY_PATH = ROOT / "glossary.json"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_TRANSLATION_MODEL = "deepseek-v4-flash"
DEFAULT_GLOSSARY_MODEL = "deepseek-v4-pro"
MODELS = {"deepseek-v4-flash", "deepseek-v4-pro"}
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
CJK_FRAGMENT_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")

ALLOWED_CATEGORIES = {
    "character",
    "place",
    "sect",
    "clan",
    "organization",
    "school",
    "faction",
    "realm",
    "rank",
    "system",
    "worldbuilding",
    "technique",
    "spell",
    "artifact",
    "weapon",
    "formation",
    "pill",
    "treasure",
    "title",
    "address",
    "proper_noun",
}
ALLOWED_GENDERS = {"", "male", "female", "unknown", "it"}


class AppError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


state_lock = threading.Lock()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AppError(f"Invalid JSON in {path.name}: {exc}", 500) from exc


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_config() -> dict[str, str]:
    config = read_json(CONFIG_PATH, {})
    if not isinstance(config, dict):
        raise AppError("translator_config.json must contain a JSON object.", 500)
    old_model = str(config.get("model", "")).strip()
    translation_model = str(
        config.get("translation_model", old_model or DEFAULT_TRANSLATION_MODEL)
    ).strip()
    glossary_model = str(config.get("glossary_model", DEFAULT_GLOSSARY_MODEL)).strip()
    return {
        "api_key": str(config.get("api_key", "")),
        "translation_model": translation_model if translation_model in MODELS else DEFAULT_TRANSLATION_MODEL,
        "glossary_model": glossary_model if glossary_model in MODELS else DEFAULT_GLOSSARY_MODEL,
    }


def save_config(config: dict[str, Any]) -> dict[str, str]:
    api_key = str(config.get("api_key", "")).strip()
    translation_model = str(
        config.get("translation_model", DEFAULT_TRANSLATION_MODEL) or DEFAULT_TRANSLATION_MODEL
    ).strip()
    glossary_model = str(
        config.get("glossary_model", DEFAULT_GLOSSARY_MODEL) or DEFAULT_GLOSSARY_MODEL
    ).strip()
    if translation_model not in MODELS or glossary_model not in MODELS:
        raise AppError("Models must be deepseek-v4-flash or deepseek-v4-pro.")
    saved = {
        "api_key": api_key,
        "translation_model": translation_model,
        "glossary_model": glossary_model,
    }
    write_json(CONFIG_PATH, saved)
    return saved


def public_config() -> dict[str, Any]:
    config = load_config()
    return {
        "has_api_key": bool(config["api_key"]),
        "api_key_mask": mask_key(config["api_key"]),
        "translation_model": config["translation_model"],
        "glossary_model": config["glossary_model"],
    }


def mask_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "********"
    return f"{api_key[:4]}...{api_key[-4:]}"


def load_glossary() -> list[dict[str, str]]:
    data = read_json(GLOSSARY_PATH, [])
    if not isinstance(data, list):
        raise AppError("glossary.json must contain a JSON array.", 500)
    return [normalize_glossary_entry(item) for item in data if isinstance(item, dict)]


def save_glossary(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized = [entry for entry in (normalize_glossary_entry(item) for item in entries) if entry]
    write_json(GLOSSARY_PATH, normalized)
    return normalized


def normalize_glossary_entry(entry: dict[str, Any]) -> dict[str, str]:
    source_term = str(entry.get("source_term", "")).strip()
    english_term = str(entry.get("english_term", "")).strip()
    category = str(entry.get("category", "")).strip().lower()
    gender = str(entry.get("gender_or_pronoun", "")).strip().lower()

    if not source_term or not english_term:
        return {}
    if contains_cjk(english_term):
        return {}
    if category not in ALLOWED_CATEGORIES:
        return {}
    if gender not in ALLOWED_GENDERS:
        gender = ""

    return {
        "source_term": source_term,
        "english_term": english_term,
        "category": category,
        "gender_or_pronoun": gender,
    }


def contains_cjk(value: str) -> bool:
    return bool(CJK_RE.search(value))


def merge_glossary_entries(
    existing: list[dict[str, Any]], updates: list[dict[str, Any]]
) -> list[dict[str, str]]:
    merged = [entry for entry in (normalize_glossary_entry(item) for item in existing) if entry]
    by_source = {entry["source_term"]: entry for entry in merged}

    for raw_update in updates:
        if not isinstance(raw_update, dict):
            continue
        update = normalize_glossary_entry(raw_update)
        if not update:
            continue
        current = by_source.get(update["source_term"])
        if current is None:
            merged.append(update)
            by_source[update["source_term"]] = update
            continue
        for key, value in update.items():
            if key != "source_term" and not current.get(key) and value:
                current[key] = value

    return merged


def safe_segment(value: str, label: str) -> str:
    value = value.strip()
    if not value or "/" in value or "\\" in value or value in {".", ".."}:
        raise AppError(f"Invalid {label}.")
    return value


def list_novels(output_root: Path | None = None) -> list[str]:
    output_root = output_root or OUTPUT_ROOT
    if not output_root.exists():
        return []
    return sorted(item.name for item in output_root.iterdir() if item.is_dir())


def source_path(novel: str, filename: str, output_root: Path | None = None) -> Path:
    output_root = output_root or OUTPUT_ROOT
    novel = safe_segment(novel, "novel")
    filename = safe_segment(filename, "chapter")
    if not filename.lower().endswith(".txt"):
        raise AppError("Chapter must be a .txt file.")
    path = output_root / novel / filename
    if not path.exists() or not path.is_file():
        raise AppError("Chapter not found.", 404)
    return path


def translated_path(
    novel: str, filename: str, translated_root: Path | None = None
) -> Path:
    translated_root = translated_root or TRANSLATED_ROOT
    novel = safe_segment(novel, "novel")
    filename = safe_segment(filename, "chapter")
    return translated_root / novel / filename


def list_chapters(
    novel: str,
    output_root: Path | None = None,
    translated_root: Path | None = None,
) -> list[dict[str, Any]]:
    output_root = output_root or OUTPUT_ROOT
    translated_root = translated_root or TRANSLATED_ROOT
    novel = safe_segment(novel, "novel")
    novel_dir = output_root / novel
    if not novel_dir.exists() or not novel_dir.is_dir():
        raise AppError("Novel not found.", 404)

    chapters = []
    for path in sorted(novel_dir.glob("*.txt")):
        target = translated_path(novel, path.name, translated_root)
        chapters.append(
            {
                "filename": path.name,
                "title": chapter_label(path.name),
                "translated": target.exists(),
                "source_size": path.stat().st_size,
                "translated_size": target.stat().st_size if target.exists() else 0,
            }
        )
    return chapters


def chapter_label(filename: str) -> str:
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


def glossary_prompt(glossary: list[dict[str, Any]]) -> str:
    if not glossary:
        return "No established glossary entries yet."
    lines = []
    for entry in glossary:
        gender = entry.get("gender_or_pronoun", "")
        detail = f"{entry['source_term']} => {entry['english_term']} [{entry['category']}]"
        if gender:
            detail += f" pronoun={gender}"
        lines.append(detail)
    return "\n".join(lines)


def build_messages(title: str, body: str, glossary: list[dict[str, Any]]) -> list[dict[str, str]]:
    system = """
You translate Traditional Chinese web novel chapters into natural English.
Preserve meaning, tone, and all story content.
Use established glossary entries exactly.
Do not leave Chinese characters in the English title or body.

Context over Dictionary: Always deduce the entity type and domain from the
provided context, including surrounding text and sibling terms in a cluster.
Prioritize structural alignment with existing translations over generic
dictionary lookups.

Translate vs Transliterate: Fully translate objects, artifacts, techniques,
and fictional organizations into English. Keep character names and established
real-world proper nouns romanized.

World-Building Context: Do not blindly map terms to real-world locations if
the text is a fantasy or historical setting. For example, translate 京都 as
"The Capital" or "Imperial Capital" rather than "Kyoto" unless the context
explicitly refers to the real-world city.

Honorifics & Address: Follow source language norms. Translate Chinese
honorifics to English, such as Senior Brother, Elder, Young Master. Retain
common Japanese honorifics, such as -san and -senpai, and Korean honorifics,
such as -ssi and sunbae, as romanized suffixes or words.

Return only valid JSON with:
{
  "translated_title": "English title",
  "translated_body": "English body with paragraph breaks"
}
""".strip()
    user = f"""
Established glossary:
{glossary_prompt(glossary)}

Chapter title:
{title}

Chapter body:
{body}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_glossary_messages(
    title: str, body: str, glossary: list[dict[str, Any]]
) -> list[dict[str, str]]:
    system = """
You extract glossary entries from Traditional Chinese web novel chapters.
Use context over dictionary lookup: deduce entity type and domain from
surrounding text and sibling terms, and align structurally with existing
translations.

Translate vs Transliterate: Fully translate objects, artifacts, techniques,
and fictional organizations into English. Keep character names and established
real-world proper nouns romanized.

World-Building Context: Do not blindly map terms to real-world locations in a
fantasy or historical setting. Translate 京都 as "The Capital" or "Imperial
Capital" unless the context explicitly refers to the real-world city.

Honorifics & Address: Translate Chinese honorifics to English, such as Senior
Brother, Elder, Young Master. Retain common Japanese honorifics, such as -san
and -senpai, and Korean honorifics, such as -ssi and sunbae, as romanized
suffixes or words.

Return only valid JSON with:
{
  "glossary_updates": [
    {
      "source_term": "original term",
      "english_term": "consistent English rendering",
      "category": "character|place|sect|clan|organization|school|faction|realm|rank|system|worldbuilding|technique|spell|artifact|weapon|formation|pill|treasure|title|address|proper_noun",
      "gender_or_pronoun": "male|female|unknown|it|"
    }
  ]
}

Add entries only for character names, places, sects/clans/organizations,
cultivation realms/ranks/systems, recurring worldbuilding terms, techniques,
spells, artifacts, weapons, formations, pills, treasures, special proper nouns,
recurring address forms/titles, and inferable character gender/pronoun facts.
Do not add ordinary vocabulary, one-off descriptive phrases, full sentences,
common verbs/adjectives/adverbs, or obvious translations unlikely to need
consistency.
""".strip()
    user = f"""
Existing glossary entries to preserve:
{glossary_prompt(glossary)}

Chapter title:
{title}

Chapter body:
{body}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def call_deepseek(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    opener: Any = urllib.request.urlopen,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "thinking": {"type": "disabled"},
        "temperature": 0.3,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        DEEPSEEK_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=180) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AppError(f"DeepSeek request failed: HTTP {exc.code} {detail}", 502) from exc
    except urllib.error.URLError as exc:
        raise AppError(f"DeepSeek request failed: {exc.reason}", 502) from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError("DeepSeek returned invalid API JSON.", 502) from exc


def parse_translation_response(data: dict[str, Any]) -> dict[str, Any]:
    if "choices" in data:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AppError("DeepSeek response did not include message content.", 502) from exc
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AppError("DeepSeek message was not valid translation JSON.", 502) from exc

    title = data.get("translated_title")
    body = data.get("translated_body")
    if not isinstance(title, str) or not title.strip():
        raise AppError("Translation JSON is missing translated_title.", 502)
    if not isinstance(body, str) or not body.strip():
        raise AppError("Translation JSON is missing translated_body.", 502)
    if contains_cjk(title) or contains_cjk(body):
        raise AppError(
            "Translation still contains Chinese characters; not saving partial output.",
            502,
        )

    return {
        "translated_title": title.strip(),
        "translated_body": body.strip(),
    }


def response_message_content(data: dict[str, Any]) -> str:
    if "choices" in data:
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise AppError("DeepSeek response did not include message content.", 502) from exc
    return json.dumps(data, ensure_ascii=False)


def cjk_fragments(value: str) -> list[str]:
    seen: set[str] = set()
    fragments = []
    for match in CJK_FRAGMENT_RE.finditer(value):
        fragment = match.group(0)
        if fragment not in seen:
            seen.add(fragment)
            fragments.append(fragment)
    return fragments


def context_window(value: str, fragment: str, size: int = 80) -> str:
    index = value.find(fragment)
    if index < 0:
        return ""
    start = max(0, index - size)
    end = min(len(value), index + len(fragment) + size)
    return value[start:end].replace("\n", "\\n")


def source_contexts_for_fragment(source_text: str, fragment: str, limit: int = 2) -> list[str]:
    contexts = []
    start = 0
    while len(contexts) < limit:
        index = source_text.find(fragment, start)
        if index < 0:
            break
        begin = max(0, index - 80)
        end = min(len(source_text), index + len(fragment) + 80)
        contexts.append(source_text[begin:end].replace("\n", "\\n"))
        start = index + len(fragment)
    return contexts


def build_fragment_repair_messages(
    title: str, body: str, draft_json: str
) -> list[dict[str, str]]:
    fragments = cjk_fragments(draft_json)
    source_text = f"{title}\n\n{body}"
    items = [
        {
            "fragment": fragment,
            "draft_context": context_window(draft_json, fragment),
            "source_context": source_contexts_for_fragment(source_text, fragment),
        }
        for fragment in fragments
    ]
    system = """
You replace untranslated Chinese fragments in an English novel translation.
Return only valid JSON with a replacements array.
For each fragment, provide a natural English replacement based on context.
Do not use Chinese Han characters in replacements.
Do not include explanations.
""".strip()
    user = json.dumps({"fragments": items}, ensure_ascii=False, indent=2)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_fragment_replacements(data: dict[str, Any]) -> dict[str, str]:
    if "choices" in data:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AppError("DeepSeek response did not include replacements.", 502) from exc
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AppError("DeepSeek message was not valid replacement JSON.", 502) from exc

    replacements = data.get("replacements")
    if not isinstance(replacements, list):
        raise AppError("Replacement JSON is missing replacements.", 502)

    parsed = {}
    for item in replacements:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", item.get("fragment", ""))).strip()
        replacement = str(item.get("replacement", "")).strip()
        if source and replacement and not contains_cjk(replacement):
            parsed[source] = replacement
    if not parsed:
        raise AppError("Replacement JSON did not include usable replacements.", 502)
    return parsed


def apply_fragment_replacements(draft_json: str, replacements: dict[str, str]) -> str:
    repaired = draft_json
    for source in sorted(replacements, key=len, reverse=True):
        repaired = repaired.replace(source, replacements[source])
    return repaired


def build_repair_messages(title: str, body: str, draft_json: str) -> list[dict[str, str]]:
    system = """
You repair English novel translation JSON.
Return only valid JSON with translated_title and translated_body.
Do not leave any Chinese Han characters anywhere in those values.
Translate remaining Chinese fragments into natural English from context.
Do not summarize, omit content, or rewrite unrelated translated text.
""".strip()
    user = f"""
This JSON translation still contains Chinese characters. Repair only the
untranslated Chinese fragments.

Original chapter title:
{title}

Original chapter body for context:
{body}

Draft JSON to repair:
{draft_json}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_glossary_response(data: dict[str, Any]) -> list[dict[str, Any]]:
    if "choices" in data:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AppError("DeepSeek response did not include glossary content.", 502) from exc
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AppError("DeepSeek message was not valid glossary JSON.", 502) from exc

    updates = data.get("glossary_updates")
    if not isinstance(updates, list):
        raise AppError("Glossary JSON is missing glossary_updates.", 502)
    return [item for item in updates if isinstance(item, dict)]


def write_translation(novel: str, filename: str, title: str, body: str) -> Path:
    target = translated_path(novel, filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{title}\n\n{body}\n", encoding="utf-8")
    return target


def populate_glossary_for_chapter(
    novel: str,
    filename: str,
    call_api: Any = call_deepseek,
) -> list[dict[str, str]]:
    config = load_config()
    if not config["api_key"]:
        raise AppError("DeepSeek API key is not configured.")

    original = source_path(novel, filename).read_text(encoding="utf-8")
    title, body = split_chapter(original)

    with state_lock:
        glossary = load_glossary()
    messages = build_glossary_messages(title, body, glossary)
    api_response = call_api(config["api_key"], config["glossary_model"], messages)
    updates = parse_glossary_response(api_response)

    with state_lock:
        merged = merge_glossary_entries(load_glossary(), updates)
        write_json(GLOSSARY_PATH, merged)
    return merged


def translate_chapter(
    novel: str,
    filename: str,
    call_api: Any = call_deepseek,
    populate_glossary: bool = True,
) -> dict[str, Any]:
    config = load_config()
    if not config["api_key"]:
        raise AppError("DeepSeek API key is not configured.")

    original = source_path(novel, filename).read_text(encoding="utf-8")
    title, body = split_chapter(original)

    glossary = populate_glossary_for_chapter(novel, filename, call_api) if populate_glossary else load_glossary()
    messages = build_messages(title, body, glossary)
    api_response = call_api(config["api_key"], config["translation_model"], messages)
    try:
        parsed = parse_translation_response(api_response)
    except AppError as exc:
        if "still contains Chinese characters" not in str(exc):
            raise
        draft_json = response_message_content(api_response)
        try:
            fragment_response = call_api(
                config["api_key"],
                config["translation_model"],
                build_fragment_repair_messages(title, body, draft_json),
            )
            compact_json = apply_fragment_replacements(
                draft_json, parse_fragment_replacements(fragment_response)
            )
            parsed = parse_translation_response(json.loads(compact_json))
        except (AppError, json.JSONDecodeError):
            repair_messages = build_repair_messages(title, body, draft_json)
            repair_response = call_api(
                config["api_key"], config["translation_model"], repair_messages
            )
            parsed = parse_translation_response(repair_response)

    with state_lock:
        current_glossary = load_glossary()
        output = write_translation(
            novel, filename, parsed["translated_title"], parsed["translated_body"]
        )

    return {
        "filename": filename,
        "translated": output.read_text(encoding="utf-8"),
        "output_path": str(output),
        "glossary": current_glossary,
    }


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Novel Translator</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #20242a;
      --muted: #626b76;
      --line: #d8dde5;
      --accent: #1f7a63;
      --accent-strong: #155946;
      --danger: #b42318;
      --done: #e7f4ef;
      --pending: #f2ece0;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 14px 20px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      position: sticky;
      top: 0;
      z-index: 2;
    }
    h1 { margin: 0; font-size: 18px; font-weight: 650; }
    main {
      display: grid;
      grid-template-columns: 300px minmax(0, 1fr) 380px;
      min-height: calc(100vh - 58px);
    }
    aside, section {
      min-width: 0;
      padding: 16px;
      border-right: 1px solid var(--line);
    }
    section:last-child { border-right: 0; }
    label {
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
      margin: 0 0 6px;
    }
    input, select, textarea, button {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      font: inherit;
    }
    input, select { height: 36px; padding: 0 10px; }
    textarea {
      min-height: 220px;
      padding: 10px;
      resize: vertical;
      white-space: pre-wrap;
    }
    button {
      height: 36px;
      cursor: pointer;
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
      font-weight: 650;
    }
    button.secondary {
      background: #fff;
      border-color: var(--line);
      color: var(--text);
    }
    button.danger {
      background: #fff;
      border-color: #f1b8b1;
      color: var(--danger);
    }
    button:disabled {
      opacity: .55;
      cursor: wait;
    }
    .stack { display: grid; gap: 12px; }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .chapters {
      display: grid;
      gap: 6px;
      margin-top: 12px;
      max-height: calc(100vh - 260px);
      overflow: auto;
    }
    .chapter {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      align-items: center;
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      text-align: left;
      color: var(--text);
      font-weight: 500;
    }
    .chapter.active { border-color: var(--accent); outline: 2px solid #d6eee7; }
    .badge {
      border-radius: 999px;
      padding: 2px 7px;
      font-size: 11px;
      color: var(--muted);
      background: var(--pending);
      white-space: nowrap;
    }
    .badge.done { background: var(--done); color: var(--accent-strong); }
    .readers {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      height: calc(100vh - 134px);
    }
    .reader {
      display: grid;
      grid-template-rows: auto 1fr;
      gap: 8px;
      min-height: 0;
    }
    .reader textarea { height: 100%; min-height: 0; }
    .status {
      color: var(--muted);
      min-height: 20px;
      overflow-wrap: anywhere;
    }
    .status.error { color: var(--danger); }
    table {
      width: 100%;
      border-collapse: collapse;
      background: #fff;
      border: 1px solid var(--line);
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 6px;
      vertical-align: top;
    }
    th {
      color: var(--muted);
      font-size: 12px;
      text-align: left;
      font-weight: 650;
      background: #fafbfc;
    }
    td input, td select { height: 30px; padding: 0 7px; }
    .glossary-wrap {
      max-height: calc(100vh - 210px);
      overflow: auto;
      border: 1px solid var(--line);
      background: #fff;
    }
    .glossary-wrap table { border: 0; }
    .tiny { width: 44px; }
    @media (max-width: 1100px) {
      main { grid-template-columns: 280px minmax(0, 1fr); }
      section.glossary-panel { grid-column: 1 / -1; border-top: 1px solid var(--line); }
      .glossary-wrap { max-height: 360px; }
    }
    @media (max-width: 760px) {
      header, main, .readers, .row { display: block; }
      aside, section { border-right: 0; border-bottom: 1px solid var(--line); }
      .readers { height: auto; }
      .reader { margin-bottom: 12px; }
      textarea { min-height: 260px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Novel Translator</h1>
    <div class="status" id="status"></div>
  </header>
  <main>
    <aside class="stack">
      <div>
        <label for="apiKey">DeepSeek API key</label>
        <div class="row">
          <input id="apiKey" type="password" autocomplete="off">
          <button id="saveConfig">Save</button>
        </div>
      </div>
      <div>
        <label for="glossaryModel">Glossary model</label>
        <select id="glossaryModel">
          <option value="deepseek-v4-pro">deepseek-v4-pro</option>
          <option value="deepseek-v4-flash">deepseek-v4-flash</option>
        </select>
      </div>
      <div>
        <label for="translationModel">Translation model</label>
        <select id="translationModel">
          <option value="deepseek-v4-flash">deepseek-v4-flash</option>
          <option value="deepseek-v4-pro">deepseek-v4-pro</option>
        </select>
      </div>
      <div>
        <label for="novel">Novel</label>
        <select id="novel"></select>
      </div>
      <button id="translate">Translate Selected Chapter</button>
      <button class="secondary" id="translateOnly">Translate Only</button>
      <div class="chapters" id="chapters"></div>
    </aside>
    <section class="stack">
      <div class="readers">
        <div class="reader">
          <label for="source">Source</label>
          <textarea id="source" readonly></textarea>
        </div>
        <div class="reader">
          <label for="translated">Translation</label>
          <textarea id="translated" readonly></textarea>
        </div>
      </div>
    </section>
    <section class="glossary-panel stack">
      <div class="row">
        <button class="secondary" id="addEntry">Add Entry</button>
        <button id="saveGlossary">Save Glossary</button>
      </div>
      <div class="glossary-wrap">
        <table>
          <thead>
            <tr>
              <th>Source</th>
              <th>English</th>
              <th>Category</th>
              <th>Pronoun</th>
              <th></th>
            </tr>
          </thead>
          <tbody id="glossary"></tbody>
        </table>
      </div>
    </section>
  </main>
  <script>
    const categories = [
      "character","place","sect","clan","organization","school","faction",
      "realm","rank","system","worldbuilding","technique","spell","artifact",
      "weapon","formation","pill","treasure","title","address","proper_noun"
    ];
    const pronouns = ["", "male", "female", "unknown", "it"];
    const state = { novel: "", file: "", busy: false };

    const $ = id => document.getElementById(id);

    function setStatus(text, isError = false) {
      $("status").textContent = text || "";
      $("status").className = isError ? "status error" : "status";
    }

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Request failed");
      return data;
    }

    async function loadConfig() {
      const config = await api("/api/config");
      $("translationModel").value = config.translation_model;
      $("glossaryModel").value = config.glossary_model;
      $("apiKey").placeholder = config.has_api_key ? config.api_key_mask : "";
    }

    async function saveConfig() {
      const apiKey = $("apiKey").value.trim();
      const current = await api("/api/config");
      await api("/api/config", {
        method: "POST",
        body: JSON.stringify({
          api_key: apiKey || undefined,
          keep_existing_key: !apiKey && current.has_api_key,
          translation_model: $("translationModel").value,
          glossary_model: $("glossaryModel").value
        })
      });
      $("apiKey").value = "";
      await loadConfig();
      setStatus("Config saved.");
    }

    async function loadNovels() {
      const novels = await api("/api/novels");
      $("novel").innerHTML = novels.map(name => `<option>${escapeHtml(name)}</option>`).join("");
      state.novel = novels[0] || "";
      if (state.novel) {
        $("novel").value = state.novel;
        await loadChapters();
      }
    }

    async function loadChapters() {
      state.novel = $("novel").value;
      state.file = "";
      $("source").value = "";
      $("translated").value = "";
      const chapters = await api(`/api/chapters?novel=${encodeURIComponent(state.novel)}`);
      $("chapters").innerHTML = "";
      for (const chapter of chapters) {
        const button = document.createElement("button");
        button.className = "chapter";
        button.type = "button";
        button.dataset.file = chapter.filename;
        button.innerHTML = `<span>${escapeHtml(chapter.title)}</span><span class="badge ${chapter.translated ? "done" : ""}">${chapter.translated ? "done" : "new"}</span>`;
        button.addEventListener("click", () => selectChapter(chapter.filename));
        $("chapters").appendChild(button);
      }
      if (chapters[0]) await selectChapter(chapters[0].filename);
    }

    async function selectChapter(filename) {
      state.file = filename;
      for (const node of document.querySelectorAll(".chapter")) {
        node.classList.toggle("active", node.dataset.file === filename);
      }
      const chapter = await api(`/api/chapter?novel=${encodeURIComponent(state.novel)}&file=${encodeURIComponent(filename)}`);
      $("source").value = chapter.source;
      $("translated").value = chapter.translated;
      setStatus(chapter.translated_exists ? "Loaded existing translation." : "Loaded source chapter.");
    }

    async function translateSelected() {
      if (!state.novel || !state.file || state.busy) return;
      state.busy = true;
      $("translate").disabled = true;
      $("translateOnly").disabled = true;
      setStatus("Populating glossary, then translating...");
      try {
        const result = await api("/api/translate", {
          method: "POST",
          body: JSON.stringify({ novel: state.novel, file: state.file })
        });
        $("translated").value = result.translated;
        renderGlossary(result.glossary);
        await loadChapters();
        await selectChapter(result.filename);
        setStatus(`Saved ${result.output_path}`);
      } catch (error) {
        setStatus(error.message, true);
      } finally {
        state.busy = false;
        $("translate").disabled = false;
        $("translateOnly").disabled = false;
      }
    }

    async function translateOnlySelected() {
      if (!state.novel || !state.file || state.busy) return;
      state.busy = true;
      $("translate").disabled = true;
      $("translateOnly").disabled = true;
      setStatus("Translating with current glossary...");
      try {
        const result = await api("/api/translate-only", {
          method: "POST",
          body: JSON.stringify({ novel: state.novel, file: state.file })
        });
        $("translated").value = result.translated;
        renderGlossary(result.glossary);
        await loadChapters();
        await selectChapter(result.filename);
        setStatus(`Saved ${result.output_path}`);
      } catch (error) {
        setStatus(error.message, true);
      } finally {
        state.busy = false;
        $("translate").disabled = false;
        $("translateOnly").disabled = false;
      }
    }

    async function loadGlossary() {
      renderGlossary(await api("/api/glossary"));
    }

    function renderGlossary(entries) {
      $("glossary").innerHTML = "";
      for (const entry of entries) addGlossaryRow(entry);
    }

    function addGlossaryRow(entry = {}) {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td><input value="${escapeAttr(entry.source_term || "")}"></td>
        <td><input value="${escapeAttr(entry.english_term || "")}"></td>
        <td><select>${categories.map(c => `<option value="${c}" ${entry.category === c ? "selected" : ""}>${c}</option>`).join("")}</select></td>
        <td><select>${pronouns.map(p => `<option value="${p}" ${entry.gender_or_pronoun === p ? "selected" : ""}>${p}</option>`).join("")}</select></td>
        <td><button type="button" class="danger tiny">X</button></td>
      `;
      row.querySelector("button").addEventListener("click", () => row.remove());
      $("glossary").appendChild(row);
    }

    function collectGlossary() {
      return Array.from($("glossary").querySelectorAll("tr")).map(row => {
        const inputs = row.querySelectorAll("input");
        const selects = row.querySelectorAll("select");
        return {
          source_term: inputs[0].value.trim(),
          english_term: inputs[1].value.trim(),
          category: selects[0].value,
          gender_or_pronoun: selects[1].value
        };
      }).filter(entry => entry.source_term && entry.english_term);
    }

    async function saveGlossary() {
      const saved = await api("/api/glossary", {
        method: "POST",
        body: JSON.stringify({ entries: collectGlossary() })
      });
      renderGlossary(saved);
      setStatus("Glossary saved.");
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, char => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[char]));
    }

    function escapeAttr(value) {
      return escapeHtml(value);
    }

    $("saveConfig").addEventListener("click", () => saveConfig().catch(error => setStatus(error.message, true)));
    $("novel").addEventListener("change", () => loadChapters().catch(error => setStatus(error.message, true)));
    $("translate").addEventListener("click", translateSelected);
    $("translateOnly").addEventListener("click", translateOnlySelected);
    $("addEntry").addEventListener("click", () => addGlossaryRow({ category: "proper_noun" }));
    $("saveGlossary").addEventListener("click", () => saveGlossary().catch(error => setStatus(error.message, true)));

    Promise.all([loadConfig(), loadNovels(), loadGlossary()]).catch(error => setStatus(error.message, true));
  </script>
</body>
</html>
"""


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
            if method == "GET" and parsed.path == "/":
                self.html(INDEX_HTML)
                return
            if parsed.path == "/api/config":
                self.handle_config(method)
                return
            if method == "GET" and parsed.path == "/api/novels":
                self.json(list_novels())
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
                self.handle_glossary(method)
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

    def handle_glossary(self, method: str) -> None:
        if method == "GET":
            self.json(load_glossary())
            return
        if method != "POST":
            raise AppError("Method not allowed.", 405)
        data = self.body_json()
        entries = data.get("entries", [])
        if not isinstance(entries, list):
            raise AppError("entries must be a list.")
        self.json(save_glossary(entries))

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
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def html(self, content: str, status: int = 200) -> None:
        raw = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def first(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key)
    return values[0] if values else ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local novel translator app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    TRANSLATED_ROOT.mkdir(exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Novel Translator running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
