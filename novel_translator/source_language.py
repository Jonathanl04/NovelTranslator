import re

SOURCE_LANGUAGE_RE = re.compile(
    r"[\u1100-\u11ff\u3130-\u318f\u3400-\u4dbf\u4e00-\u9fff"
    r"\uac00-\ud7af\uf900-\ufaff]"
)
SOURCE_LANGUAGE_FRAGMENT_RE = re.compile(
    r"[\u1100-\u11ff\u3130-\u318f\u3400-\u4dbf\u4e00-\u9fff"
    r"\uac00-\ud7af\uf900-\ufaff]+"
)


def contains_source_language_text(value: str) -> bool:
    return bool(SOURCE_LANGUAGE_RE.search(value))


def source_language_fragments(value: str) -> list[str]:
    seen: set[str] = set()
    fragments = []
    for match in SOURCE_LANGUAGE_FRAGMENT_RE.finditer(value):
        fragment = match.group(0)
        if fragment not in seen:
            seen.add(fragment)
            fragments.append(fragment)
    return fragments
