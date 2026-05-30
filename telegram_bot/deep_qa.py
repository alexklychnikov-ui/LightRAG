from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from .lightrag_client import LightRAGClient

_PLANNER_SYSTEM = """Ты планировщик глубокого поиска по базе знаний LightRAG пользователя.
Верни ТОЛЬКО JSON-объект без markdown.

Поля:
- task_type (string): resume | document | qa | analysis | other
- sub_queries (array of strings): минимум 3, максимум 10 самодостаточных запросов на русском к базе знаний.
  Обязательно покрой три угла: (1) суть/прямой ответ, (2) детали/шаги/примеры, (3) источники в БЗ (документы, уроки, файлы).
  Каждый запрос ищет конкретные факты, не дублируй формулировки.
  Если в вопросе упомянут урок/модуль (например OV05) — включи отдельный запрос по рекомендациям этого урока.
- synthesis_notes (string): кратко, как собирать финальный ответ (структура, тон, ограничения).

Правила:
- sub_queries не дублируют друг друга по смыслу.
- Для резюме: отдельные запросы по рекомендациям урока, introMain/профилю, контактам, проектам, AX/ERP, образованию.
- Не включай в sub_queries просьбы «написать резюме» — только поиск фактов в БЗ.
"""

_SYNTHESIS_SYSTEM = """Ты собираешь финальный ответ пользователю ИСКЛЮЧИТЕЛЬНО из фрагментов базы знаний LightRAG.

Жёсткие правила:
- ЗАПРЕЩЕНО выдумывать факты: компании, должности, даты, города, контакты, ссылки, образование, цифры достижений.
- Используй только то, что явно есть во фрагментах; при отсутствии данных — пропусти пункт или напиши «в базе знаний нет данных».
- Не подставляй плейсхолдеры вида [ваш email] или вымышленные организации.
- Для резюме: следуй структуре и рекомендациям из фрагментов урока; контакты и проекты — только из БЗ.
- Пиши на русском, связным markdown-текстом, без JSON и без секции References.
- Если фрагменты противоречат друг другу — укажи неопределённость, не выбирай «на глаз».
"""

_LESSON_REF_RE = re.compile(r"\b(ov|урок|lesson|модуль|module)[\s_-]*(\d{1,3})\b", re.I)
_NAME_HINT_RE = re.compile(
    r"клычников|alexandr[_\s-]?klychnikov|александр\s+клычников",
    re.I,
)


@dataclass(frozen=True)
class DeepQaPlan:
    task_type: str
    sub_queries: tuple[str, ...]
    synthesis_notes: str = ""


@dataclass(frozen=True)
class RagEvidenceItem:
    sub_query: str
    mode_label: str
    text: str


@dataclass(frozen=True)
class DeepQaOutcome:
    answer: str
    mode_label: str
    task_type: str
    queries_run: int
    evidence_count: int


def is_deep_qa_enabled() -> bool:
    raw = os.getenv("BOT_ENABLE_DEEP_QA", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def deep_qa_blocks_openai_fallback() -> bool:
    raw = os.getenv("BOT_DEEP_QA_BLOCK_OPENAI_FALLBACK", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def deep_qa_skips_web_enrichment(task_type: str) -> bool:
    if os.getenv("BOT_DEEP_QA_SKIP_WEB", "true").strip().lower() in {"0", "false", "no", "off"}:
        return False
    return (task_type or "").strip().lower() in {"resume", "document"}


def _max_subqueries() -> int:
    try:
        value = int(os.getenv("BOT_DEEP_QA_MAX_SUBQUERIES", "8"))
    except ValueError:
        value = 8
    return max(3, min(value, 12))


def _min_subqueries() -> int:
    try:
        value = int(os.getenv("BOT_DEEP_QA_MIN_SUBQUERIES", "3"))
    except ValueError:
        value = 3
    return max(3, min(value, _max_subqueries()))


def _triad_sub_query_templates(question: str) -> tuple[str, str, str]:
    q = _clip(question, 400) or "запрос пользователя"
    return (
        f"Суть и прямой ответ по запросу в базе знаний: {q}",
        f"Детали, шаги, примеры и нюансы по теме в базе знаний: {q}",
        f"Источники в базе знаний — документы, уроки, файлы, разделы по теме: {q}",
    )


def ensure_minimum_sub_queries(
    queries: list[str],
    question: str,
    *,
    minimum: int | None = None,
) -> tuple[str, ...]:
    min_count = minimum if minimum is not None else _min_subqueries()
    q = (question or "").strip()
    merged: list[str] = []
    seen: set[str] = set()

    def add(item: str) -> None:
        text = _clip(item, 500)
        if not text:
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        merged.append(text)

    for item in queries:
        add(item)
    if len(merged) < min_count:
        for item in _triad_sub_query_templates(q):
            add(item)
    while len(merged) < min_count:
        add(f"Факты и формулировки в базе знаний по теме: {q or 'запрос пользователя'}")
    return tuple(merged)


def _max_evidence_chars() -> int:
    try:
        value = int(os.getenv("BOT_DEEP_QA_MAX_EVIDENCE_CHARS", "28000"))
    except ValueError:
        value = 28000
    return max(4000, min(value, 60000))


def _clip(text: str, limit: int) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _lesson_refs_from_question(question: str) -> list[str]:
    refs: list[str] = []
    for match in _LESSON_REF_RE.finditer(question or ""):
        num = match.group(2)
        token = f"OV{num}"
        if token not in refs:
            refs.append(token)
    return refs


def _default_sub_queries(question: str) -> tuple[str, ...]:
    q = (question or "").strip()
    lessons = _lesson_refs_from_question(q)
    queries: list[str] = []
    for lesson in lessons:
        queries.append(f"рекомендации урока {lesson} по составлению резюме и структура")
    if _NAME_HINT_RE.search(q) or "резюме" in q.lower():
        queries.extend(
            [
                "контакты телефон email telegram github Александр Клычников introMain",
                "проекты pet-проекты репозитории github LightRAG Telegram Zerocode",
                "опыт Microsoft Dynamics AX X++ CRM лояльность GTIN",
                "образование ИГУ Zerocoder навыки стек разработчика",
                "чем полезен заказчику MVP автоматизация портфолио",
            ]
        )
    if not queries:
        queries.extend(_triad_sub_query_templates(q))
    return tuple(ensure_minimum_sub_queries(queries, q)[: _max_subqueries()])


def parse_planner_payload(payload: dict) -> DeepQaPlan | None:
    if not isinstance(payload, dict):
        return None
    task_type = _clip(str(payload.get("task_type") or "other"), 40).lower() or "other"
    notes = _clip(str(payload.get("synthesis_notes") or ""), 800)
    raw = payload.get("sub_queries") or []
    if not isinstance(raw, list):
        return None
    queries: list[str] = []
    for item in raw:
        q = _clip(str(item or ""), 500)
        if not q:
            continue
        key = q.lower()
        if key in {x.lower() for x in queries}:
            continue
        queries.append(q)
        if len(queries) >= _max_subqueries():
            break
    if not queries:
        return None
    return DeepQaPlan(task_type=task_type, sub_queries=tuple(queries), synthesis_notes=notes)


def plan_deep_qa(
    question: str,
    *,
    chat_context: str = "",
    client: LightRAGClient,
    model: str | None = None,
) -> tuple[bool, DeepQaPlan | None, str]:
    q = (question or "").strip()
    if not q:
        return False, None, "empty question"

    ctx = _clip(chat_context, 2500)
    ctx_block = f"\n\nКонтекст диалога:\n{ctx}" if ctx else ""
    user_prompt = f"Задача пользователя:\n{_clip(q, 3000)}{ctx_block}"

    ok, payload_or_err = client.query_openai_json(
        _PLANNER_SYSTEM,
        user_prompt,
        temperature=0.15,
        model=model,
    )
    if not ok:
        fallback = _default_sub_queries(q)
        task = "resume" if "резюме" in q.lower() else "qa"
        return (
            True,
            DeepQaPlan(task_type=task, sub_queries=fallback, synthesis_notes="fallback plan"),
            str(payload_or_err),
        )

    plan = parse_planner_payload(payload_or_err)
    if plan is None:
        fallback = _default_sub_queries(q)
        task = "resume" if "резюме" in q.lower() else "qa"
        return (
            True,
            DeepQaPlan(task_type=task, sub_queries=fallback, synthesis_notes="fallback plan"),
            "invalid planner json",
        )

    merged = list(plan.sub_queries)
    for lesson in _lesson_refs_from_question(q):
        extra = f"рекомендации урока {lesson} для резюме структура ошибки типичные"
        if extra.lower() not in {x.lower() for x in merged}:
            merged.insert(0, extra)
    merged = list(ensure_minimum_sub_queries(merged, q))
    if q.lower() not in {x.lower() for x in merged}:
        merged.append(_clip(q, 500))
    merged = list(ensure_minimum_sub_queries(merged[: _max_subqueries()], q))
    return True, DeepQaPlan(plan.task_type, tuple(merged), plan.synthesis_notes), ""


def gather_rag_evidence(
    client: LightRAGClient,
    plan: DeepQaPlan,
    *,
    primary_mode: str,
    fallback_modes: tuple[str, ...],
) -> list[RagEvidenceItem]:
    items: list[RagEvidenceItem] = []
    seen_text: set[str] = set()
    for sub_query in plan.sub_queries:
        ok, answer, mode_label = client.ask_with_fallback(
            sub_query,
            primary_mode,
            fallback_modes,
        )
        if not ok:
            continue
        text = (answer or "").strip()
        if not text:
            continue
        key = text.lower()[:400]
        if key in seen_text:
            continue
        seen_text.add(key)
        items.append(
            RagEvidenceItem(
                sub_query=sub_query,
                mode_label=mode_label,
                text=text,
            )
        )
    return items


def _build_evidence_block(evidence: list[RagEvidenceItem]) -> str:
    parts: list[str] = []
    total = 0
    max_chars = _max_evidence_chars()
    for idx, item in enumerate(evidence, start=1):
        block = (
            f"### Фрагмент {idx}\n"
            f"Подзапрос: {item.sub_query}\n"
            f"Режим: {item.mode_label}\n"
            f"Текст:\n{_clip(item.text, 6000)}\n"
        )
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n".join(parts).strip()


def synthesize_from_evidence(
    question: str,
    plan: DeepQaPlan,
    evidence: list[RagEvidenceItem],
    *,
    chat_context: str = "",
    client: LightRAGClient,
    model: str | None = None,
) -> tuple[bool, str, str]:
    q = (question or "").strip()
    if not evidence:
        return False, "", "no evidence"

    ctx = _clip(chat_context, 2000)
    ctx_block = f"\n\nКонтекст диалога:\n{ctx}" if ctx else ""
    notes = _clip(plan.synthesis_notes, 600)
    notes_block = f"\n\nЗаметки планировщика:\n{notes}" if notes else ""

    user_prompt = (
        f"Тип задачи: {plan.task_type}\n\n"
        f"Запрос пользователя:\n{_clip(q, 3000)}\n\n"
        f"Фрагменты базы знаний:\n{_build_evidence_block(evidence)}"
        f"{notes_block}{ctx_block}"
    )

    ok, answer_or_err = client.query_openai_chat(
        _SYNTHESIS_SYSTEM,
        user_prompt,
        temperature=0.2,
        model=model,
    )
    if not ok:
        return False, "", str(answer_or_err)
    answer = str(answer_or_err).strip()
    if not answer:
        return False, "", "synthesis empty"
    return True, answer, ""


def run_deep_qa(
    contextual_question: str,
    effective_question: str,
    *,
    client: LightRAGClient,
    primary_mode: str,
    fallback_modes: tuple[str, ...],
    chat_context: str = "",
    openai_model: str | None = None,
) -> tuple[bool, DeepQaOutcome | None, str]:
    plan_ok, plan, plan_err = plan_deep_qa(
        contextual_question,
        chat_context=chat_context,
        client=client,
        model=openai_model,
    )
    if not plan_ok or plan is None:
        return False, None, plan_err or "plan failed"

    evidence = gather_rag_evidence(
        client,
        plan,
        primary_mode=primary_mode,
        fallback_modes=fallback_modes,
    )
    if not evidence:
        return False, None, "all sub-queries failed"

    synth_ok, answer, synth_err = synthesize_from_evidence(
        effective_question or contextual_question,
        plan,
        evidence,
        chat_context=chat_context,
        client=client,
        model=openai_model,
    )
    if not synth_ok:
        fallback_answer = _build_evidence_block(evidence)
        if not fallback_answer:
            return False, None, synth_err or "synthesis failed"
        answer = (
            "Не удалось собрать связный ответ моделью; ниже сырые фрагменты из базы знаний:\n\n"
            + fallback_answer
        )

    modes = sorted({e.mode_label for e in evidence})
    mode_label = (
        f"deep:{len(plan.sub_queries)}q,"
        f"{len(evidence)}hits,"
        f"{plan.task_type} ({'; '.join(modes[:3])})"
    )
    return (
        True,
        DeepQaOutcome(
            answer=answer,
            mode_label=mode_label,
            task_type=plan.task_type,
            queries_run=len(plan.sub_queries),
            evidence_count=len(evidence),
        ),
        plan_err,
    )
