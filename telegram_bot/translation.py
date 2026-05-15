import os
import re


_TRUE_VALUES = {"1", "true", "yes", "on"}
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_CODE_LINE_START_RE = re.compile(
    r"^\s*("
    r"\$\s|"
    r"#include\b|"
    r"package\s+\w|"
    r"import\s+|from\s+[\w.]+\s+import|"
    r"export\s+(default\s+)?(function|class|const|let|var)|"
    r"(public|private|protected)\s+static|"
    r"(def|async\s+def|class)\s+\w|"
    r"@(staticmethod|classmethod|property|\w+)\b|"
    r"(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\s+"
    r")\s*",
    re.IGNORECASE,
)


TECHNICAL_TRANSLATION_RULES_RU = """Ты профессиональный технический переводчик на русский язык.

Цель: перевести смысл и структуру текста максимально близко к оригиналу (документация, статьи, инструкции). Не сокращай факты, не добавляй своих выводов и комментариев.

НЕ переводить и оставить дословно (включая регистр и пунктуацию внутри этих фрагментов):
- текст в обратных кавычках `...` и целые блоки между тройными ```
- команды оболочки и CLI (строки после $ или > в начале), флаги (-h, --help, -rf), пути, URL, UUID, версии ПО
- имена функций, методов, классов, переменных, модулей, пакетов, пространств имён, атрибутов через точку
- ключевые слова и операторы в примерах кода (if, return, async, await, const, let, def, class, import, …)
- SQL/DDL как синтаксис; имена таблиц/колонок если они в snake_case/camelCase как в коде
- имена HTTP-методов, заголовков, JSON/XML-тегов и значений-идентификаторов, если они заданы как в протоколе/конфиге
- аббревиатуры и бренды (REST, OAuth, CPU, API, SDK и т.п.), если замена исказит смысл

Переводить: обычные фразы, описания, пояснения вокруг кода, заголовки разделов (если это не имя продукта как маркер).

Формат ответа: только переведённый текст, без преамбулы («Вот перевод:») и без пояснений."""


def is_translate_to_ru_enabled() -> bool:
    raw = os.getenv("BOT_TRANSLATE_TO_RU", "").strip().lower()
    return raw in _TRUE_VALUES


def is_mostly_raw_code(text: str) -> bool:
    sample = (text or "")[:12000]
    lines = [ln for ln in sample.splitlines() if ln.strip()]
    if len(lines) < 10:
        return False
    code_like = 0
    for ln in lines:
        s = ln.strip()
        if _CODE_LINE_START_RE.match(s):
            code_like += 1
            continue
        if s.startswith(("/*", "*/", "{", "}", "};", "],")) and len(s) < 200:
            code_like += 1
    return (code_like / len(lines)) >= 0.72


def needs_translation_to_ru(text: str) -> bool:
    sample = (text or "")[:4000]
    if not sample.strip():
        return False
    if is_mostly_raw_code(text):
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

