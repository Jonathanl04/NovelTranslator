from novel_translator.bulk_translate import get_bulk_state, load_bulk_state, save_bulk_state, start_bulk_translation
from novel_translator.chapters import (
    chapter_label,
    cover_path,
    list_chapters,
    list_novels,
    novel_metadata,
    read_chapter,
    safe_segment,
    source_path,
    split_chapter,
    translated_path,
    write_translation,
)
from novel_translator.config import load_config, mask_key, public_config, safe_file_stem, save_config
from novel_translator.deepseek import call_deepseek
from novel_translator.epub import build_translated_epub
from novel_translator.errors import AppError
from novel_translator.failure_log import log_deepseek_failure
from novel_translator.glossary import (
    glossary_path,
    glossary_prompt,
    load_glossary,
    merge_glossary_entries,
    normalize_glossary_entry,
    save_glossary,
)
from novel_translator.json_store import read_json, write_json
from novel_translator.novel_names import (
    build_novel_name_messages,
    ensure_translated_novel_name,
    load_novel_display_name,
    novel_metadata_path,
    parse_novel_name_response,
)
from novel_translator.server import Handler, first, main
from novel_translator.settings import (
    ALLOWED_GENDERS,
    CONFIG_PATH,
    DEEPSEEK_URL,
    DEFAULT_GLOSSARY_MODEL,
    DEFAULT_TRANSLATION_MODEL,
    FRONTEND_DIST,
    GLOSSARY_PATH,
    GLOSSARY_ROOT,
    MODELS,
    OUTPUT_ROOT,
    ROOT,
    TRANSLATED_ROOT,
)
from novel_translator.source_language import (
    SOURCE_LANGUAGE_FRAGMENT_RE,
    SOURCE_LANGUAGE_RE,
    contains_source_language_text,
    source_language_fragments,
)
from novel_translator.translation import (
    SHARED_PROMPT_PREFIX,
    apply_fragment_replacements,
    build_cached_prefix,
    build_fragment_repair_messages,
    build_glossary_messages,
    build_invalid_translation_json_retry_messages,
    build_messages,
    build_repair_messages,
    context_window,
    parse_fragment_replacements,
    parse_glossary_response,
    parse_translation_response,
    populate_glossary_for_chapter,
    response_message_content,
    translate_chapter,
)
from novel_translator.usage import current_usage, record_deepseek_usage, reset_usage


if __name__ == "__main__":
    main()
