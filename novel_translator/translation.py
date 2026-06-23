import json
import threading
from typing import Any, Callable

from .chapters import source_path, split_chapter, write_translation
from .config import load_config
from .deepseek import DEEPSEEK_TIMEOUT_MESSAGE, call_deepseek
from .errors import AppError
from .failure_log import log_deepseek_failure
from .glossary import glossary_path, glossary_prompt, load_glossary, merge_glossary_entries
from .json_store import write_json
from .source_language import contains_source_language_text, source_language_fragments

state_lock = threading.Lock()
TRANSLATION_JSON_RETRIES = 2
INVALID_TRANSLATION_JSON_MESSAGE = "DeepSeek message was not valid translation JSON."
INVALID_GLOSSARY_JSON_MESSAGE = "DeepSeek message was not valid glossary JSON."
INCOMPLETE_TRANSLATION_MESSAGE = "DeepSeek returned an incomplete translation."
MIN_SOURCE_LENGTH_FOR_INCOMPLETE_TRANSLATION_CHECK = 200
MIN_TRANSLATION_TO_SOURCE_RATIO = 0.8
MIN_TRANSLATION_LENGTH_FOR_FULL_CHAPTER = 200

SHARED_PROMPT_PREFIX = """
You are working on web novel localization into English. 
Apply these rules consistently.

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

Honorifics & Address: Follow source language norms. Translate Chinese and
Korean honorifics to English. Retain common Japanese honorifics,
such as -san and -senpai, and Korean honorifics, such as -ssi and sunbae, as
romanized suffixes or words.

Cultural Adaptation: Adapt idioms, cultural references, and humor to their natural, 
culturally appropriate equivalents in the target language so they resonate correctly.

Syntax & Rhythm: Preserve the original text's unique sentence structure, cadence, 
and poetic flow as much as possible, while ensuring it sounds completely natural 
in the target language.

Handling Unsavable Nuances: If a metaphor or wordplay cannot be adapted naturally, 
translate it for overall narrative flow rather than adding clunky translator notes.
""".strip()


def build_cached_prefix(glossary: list[dict[str, Any]]) -> str:
    return f"""
{SHARED_PROMPT_PREFIX}

Established glossary:
{glossary_prompt(glossary)}
""".strip()


def glossary_entries_for_chapter(
    title: str, body: str, glossary: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    source_text = f"{title}\n{body}"
    return [
        entry
        for entry in glossary
        if str(entry.get("source_term", "")).strip()
        and str(entry.get("source_term", "")).strip() in source_text
    ]


def build_messages(title: str, body: str, glossary: list[dict[str, Any]]) -> list[dict[str, str]]:
    user = f"""
Task: Translate the provided chapter into English.
Preserve all story content.
Write fluent, idiomatic English prose that sounds like a published web novel,
not a literal line-by-line translation. Read the whole sentence and surrounding
paragraph before choosing phrasing.
For mental states, describe the actual attitude shown in context, such as
composure, resilience, calm, optimism, or determination; do not translate them
as awkward noun phrases, and avoid vague "good/bad" modifiers when a precise
English attitude word fits better.
You may restructure sentences, split or combine clauses, change passive voice to
active voice, and choose natural English idioms when they preserve the original
meaning, tone, and characterization.

Use established glossary entries exactly.
Do not leave Chinese or Korean source-language text in the English title or body.

Return only valid JSON with:
{{
  "translated_title": "English title",
  "translated_body": "English body with paragraph breaks"
}}

Chapter title:
{title}

Chapter body:
{body}
""".strip()
    chapter_glossary = glossary_entries_for_chapter(title, body, glossary)
    return [{"role": "system", "content": build_cached_prefix(chapter_glossary)}, {"role": "user", "content": user}]


def build_glossary_messages(
    title: str, body: str, glossary: list[dict[str, Any]]
) -> list[dict[str, str]]:
    user = f"""
Task: Extract glossary entries from the provided chapter.

Return only valid JSON with:
{{
  "glossary_updates": [
    {{
      "source_term": "original term",
      "english_term": "consistent English rendering",
      "category": "AI-chosen concise category label",
      "gender_or_pronoun": "male|female|unknown|it|"
    }}
  ]
}}

Add entries for character names, places, sects/clans/organizations,
cultivation realms/ranks/systems, recurring worldbuilding terms, techniques,
spells, artifacts, weapons, materials, formations, pills, treasures, special proper nouns,
recurring address forms/titles, inferable character gender/pronoun facts, and any any other words that needs to be kept consistent.
Choose each category from context as a concise lowercase label.
Do not add ordinary vocabulary, one-off descriptive phrases, full sentences,
common verbs/adjectives/adverbs, chapter titles, or obvious translations unlikely to need
consistency.
If all glossary candidates already exists, don't add any new words.

Chapter title:
{title}

Chapter body:
{body}
    """.strip()
    return [{"role": "system", "content": build_cached_prefix(glossary)}, {"role": "user", "content": user}]


def build_invalid_glossary_json_retry_messages(
    glossary_messages: list[dict[str, str]], invalid_json: str
) -> list[dict[str, str]]:
    user = """
The previous message was not valid JSON and could not be parsed.
Please check it and resend the glossary extraction as valid JSON only.
Return exactly the same schema with glossary_updates.
Do not include explanations or Markdown.
""".strip()
    return [
        *glossary_messages,
        {"role": "assistant", "content": invalid_json},
        {"role": "user", "content": user},
    ]


def deepseek_request_payload(model: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "model": model,
        "messages": messages,
        "thinking": {"type": "disabled"},
        "temperature": 1,
        "stream": False,
        "response_format": {"type": "json_object"},
    }


def log_parse_failure(
    event: str,
    model: str,
    messages: list[dict[str, str]],
    response: dict[str, Any],
    error: AppError,
) -> None:
    log_deepseek_failure(event, deepseek_request_payload(model, messages), str(error), response=response)


def is_retryable_translation_timeout(error: AppError) -> bool:
    return DEEPSEEK_TIMEOUT_MESSAGE in str(error)


def parse_translation_response(data: dict[str, Any], source_body: str = "") -> dict[str, Any]:
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
            raise AppError("DeepSeek response did not include message content.", 502) from exc
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
            raise AppError("DeepSeek response did not include glossary content.", 502) from exc
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AppError(INVALID_GLOSSARY_JSON_MESSAGE, 502) from exc

    updates = data.get("glossary_updates")
    if not isinstance(updates, list):
        raise AppError("Glossary JSON is missing glossary_updates.", 502)
    return [item for item in updates if isinstance(item, dict)]


def populate_glossary_for_chapter(
    novel: str,
    filename: str,
    call_api: Any = call_deepseek,
    should_abort: Callable[[], bool] | None = None,
) -> list[dict[str, str]]:
    config = load_config()
    if not config["api_key"]:
        raise AppError("OpenRouter API key is not configured.")

    original = source_path(novel, filename).read_text(encoding="utf-8")
    title, body = split_chapter(original)

    with state_lock:
        glossary = load_glossary(novel)
    messages = build_glossary_messages(title, body, glossary)
    retry_messages = messages
    api_response: dict[str, Any] = {}
    if should_abort and should_abort():
        raise AppError("Bulk translation aborted.", 409)
    try:
        for retry_index in range(TRANSLATION_JSON_RETRIES + 1):
            if should_abort and should_abort():
                raise AppError("Bulk translation aborted.", 409)
            api_response = call_api(config["api_key"], config["glossary_model"], retry_messages)
            try:
                updates = parse_glossary_response(api_response)
                break
            except AppError as exc:
                log_parse_failure("glossary_parse_error", config["glossary_model"], retry_messages, api_response, exc)
                if INVALID_GLOSSARY_JSON_MESSAGE not in str(exc) or retry_index == TRANSLATION_JSON_RETRIES:
                    raise
                retry_messages = build_invalid_glossary_json_retry_messages(
                    retry_messages, response_message_content(api_response)
                )
    except AppError:
        raise
    if should_abort and should_abort():
        raise AppError("Bulk translation aborted.", 409)

    with state_lock:
        merged = merge_glossary_entries(load_glossary(novel), updates)
        write_json(glossary_path(novel), merged)
    return merged


def translate_chapter(
    novel: str,
    filename: str,
    call_api: Any = call_deepseek,
    populate_glossary: bool = True,
    should_abort: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    config = load_config()
    if not config["api_key"]:
        raise AppError("OpenRouter API key is not configured.")

    original = source_path(novel, filename).read_text(encoding="utf-8")
    title, body = split_chapter(original)

    glossary = (
        populate_glossary_for_chapter(novel, filename, call_api, should_abort=should_abort)
        if populate_glossary
        else load_glossary(novel)
    )
    messages = build_messages(title, body, glossary)
    retry_messages = messages
    try:
        for retry_index in range(TRANSLATION_JSON_RETRIES + 1):
            if should_abort and should_abort():
                raise AppError("Bulk translation aborted.", 409)
            try:
                api_response = call_api(
                    config["api_key"], config["translation_model"], retry_messages
                )
            except AppError as exc:
                if not is_retryable_translation_timeout(exc) or retry_index == TRANSLATION_JSON_RETRIES:
                    raise
                continue
            try:
                parsed = parse_translation_response(api_response, body)
                break
            except AppError as exc:
                log_parse_failure("translation_parse_error", config["translation_model"], retry_messages, api_response, exc)
                if (
                    INVALID_TRANSLATION_JSON_MESSAGE not in str(exc)
                    and INCOMPLETE_TRANSLATION_MESSAGE not in str(exc)
                ) or retry_index == TRANSLATION_JSON_RETRIES:
                    raise
                retry_content = response_message_content(api_response)
                if INCOMPLETE_TRANSLATION_MESSAGE in str(exc):
                    retry_messages = build_incomplete_translation_retry_messages(
                        retry_messages, retry_content
                    )
                else:
                    retry_messages = build_invalid_translation_json_retry_messages(
                        retry_messages, retry_content
                    )
    except AppError as exc:
        if "still contains Chinese or Korean source-language text" not in str(exc):
            raise
        draft_json = response_message_content(api_response)
        try:
            fragment_response = call_api(
                config["api_key"],
                config["translation_model"],
                build_fragment_repair_messages(retry_messages, draft_json),
            )
            if should_abort and should_abort():
                raise AppError("Bulk translation aborted.", 409)
            compact_json = apply_fragment_replacements(
                draft_json, parse_fragment_replacements(fragment_response)
            )
            parsed = parse_translation_response(json.loads(compact_json))
        except (AppError, json.JSONDecodeError) as exc:
            log_deepseek_failure(
                "fragment_repair_parse_error",
                deepseek_request_payload(config["translation_model"], build_fragment_repair_messages(retry_messages, draft_json)),
                str(exc),
                response=locals().get("fragment_response"),
            )
            repair_messages = build_repair_messages(title, body, draft_json)
            if should_abort and should_abort():
                raise AppError("Bulk translation aborted.", 409)
            repair_response = call_api(
                config["api_key"], config["translation_model"], repair_messages
            )
            try:
                parsed = parse_translation_response(repair_response)
            except AppError as exc:
                log_parse_failure("full_repair_parse_error", config["translation_model"], repair_messages, repair_response, exc)
                raise

    with state_lock:
        if should_abort and should_abort():
            raise AppError("Bulk translation aborted.", 409)
        current_glossary = load_glossary(novel)
        output = write_translation(
            novel, filename, parsed["translated_title"], parsed["translated_body"]
        )

    return {
        "filename": filename,
        "translated": output.read_text(encoding="utf-8"),
        "output_path": str(output),
        "glossary": current_glossary,
    }
