from aiogram.fsm.state import State, StatesGroup


class BotStates(StatesGroup):
    choosing_mode = State()
    ingest_mode = State()
    qa_mode = State()
    status_mode = State()

