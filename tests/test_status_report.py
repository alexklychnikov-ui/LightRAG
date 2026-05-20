import unittest
from unittest.mock import patch

from telegram_bot.reliability import BotRuntimeMetrics, format_metrics_ru
from telegram_bot.status_report import _qa_settings_lines


class TestStatusReport(unittest.TestCase):
    def test_format_metrics_ru_shows_zeros(self) -> None:
        text = format_metrics_ru({})
        self.assertIn("вопросов получено: 0", text)

    def test_format_metrics_ru_with_values(self) -> None:
        metrics = BotRuntimeMetrics()
        metrics.inc("qa_total", 3)
        text = format_metrics_ru(metrics.snapshot())
        self.assertIn("вопросов получено: 3", text)

    @patch.dict(
        "os.environ",
        {
            "BOT_QUERY_MODE": "hybrid",
            "BOT_ENABLE_WEB_SEARCH": "true",
            "BOT_WEB_SEARCH_PROVIDER": "tavily",
        },
        clear=False,
    )
    def test_qa_settings_lines(self) -> None:
        lines = _qa_settings_lines({"qa_mode_override": "global"})
        joined = "\n".join(lines)
        self.assertIn("hybrid", joined)
        self.assertIn("global", joined)
        self.assertIn("веб-поиск: вкл", joined)
