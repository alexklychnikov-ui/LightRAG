import unittest
from unittest.mock import AsyncMock, Mock, patch

from telegram_bot.handlers import _is_openai_fallback_enabled
from telegram_bot.lightrag_client import LightRAGClient
from telegram_bot.web_search import WebSearchResult


class TestOpenAiFallbackAfterWeb(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {"BOT_ENABLE_OPENAI_FALLBACK": "true", "BOT_ENABLE_WEB_SEARCH": "true"},
        clear=False,
    )
    def test_web_enriched_skips_weak_openai_replace(self) -> None:
        web_references = (WebSearchResult("T", "https://t.com", "s", "q"),)
        web_enriched = bool(web_references)
        final_answer = "Недостаточно информации в открытых источниках, но есть детали."
        client = Mock(spec=LightRAGClient)
        client.is_weak_answer.return_value = True

        should_call_openai = (
            _is_openai_fallback_enabled()
            and not web_enriched
            and client.is_weak_answer(final_answer)
        )
        self.assertFalse(should_call_openai)
