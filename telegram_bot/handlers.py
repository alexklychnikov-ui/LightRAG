import asyncio
from io import BytesIO
import logging
import re
from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
import os

from .domain import BotMode, mode_prompt
from .file_text_extract import extract_text_from_file_bytes, is_text_like_file
from .answer_completeness import assess_rag_answer
from .deep_qa import (
    deep_qa_blocks_openai_fallback,
    deep_qa_skips_web_enrichment,
    is_deep_qa_enabled,
    run_deep_qa,
)
from .lightrag_client import LightRAGClient
from .qa_context import qa_conversation_store
from .web_answer_synthesis import (
    answer_body_without_references,
    format_answer_with_references,
    synthesize_with_web,
)
from .web_search import WebSearchResult, is_web_search_enabled, search_web
from .reliability import BotRuntimeMetrics, InMemoryRateLimiter
from .status_report import build_status_report_text
from .translation import is_translate_to_ru_enabled, needs_translation_to_ru
from .url_ingest import fetch_significant_text_from_url, is_http_url
from .keyboards import (
    BACK_TO_MENU_CALLBACK,
    MENU_BUTTON_TEXT,
    MODE_INGEST_CALLBACK,
    MODE_QA_CALLBACK,
    MODE_STATUS_CALLBACK,
    OMODEL_SET_PREFIX,
    QMODE_SET_PREFIX,
    back_to_menu_inline_keyboard,
    modes_inline_keyboard,
    persistent_menu_keyboard,
    qa_modes_inline_keyboard,
    qa_openai_models_inline_keyboard,
)
from .openai_models import (
    get_available_openai_models,
    is_allowed_openai_model,
    resolve_openai_model,
)
from .states import BotStates

router = Router(name="menu-router")
_DEFAULT_LIGHTRAG_URL = "http://127.0.0.1:9621"
_INGEST_MAX_LEN = 4096
_INGEST_FILE_MAX_BYTES = 20 * 1024 * 1024
_STATUS_CODE_PATTERN = re.compile(r"status=(\d+)")
_TRACK_POLL_ATTEMPTS = 20
_TRACK_POLL_INTERVAL_SECONDS = 3
_DEFAULT_QUERY_MODE = "mix"
_DEFAULT_FALLBACK_MODES = ("hybrid", "global")
_MODEL_FALLBACK_MODE = "naive"
_ALLOWED_QUERY_MODES = {"naive", "local", "global", "hybrid", "mix"}
_STATUS_REFRESH_WORDS = frozenset({"статус", "обновить", "refresh", "status"})


def _is_status_refresh_text(text: str) -> bool:
    t = text.strip().lower()
    if t.startswith("/status"):
        return True
    return t in _STATUS_REFRESH_WORDS
_RATE_LIMIT_MAX_EVENTS = int(os.getenv("BOT_RATE_LIMIT_MAX_EVENTS", "6"))
_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("BOT_RATE_LIMIT_WINDOW_SECONDS", "30"))
_TELEGRAM_MAX_MESSAGE_CHARS = 3900
logger = logging.getLogger(__name__)
_rate_limiter = InMemoryRateLimiter(
    max_events=_RATE_LIMIT_MAX_EVENTS,
    window_seconds=_RATE_LIMIT_WINDOW_SECONDS,
)
_metrics = BotRuntimeMetrics()


def build_lightrag_client() -> LightRAGClient:
    lightrag_url = os.getenv("LIGHTRAG_URL", _DEFAULT_LIGHTRAG_URL)
    lightrag_api_key = os.getenv("LIGHTRAG_API_KEY", "")
    return LightRAGClient(base_url=lightrag_url, api_key=lightrag_api_key)


def _safe_ingest_error(details: str, target: str) -> str:
    status_match = _STATUS_CODE_PATTERN.search(details)
    if status_match:
        status_code = status_match.group(1)
        return (
            f"Не удалось добавить {target} в LightRAG (HTTP {status_code}). "
            "Попробуй снова."
        )
    return f"Не удалось добавить {target} в LightRAG. Попробуй снова."


def _rewrite_qa_question(question: str) -> str:
    q = (question or "").strip().lower()
    if q in {"как меня зовут", "как меня зовут?", "кто я", "кто я?"}:
        return "как зовут разработчика в introMain.md"
    if q in {"мой стек", "мой стек?", "основной технический стек"}:
        return "основной технологический стек разработчика в introMain.md"
    if q in {"что полезного про меня", "что полезного про меня?"}:
        return "ключевые навыки, опыт и полезная информация о разработчике из introMain.md"
    if q in {
        "где я живу",
        "где я живу?",
        "где я живу сейчас",
        "где я живу сейчас?",
        "мой город",
        "мой город?",
        "где я проживаю",
        "где я проживаю?",
    } or re.search(r"\bгде\s+я\s+жив", q):
        return (
            "в каком городе проживает разработчик Клычников Александр Васильевич "
            "по резюме и документам в базе знаний (Иркутск и связанные факты)"
        )
    return question


def _parse_fallback_modes() -> tuple[str, ...]:
    raw = os.getenv("BOT_QUERY_FALLBACK_MODES", ",".join(_DEFAULT_FALLBACK_MODES)).strip()
    if not raw:
        result = list(_DEFAULT_FALLBACK_MODES)
    else:
        result = []
        for part in raw.split(","):
            mode = part.strip().lower()
            if mode in _ALLOWED_QUERY_MODES and mode not in result:
                result.append(mode)
    if _MODEL_FALLBACK_MODE in _ALLOWED_QUERY_MODES and _MODEL_FALLBACK_MODE not in result:
        result.append(_MODEL_FALLBACK_MODE)
    return tuple(result) if result else (_MODEL_FALLBACK_MODE,)


def _is_openai_fallback_enabled() -> bool:
    return os.getenv("BOT_ENABLE_OPENAI_FALLBACK", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _qa_openai_model_from_state(state_data: dict) -> str:
    override = (state_data.get("qa_openai_model_override") or "").strip().lower()
    return resolve_openai_model(override or None)


def _openai_model_price_hint(model_id: str) -> str:
    for info in get_available_openai_models():
        if info.model_id == model_id:
            return info.price_label()
    return ""


async def _try_enrich_with_web_search(
    message: Message,
    client: LightRAGClient,
    *,
    contextual_question: str,
    effective_question: str,
    rag_answer: str,
    used_mode: str,
    openai_model: str,
) -> tuple[str, str, str, tuple[WebSearchResult, ...], str]:
    empty_notice = ""
    if not is_web_search_enabled():
        return rag_answer, "LightRAG", used_mode, (), empty_notice

    chat_context = await qa_conversation_store.get_dialog_context_block(message.chat.id)
    judge_question = effective_question.strip() or contextual_question.strip()
    assess_ok, verdict, assess_err = await asyncio.to_thread(
        assess_rag_answer,
        judge_question,
        rag_answer,
        chat_context=chat_context,
        client=client,
        model=openai_model,
    )
    _metrics.inc("qa_web_judge_total")
    if not assess_ok or verdict is None:
        logger.warning("QA web judge failed: %s", assess_err)
        return rag_answer, "LightRAG", used_mode, (), empty_notice
    if not verdict.needs_web:
        return rag_answer, "LightRAG", used_mode, (), empty_notice

    _metrics.inc("qa_web_search_triggered_total")
    await message.answer(
        "Дополняю ответ поиском в интернете…",
        reply_markup=persistent_menu_keyboard(),
    )

    search_ok, results, search_err = await asyncio.to_thread(
        search_web,
        list(verdict.queries),
    )
    if not search_ok or not results:
        logger.warning("QA web search failed: %s", search_err)
        return (
            rag_answer,
            "LightRAG",
            used_mode,
            (),
            "Не удалось дополнить ответ из интернета (поиск).",
        )

    synth_ok, outcome, synth_err = await asyncio.to_thread(
        synthesize_with_web,
        judge_question,
        rag_answer,
        results,
        chat_context=chat_context,
        client=client,
        model=openai_model,
    )
    if not synth_ok or outcome is None:
        logger.warning("QA web synthesis failed: %s", synth_err)
        return (
            rag_answer,
            "LightRAG",
            used_mode,
            (),
            "Не удалось дополнить ответ из интернета (синтез).",
        )

    _metrics.inc("qa_web_synthesis_success_total")
    return (
        outcome.answer,
        "LightRAG + интернет",
        f"{used_mode} -> web",
        outcome.references,
        "",
    )


def _extract_inline_mode(raw_question: str) -> tuple[str | None, str]:
    question = (raw_question or "").strip()
    # Examples:
    #   режим:global | что ты знаешь ...
    #   mode=hybrid: summarize ...
    match = re.match(
        r"^(?:режим|mode)\s*[:=]\s*(naive|local|global|hybrid|mix)\s*(?:\||:)\s*(.+)$",
        question,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None, question
    mode = match.group(1).lower().strip()
    rest = match.group(2).strip()
    return mode, rest


def _split_long_message(text: str, chunk_size: int = _TELEGRAM_MAX_MESSAGE_CHARS) -> list[str]:
    value = (text or "").strip()
    if not value:
        return []
    if len(value) <= chunk_size:
        return [value]

    chunks: list[str] = []
    remaining = value
    while remaining:
        if len(remaining) <= chunk_size:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, chunk_size)
        if split_at < chunk_size // 3:
            split_at = chunk_size
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return [chunk for chunk in chunks if chunk]


async def _send_long_message(message: Message, text: str) -> None:
    parts = _split_long_message(text)
    if not parts:
        await message.answer("Пустой ответ.", reply_markup=persistent_menu_keyboard())
        return
    for idx, part in enumerate(parts):
        if idx == 0:
            await message.answer(part, reply_markup=persistent_menu_keyboard())
        else:
            await message.answer(part)


async def _apply_rate_limit(message: Message) -> bool:
    decision = _rate_limiter.check(message.chat.id)
    if decision.allowed:
        return True
    await message.answer(
        "Слишком много запросов. "
        f"Повтори через {decision.retry_after_seconds} сек.",
        reply_markup=persistent_menu_keyboard(),
    )
    _metrics.inc("rate_limited_total")
    return False


async def _notify_track_status(
    bot,
    chat_id: int,
    client: LightRAGClient,
    track_id: str,
    target: str,
) -> None:
    progress_points = {1, 4, 8, 12}
    for attempt in range(1, _TRACK_POLL_ATTEMPTS + 1):
        await asyncio.sleep(_TRACK_POLL_INTERVAL_SECONDS)
        try:
            ok, summary, is_terminal, is_success = await asyncio.to_thread(
                client.track_status,
                track_id,
            )
        except Exception as exc:
            logger.warning("Track polling failed for %s: %s", track_id, exc)
            continue
        if not ok:
            logger.warning("Track status check failed for %s: %s", track_id, summary)
            continue
        if is_terminal:
            if is_success:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"{target.capitalize()} обработан в LightRAG. {summary}",
                )
                _metrics.inc("track_success_total")
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"{target.capitalize()} обработан с ошибками. {summary}",
                )
                _metrics.inc("track_failed_total")
            return
        if attempt in progress_points:
            await bot.send_message(
                chat_id=chat_id,
                text=f"{target.capitalize()} все еще обрабатывается... {summary}",
            )

    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"Пока нет финального статуса обработки ({target}). "
            "Проверь позже в меню Статус."
        ),
    )
    _metrics.inc("track_timeout_total")


async def show_modes_menu(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.choosing_mode)
    await message.answer(
        "Выбери режим работы:",
        reply_markup=modes_inline_keyboard(),
    )


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await qa_conversation_store.clear(message.chat.id)
    await message.answer(
        "Бот LightRAG готов к работе.",
        reply_markup=persistent_menu_keyboard(),
    )
    await show_modes_menu(message=message, state=state)


@router.message(Command("menu"))
async def menu_command_handler(message: Message, state: FSMContext) -> None:
    await show_modes_menu(message=message, state=state)


@router.message(Command("forgetctx", "forget_context"))
async def forget_context_handler(message: Message, state: FSMContext) -> None:
    await qa_conversation_store.clear(message.chat.id)
    await message.answer(
        "Контекст диалога для Q&A сброшен.",
        reply_markup=persistent_menu_keyboard(),
    )


@router.message(Command("omodel"))
async def omodel_command_handler(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    parts = raw.split(maxsplit=1)
    data = await state.get_data()
    current = _qa_openai_model_from_state(data)
    if len(parts) == 1:
        hint = _openai_model_price_hint(current)
        price = f" ({hint})" if hint else ""
        await message.answer(
            f"Текущая модель OpenAI для Q&A: {current}{price}",
            reply_markup=qa_openai_models_inline_keyboard(current),
        )
        return

    model = parts[1].strip().lower()
    if model in {"auto", "default"}:
        await state.update_data(qa_openai_model_override=None)
        resolved = resolve_openai_model(None)
        await message.answer(
            f"Модель OpenAI сброшена в default: {resolved}",
            reply_markup=qa_openai_models_inline_keyboard(resolved),
        )
        return
    if not is_allowed_openai_model(model):
        catalog = ", ".join(m.model_id for m in get_available_openai_models())
        await message.answer(
            f"Неверная модель. Доступно: {catalog}",
            reply_markup=qa_openai_models_inline_keyboard(current),
        )
        return

    await state.update_data(qa_openai_model_override=model)
    hint = _openai_model_price_hint(model)
    await message.answer(
        f"Модель OpenAI для Q&A: {model} ({hint})",
        reply_markup=qa_openai_models_inline_keyboard(model),
    )


@router.message(Command("qmode"))
async def qmode_command_handler(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    parts = raw.split(maxsplit=1)
    if len(parts) == 1:
        data = await state.get_data()
        current = data.get("qa_mode_override")
        if current:
            await message.answer(
                f"Текущий режим Q&A для этого чата: {current}",
                reply_markup=persistent_menu_keyboard(),
            )
        else:
            await message.answer(
                "Текущий режим Q&A: auto (из BOT_QUERY_MODE + fallback).",
                reply_markup=persistent_menu_keyboard(),
            )
        return

    mode = parts[1].strip().lower()
    if mode in {"auto", "default"}:
        await state.update_data(qa_mode_override=None)
        await message.answer("Q&A режим сброшен в auto.", reply_markup=persistent_menu_keyboard())
        return
    if mode not in _ALLOWED_QUERY_MODES:
        await message.answer(
            "Неверный режим. Доступно: naive, local, global, hybrid, mix, auto.",
            reply_markup=persistent_menu_keyboard(),
        )
        return

    await state.update_data(qa_mode_override=mode)
    await message.answer(
        f"Q&A режим для этого чата установлен: {mode}",
        reply_markup=persistent_menu_keyboard(),
    )


@router.callback_query(F.data.startswith(OMODEL_SET_PREFIX))
async def omodel_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    model = (callback.data or "")[len(OMODEL_SET_PREFIX) :].strip().lower()
    if not is_allowed_openai_model(model):
        await callback.answer("Модель недоступна", show_alert=False)
        return
    await state.update_data(qa_openai_model_override=model)
    hint = _openai_model_price_hint(model)
    await callback.message.answer(
        f"Модель OpenAI для Q&A: {model} ({hint})",
        reply_markup=qa_openai_models_inline_keyboard(model),
    )
    await callback.answer()


@router.callback_query(F.data.startswith(QMODE_SET_PREFIX))
async def qmode_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    mode = (callback.data or "")[len(QMODE_SET_PREFIX) :].strip().lower()
    if mode in {"auto", "default"}:
        await state.update_data(qa_mode_override=None)
        await callback.message.answer(
            "Q&A режим сброшен в auto.",
            reply_markup=qa_modes_inline_keyboard(None),
        )
        await callback.answer()
        return
    if mode not in _ALLOWED_QUERY_MODES:
        await callback.answer("Неверный режим", show_alert=False)
        return
    await state.update_data(qa_mode_override=mode)
    await callback.message.answer(
        f"Q&A режим для этого чата установлен: {mode}",
        reply_markup=qa_modes_inline_keyboard(mode),
    )
    await callback.answer()


@router.message(F.text == MENU_BUTTON_TEXT)
async def menu_button_handler(message: Message, state: FSMContext) -> None:
    await show_modes_menu(message=message, state=state)


@router.callback_query(F.data == MODE_INGEST_CALLBACK)
async def ingest_mode_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BotStates.ingest_mode)
    await callback.message.answer(
        mode_prompt(BotMode.INGEST),
        reply_markup=back_to_menu_inline_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == MODE_QA_CALLBACK)
async def qa_mode_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BotStates.qa_mode)
    data = await state.get_data()
    current_mode = data.get("qa_mode_override")
    await callback.message.answer(
        "Кнопка «Меню» закреплена внизу.",
        reply_markup=persistent_menu_keyboard(),
    )
    openai_model = _qa_openai_model_from_state(data)
    await callback.message.answer(
        (
            f"{mode_prompt(BotMode.QA)}\n\n"
            "Режим LightRAG: кнопки ниже или /qmode <mode>.\n"
            f"Модель OpenAI: {openai_model} ({_openai_model_price_hint(openai_model)}) — /omodel"
        ),
        reply_markup=qa_modes_inline_keyboard(current_mode),
    )
    await callback.message.answer(
        "Выбери модель OpenAI (judge / веб-синтез / fallback):",
        reply_markup=qa_openai_models_inline_keyboard(openai_model),
    )
    await callback.answer()


async def _send_status_report(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.status_mode)
    client = build_lightrag_client()
    ok, details = await asyncio.to_thread(client.health)
    text = await build_status_report_text(
        state,
        _metrics,
        lightrag_ok=ok,
        lightrag_details=details,
    )
    text = f"{text}\n\nОбновить: /status или «статус». Любой другой текст — вопрос в Q&A."
    parts = _split_long_message(text)
    for idx, part in enumerate(parts):
        if idx == 0:
            markup = persistent_menu_keyboard()
        elif idx == len(parts) - 1:
            markup = back_to_menu_inline_keyboard()
        else:
            markup = None
        await message.answer(part, reply_markup=markup)


@router.callback_query(F.data == MODE_STATUS_CALLBACK)
async def status_mode_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await _send_status_report(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == BACK_TO_MENU_CALLBACK)
async def back_to_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BotStates.choosing_mode)
    await callback.message.answer(
        "Выбери режим работы:",
        reply_markup=modes_inline_keyboard(),
    )
    await callback.answer()


@router.message(BotStates.ingest_mode, F.text)
async def ingest_text_handler(message: Message, state: FSMContext) -> None:
    if not await _apply_rate_limit(message):
        return
    _metrics.inc("ingest_text_total")
    raw_text = message.text or ""
    normalized_text = raw_text.strip()
    if not normalized_text:
        await message.answer(
            "Пустой текст не добавляю. Отправь нормальный текст.",
            reply_markup=persistent_menu_keyboard(),
        )
        return
    if len(normalized_text) > _INGEST_MAX_LEN:
        await message.answer(
            f"Текст слишком длинный для одного сообщения (> {_INGEST_MAX_LEN} символов). "
            "Разбей на несколько сообщений.",
            reply_markup=persistent_menu_keyboard(),
        )
        return

    client = build_lightrag_client()
    is_url_mode = is_http_url(normalized_text)
    translated_applied = False
    translate_enabled = is_translate_to_ru_enabled()

    if is_url_mode:
        await message.answer("Принял ссылку. Парсю страницу и извлекаю значимую информацию...")
        fetch_ok, extracted_or_error = await asyncio.to_thread(
            fetch_significant_text_from_url,
            normalized_text,
        )
        if not fetch_ok:
            await message.answer(
                "Не удалось обработать ссылку. Проверь URL и доступность сайта.",
                reply_markup=persistent_menu_keyboard(),
            )
            logger.warning("URL fetch failed: %s", extracted_or_error)
            return
        ingest_text = extracted_or_error
        description = f"telegram:url chat={message.chat.id} src={normalized_text}"
    else:
        await message.answer("Принял. Добавляю текст в базу знаний...")
        ingest_text = normalized_text
        description = f"telegram:text chat={message.chat.id}"

    if translate_enabled and needs_translation_to_ru(ingest_text):
        await message.answer("Обнаружен не-русский текст. Делаю авто-перевод на русский...")
        tr_ok, tr_or_err = await asyncio.to_thread(
            client.translate_to_russian,
            ingest_text,
        )
        if tr_ok:
            ingest_text = tr_or_err
            description += " translated=ru"
            translated_applied = True
        else:
            logger.warning("Auto-translate failed: %s", tr_or_err)
            await message.answer("Авто-перевод не удался, отправляю оригинал.")

    ok, details, track_id = await asyncio.to_thread(
        client.ingest_text,
        ingest_text,
        description,
    )
    if ok:
        _metrics.inc("ingest_text_success_total")
        base_text = (
            "Данные по ссылке отправлены в LightRAG."
            if is_url_mode
            else "Текст отправлен в LightRAG."
        )
        mode_label = "перевод" if translated_applied else "оригинал"
        if track_id:
            await message.answer(
                f"{base_text} Режим: {mode_label}. Задача поставлена в обработку (ID: {track_id}).",
                reply_markup=persistent_menu_keyboard(),
            )
            asyncio.create_task(
                _notify_track_status(
                    bot=message.bot,
                    chat_id=message.chat.id,
                    client=client,
                    track_id=track_id,
                    target="ссылка" if is_url_mode else "текст",
                )
            )
        else:
            await message.answer(
                f"{base_text} Режим: {mode_label}. Обработка может занять немного времени.",
                reply_markup=persistent_menu_keyboard(),
            )
        return

    logger.warning("Text ingest failed: %s", details)
    _metrics.inc("ingest_text_failed_total")
    await message.answer(_safe_ingest_error(details, "ссылку" if is_url_mode else "текст"))


@router.message(BotStates.ingest_mode, F.document)
async def ingest_document_handler(message: Message, state: FSMContext) -> None:
    if not await _apply_rate_limit(message):
        return
    _metrics.inc("ingest_file_total")
    document = message.document
    if document is None:
        await message.answer("Файл не найден в сообщении.", reply_markup=persistent_menu_keyboard())
        return
    if document.file_size and document.file_size > _INGEST_FILE_MAX_BYTES:
        await message.answer(
            "Файл слишком большой для ingest через бота. "
            "Лимит 20 MB.",
            reply_markup=persistent_menu_keyboard(),
        )
        return

    await message.answer("Принял файл. Добавляю в базу знаний...", reply_markup=persistent_menu_keyboard())
    file_buffer = BytesIO()
    try:
        await message.bot.download(document, destination=file_buffer)
    except Exception as exc:
        logger.warning("Telegram file download failed: %s", exc)
        await message.answer(
            "Не удалось скачать файл из Telegram. Попробуй снова.",
            reply_markup=persistent_menu_keyboard(),
        )
        return
    file_bytes = file_buffer.getvalue()
    if not file_bytes:
        await message.answer("Не удалось прочитать файл из Telegram.", reply_markup=persistent_menu_keyboard())
        return
    if len(file_bytes) > _INGEST_FILE_MAX_BYTES:
        await message.answer(
            "Файл слишком большой для ingest через бота. "
            "Лимит 20 MB.",
            reply_markup=persistent_menu_keyboard(),
        )
        return

    file_name = document.file_name or f"telegram-{document.file_id}.bin"
    mime_type = document.mime_type
    client = build_lightrag_client()
    translate_enabled = is_translate_to_ru_enabled()

    use_text_ingest = False
    text_payload = None
    if translate_enabled and is_text_like_file(file_name, mime_type):
        text_payload = extract_text_from_file_bytes(file_bytes)
        if text_payload:
            use_text_ingest = True

    if use_text_ingest and text_payload is not None:
        await message.answer("Файл распознан как текст. Проверяю, нужен ли авто-перевод...")
        final_text = text_payload
        translated_flag = "false"
        if needs_translation_to_ru(text_payload):
            tr_ok, tr_or_err = await asyncio.to_thread(
                client.translate_to_russian,
                text_payload,
            )
            if tr_ok:
                final_text = tr_or_err
                translated_flag = "true"
            else:
                logger.warning("File auto-translate failed: %s", tr_or_err)
                await message.answer(
                    "Авто-перевод файла не удался, отправляю оригинальный текст.",
                    reply_markup=persistent_menu_keyboard(),
                )
        description = (
            f"telegram:file-text chat={message.chat.id} "
            f"name={file_name} translated_ru={translated_flag}"
        )
        file_mode_label = "перевод" if translated_flag == "true" else "оригинал"
        ok, details, track_id = await asyncio.to_thread(
            client.ingest_text,
            final_text,
            description,
        )
    else:
        description = f"telegram:file chat={message.chat.id}"
        file_mode_label = "оригинал"
        ok, details, track_id = await asyncio.to_thread(
            client.ingest_file,
            file_name,
            file_bytes,
            mime_type,
            description,
        )
    if ok:
        _metrics.inc("ingest_file_success_total")
        base_text = "Файл отправлен в LightRAG."
        if track_id:
            await message.answer(
                f"{base_text} Режим: {file_mode_label}. Задача поставлена в обработку (ID: {track_id}).",
                reply_markup=persistent_menu_keyboard(),
            )
            asyncio.create_task(
                _notify_track_status(
                    bot=message.bot,
                    chat_id=message.chat.id,
                    client=client,
                    track_id=track_id,
                    target="файл",
                )
            )
        else:
            await message.answer(
                f"{base_text} Режим: {file_mode_label}. Обработка может занять немного времени.",
                reply_markup=persistent_menu_keyboard(),
            )
        return

    logger.warning("File ingest failed: %s", details)
    _metrics.inc("ingest_file_failed_total")
    await message.answer(_safe_ingest_error(details, "файл"))


@router.message(BotStates.choosing_mode, F.text)
async def choosing_mode_text_handler(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text == MENU_BUTTON_TEXT:
        return
    await state.set_state(BotStates.qa_mode)
    await qa_question_handler(message, state)


@router.message(Command("status"))
async def status_command_handler(message: Message, state: FSMContext) -> None:
    await _send_status_report(message, state)


@router.message(BotStates.status_mode, F.text)
async def status_mode_text_handler(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text == MENU_BUTTON_TEXT:
        return
    if _is_status_refresh_text(text):
        await _send_status_report(message, state)
        return
    await state.set_state(BotStates.qa_mode)
    await qa_question_handler(message, state)


@router.message(BotStates.qa_mode, F.text)
async def qa_question_handler(message: Message, state: FSMContext) -> None:
    if not await _apply_rate_limit(message):
        return
    _metrics.inc("qa_total")
    question = (message.text or "").strip()
    if not question:
        await message.answer(
            "Пустой вопрос не отправляю. Напиши вопрос текстом.",
            reply_markup=persistent_menu_keyboard(),
        )
        return

    inline_mode, question_without_mode = _extract_inline_mode(question)
    effective_question = _rewrite_qa_question(question_without_mode)
    state_data = await state.get_data()
    openai_model = _qa_openai_model_from_state(state_data)
    configured_mode = (state_data.get("qa_mode_override") or "").strip().lower()
    start_mode = inline_mode or configured_mode or (
        os.getenv("BOT_QUERY_MODE", _DEFAULT_QUERY_MODE).strip().lower() or _DEFAULT_QUERY_MODE
    )
    if start_mode not in _ALLOWED_QUERY_MODES:
        start_mode = _DEFAULT_QUERY_MODE
    fallback_modes = _parse_fallback_modes()

    await qa_conversation_store.expire_if_idle(message.chat.id)
    contextual_question = await qa_conversation_store.build_contextual_query(
        message.chat.id,
        effective_question,
    )

    client = build_lightrag_client()
    model_hint = _openai_model_price_hint(openai_model)
    chat_context = await qa_conversation_store.get_dialog_context_block(message.chat.id)
    deep_task_type = ""
    used_deep_qa = False

    if is_deep_qa_enabled():
        await message.answer(
            "Принял вопрос. Глубокий поиск в базе знаний "
            f"(несколько запросов LightRAG; OpenAI: {openai_model} {model_hint})…",
            reply_markup=persistent_menu_keyboard(),
        )
        deep_ok, deep_outcome, deep_err = await asyncio.to_thread(
            run_deep_qa,
            contextual_question,
            effective_question,
            client=client,
            primary_mode=start_mode,
            fallback_modes=fallback_modes,
            chat_context=chat_context,
            openai_model=openai_model,
        )
        if deep_ok and deep_outcome is not None:
            _metrics.inc("qa_deep_success_total")
            used_deep_qa = True
            rag_answer = deep_outcome.answer
            used_mode = deep_outcome.mode_label
            deep_task_type = deep_outcome.task_type
            if deep_err:
                logger.info("Deep QA plan note: %s", deep_err)
        else:
            _metrics.inc("qa_deep_fallback_total")
            logger.warning("Deep QA failed, fallback to single query: %s", deep_err)
            await message.answer(
                "Глубокий поиск не удался, пробую обычный запрос в LightRAG…",
                reply_markup=persistent_menu_keyboard(),
            )

    if not used_deep_qa:
        await message.answer(
            "Принял вопрос. Ищу ответ в LightRAG "
            f"(старт: {start_mode}, fallback: {','.join(fallback_modes)}; "
            f"OpenAI: {openai_model} {model_hint})...",
            reply_markup=persistent_menu_keyboard(),
        )
        ok, answer_or_error, used_mode = await asyncio.to_thread(
            client.ask_with_fallback,
            contextual_question,
            start_mode,
            fallback_modes,
        )
        if not ok:
            logger.warning("QA query failed: %s (%s)", answer_or_error, used_mode)
            _metrics.inc("qa_failed_total")
            await message.answer(
                "Не удалось получить ответ из LightRAG. Попробуй снова.",
                reply_markup=persistent_menu_keyboard(),
            )
            return
        rag_answer = answer_or_error

    skip_web = used_deep_qa and deep_qa_skips_web_enrichment(deep_task_type)
    if skip_web:
        final_answer = rag_answer
        source_label = "LightRAG (глубокий, только БЗ)"
        web_references: tuple = ()
        web_notice = ""
    else:
        final_answer, source_label, used_mode, web_references, web_notice = (
            await _try_enrich_with_web_search(
                message,
                client,
                contextual_question=contextual_question,
                effective_question=effective_question,
                rag_answer=rag_answer,
                used_mode=used_mode,
                openai_model=openai_model,
            )
        )
    web_enriched = bool(web_references)

    openai_fallback_allowed = _is_openai_fallback_enabled() and not (
        used_deep_qa and deep_qa_blocks_openai_fallback()
    )
    if (
        openai_fallback_allowed
        and not web_enriched
        and client.is_weak_answer(final_answer)
    ):
        openai_ok, openai_answer = await asyncio.to_thread(
            client.query_openai_general,
            contextual_question,
            model=openai_model,
        )
        if openai_ok and not client.is_weak_answer(openai_answer):
            final_answer = openai_answer
            base_mode = used_mode.split(" -> web")[0]
            used_mode = f"{base_mode} -> openai"
            source_label = "модель (вне RAG)"
            web_references = ()

    translated_mode = "оригинал"
    if is_translate_to_ru_enabled() and needs_translation_to_ru(final_answer):
        tr_ok, tr_or_err = await asyncio.to_thread(
            client.translate_to_russian,
            final_answer,
        )
        if tr_ok:
            final_answer = tr_or_err
            translated_mode = "перевод"
        else:
            logger.warning("QA auto-translate failed: %s", tr_or_err)

    if web_references:
        final_answer = format_answer_with_references(final_answer, web_references)

    notice_prefix = f"{web_notice}\n\n" if web_notice else ""
    await _send_long_message(
        message,
        (
            f"Режим поиска: {used_mode}\n"
            f"Модель OpenAI: {openai_model}\n"
            f"Источник ответа: {source_label}\n"
            f"Режим ответа: {translated_mode}\n\n{notice_prefix}{final_answer}"
        ),
    )
    _metrics.inc("qa_success_total")
    await qa_conversation_store.record_exchange(
        message.chat.id,
        effective_question,
        answer_body_without_references(final_answer),
    )


@router.message(F.text, StateFilter(None))
async def fallback_text_handler(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text == MENU_BUTTON_TEXT:
        return
    await state.set_state(BotStates.qa_mode)
    await qa_question_handler(message, state)


@router.errors()
async def router_error_handler(event) -> bool:
    logger.exception("Unhandled router error: %s", event.exception)
    update = getattr(event, "update", None)
    message = getattr(update, "message", None) if update else None
    if message is None and update is not None:
        callback_query = getattr(update, "callback_query", None)
        if callback_query is not None:
            message = callback_query.message
    if message is not None:
        await message.answer(
            "Внутренняя ошибка бота. Попробуй еще раз.",
            reply_markup=persistent_menu_keyboard(),
        )
    _metrics.inc("unhandled_errors_total")
    return True

