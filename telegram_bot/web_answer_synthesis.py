from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .lightrag_client import LightRAGClient
from .web_search import WebSearchResult, merge_results

_URL_IN_TEXT_RE = re.compile(r"https?://[^\s\])<>\"']+", re.IGNORECASE)

_SYNTHESIS_SYSTEM_PROMPT = """Ты технический ассистент. Собери финальный ответ пользователю из двух источников:
1) ответ RAG (база знаний пользователя);
2) фрагменты из интернет-поиска.

Правила:
- Пиши на том же языке, что и вопрос (если вопрос на русском — ответ на русском).
- Явно разделяй, что опирается на базу знаний, а что дополнено из открытых источников.
- Не выдумывай факты и не добавляй URL/ссылки в текст ответа — ссылки будут отдельным блоком References.
- Если интернет-фрагментов мало или они противоречивы — скажи об этом честно.
- Сохраняй команды, код, имена API и идентификаторы без искажений.
- Ответ: связный текст, без JSON и без секции References в теле ответа.
"""


@dataclass(frozen=True)
class WebSynthesisOutcome:
    answer: str
    references: tuple[WebSearchResult, ...]


def _clip(text: str, limit: int) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _max_snippet_chars() -> int:
    try:
        value = int(os.getenv("BOT_WEB_SYNTHESIS_MAX_SNIPPET_CHARS", "700"))
    except ValueError:
        value = 700
    return max(200, min(value, 2000))


def _max_reference_count() -> int:
    try:
        value = int(os.getenv("BOT_WEB_SYNTHESIS_MAX_SOURCES", "8"))
    except ValueError:
        value = 8
    return max(1, min(value, 15))


def _max_question_chars() -> int:
    try:
        value = int(os.getenv("BOT_WEB_SYNTHESIS_MAX_QUESTION_CHARS", "2000"))
    except ValueError:
        value = 2000
    return max(300, min(value, 4000))


def _max_rag_chars() -> int:
    try:
        value = int(os.getenv("BOT_WEB_SYNTHESIS_MAX_RAG_CHARS", "4500"))
    except ValueError:
        value = 4500
    return max(500, min(value, 12000))


def normalize_reference_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/") or ""
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}"


def collect_references(web_results: list[WebSearchResult]) -> tuple[WebSearchResult, ...]:
    merged = merge_results([web_results], max_total=_max_reference_count())
    return tuple(merged)


def build_web_sources_block(web_results: list[WebSearchResult]) -> str:
    refs = collect_references(web_results)
    if not refs:
        return ""
    lines: list[str] = []
    for index, item in enumerate(refs, start=1):
        title = _clip(item.title or item.url, 200)
        snippet = _clip(item.snippet, _max_snippet_chars())
        lines.append(
            f"[{index}] {title}\nURL: {item.url}\nФрагмент: {snippet or '(нет текста)'}"
        )
    return "\n\n".join(lines)


def format_references_block(references: tuple[WebSearchResult, ...]) -> str:
    if not references:
        return ""
    lines = ["References:"]
    for item in references:
        title = _clip((item.title or item.url).replace("\n", " "), 200)
        lines.append(f"- {title}\n  {item.url}")
    return "\n".join(lines)


def _strip_embedded_references_section(text: str) -> str:
    body = (text or "").strip()
    match = re.search(r"(?im)^\s*references\s*:\s*$", body)
    if match:
        return body[: match.start()].strip()
    return body


def answer_body_without_references(text: str) -> str:
    return _strip_embedded_references_section(text).strip()


def format_answer_with_references(answer: str, references: tuple[WebSearchResult, ...]) -> str:
    body = _strip_embedded_references_section(answer)
    ref_block = format_references_block(references)
    if not ref_block:
        return body
    if not body:
        return ref_block
    return f"{body}\n\n{ref_block}"


def _scrub_unknown_urls(text: str, allowed_urls: set[str]) -> str:
    if not text or not allowed_urls:
        return (text or "").strip()

    def replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        trimmed = raw.rstrip(".,);]")
        if normalize_reference_url(trimmed) in allowed_urls:
            return raw
        return ""

    return _URL_IN_TEXT_RE.sub(replace, text).strip()


def _build_synthesis_user_prompt(
    question: str,
    rag_answer: str,
    web_results: list[WebSearchResult],
    chat_context: str,
) -> str:
    ctx = _clip(chat_context, 2000)
    ctx_block = f"\n\nКонтекст диалога:\n{ctx}" if ctx else ""
    sources = build_web_sources_block(web_results)
    if not sources:
        return ""
    rag_block = _clip(rag_answer, _max_rag_chars()) if rag_answer.strip() else (
        "(в базе знаний нет содержательного ответа по этому вопросу)"
    )
    return (
        f"Вопрос пользователя:\n{_clip(question, _max_question_chars())}\n\n"
        f"Ответ RAG (база знаний):\n{rag_block}\n\n"
        f"Фрагменты из интернета:\n{sources}"
        f"{ctx_block}"
    )


def synthesize_with_web(
    question: str,
    rag_answer: str,
    web_results: list[WebSearchResult],
    *,
    chat_context: str = "",
    client: LightRAGClient | None = None,
    model: str | None = None,
) -> tuple[bool, WebSynthesisOutcome | None, str]:
    q = (question or "").strip()
    rag = (rag_answer or "").strip()
    if not q:
        return False, None, "empty question"

    references = collect_references(web_results)
    if not references:
        return False, None, "no web results for synthesis"

    user_prompt = _build_synthesis_user_prompt(q, rag, list(references), chat_context)
    if not user_prompt:
        return False, None, "empty synthesis prompt"

    active_client = client
    if active_client is None:
        active_client = LightRAGClient(
            base_url=os.getenv("LIGHTRAG_URL", "http://127.0.0.1:9621"),
            api_key=os.getenv("LIGHTRAG_API_KEY"),
        )

    ok, answer_or_err = active_client.query_openai_chat(
        _SYNTHESIS_SYSTEM_PROMPT,
        user_prompt,
        temperature=0.25,
        model=model,
    )
    if not ok:
        return False, None, str(answer_or_err)

    allowed = {normalize_reference_url(item.url) for item in references}
    allowed.discard("")
    cleaned = _scrub_unknown_urls(str(answer_or_err).strip(), allowed)
    if not cleaned:
        return False, None, "synthesis empty response"

    return True, WebSynthesisOutcome(answer=cleaned, references=references), ""
