import os
import unittest
from unittest.mock import patch

from telegram_bot.qa_context import QaConversationStore


class TestQaConversationStore(unittest.IsolatedAsyncioTestCase):
    async def test_build_without_history_returns_plain_question(self) -> None:
        store = QaConversationStore()
        q = await store.build_contextual_query(42, "hello")
        self.assertEqual(q, "hello")

    @patch.dict(os.environ, {"BOT_QA_CONTEXT_MAX_MESSAGES": "24", "BOT_QA_CONTEXT_MAX_CHARS": "7000"})
    async def test_record_then_context_contains_prior_turns(self) -> None:
        store = QaConversationStore()
        await store.record_exchange(7, "What is X?", "X is a thing.")
        wrapped = await store.build_contextual_query(7, "And Y?")
        self.assertIn("Контекст диалога", wrapped)
        self.assertIn("What is X?", wrapped)
        self.assertIn("X is a thing.", wrapped)
        self.assertIn("Текущий вопрос", wrapped)
        self.assertIn("And Y?", wrapped)

    @patch.dict(os.environ, {"BOT_QA_SESSION_IDLE_MINUTES": "20"})
    async def test_expire_if_idle_clears_session(self) -> None:
        store = QaConversationStore()
        with patch("telegram_bot.qa_context.time.time", return_value=1_000_000.0):
            await store.record_exchange(99, "u", "a")
        await store.expire_if_idle(99, now=1_000_000.0 + 21 * 60)
        out = await store.build_contextual_query(99, "next")
        self.assertEqual(out, "next")

    @patch.dict(os.environ, {"BOT_QA_SESSION_IDLE_MINUTES": "0"})
    async def test_idle_zero_disables_ttl(self) -> None:
        from telegram_bot import qa_context as qc

        self.assertIsNone(qc._idle_seconds())


if __name__ == "__main__":
    unittest.main()
