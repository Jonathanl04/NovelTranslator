import json
import threading
import uuid
from typing import Any, Callable

from .chapters import source_path, split_chapter, write_translation
from .config import load_config
from .codex_backend import (
    CODEX_PREMATURE_RESPONSE_MESSAGE,
    CODEX_TIMEOUT_MESSAGE,
    call_codex,
)
from .openrouter import OPENROUTER_TIMEOUT_MESSAGE, call_openrouter
from .errors import AppError
from .failure_log import log_llm_failure
from .glossary import glossary_path, glossary_prompt, load_glossary, merge_glossary_entries
from .glossary_strategy import recent_glossary_for_chapter
from .json_store import write_json
from .llm_schemas import FRAGMENT_REPLACEMENTS_SCHEMA, GLOSSARY_SCHEMA, TRANSLATION_SCHEMA
from .translation_prompts import (
    SHARED_PROMPT_PREFIX,
    build_cached_prefix,
    build_glossary_messages,
    build_invalid_glossary_json_retry_messages,
    build_messages,
)
from .translation_responses import (
    INCOMPLETE_TRANSLATION_MESSAGE,
    INVALID_GLOSSARY_JSON_MESSAGE,
    INVALID_TRANSLATION_JSON_MESSAGE,
    apply_fragment_replacements,
    build_fragment_repair_messages,
    build_incomplete_translation_retry_messages,
    build_invalid_translation_json_retry_messages,
    build_repair_messages,
    context_window,
    parse_fragment_replacements,
    parse_glossary_response,
    parse_translation_response,
    response_message_content,
)
state_lock = threading.Lock()
TRANSLATION_JSON_RETRIES = 2

def configured_api_call(
    call_api: Any,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    provider: str = "",
    backend: str = "openrouter",
    codex_model: str = "",
    output_schema: dict[str, Any] | None = None,
    codex_cache_key: str = "",
    reasoning_effort: str = "none",
    codex_fast_mode: bool = False,
) -> dict[str, Any]:
    if call_api is call_openrouter and backend == "codex":
        if output_schema is None:
            raise AppError("Codex requests require an output schema.", 500)
        return call_codex(
            codex_model,
            messages,
            output_schema,
            codex_cache_key,
            reasoning_effort,
            codex_fast_mode,
        )
    if provider and call_api is call_openrouter:
        return call_api(
            api_key,
            model,
            messages,
            provider,
            output_schema=output_schema,
            reasoning_effort=reasoning_effort,
        )
    if call_api is call_openrouter:
        return call_api(
            api_key,
            model,
            messages,
            output_schema=output_schema,
            reasoning_effort=reasoning_effort,
        )
    return call_api(api_key, model, messages)


def codex_cache_key(novel: str, workload: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"novel-translator:{workload}:{novel}"))


def require_workload_backend(config: dict[str, Any], workload: str) -> None:
    backend = config[f"{workload}_backend"]
    if backend == "openrouter" and not config["openrouter_api_key"]:
        raise AppError("OpenRouter API key is not configured.")
    if backend == "codex" and not config[f"codex_{workload}_model"]:
        raise AppError(f"Codex {workload} model is not configured.")


def llm_request_payload(model: str, messages: list[dict[str, str]]) -> dict[str, Any]:
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
    log_llm_failure(event, llm_request_payload(model, messages), str(error), response=response)


def is_retryable_translation_request_error(error: AppError) -> bool:
    message = str(error)
    return (
        OPENROUTER_TIMEOUT_MESSAGE in message
        or CODEX_TIMEOUT_MESSAGE in message
        or CODEX_PREMATURE_RESPONSE_MESSAGE in message
    )


def populate_glossary_for_chapter(
    novel: str,
    filename: str,
    call_api: Any = call_openrouter,
    should_abort: Callable[[], bool] | None = None,
    defer_existing_updates: bool = False,
    deferred_existing_updates: list[dict[str, Any]] | None = None,
    prompt_glossary: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    config = load_config()
    api_key = config["openrouter_api_key"]
    require_workload_backend(config, "glossary")

    original = source_path(novel, filename).read_text(encoding="utf-8")
    title, body = split_chapter(original)

    with state_lock:
        glossary = load_glossary(novel)
    if prompt_glossary is None and config.get("glossary_strategy", "full") == "rolling":
        prompt_glossary = recent_glossary_for_chapter(
            novel, filename, original, glossary
        )
    messages = build_glossary_messages(
        title, body, glossary if prompt_glossary is None else prompt_glossary
    )
    retry_messages = messages
    api_response: dict[str, Any] = {}
    if should_abort and should_abort():
        raise AppError("Bulk translation aborted.", 409)
    try:
        for retry_index in range(TRANSLATION_JSON_RETRIES + 1):
            if should_abort and should_abort():
                raise AppError("Bulk translation aborted.", 409)
            api_response = configured_api_call(
                call_api,
                api_key,
                config["glossary_model"],
                retry_messages,
                config["glossary_provider"],
                config["glossary_backend"],
                config["codex_glossary_model"],
                GLOSSARY_SCHEMA,
                codex_cache_key(novel, "glossary"),
                config["glossary_reasoning_effort"],
                config["codex_fast_mode"],
            )
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
        current_glossary = load_glossary(novel)
        if defer_existing_updates:
            existing_sources = {
                str(entry.get("source_term", "")).strip()
                for entry in current_glossary
                if str(entry.get("source_term", "")).strip()
            }
            new_updates = []
            existing_updates = []
            for update in updates:
                source_term = str(update.get("source_term", "")).strip()
                if source_term and source_term in existing_sources:
                    existing_updates.append(update)
                else:
                    new_updates.append(update)
            merged = merge_glossary_entries(current_glossary, new_updates)
            if deferred_existing_updates is not None:
                deferred_existing_updates.extend(existing_updates)
        else:
            merged = merge_glossary_entries(current_glossary, updates)
        write_json(glossary_path(novel), merged)
    return merged


def translate_chapter(
    novel: str,
    filename: str,
    call_api: Any = call_openrouter,
    populate_glossary: bool = True,
    should_abort: Callable[[], bool] | None = None,
    defer_existing_glossary_updates: bool = False,
    deferred_existing_glossary_updates: list[dict[str, Any]] | None = None,
    glossary_prompt_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    config = load_config()
    api_key = config["openrouter_api_key"]
    require_workload_backend(config, "translation")

    original = source_path(novel, filename).read_text(encoding="utf-8")
    title, body = split_chapter(original)

    glossary = (
        populate_glossary_for_chapter(
            novel,
            filename,
            call_api,
            should_abort=should_abort,
            defer_existing_updates=defer_existing_glossary_updates,
            deferred_existing_updates=deferred_existing_glossary_updates,
            prompt_glossary=glossary_prompt_entries,
        )
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
                api_response = configured_api_call(
                    call_api,
                    api_key,
                    config["translation_model"],
                    retry_messages,
                    config["translation_provider"],
                    config["translation_backend"],
                    config["codex_translation_model"],
                    TRANSLATION_SCHEMA,
                    codex_cache_key(novel, "translation"),
                    config["translation_reasoning_effort"],
                    config["codex_fast_mode"],
                )
            except AppError as exc:
                if not is_retryable_translation_request_error(exc) or retry_index == TRANSLATION_JSON_RETRIES:
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
            fragment_response = configured_api_call(
                call_api,
                api_key,
                config["translation_model"],
                build_fragment_repair_messages(retry_messages, draft_json),
                config["translation_provider"],
                config["translation_backend"],
                config["codex_translation_model"],
                FRAGMENT_REPLACEMENTS_SCHEMA,
                reasoning_effort=config["translation_reasoning_effort"],
                codex_fast_mode=config["codex_fast_mode"],
            )
            if should_abort and should_abort():
                raise AppError("Bulk translation aborted.", 409)
            compact_json = apply_fragment_replacements(
                draft_json, parse_fragment_replacements(fragment_response)
            )
            parsed = parse_translation_response(json.loads(compact_json))
        except (AppError, json.JSONDecodeError) as exc:
            log_llm_failure(
                "fragment_repair_parse_error",
                llm_request_payload(config["translation_model"], build_fragment_repair_messages(retry_messages, draft_json)),
                str(exc),
                response=locals().get("fragment_response"),
            )
            repair_messages = build_repair_messages(title, body, draft_json)
            if should_abort and should_abort():
                raise AppError("Bulk translation aborted.", 409)
            repair_response = configured_api_call(
                call_api,
                api_key,
                config["translation_model"],
                repair_messages,
                config["translation_provider"],
                config["translation_backend"],
                config["codex_translation_model"],
                TRANSLATION_SCHEMA,
                reasoning_effort=config["translation_reasoning_effort"],
                codex_fast_mode=config["codex_fast_mode"],
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
