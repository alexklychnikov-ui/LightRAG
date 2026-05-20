from __future__ import annotations

import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

logger = logging.getLogger(__name__)

_DENY_NOTIFY_COOLDOWN_SECONDS = 300.0
_last_deny_notify: dict[int, float] = {}


def _parse_id_list(raw: str) -> set[int]:
    ids: set[int] = set()
    for part in (raw or "").split(","):
        piece = part.strip()
        if not piece:
            continue
        try:
            ids.add(int(piece))
        except ValueError:
            logger.warning("Ignoring invalid id in access control list: %s", piece)
    return ids


def allowed_user_ids() -> frozenset[int]:
    ids = _parse_id_list(os.getenv("BOT_ALLOWED_USER_IDS", ""))
    chat_id_raw = os.getenv("TELEGRAM_BOT_CHATID", "").strip()
    if chat_id_raw:
        try:
            ids.add(int(chat_id_raw))
        except ValueError:
            logger.warning("Invalid TELEGRAM_BOT_CHATID for access control: %s", chat_id_raw)
    return frozenset(ids)


def is_access_control_enabled() -> bool:
    return bool(allowed_user_ids())


def access_control_required_at_startup() -> bool:
    raw = os.getenv("BOT_ACCESS_CONTROL_REQUIRED", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def deny_group_chats_enabled() -> bool:
    raw = os.getenv("BOT_DENY_GROUP_CHATS", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _extract_actor(update: TelegramObject) -> tuple[int | None, int | None, str | None]:
    if isinstance(update, Update):
        if update.message:
            return (
                update.message.from_user.id if update.message.from_user else None,
                update.message.chat.id,
                update.message.chat.type,
            )
        if update.callback_query:
            cq = update.callback_query
            chat = cq.message.chat if cq.message else None
            return (
                cq.from_user.id if cq.from_user else None,
                chat.id if chat else None,
                chat.type if chat else None,
            )
        if update.edited_message:
            return (
                update.edited_message.from_user.id if update.edited_message.from_user else None,
                update.edited_message.chat.id,
                update.edited_message.chat.type,
            )
        return None, None, None

    if isinstance(update, Message):
        return (
            update.from_user.id if update.from_user else None,
            update.chat.id,
            update.chat.type,
        )
    if isinstance(update, CallbackQuery):
        chat = update.message.chat if update.message else None
        return (
            update.from_user.id if update.from_user else None,
            chat.id if chat else None,
            chat.type if chat else None,
        )
    return None, None, None


def is_user_allowed(user_id: int | None, chat_type: str | None) -> bool:
    allowed = allowed_user_ids()
    if not allowed:
        return True
    if user_id is None:
        return False
    if deny_group_chats_enabled() and chat_type and chat_type != "private":
        return False
    return user_id in allowed


def _should_notify_denied(user_id: int | None) -> bool:
    if user_id is None:
        return False
    now = time.time()
    last = _last_deny_notify.get(user_id, 0.0)
    if now - last < _DENY_NOTIFY_COOLDOWN_SECONDS:
        return False
    _last_deny_notify[user_id] = now
    return True


async def _answer_denied_callback(event: TelegramObject) -> None:
    callback: CallbackQuery | None = None
    if isinstance(event, Update) and event.callback_query:
        callback = event.callback_query
    elif isinstance(event, CallbackQuery):
        callback = event
    if callback is None:
        return
    try:
        await callback.answer("Доступ запрещён", show_alert=True)
    except Exception as exc:
        logger.warning("Failed to answer denied callback: %s", exc)


async def _notify_access_denied(event: TelegramObject, data: dict[str, Any]) -> None:
    await _answer_denied_callback(event)
    user_id, chat_id, chat_type = _extract_actor(event)
    if chat_type and chat_type != "private":
        return
    if not _should_notify_denied(user_id) or chat_id is None:
        return
    bot = data.get("bot")
    if bot is None:
        return
    text = os.getenv(
        "BOT_ACCESS_DENIED_MESSAGE",
        "Доступ к этому боту ограничён.",
    ).strip()
    if not text:
        return
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except Exception as exc:
        logger.warning("Failed to send access denied message: %s", exc)


class AccessControlMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id, _chat_id, chat_type = _extract_actor(event)
        if is_user_allowed(user_id, chat_type):
            return await handler(event, data)

        logger.info(
            "Access denied for user_id=%s chat_type=%s",
            user_id,
            chat_type,
        )
        await _notify_access_denied(event, data)
        return None
