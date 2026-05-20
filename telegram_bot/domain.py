from enum import Enum


class BotMode(str, Enum):
    INGEST = "ingest"
    QA = "qa"
    STATUS = "status"


MODE_PROMPTS: dict[BotMode, str] = {
    BotMode.INGEST: (
        "Режим: Пополнить БЗ\n"
        "Отправь текст, файл или ссылку."
    ),
    BotMode.QA: (
        "Режим: Задать вопрос\n"
        "Отправь вопрос в одном сообщении. "
        "Контекст диалога в этом чате учитывается для следующих вопросов; "
        "при неполном ответе из базы — дополнение из интернета (References внизу). "
        "Сброс контекста: /forgetctx или /start."
    ),
    BotMode.STATUS: (
        "Режим: Статус\n"
        "Покажу состояние LightRAG и пайплайна."
    ),
}


def mode_prompt(mode: BotMode) -> str:
    return MODE_PROMPTS[mode]

