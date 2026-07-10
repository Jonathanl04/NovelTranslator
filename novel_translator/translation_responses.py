import json
from typing import Any

from .errors import AppError
from .source_language import contains_source_language_text, source_language_fragments

INVALID_TRANSLATION_JSON_MESSAGE = 'Model message was not valid translation JSON.'
INVALID_GLOSSARY_JSON_MESSAGE = 'Model message was not valid glossary JSON.'
INCOMPLETE_TRANSLATION_MESSAGE = 'Model returned an incomplete translation.'
MIN_SOURCE_LENGTH_FOR_INCOMPLETE_TRANSLATION_CHECK = 200
MIN_TRANSLATION_TO_SOURCE_RATIO = 0.8
MIN_TRANSLATION_LENGTH_FOR_FULL_CHAPTER = 200

def parse_translation_response(data: dict[str, Any], source_body: str = "") -> dict[str, Any]:
    if "choices" in data:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AppError("Model response did not include message content.", 502) from exc
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AppError("Model message was not valid translation JSON.", 502) from exc

    title = data.get("translated_title")
    body = data.get("translated_body")
    if not isinstance(title, str) or not title.strip():
        raise AppError("Translation JSON is missing translated_title.", 502)
    if not isinstance(body, str) or not body.strip():
        raise AppError("Translation JSON is missing translated_body.", 502)
    if contains_source_language_text(body) and is_incomplete_translation_body(source_body, body):
        raise AppError(INCOMPLETE_TRANSLATION_MESSAGE, 502)
    if contains_source_language_text(title) or contains_source_language_text(body):
        raise AppError(
            "Translation still contains Chinese or Korean source-language text; not saving partial output.",
            502,
        )

    return {
        "translated_title": title.strip(),
        "translated_body": body.strip(),
    }


def is_incomplete_translation_body(source_body: str, translated_body: str) -> bool:
    source_length = len(source_body.strip())
    translated_length = len(translated_body.strip())
    if source_length < MIN_SOURCE_LENGTH_FOR_INCOMPLETE_TRANSLATION_CHECK:
        return False
    return (
        translated_length < MIN_TRANSLATION_LENGTH_FOR_FULL_CHAPTER
        or translated_length < source_length * MIN_TRANSLATION_TO_SOURCE_RATIO
    )


def response_message_content(data: dict[str, Any]) -> str:
    if "choices" in data:
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise AppError("Model response did not include message content.", 502) from exc
    return json.dumps(data, ensure_ascii=False)


def context_window(value: str, fragment: str, size: int = 80) -> str:
    index = value.find(fragment)
    if index < 0:
        return ""
    start = max(0, index - size)
    end = min(len(value), index + len(fragment) + size)
    return value[start:end].replace("\n", "\\n")


def build_fragment_repair_messages(
    translation_messages: list[dict[str, str]], draft_json: str
) -> list[dict[str, str]]:
    fragments = source_language_fragments(draft_json)
    items = [
        {
            "fragment": fragment,
            "draft_context": context_window(draft_json, fragment),
        }
        for fragment in fragments
    ]
    instruction = f"""
The previous translation JSON still contains untranslated Chinese or Korean fragments.
Using the full source context and draft translation already present in this chat.
For each fragment, provide a natural English replacement based on context.
Do not use Chinese or Korean source-language text in replacements.
Do not include explanations.

Return only valid JSON with:
{{
  "replacements": [
    {{
      "fragment": "original term",
      "replacement": "English replacement"
    }}
  ]
}}
""".strip()
    user = instruction + "\n\n" + json.dumps({"fragments": items}, ensure_ascii=False, indent=2)
    return [
        *translation_messages,
        {"role": "assistant", "content": draft_json},
        {"role": "user", "content": user},
    ]


def build_invalid_translation_json_retry_messages(
    translation_messages: list[dict[str, str]], invalid_json: str
) -> list[dict[str, str]]:
    user = """
The previous message was not valid JSON and could not be parsed.
Please check it and resend the corrected translation as valid JSON only.
Return exactly the same schema with translated_title and translated_body.
Do not include explanations or Markdown.
""".strip()
    return [
        *translation_messages,
        {"role": "assistant", "content": invalid_json},
        {"role": "user", "content": user},
    ]


def build_incomplete_translation_retry_messages(
    translation_messages: list[dict[str, str]], incomplete_json: str
) -> list[dict[str, str]]:
    user = """
The previous did not provide a complete chapter translation.
It returned only a short body.
Please translate the entire original chapter again from the source context already present in this chat.
Return valid JSON only, with the complete translated_title and complete translated_body.
Do not include explanations or Markdown.
""".strip()
    return [
        *translation_messages,
        {"role": "assistant", "content": incomplete_json},
        {"role": "user", "content": user},
    ]


def parse_fragment_replacements(data: dict[str, Any]) -> dict[str, str]:
    if "choices" in data:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AppError("Model response did not include replacements.", 502) from exc
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AppError("Model message was not valid replacement JSON.", 502) from exc

    replacements = data.get("replacements")
    if not isinstance(replacements, list):
        raise AppError("Replacement JSON is missing replacements.", 502)

    parsed = {}
    for item in replacements:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", item.get("fragment", ""))).strip()
        replacement = str(item.get("replacement", "")).strip()
        if source and replacement and not contains_source_language_text(replacement):
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
Do not leave any Chinese or Korean source-language text anywhere in those values.
Translate remaining source-language fragments into natural English from context.
Do not summarize, omit content, or rewrite unrelated translated text.
""".strip()
    user = f"""
This JSON translation still contains Chinese or Korean source-language text.
Repair only the untranslated source-language fragments.

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
            raise AppError("Model response did not include glossary content.", 502) from exc
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AppError(INVALID_GLOSSARY_JSON_MESSAGE, 502) from exc

    updates = data.get("glossary_updates")
    if not isinstance(updates, list):
        raise AppError("Glossary JSON is missing glossary_updates.", 502)
    return [item for item in updates if isinstance(item, dict)]


