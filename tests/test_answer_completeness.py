import unittest
from unittest.mock import Mock, patch

from telegram_bot.answer_completeness import (
    CompletenessVerdict,
    assess_rag_answer,
    is_completeness_judge_enabled,
    parse_completeness_json_text,
    parse_completeness_payload,
)
from telegram_bot.lightrag_client import LightRAGClient


class TestParseCompleteness(unittest.TestCase):
    def test_parse_needs_web_with_queries(self) -> None:
        verdict = parse_completeness_payload(
            {
                "needs_web": True,
                "queries": ["LightRAG release 2025", "LightRAG docs"],
                "reason": "нет актуальных дат",
                "confidence": 0.9,
            }
        )
        self.assertIsNotNone(verdict)
        assert verdict is not None
        self.assertTrue(verdict.needs_web)
        self.assertEqual(len(verdict.queries), 2)

    def test_low_confidence_blocks_web(self) -> None:
        verdict = parse_completeness_payload(
            {
                "needs_web": True,
                "queries": ["x"],
                "reason": "maybe",
                "confidence": 0.2,
            }
        )
        self.assertIsNotNone(verdict)
        assert verdict is not None
        self.assertFalse(verdict.needs_web)

    def test_needs_web_without_queries_invalid(self) -> None:
        self.assertIsNone(
            parse_completeness_payload(
                {"needs_web": True, "queries": [], "confidence": 0.9}
            )
        )

    def test_parse_json_text_with_wrapper(self) -> None:
        raw = 'prefix {"needs_web": false, "queries": [], "reason": "ok", "confidence": 0.8} suffix'
        verdict = parse_completeness_json_text(raw)
        self.assertIsNotNone(verdict)
        assert verdict is not None
        self.assertFalse(verdict.needs_web)


class TestAssessRagAnswer(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {"BOT_ENABLE_ANSWER_COMPLETENESS_JUDGE": "false", "BOT_ENABLE_WEB_SEARCH": "false"},
        clear=False,
    )
    def test_judge_disabled(self) -> None:
        ok, verdict, err = assess_rag_answer("q", "a")
        self.assertTrue(ok)
        self.assertEqual(err, "")
        assert verdict is not None
        self.assertFalse(verdict.needs_web)

    @patch.dict(
        "os.environ",
        {"BOT_ENABLE_ANSWER_COMPLETENESS_JUDGE": "false", "BOT_ENABLE_WEB_SEARCH": "true"},
        clear=False,
    )
    def test_weak_answer_with_judge_disabled_still_needs_web(self) -> None:
        ok, verdict, err = assess_rag_answer("q", "Недостаточно информации в базе.")
        self.assertTrue(ok)
        assert verdict is not None
        self.assertTrue(verdict.needs_web)
        self.assertTrue(verdict.queries)

    @patch.dict(
        "os.environ",
        {"BOT_ENABLE_ANSWER_COMPLETENESS_JUDGE": "true", "BOT_ENABLE_WEB_SEARCH": "true"},
        clear=False,
    )
    def test_weak_answer_skips_llm(self) -> None:
        client = Mock(spec=LightRAGClient)
        ok, verdict, err = assess_rag_answer(
            "Что нового в Python 3.13?",
            "Недостаточно информации в базе.",
            client=client,
        )
        self.assertTrue(ok)
        assert verdict is not None
        self.assertTrue(verdict.needs_web)
        self.assertTrue(verdict.queries)
        client.query_openai_json.assert_not_called()

    @patch.dict("os.environ", {"BOT_ENABLE_ANSWER_COMPLETENESS_JUDGE": "true"}, clear=False)
    def test_llm_judge_needs_web(self) -> None:
        client = Mock(spec=LightRAGClient)
        client.query_openai_json.return_value = (
            True,
            {
                "needs_web": True,
                "queries": ["Python 3.13 release date"],
                "reason": "нужны внешние факты",
                "confidence": 0.88,
            },
        )
        ok, verdict, err = assess_rag_answer(
            "Когда вышел Python 3.13?",
            "Python 3.13 — версия языка.",
            client=client,
        )
        self.assertTrue(ok)
        self.assertEqual(err, "")
        assert verdict is not None
        self.assertTrue(verdict.needs_web)
        self.assertIn("Python 3.13", verdict.queries[0])


class TestJudgeConfig(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {"BOT_ENABLE_ANSWER_COMPLETENESS_JUDGE": "", "BOT_ENABLE_WEB_SEARCH": "true"},
        clear=False,
    )
    def test_follows_web_search_flag(self) -> None:
        self.assertTrue(is_completeness_judge_enabled())
