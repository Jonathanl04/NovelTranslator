TRANSLATION_SCHEMA = {
    "type": "object",
    "properties": {
        "translated_title": {"type": "string"},
        "translated_body": {"type": "string"},
    },
    "required": ["translated_title", "translated_body"],
    "additionalProperties": False,
}

GLOSSARY_SCHEMA = {
    "type": "object",
    "properties": {
        "glossary_updates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_term": {"type": "string"},
                    "english_term": {"type": "string"},
                    "category": {"type": "string"},
                    "gender_or_pronoun": {"type": "string"},
                },
                "required": [
                    "source_term",
                    "english_term",
                    "category",
                    "gender_or_pronoun",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["glossary_updates"],
    "additionalProperties": False,
}

FRAGMENT_REPLACEMENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "replacements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fragment": {"type": "string"},
                    "replacement": {"type": "string"},
                },
                "required": ["fragment", "replacement"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["replacements"],
    "additionalProperties": False,
}

NOVEL_NAME_SCHEMA = {
    "type": "object",
    "properties": {"translated_name": {"type": "string"}},
    "required": ["translated_name"],
    "additionalProperties": False,
}
