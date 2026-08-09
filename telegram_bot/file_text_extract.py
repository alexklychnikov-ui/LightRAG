from pathlib import Path


_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".json",
    ".log",
    ".xml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".py",
    ".js",
    ".ts",
    ".html",
    ".htm",
    ".rtf",
}

_MAX_TEXT_CHARS = 15000
_MAX_QA_ATTACHMENT_CHARS = 40000


def is_text_like_file(file_name: str | None, mime_type: str | None) -> bool:
    mt = (mime_type or "").lower()
    if mt.startswith("text/"):
        return True
    ext = Path(file_name or "").suffix.lower()
    return ext in _TEXT_EXTENSIONS


def extract_text_from_file_bytes(
    file_bytes: bytes,
    *,
    max_chars: int | None = None,
) -> str | None:
    if not file_bytes:
        return None
    limit = _MAX_TEXT_CHARS if max_chars is None else max(1, int(max_chars))
    for encoding in ("utf-8", "utf-16", "cp1251"):
        try:
            text = file_bytes.decode(encoding)
            cleaned = text.strip()
            if cleaned:
                return cleaned[:limit]
        except UnicodeDecodeError:
            continue
    return None


def qa_attachment_char_limit() -> int:
    return _MAX_QA_ATTACHMENT_CHARS

