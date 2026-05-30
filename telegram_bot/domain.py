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
        "Ответ строится глубоким поиском по базе знаний (несколько запросов LightRAG + синтез). "
        "Контекст диалога учитывается; для резюме/документов — только факты из БЗ, без выдумок. "
        "При неполном ответе по другим темам — дополнение из интернета (References). "
        "Модель OpenAI — кнопками ниже (по умолчанию o4-mini). "
        "Сброс контекста: /forgetctx или /start."
    ),
    BotMode.STATUS: (
        "Режим: Статус\n"
        "Покажу состояние LightRAG и пайплайна."
    ),
}


def mode_prompt(mode: BotMode) -> str:
    return MODE_PROMPTS[mode]

