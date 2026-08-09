import unittest
from unittest.mock import patch

from telegram_bot.handlers import (
    _extract_inline_mode,
    _is_status_refresh_text,
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

    def test_rewrite_where_i_live(self) -> None:
        rewritten = _rewrite_qa_question("где я живу")
        self.assertIn("городе", rewritten)
        self.assertIn("Клычников", rewritten)

    def test_is_status_refresh_text(self) -> None:
        self.assertTrue(_is_status_refresh_text("/status"))
        self.assertTrue(_is_status_refresh_text("  статус "))
        self.assertFalse(_is_status_refresh_text("Перечисли где я работал"))

    def test_extract_inline_mode(self) -> None:
        mode, question = _extract_inline_mode("режим:global | что ты знаешь?")
        self.assertEqual(mode, "global")
        self.assertEqual(question, "что ты знаешь?")

    @patch.dict("os.environ", {"BOT_QUERY_FALLBACK_MODES": "hybrid,global,hybrid,unknown"})
    def test_parse_fallback_modes(self) -> None:
        modes = _parse_fallback_modes()
        self.assertEqual(modes, ("hybrid", "global", "naive"))

    def test_resolve_attachment_question_uses_caption(self) -> None:
        from telegram_bot.handlers import _resolve_attachment_question

        self.assertEqual(
            _resolve_attachment_question("что думаешь?"),
            "что думаешь?",
        )

    def test_resolve_attachment_question_default(self) -> None:
        from telegram_bot.handlers import (
            _DEFAULT_ATTACHMENT_QUESTION,
            _resolve_attachment_question,
        )

        self.assertEqual(_resolve_attachment_question(None), _DEFAULT_ATTACHMENT_QUESTION)
        self.assertEqual(_resolve_attachment_question("  "), _DEFAULT_ATTACHMENT_QUESTION)

    def test_build_attachment_prompt_block(self) -> None:
        from telegram_bot.handlers import _build_attachment_prompt_block

        block = _build_attachment_prompt_block("zeroInput.md", "hello TZ")
        self.assertIn("zeroInput.md", block)
        self.assertIn("hello TZ", block)

    def test_extract_text_respects_max_chars(self) -> None:
        from telegram_bot.file_text_extract import extract_text_from_file_bytes

        payload = ("x" * 5000).encode("utf-8")
        text = extract_text_from_file_bytes(payload, max_chars=100)
        self.assertIsNotNone(text)
        self.assertEqual(len(text or ""), 100)

    @patch.dict("os.environ", {"BOT_QUERY_FALLBACK_MODES": "naive,global"})
    def test_parse_fallback_modes_keeps_single_naive(self) -> None:
        modes = _parse_fallback_modes()
        self.assertEqual(modes, ("naive", "global"))


if __name__ == "__main__":
    unittest.main()

