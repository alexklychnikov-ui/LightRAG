import unittest

from telegram_bot.translation import needs_translation_to_ru, split_text_for_translation


class TestTranslationUtils(unittest.TestCase):
    def test_needs_translation_true_for_english_text(self) -> None:
        text = "This is a long enough English text block " * 4
        self.assertTrue(needs_translation_to_ru(text))

    def test_needs_translation_false_for_code_like_content(self) -> None:
        text = "https://example.com/api { id: 10, name: 'alex' }"
        self.assertFalse(needs_translation_to_ru(text))

    def test_split_text_for_translation(self) -> None:
        text = ("Paragraph one.\n\n" + ("A" * 1200) + "\n\n") * 4
        chunks = split_text_for_translation(text, max_chunk_chars=1000)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 1000 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()

