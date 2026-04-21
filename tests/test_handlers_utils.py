import unittest
from unittest.mock import patch

from telegram_bot.handlers import (
    _extract_inline_mode,
    _parse_fallback_modes,
    _rewrite_qa_question,
    _safe_ingest_error,
    _split_long_message,
)


class TestHandlerUtils(unittest.TestCase):
    def test_safe_ingest_error_with_status(self) -> None:
        text = _safe_ingest_error("ingest status=415 body=unsupported", "файл")
        self.assertIn("HTTP 415", text)
        self.assertIn("файл", text)
        self.assertNotIn("unsupported", text)

    def test_safe_ingest_error_without_status(self) -> None:
        text = _safe_ingest_error("ingest error=timeout", "текст")
        self.assertIn("Не удалось добавить текст", text)
        self.assertNotIn("timeout", text)

    def test_split_long_message(self) -> None:
        long_text = ("line\n" * 2000).strip()
        parts = _split_long_message(long_text, chunk_size=500)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= 500 for part in parts))

    def test_rewrite_qa_question(self) -> None:
        rewritten = _rewrite_qa_question("Как меня зовут?")
        self.assertEqual(rewritten, "как зовут разработчика в introMain.md")

    def test_extract_inline_mode(self) -> None:
        mode, question = _extract_inline_mode("режим:global | что ты знаешь?")
        self.assertEqual(mode, "global")
        self.assertEqual(question, "что ты знаешь?")

    @patch.dict("os.environ", {"BOT_QUERY_FALLBACK_MODES": "hybrid,global,hybrid,unknown"})
    def test_parse_fallback_modes(self) -> None:
        modes = _parse_fallback_modes()
        self.assertEqual(modes, ("hybrid", "global"))


if __name__ == "__main__":
    unittest.main()

