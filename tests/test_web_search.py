import unittest
from unittest.mock import Mock, patch

from telegram_bot.web_search import (
    DdgsWebSearchProvider,
    TavilyWebSearchProvider,
    WebSearchResult,
    build_web_search_provider,
    is_web_search_enabled,
    merge_results,
    search_web,
)


class TestWebSearchConfig(unittest.TestCase):
    @patch.dict("os.environ", {"BOT_ENABLE_WEB_SEARCH": "true"})
    def test_is_web_search_enabled(self) -> None:
        self.assertTrue(is_web_search_enabled())

    @patch.dict("os.environ", {"BOT_ENABLE_WEB_SEARCH": "off"})
    def test_is_web_search_disabled(self) -> None:
        self.assertFalse(is_web_search_enabled())

    @patch.dict("os.environ", {"BOT_WEB_SEARCH_PROVIDER": "tavily"}, clear=False)
    def test_build_tavily_missing_key(self) -> None:
        with patch.dict("os.environ", {"TAVILY_API_KEY": ""}, clear=False):
            provider, err = build_web_search_provider("tavily")
        self.assertIsNone(provider)
        self.assertIn("missing", err)

    @patch.dict(
        "os.environ",
        {"BOT_WEB_SEARCH_PROVIDER": "tavily", "TAVILY_API_KEY": "tvly-test"},
        clear=False,
    )
    def test_build_tavily_ok(self) -> None:
        provider, err = build_web_search_provider("tavily")
        self.assertIsNotNone(provider)
        self.assertEqual(err, "")


class TestMergeResults(unittest.TestCase):
    def test_dedupe_by_url(self) -> None:
        a = WebSearchResult("A", "https://Example.com/x", "s1", "q1")
        b = WebSearchResult("B", "https://example.com/x/", "s2", "q2")
        c = WebSearchResult("C", "https://other.com", "s3", "q3")
        merged = merge_results([[a, c], [b]], max_total=10)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0].title, "A")
        self.assertEqual(merged[1].url, "https://other.com")


class TestTavilyProvider(unittest.TestCase):
    @patch("telegram_bot.web_search.requests.post")
    def test_tavily_search_one_parses_results(self, post_mock: Mock) -> None:
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "results": [
                {
                    "title": "Doc",
                    "url": "https://docs.example.com/a",
                    "content": "Snippet text",
                }
            ]
        }
        post_mock.return_value = response

        provider = TavilyWebSearchProvider("key", timeout_seconds=10)
        ok, rows, err = provider.search_one("lightrag tutorial", max_results=3)

        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].title, "Doc")
        self.assertEqual(rows[0].snippet, "Snippet text")
        self.assertEqual(rows[0].query, "lightrag tutorial")


class TestSearchWebProviderInjection(unittest.TestCase):
    def test_search_web_uses_injected_provider(self) -> None:
        provider = Mock()
        provider.search_one.return_value = (
            True,
            [WebSearchResult("T", "https://a.com", "body", "q")],
            "",
        )

        with patch.dict("os.environ", {"BOT_ENABLE_WEB_SEARCH": "true"}, clear=False):
            ok, rows, err = search_web(["query"], provider=provider)

        self.assertTrue(ok)
        self.assertEqual(len(rows), 1)
        self.assertEqual(err, "")
        provider.search_one.assert_called_once()


class TestSearchWeb(unittest.TestCase):
    @patch.dict("os.environ", {"BOT_ENABLE_WEB_SEARCH": "false"}, clear=False)
    def test_disabled(self) -> None:
        ok, rows, err = search_web(["x"])
        self.assertFalse(ok)
        self.assertEqual(rows, [])
        self.assertEqual(err, "web search disabled")

    @patch.dict(
        "os.environ",
        {
            "BOT_ENABLE_WEB_SEARCH": "true",
            "BOT_WEB_SEARCH_MAX_QUERIES": "2",
            "BOT_WEB_SEARCH_MAX_TOTAL_RESULTS": "3",
        },
        clear=False,
    )
    def test_limits_queries_and_total(self) -> None:
        provider = Mock()
        provider.search_one.side_effect = [
            (
                True,
                [
                    WebSearchResult("1", "https://a.com", "s", "q1"),
                    WebSearchResult("2", "https://b.com", "s", "q1"),
                ],
                "",
            ),
            (
                True,
                [WebSearchResult("3", "https://c.com", "s", "q2")],
                "",
            ),
            (
                True,
                [WebSearchResult("4", "https://d.com", "s", "q3")],
                "",
            ),
        ]

        ok, rows, err = search_web(
            ["q1", "q2", "q3"],
            provider=provider,
        )

        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertEqual(len(rows), 3)
        self.assertEqual(provider.search_one.call_count, 2)
