import unittest

from telegram_bot.translation import (
    is_mostly_raw_code,
    needs_translation_to_ru,
    split_text_for_translation,
)


class TestTranslationUtils(unittest.TestCase):
    def test_needs_translation_true_for_english_text(self) -> None:
        text = "This is a long enough English text block " * 4
        self.assertTrue(needs_translation_to_ru(text))

    def test_needs_translation_false_for_code_like_content(self) -> None:
        lines = [
            "import os",
            "from pathlib import Path",
            "",
            "class Foo:",
            "    def bar(self) -> None:",
            "        return None",
            "",
            "async def main() -> None:",
            "    pass",
            "",
            "SELECT id, name FROM users WHERE active = 1;",
            "#include <stdio.h>",
            "package com.example;",
            "export const x = 1;",
            "{",
            "};",
        ]
        text = "\n".join(lines)
        self.assertTrue(is_mostly_raw_code(text))
        self.assertFalse(needs_translation_to_ru(text))

    def test_needs_translation_true_for_prose_with_code_snippet(self) -> None:
        prose = (
            "This documentation explains how to configure the service in production. "
            "Follow each step carefully before you deploy. "
        ) * 5
        text = prose + "Example: `kubectl apply -f manifest.yaml` and then run `systemctl restart app`."
        self.assertFalse(is_mostly_raw_code(text))
        self.assertTrue(needs_translation_to_ru(text))

    def test_split_text_for_translation(self) -> None:
        text = ("Paragraph one.\n\n" + ("A" * 1200) + "\n\n") * 4
        chunks = split_text_for_translation(text, max_chunk_chars=1000)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 1000 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()

