import unittest
from unittest.mock import Mock

from telegram_bot.web_answer_synthesis import (
    collect_references,
    format_answer_with_references,
    format_references_block,
    normalize_reference_url,
    synthesize_with_web,
)
from telegram_bot.web_search import WebSearchResult


class TestWebAnswerSynthesisFormatting(unittest.TestCase):
    def test_format_references_block(self) -> None:
        refs = (
            WebSearchResult("Doc A", "https://a.com/x", "snippet", "q"),
            WebSearchResult("Doc B", "https://b.com", "snippet", "q"),
        )
        block = format_references_block(refs)
        self.assertIn("References:", block)
        self.assertIn("https://a.com/x", block)
        self.assertIn("Doc B", block)

    def test_format_answer_with_references_strips_duplicate_header(self) -> None:
        refs = (WebSearchResult("T", "https://t.com", "s", "q"),)
        text = format_answer_with_references(
            "Основной ответ.\n\nReferences:\n- fake",
            refs,
        )
        self.assertIn("Основной ответ.", text)
        self.assertIn("https://t.com", text)
        self.assertNotIn("fake", text)

    def test_collect_references_dedupes(self) -> None:
        rows = [
            WebSearchResult("A", "https://Example.com/p", "s", "q1"),
            WebSearchResult("B", "https://example.com/p/", "s", "q2"),
        ]
        refs = collect_references(rows)
        self.assertEqual(len(refs), 1)


class TestSynthesizeWithWeb(unittest.TestCase):
    def test_synthesize_success(self) -> None:
        client = Mock()
        client.query_openai_chat.return_value = (
            True,
            "По базе знаний: X. Из открытых источников: Y.",
        )
        web = [
            WebSearchResult("Source", "https://source.com/doc", "web snippet", "q"),
        ]
        ok, outcome, err = synthesize_with_web(
            "Что такое LightRAG?",
            "LightRAG — graph RAG.",
            web,
            client=client,
        )
        self.assertTrue(ok)
        self.assertEqual(err, "")
        assert outcome is not None
        self.assertIn("базе знаний", outcome.answer)
        self.assertEqual(len(outcome.references), 1)
        self.assertEqual(
            normalize_reference_url(outcome.references[0].url),
            "https://source.com/doc",
        )
        client.query_openai_chat.assert_called_once()

    def test_scrubs_hallucinated_url(self) -> None:
        client = Mock()
        client.query_openai_chat.return_value = (
            True,
            "Ответ с левой ссылкой https://evil.com/x и без раздела References.",
        )
        web = [WebSearchResult("Ok", "https://good.com/a", "s", "q")]
        ok, outcome, err = synthesize_with_web("q", "rag", web, client=client)
        self.assertTrue(ok)
        assert outcome is not None
        self.assertNotIn("evil.com", outcome.answer)

    def test_no_web_results(self) -> None:
        ok, outcome, err = synthesize_with_web("q", "rag", [])
        self.assertFalse(ok)
        self.assertIsNone(outcome)
        self.assertIn("no web results", err)

    def test_synthesize_with_empty_rag(self) -> None:
        client = Mock()
        client.query_openai_chat.return_value = (True, "Ответ только из сети.")
        web = [WebSearchResult("S", "https://good.com", "snippet", "q")]
        ok, outcome, err = synthesize_with_web("q", "", web, client=client)
        self.assertTrue(ok)
        assert outcome is not None
        self.assertIn("сети", outcome.answer)
