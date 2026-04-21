import unittest
from unittest.mock import Mock, patch

from telegram_bot.url_ingest import fetch_significant_text_from_url, is_http_url


class TestUrlIngest(unittest.TestCase):
    def test_is_http_url(self) -> None:
        self.assertTrue(is_http_url("https://example.com/path"))
        self.assertFalse(is_http_url("ftp://example.com"))
        self.assertFalse(is_http_url("just text"))

    @patch("telegram_bot.url_ingest.socket.getaddrinfo")
    @patch("telegram_bot.url_ingest.requests.get")
    def test_fetch_html_significant_text(
        self,
        get_mock: Mock,
        getaddrinfo_mock: Mock,
    ) -> None:
        getaddrinfo_mock.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 443)),
        ]
        response = Mock()
        response.status_code = 200
        response.headers = {"Content-Type": "text/html; charset=utf-8"}
        response.encoding = "utf-8"
        response.iter_content.return_value = [
            b"""
        <html>
          <head><title>Example</title></head>
          <body>
            <h1>Important heading</h1>
            <p>This is a meaningful paragraph with enough characters to pass filter.</p>
          </body>
        </html>
        """
        ]
        get_mock.return_value.__enter__.return_value = response

        ok, payload = fetch_significant_text_from_url("https://example.com")

        self.assertTrue(ok)
        self.assertIn("Source URL: https://example.com", payload)
        self.assertIn("Title: Example", payload)
        self.assertIn("Important heading", payload)

    @patch("telegram_bot.url_ingest.socket.getaddrinfo")
    @patch("telegram_bot.url_ingest.requests.get")
    def test_fetch_unsupported_type(
        self,
        get_mock: Mock,
        getaddrinfo_mock: Mock,
    ) -> None:
        getaddrinfo_mock.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 443)),
        ]
        response = Mock()
        response.status_code = 200
        response.headers = {"Content-Type": "application/pdf"}
        response.encoding = "utf-8"
        response.iter_content.return_value = [b"binary"]
        get_mock.return_value.__enter__.return_value = response

        ok, details = fetch_significant_text_from_url("https://example.com/file.pdf")

        self.assertFalse(ok)
        self.assertIn("unsupported content-type", details)

    @patch("telegram_bot.url_ingest.socket.getaddrinfo")
    @patch("telegram_bot.url_ingest.requests.get")
    def test_fetch_blocks_redirects(
        self,
        get_mock: Mock,
        getaddrinfo_mock: Mock,
    ) -> None:
        getaddrinfo_mock.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 443)),
        ]
        response = Mock()
        response.status_code = 302
        response.headers = {"Location": "http://127.0.0.1/private"}
        response.encoding = "utf-8"
        response.iter_content.return_value = []
        get_mock.return_value.__enter__.return_value = response

        ok, details = fetch_significant_text_from_url("https://example.com/go")

        self.assertFalse(ok)
        self.assertIn("redirects are blocked", details)

    def test_block_localhost_url(self) -> None:
        ok, details = fetch_significant_text_from_url("http://localhost:8000")
        self.assertFalse(ok)
        self.assertIn("blocked", details)


if __name__ == "__main__":
    unittest.main()

