import os
import re


_TRUE_VALUES = {"1", "true", "yes", "on"}
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_CODE_HINT_RE = re.compile(r"[{}<>;`]", re.IGNORECASE)


def is_translate_to_ru_enabled() -> bool:
    raw = os.getenv("BOT_TRANSLATE_TO_RU", "").strip().lower()
    return raw in _TRUE_VALUES


def needs_translation_to_ru(text: str) -> bool:
    sample = (text or "")[:4000]
    if not sample.strip():
        return False
    if _CODE_HINT_RE.search(sample):
        return False
    cyr_count = len(_CYRILLIC_RE.findall(sample))
    lat_count = len(_LATIN_RE.findall(sample))
    if lat_count < 40:
        return False
    return lat_count > (cyr_count * 3 + 10)


def split_text_for_translation(text: str, max_chunk_chars: int = 2800) -> list[str]:
    value = (text or "").strip()
    if not value:
        return []
    if len(value) <= max_chunk_chars:
        return [value]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for paragraph in value.split("\n\n"):
        para = paragraph.strip()
        if not para:
            continue
        para_len = len(para)
        if para_len > max_chunk_chars:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            start = 0
            while start < para_len:
                end = start + max_chunk_chars
                chunks.append(para[start:end])
                start = end
            continue
        if current_len + para_len + (2 if current else 0) > max_chunk_chars:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = para_len
        else:
            current.append(para)
            current_len += para_len + (2 if len(current) > 1 else 0)
    if current:
        chunks.append("\n\n".join(current))
    return chunks

