import unittest

from telegram_bot.reliability import BotRuntimeMetrics, InMemoryRateLimiter


class TestReliability(unittest.TestCase):
    def test_rate_limiter_blocks_after_limit(self) -> None:
        limiter = InMemoryRateLimiter(max_events=2, window_seconds=60)
        first = limiter.check(1)
        second = limiter.check(1)
        third = limiter.check(1)
        self.assertTrue(first.allowed)
        self.assertTrue(second.allowed)
        self.assertFalse(third.allowed)
        self.assertGreaterEqual(third.retry_after_seconds, 1)

    def test_metrics_counter(self) -> None:
        metrics = BotRuntimeMetrics()
        metrics.inc("qa_total")
        metrics.inc("qa_total")
        metrics.inc("qa_success_total")
        snapshot = metrics.snapshot()
        self.assertEqual(snapshot["qa_total"], 2)
        self.assertEqual(snapshot["qa_success_total"], 1)


if __name__ == "__main__":
    unittest.main()

