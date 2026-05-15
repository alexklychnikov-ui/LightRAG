import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from .config import load_config
from .handlers import router
from .qa_context import qa_session_ttl_enabled, session_prune_loop


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    return dp


async def run_bot() -> None:
    config = load_config()
    bot = Bot(token=config.telegram_bot_token)
    dp = build_dispatcher()
    await bot.delete_webhook(drop_pending_updates=True)
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

