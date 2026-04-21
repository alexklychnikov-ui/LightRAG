import unittest

from telegram_bot.domain import BotMode, mode_prompt


class TestBotDomain(unittest.TestCase):
    def test_mode_prompt_for_ingest(self) -> None:
        text = mode_prompt(BotMode.INGEST)
        self.assertIn("Пополнить БЗ", text)

    def test_mode_prompt_for_qa(self) -> None:
        text = mode_prompt(BotMode.QA)
        self.assertIn("Задать вопрос", text)

    def test_mode_prompt_for_status(self) -> None:
        text = mode_prompt(BotMode.STATUS)
        self.assertIn("Статус", text)


if __name__ == "__main__":
    unittest.main()

