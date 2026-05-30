import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from .access_control import (
    AccessControlMiddleware,
    access_control_required_at_startup,
    allowed_user_ids,
    is_access_control_enabled,
)
from .config import load_config
from .handlers import router
from .openai_models import refresh_openai_models_catalog
from .qa_context import qa_session_ttl_enabled, session_prune_loop

logger = logging.getLogger(__name__)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(AccessControlMiddleware())
    dp.include_router(router)
    return dp


async def run_bot() -> None:
    config = load_config()
    if access_control_required_at_startup() and not is_access_control_enabled():
        raise ValueError(
            "BOT_ACCESS_CONTROL_REQUIRED=true but BOT_ALLOWED_USER_IDS "
            "and TELEGRAM_BOT_CHATID are empty"
        )
    if is_access_control_enabled() and config.telegram_bot_chat_id is not None:
        allowed = allowed_user_ids()
        if config.telegram_bot_chat_id not in allowed:
            logger.warning(
                "TELEGRAM_BOT_CHATID=%s is not in allowed user id set",
                config.telegram_bot_chat_id,
            )
    bot = Bot(token=config.telegram_bot_token)
    dp = build_dispatcher()
    if is_access_control_enabled():
        logger.info(
            "Access control enabled for user ids: %s",
            ",".join(str(uid) for uid in sorted(allowed_user_ids())),
        )
    else:
        logger.warning(
            "Access control DISABLED: set BOT_ALLOWED_USER_IDS or TELEGRAM_BOT_CHATID"
        )
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.to_thread(refresh_openai_models_catalog)
    prune_task: asyncio.Task | None = None
    if qa_session_ttl_enabled():
        prune_task = asyncio.create_task(session_prune_loop(60.0), name="qa-session-prune")
    try:
        await dp.start_polling(bot)
    finally:
        if prune_task is not None:
            prune_task.cancel()
            try:
                await prune_task
            except asyncio.CancelledError:
                pass


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()

