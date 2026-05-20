from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from .lightrag_client import LightRAGClient
from .web_search import is_web_search_enabled

_JUDGE_SYSTEM_PROMPT = """Ты оцениваешь полноту ответа RAG-ассистента на вопрос пользователя.
Верни ТОЛЬКО JSON-объект без markdown.

Поля:
- needs_web (boolean): true, если для полноценного ответа нужны актуальные или внешние факты
  (даты релизов, цены, новости, официальная документация, API, сравнение продуктов на рынке),
  которых нет в ответе RAG или в базе знаний пользователя.
- queries (array of strings): 1-3 коротких поисковых запроса на языке вопроса; только если needs_web=true.
- reason (string): краткое объяснение на русском (1-2 предложения).
- confidence (number): 0.0-1.0, насколько уверен в решении.

needs_web=false, если ответ RAG уже достаточно полный по сути вопроса, даже если краткий.
needs_web=false для чисто локальных вопросов по загруженным материалам пользователя.
"""


@dataclass(frozen=True)
class CompletenessVerdict:
    needs_web: bool
    queries: tuple[str, ...]
    reason: str
    confidence: float = 0.0


def is_completeness_judge_enabled() -> bool:
    raw = os.getenv("BOT_ENABLE_ANSWER_COMPLETENESS_JUDGE", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return is_web_search_enabled()


def _min_confidence() -> float:
    try:
        value = float(os.getenv("BOT_WEB_JUDGE_MIN_CONFIDENCE", "0.55"))
    except ValueError:
        value = 0.55
    return max(0.0, min(value, 1.0))


def _max_queries() -> int:
    try:
        value = int(os.getenv("BOT_WEB_SEARCH_MAX_QUERIES", "3"))
    except ValueError:
        value = 3
    return max(1, min(value, 5))


def _clip(text: str, limit: int) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _max_rag_chars() -> int:
    try:
        value = int(os.getenv("BOT_WEB_JUDGE_MAX_RAG_CHARS", "4500"))
    except ValueError:
        value = 4500
    return max(500, min(value, 12000))


def _queries_from_question(question: str, *, limit: int) -> tuple[str, ...]:
    q = (question or "").strip()
    if not q:
        return ()
    cleaned = re.sub(r"\s+", " ", q)
    parts = [cleaned]
    if len(cleaned) > 120:
        parts.append(cleaned[:120])
    unique: list[str] = []
    seen: set[str] = set()
    for part in parts:
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(part)
        if len(unique) >= limit:
            break
    return tuple(unique)


def parse_completeness_payload(payload: dict) -> CompletenessVerdict | None:
    if not isinstance(payload, dict):
        return None
    needs_web = bool(payload.get("needs_web"))
    reason = _clip(str(payload.get("reason") or ""), 500)
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(confidence, 1.0))

    raw_queries = payload.get("queries") or []
    queries: list[str] = []
    if isinstance(raw_queries, list):
        for item in raw_queries:
            q = _clip(str(item or ""), 200)
            if not q:
                continue
            key = q.lower()
            if key in {x.lower() for x in queries}:
                continue
            queries.append(q)
            if len(queries) >= _max_queries():
                break

    if needs_web and not queries:
        return None
    if needs_web and confidence < _min_confidence():
        return CompletenessVerdict(
            needs_web=False,
            queries=(),
            reason=reason or "низкая уверенность judge",
            confidence=confidence,
        )
    return CompletenessVerdict(
        needs_web=needs_web,
        queries=tuple(queries),
        reason=reason,
        confidence=confidence,
    )


def parse_completeness_json_text(raw: str) -> CompletenessVerdict | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return parse_completeness_payload(payload)


def _build_user_prompt(question: str, rag_answer: str, chat_context: str) -> str:
    ctx = _clip(chat_context, 2500)
    ctx_block = f"\n\nКонтекст диалога:\n{ctx}" if ctx else ""
    return (
        f"Вопрос пользователя:\n{_clip(question, 1500)}\n\n"
        f"Ответ RAG:\n{_clip(rag_answer, _max_rag_chars())}"
        f"{ctx_block}"
    )


def _weak_or_empty_verdict(question: str, reason: str) -> CompletenessVerdict:
    return CompletenessVerdict(
        True,
        _queries_from_question(question, limit=_max_queries()),
        reason,
        confidence=1.0,
    )


def assess_rag_answer(
    question: str,
    rag_answer: str,
    *,
    chat_context: str = "",
    client: LightRAGClient | None = None,
) -> tuple[bool, CompletenessVerdict | None, str]:
    q = (question or "").strip()
    answer = (rag_answer or "").strip()
    if not q:
        return False, None, "empty question"

    if is_web_search_enabled():
        if not answer:
            return True, _weak_or_empty_verdict(q, "пустой ответ RAG"), ""
        if LightRAGClient.is_weak_answer(answer):
            return True, _weak_or_empty_verdict(q, "слабый ответ RAG"), ""

    if not is_completeness_judge_enabled():
        return True, CompletenessVerdict(False, (), "judge disabled"), ""

    active_client = client
    if active_client is None:
        active_client = LightRAGClient(
            base_url=os.getenv("LIGHTRAG_URL", "http://127.0.0.1:9621"),
            api_key=os.getenv("LIGHTRAG_API_KEY"),
        )

    ok, payload_or_err = active_client.query_openai_json(
        _JUDGE_SYSTEM_PROMPT,
        _build_user_prompt(q, answer, chat_context),
    )
    if not ok:
        return False, None, str(payload_or_err)

    verdict = parse_completeness_payload(payload_or_err)
    if verdict is None:
        return False, None, "invalid judge json payload"
    return True, verdict, ""
