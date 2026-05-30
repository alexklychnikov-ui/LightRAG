from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from .openai_models import OMODEL_SET_PREFIX, get_available_openai_models

MENU_BUTTON_TEXT = "Меню"
BACK_TO_MENU_CALLBACK = "menu:open"
MODE_INGEST_CALLBACK = "mode:ingest"
MODE_QA_CALLBACK = "mode:qa"
MODE_STATUS_CALLBACK = "mode:status"
QMODE_SET_PREFIX = "qmode:set:"


def persistent_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=MENU_BUTTON_TEXT)]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
    )


def modes_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Пополнить БЗ",
                    callback_data=MODE_INGEST_CALLBACK,
                )
            ],
            [
                InlineKeyboardButton(
                    text="Задать вопрос",
                    callback_data=MODE_QA_CALLBACK,
                )
            ],
            [
                InlineKeyboardButton(
                    text="Статус",
                    callback_data=MODE_STATUS_CALLBACK,
                )
            ],
        ]
    )


def back_to_menu_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Назад в меню",
                    callback_data=BACK_TO_MENU_CALLBACK,
                )
            ]
        ]
    )


def qa_modes_inline_keyboard(current_mode: str | None) -> InlineKeyboardMarkup:
    def label(mode: str) -> str:
        if current_mode == mode:
            return f"✅ {mode}"
        return mode

    auto_label = "✅ auto" if not current_mode else "auto"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label("mix"),
                    callback_data=f"{QMODE_SET_PREFIX}mix",
                ),
                InlineKeyboardButton(
                    text=label("hybrid"),
                    callback_data=f"{QMODE_SET_PREFIX}hybrid",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=label("global"),
                    callback_data=f"{QMODE_SET_PREFIX}global",
                ),
                InlineKeyboardButton(
                    text=label("local"),
                    callback_data=f"{QMODE_SET_PREFIX}local",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=label("naive"),
                    callback_data=f"{QMODE_SET_PREFIX}naive",
                ),
                InlineKeyboardButton(
                    text=auto_label,
                    callback_data=f"{QMODE_SET_PREFIX}auto",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Назад в меню",
                    callback_data=BACK_TO_MENU_CALLBACK,
                )
            ],
        ]
    )


def qa_openai_models_inline_keyboard(
    current_model: str | None,
) -> InlineKeyboardMarkup:
    models = get_available_openai_models()
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for info in models:
        row.append(
            InlineKeyboardButton(
                text=info.button_label(selected=current_model == info.model_id),
                callback_data=f"{OMODEL_SET_PREFIX}{info.model_id}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(
                text="Назад в меню",
                callback_data=BACK_TO_MENU_CALLBACK,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)

