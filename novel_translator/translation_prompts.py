import json
from typing import Any

from .glossary import glossary_prompt
from .translation_responses import context_window
from .source_language import source_language_fragments

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


