import unittest
from unittest.mock import AsyncMock, Mock, patch

from telegram_bot.answer_completeness import CompletenessVerdict
from telegram_bot.handlers import _try_enrich_with_web_search
from telegram_bot.web_answer_synthesis import WebSynthesisOutcome
from telegram_bot.web_search import WebSearchResult


class TestTryEnrichWithWebSearch(unittest.IsolatedAsyncioTestCase):
    @patch.dict("os.environ", {"BOT_ENABLE_WEB_SEARCH": "false"}, clear=False)
    async def test_skips_when_disabled(self) -> None:
        message = Mock()
        message.chat.id = 1
        client = Mock()
        body, source, mode, refs, notice = await _try_enrich_with_web_search(
            message,
            client,
            contextual_question="q",
            effective_question="q",
            rag_answer="rag",
            used_mode="mix",
            openai_model="o4-mini",
        )
        self.assertEqual(body, "rag")
        self.assertEqual(source, "LightRAG")
        self.assertEqual(refs, ())
        self.assertEqual(notice, "")

    @patch("telegram_bot.handlers.synthesize_with_web")
    @patch("telegram_bot.handlers.search_web")
    @patch("telegram_bot.handlers.assess_rag_answer")
    @patch("telegram_bot.handlers.qa_conversation_store.get_dialog_context_block", new_callable=AsyncMock)
    @patch.dict("os.environ", {"BOT_ENABLE_WEB_SEARCH": "true"}, clear=False)
    async def test_full_web_pipeline(
        self,
        ctx_mock: AsyncMock,
        assess_mock: Mock,
        search_mock: Mock,
        synth_mock: Mock,
    ) -> None:
        ctx_mock.return_value = ""
        assess_mock.return_value = (
            True,
            CompletenessVerdict(
                True,
                ("python 3.13 release",),
                "нужны внешние факты",
                0.9,
            ),
            "",
        )
        search_mock.return_value = (
            True,
            [WebSearchResult("Py", "https://py.org", "snippet", "q")],
            "",
        )
        synth_mock.return_value = (
            True,
            WebSynthesisOutcome("Синтез.", (WebSearchResult("Py", "https://py.org", "s", "q"),)),
            "",
        )

        message = Mock()
        message.chat.id = 1
        message.answer = AsyncMock()
        client = Mock()

        body, source, mode, refs, notice = await _try_enrich_with_web_search(
            message,
            client,
            contextual_question="Когда Python 3.13?",
            effective_question="Когда Python 3.13?",
            rag_answer="Не знаю даты.",
            used_mode="mix (проверено: mix)",
            openai_model="o4-mini",
        )

        self.assertEqual(body, "Синтез.")
        self.assertEqual(source, "LightRAG + интернет")
        self.assertIn("-> web", mode)
        self.assertEqual(len(refs), 1)
        self.assertEqual(notice, "")
        message.answer.assert_awaited_once()
        search_mock.assert_called_once()
        synth_mock.assert_called_once()
        assess_mock.assert_called_once()
        self.assertEqual(assess_mock.call_args.kwargs.get("model"), "o4-mini")
        self.assertEqual(synth_mock.call_args.kwargs.get("model"), "o4-mini")

    @patch("telegram_bot.handlers.synthesize_with_web")
    @patch("telegram_bot.handlers.search_web")
    @patch("telegram_bot.handlers.assess_rag_answer")
    @patch("telegram_bot.handlers.qa_conversation_store.get_dialog_context_block", new_callable=AsyncMock)
    @patch.dict("os.environ", {"BOT_ENABLE_WEB_SEARCH": "true"}, clear=False)
    async def test_search_failure_returns_notice(
        self,
        ctx_mock: AsyncMock,
        assess_mock: Mock,
        search_mock: Mock,
        synth_mock: Mock,
    ) -> None:
        ctx_mock.return_value = ""
        assess_mock.return_value = (
            True,
            CompletenessVerdict(True, ("q",), "need web", 0.9),
            "",
        )
        search_mock.return_value = (False, [], "tavily down")
        message = Mock()
        message.chat.id = 1
        message.answer = AsyncMock()

        body, _source, _mode, refs, notice = await _try_enrich_with_web_search(
            message,
            Mock(),
            contextual_question="q",
            effective_question="q",
            rag_answer="rag",
            used_mode="mix",
            openai_model="o4-mini",
        )
        self.assertEqual(body, "rag")
        self.assertEqual(refs, ())
        self.assertIn("интернета", notice)
        synth_mock.assert_not_called()
