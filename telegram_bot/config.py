import os
from dataclasses import dataclass


@dataclass(frozen=True)
class BotConfig:
    telegram_bot_token: str
    lightrag_url: str
    telegram_bot_chat_id: int | None


def load_config() -> BotConfig:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    lightrag_url = os.getenv("LIGHTRAG_URL", "http://127.0.0.1:9621").strip()
    chat_id_raw = os.getenv("TELEGRAM_BOT_CHATID", "").strip()
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    if chat_id_raw:
        try:
            chat_id = int(chat_id_raw)
        except ValueError as exc:
            raise ValueError("TELEGRAM_BOT_CHATID must be integer") from exc
    else:
        chat_id = None
    return BotConfig(
        telegram_bot_token=token,
        lightrag_url=lightrag_url,
        telegram_bot_chat_id=chat_id,
    )

