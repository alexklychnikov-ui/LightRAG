from __future__ import annotations

import os
import time
from aiogram.fsm.context import FSMContext

from .domain import BotMode, mode_prompt
from .qa_context import qa_session_ttl_enabled
from .reliability import BotRuntimeMetrics, format_metrics_ru
from .states import BotStates
from .web_search import is_web_search_enabled, web_search_provider_name

_BOT_STARTED_AT = time.time()

_STATE_LABELS: dict[str | None, str] = {
    None: "не задан (отправь /start)",
    BotStates.choosing_mode.state: "меню — выбор режима",
    BotStates.ingest_mode.state: "пополнение базы знаний",
    BotStates.qa_mode.state: "Q&A — задать вопрос",
    BotStates.status_mode.state: "статус (этот экран)",
}


def _flag_on(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _format_uptime() -> str:
    seconds = int(time.time() - _BOT_STARTED_AT)
    if seconds < 60:
        return f"{seconds} сек"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} мин {sec} сек"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} ч {minutes} мин"


def _qa_settings_lines(state_data: dict) -> list[str]:
    default_mode = os.getenv("BOT_QUERY_MODE", "mix").strip().lower() or "mix"
    fallback = os.getenv("BOT_QUERY_FALLBACK_MODES", "hybrid,global").strip()
    override = (state_data.get("qa_mode_override") or "").strip().lower()
    lines = [
        f"• стартовый режим LightRAG: {default_mode}",
        f"• цепочка fallback: {fallback}, naive",
    ]
    if override:
        lines.append(f"• override для этого чата: {override}")
    else:
        lines.append("• override для этого чата: auto")
    lines.append(
        f"• веб-поиск: {'вкл' if is_web_search_enabled() else 'выкл'}"
        + (f" ({web_search_provider_name()})" if is_web_search_enabled() else "")
    )
    lines.append(
        f"• OpenAI вне RAG: {'вкл' if _flag_on('BOT_ENABLE_OPENAI_FALLBACK', 'true') else 'выкл'}"
    )
    lines.append(
        f"• перевод ответов RU: {'вкл' if _flag_on('BOT_TRANSLATE_TO_RU', 'false') else 'выкл'}"
    )
    if qa_session_ttl_enabled():
        idle = os.getenv("BOT_QA_SESSION_IDLE_MINUTES", "20")
        lines.append(f"• сброс контекста Q&A: через {idle} мин простоя")
    else:
        lines.append("• сброс контекста Q&A: только /forgetctx")
    return lines


async def build_status_report_text(
    state: FSMContext,
    metrics: BotRuntimeMetrics,
    *,
    lightrag_ok: bool,
    lightrag_details: str,
) -> str:
    current_state = await state.get_state()
    state_label = _STATE_LABELS.get(current_state, current_state or "неизвестно")
    state_data = await state.get_data()

    health_line = "OK" if lightrag_ok else "FAIL"
    lines = [
        mode_prompt(BotMode.STATUS),
        "",
        "Текущее состояние бота",
        f"• активный режим UI: {state_label}",
        f"• аптайм процесса: {_format_uptime()}",
        "",
        "LightRAG",
        f"• health: {health_line}",
        f"• детали: {lightrag_details or '—'}",
        f"• URL: {os.getenv('LIGHTRAG_URL', 'http://127.0.0.1:9621')}",
        "",
        "Настройки Q&A (как отвечает на вопросы)",
        *_qa_settings_lines(state_data),
        "",
        "Счётчики с последнего перезапуска",
        format_metrics_ru(metrics.snapshot()),
    ]
    return "\n".join(lines)
