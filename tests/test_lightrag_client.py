import unittest
from unittest.mock import Mock, patch

import os
import requests

from telegram_bot.lightrag_client import LightRAGClient


class TestLightRAGClient(unittest.TestCase):
    @patch("telegram_bot.lightrag_client.requests.post")
    def test_query_success(self, post_mock: Mock) -> None:
        post_mock.return_value.status_code = 200
        post_mock.return_value.json.return_value = {"response": "ok answer"}
        client = LightRAGClient(base_url="http://127.0.0.1:9621", api_key="secret")

        ok, answer = client.query("hello", mode="naive")

        self.assertTrue(ok)
        self.assertEqual(answer, "ok answer")

    @patch("telegram_bot.lightrag_client.requests.post")
    def test_query_failure_status(self, post_mock: Mock) -> None:
        post_mock.return_value.status_code = 500
        client = LightRAGClient(base_url="http://127.0.0.1:9621", api_key="secret")

        ok, details = client.query("hello", mode="mix")

        self.assertFalse(ok)
        self.assertIn("query status=500", details)

    @patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False)
    def test_query_openai_general_without_key(self) -> None:
        client = LightRAGClient(base_url="http://127.0.0.1:9621", api_key="secret")
        ok, details = client.query_openai_general("Что такое Celery?")
        self.assertFalse(ok)
        self.assertIn("openai api key is missing", details)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test", "BOT_OPENAI_MODEL": "gpt-4o-mini"}, clear=False)
    @patch("telegram_bot.lightrag_client.requests.post")
    def test_query_openai_general_success(self, post_mock: Mock) -> None:
        post_mock.return_value.status_code = 200
        post_mock.return_value.json.return_value = {
            "choices": [{"message": {"content": "Celery — это очередь задач."}}]
        }
        client = LightRAGClient(base_url="http://127.0.0.1:9621", api_key="secret")
        ok, answer = client.query_openai_general("Что такое Celery?")
        self.assertTrue(ok)
        self.assertIn("Celery", answer)

    @patch.dict(os.environ, {"BOT_HTTP_RETRY_ATTEMPTS": "1", "BOT_HTTP_RETRY_BACKOFF": "0"})
    @patch("telegram_bot.lightrag_client.requests.post")
    def test_query_retries_once_then_succeeds(self, post_mock: Mock) -> None:
        first_exc = requests.RequestException("temporary")
        second_response = Mock()
        second_response.status_code = 200
        second_response.json.return_value = {"response": "ok"}
        post_mock.side_effect = [first_exc, second_response]
        client = LightRAGClient(base_url="http://127.0.0.1:9621", api_key="secret")

        ok, answer = client.query("hello", mode="mix")

        self.assertTrue(ok)
        self.assertEqual(answer, "ok")
        self.assertEqual(post_mock.call_count, 2)

    @patch.dict(os.environ, {"BOT_HTTP_RETRY_ATTEMPTS": "1", "BOT_HTTP_RETRY_BACKOFF": "0"})
    @patch("telegram_bot.lightrag_client.requests.post")
    def test_query_respects_retry_after_header(self, post_mock: Mock) -> None:
        first_response = Mock()
        first_response.status_code = 429
        first_response.headers = {"Retry-After": "0"}
        second_response = Mock()
        second_response.status_code = 200
        second_response.json.return_value = {"response": "ok"}
        post_mock.side_effect = [first_response, second_response]
        client = LightRAGClient(base_url="http://127.0.0.1:9621", api_key="secret")

        ok, answer = client.query("hello", mode="mix")

        self.assertTrue(ok)
        self.assertEqual(answer, "ok")
        self.assertEqual(post_mock.call_count, 2)

    @patch.object(LightRAGClient, "query")
    def test_ask_with_fallback_uses_secondary_mode(self, query_mock: Mock) -> None:
        query_mock.side_effect = [
            (False, "query status=500"),
            (True, "fallback answer"),
        ]
        client = LightRAGClient(base_url="http://127.0.0.1:9621", api_key="secret")

        ok, answer, used_mode = client.ask_with_fallback("question", primary_mode="mix")

        self.assertTrue(ok)
        self.assertEqual(answer, "fallback answer")
        self.assertEqual(used_mode, "hybrid (проверено: mix,hybrid)")

    @patch.object(LightRAGClient, "query")
    def test_ask_with_fallback_when_mix_is_weak_answer(self, query_mock: Mock) -> None:
        query_mock.side_effect = [
            (True, "У меня недостаточно информации, чтобы ответить."),
            (True, "Вас зовут Клычников Александр."),
        ]
        client = LightRAGClient(base_url="http://127.0.0.1:9621", api_key="secret")

        ok, answer, used_mode = client.ask_with_fallback("как меня зовут?", primary_mode="mix")

        self.assertTrue(ok)
        self.assertIn("Клычников", answer)
        self.assertEqual(used_mode, "hybrid (проверено: mix,hybrid)")

    @patch.object(LightRAGClient, "query")
    def test_ask_with_fallback_all_modes_weak(self, query_mock: Mock) -> None:
        query_mock.side_effect = [
            (True, "У меня недостаточно информации."),
            (True, "Недостаточно информации в контексте."),
            (True, "Не могу ответить по предоставленным данным."),
        ]
        client = LightRAGClient(base_url="http://127.0.0.1:9621", api_key="secret")

        ok, answer, used_mode = client.ask_with_fallback("question", primary_mode="mix")

        self.assertTrue(ok)
        self.assertIn("Не могу ответить", answer)
        self.assertEqual(
            used_mode,
            "global (все режимы слабые; проверено: mix,hybrid,global)",
        )

    @patch.object(LightRAGClient, "query")
    def test_ask_with_fallback_all_failed(self, query_mock: Mock) -> None:
        query_mock.side_effect = [
            (False, "query status=500"),
            (False, "query status=500"),
            (False, "query status=500"),
        ]
        client = LightRAGClient(base_url="http://127.0.0.1:9621", api_key="secret")

        ok, answer, used_mode = client.ask_with_fallback("question", primary_mode="mix")

        self.assertFalse(ok)
        self.assertEqual(answer, "all query modes failed")
        self.assertEqual(used_mode, "mix,hybrid,global")

    @patch.object(LightRAGClient, "query")
    def test_translate_to_russian_success(self, query_mock: Mock) -> None:
        query_mock.return_value = (True, "перевод")
        client = LightRAGClient(base_url="http://127.0.0.1:9621", api_key="secret")

        ok, translated = client.translate_to_russian("hello world")

        self.assertTrue(ok)
        self.assertEqual(translated, "перевод")

    @patch.object(LightRAGClient, "query")
    def test_translate_to_russian_failure(self, query_mock: Mock) -> None:
        query_mock.return_value = (False, "query status=500")
        client = LightRAGClient(base_url="http://127.0.0.1:9621", api_key="secret")

        ok, translated = client.translate_to_russian("long english text " * 100)

        self.assertFalse(ok)
        self.assertIn("query status=500", translated)

    @patch("telegram_bot.lightrag_client.requests.post")
    def test_ingest_text_success(self, post_mock: Mock) -> None:
        post_mock.return_value.status_code = 200
        client = LightRAGClient(
            base_url="http://127.0.0.1:9621",
            api_key="secret",
        )

        post_mock.return_value.json.return_value = {"track_id": "track-1"}
        ok, details, track_id = client.ingest_text("hello", "telegram:test")

        self.assertTrue(ok)
        self.assertEqual(details, "accepted status=200")
        self.assertEqual(track_id, "track-1")
        post_mock.assert_called_once_with(
            "http://127.0.0.1:9621/documents/text",
            json={"text": "hello", "description": "telegram:test"},
            headers={"X-API-Key": "secret"},
            timeout=20,
        )

    @patch("telegram_bot.lightrag_client.requests.post")
    def test_ingest_text_accepts_202(self, post_mock: Mock) -> None:
        post_mock.return_value.status_code = 202
        client = LightRAGClient(
            base_url="http://127.0.0.1:9621",
            api_key="secret",
        )

        post_mock.return_value.json.return_value = {"track_id": "track-2"}
        ok, details, track_id = client.ingest_text("hello")

        self.assertTrue(ok)
        self.assertEqual(details, "accepted status=202")
        self.assertEqual(track_id, "track-2")

    @patch("telegram_bot.lightrag_client.requests.post")
    def test_ingest_text_failure_status(self, post_mock: Mock) -> None:
        post_mock.return_value.status_code = 500
        post_mock.return_value.json.return_value = {"detail": "internal"}
        client = LightRAGClient(
            base_url="http://127.0.0.1:9621",
            api_key="secret",
        )

        ok, details, track_id = client.ingest_text("hello")

        self.assertFalse(ok)
        self.assertIn("ingest status=500", details)
        self.assertIn("internal", details)
        self.assertIsNone(track_id)

    @patch("telegram_bot.lightrag_client.requests.post")
    def test_ingest_text_request_exception(self, post_mock: Mock) -> None:
        post_mock.side_effect = requests.RequestException("timeout")
        client = LightRAGClient(
            base_url="http://127.0.0.1:9621",
            api_key="secret",
        )

        ok, details, track_id = client.ingest_text("hello")

        self.assertFalse(ok)
        self.assertIn("ingest error=timeout", details)
        self.assertIsNone(track_id)
        self.assertEqual(post_mock.call_count, 1)

    @patch("telegram_bot.lightrag_client.requests.get")
    def test_health_with_api_key_header(self, get_mock: Mock) -> None:
        get_mock.return_value.status_code = 200
        client = LightRAGClient(
            base_url="http://127.0.0.1:9621",
            api_key="secret",
        )

        ok, details = client.health()

        self.assertTrue(ok)
        self.assertEqual(details, "ok")
        get_mock.assert_called_once_with(
            "http://127.0.0.1:9621/health",
            headers={"X-API-Key": "secret"},
            timeout=20,
        )

    @patch("telegram_bot.lightrag_client.requests.post")
    def test_ingest_file_success(self, post_mock: Mock) -> None:
        post_mock.return_value.status_code = 200
        client = LightRAGClient(
            base_url="http://127.0.0.1:9621",
            api_key="secret",
        )

        post_mock.return_value.json.return_value = {"track_id": "track-file-1"}
        ok, details, track_id = client.ingest_file(
            file_name="note.txt",
            file_bytes=b"hello",
            mime_type="text/plain",
            description="telegram:file",
        )

        self.assertTrue(ok)
        self.assertEqual(details, "accepted status=200 endpoint=/documents/upload")
        self.assertEqual(track_id, "track-file-1")
        post_mock.assert_called_once_with(
            "http://127.0.0.1:9621/documents/upload",
            files={"file": ("note.txt", b"hello", "text/plain")},
            data={"description": "telegram:file"},
            headers={"X-API-Key": "secret"},
            timeout=20,
        )

    @patch("telegram_bot.lightrag_client.requests.post")
    def test_ingest_file_failure_status(self, post_mock: Mock) -> None:
        post_mock.return_value.status_code = 415
        post_mock.return_value.json.return_value = {"detail": "unsupported"}
        client = LightRAGClient(
            base_url="http://127.0.0.1:9621",
            api_key="secret",
        )

        ok, details, track_id = client.ingest_file(
            file_name="bad.exe",
            file_bytes=b"\x00\x01",
            mime_type="application/octet-stream",
        )

        self.assertFalse(ok)
        self.assertIn("ingest status=415", details)
        self.assertIn("unsupported", details)
        self.assertIsNone(track_id)

    @patch("telegram_bot.lightrag_client.requests.post")
    def test_ingest_file_fallback_from_upload_to_file(self, post_mock: Mock) -> None:
        first_response = Mock()
        first_response.status_code = 404
        first_response.json.return_value = {"detail": "Not Found"}
        second_response = Mock()
        second_response.status_code = 200
        second_response.json.return_value = {"track_id": "legacy-track"}
        post_mock.side_effect = [first_response, second_response]
        client = LightRAGClient(
            base_url="http://127.0.0.1:9621",
            api_key="secret",
        )

        ok, details, track_id = client.ingest_file(
            file_name="legacy.txt",
            file_bytes=b"legacy",
            mime_type="text/plain",
        )

        self.assertTrue(ok)
        self.assertEqual(details, "accepted status=200 endpoint=/documents/file")
        self.assertEqual(track_id, "legacy-track")
        self.assertEqual(post_mock.call_count, 2)

    @patch("telegram_bot.lightrag_client.requests.get")
    def test_track_status_processed(self, get_mock: Mock) -> None:
        get_mock.return_value.status_code = 200
        get_mock.return_value.json.return_value = {
            "documents": [{"status": "processed"}],
            "status_summary": {"processed": 1},
        }
        client = LightRAGClient(base_url="http://127.0.0.1:9621", api_key="secret")

        ok, summary, is_terminal, is_success = client.track_status("track-1")

        self.assertTrue(ok)
        self.assertTrue(is_terminal)
        self.assertTrue(is_success)
        self.assertIn("processed=1", summary)

    @patch("telegram_bot.lightrag_client.requests.get")
    def test_track_status_processing(self, get_mock: Mock) -> None:
        get_mock.return_value.status_code = 200
        get_mock.return_value.json.return_value = {
            "documents": [{"status": "processing"}],
            "status_summary": {"processing": 1},
        }
        client = LightRAGClient(base_url="http://127.0.0.1:9621", api_key="secret")

        ok, summary, is_terminal, is_success = client.track_status("track-2")

        self.assertTrue(ok)
        self.assertFalse(is_terminal)
        self.assertFalse(is_success)
        self.assertIn("processing=1", summary)

    @patch("telegram_bot.lightrag_client.requests.get")
    def test_track_status_summary_only_processed(self, get_mock: Mock) -> None:
        get_mock.return_value.status_code = 200
        get_mock.return_value.json.return_value = {
            "documents": [],
            "status_summary": {"processed": 2},
        }
        client = LightRAGClient(base_url="http://127.0.0.1:9621", api_key="secret")

        ok, summary, is_terminal, is_success = client.track_status("track-3")

        self.assertTrue(ok)
        self.assertTrue(is_terminal)
        self.assertTrue(is_success)
        self.assertIn("processed=2", summary)

    @patch("telegram_bot.lightrag_client.requests.get")
    def test_track_status_summary_non_numeric(self, get_mock: Mock) -> None:
        get_mock.return_value.status_code = 200
        get_mock.return_value.json.return_value = {
            "documents": [],
            "status_summary": {"processing": "oops"},
        }
        client = LightRAGClient(base_url="http://127.0.0.1:9621", api_key="secret")

        ok, summary, is_terminal, is_success = client.track_status("track-x")

        self.assertTrue(ok)
        self.assertFalse(is_terminal)
        self.assertFalse(is_success)
        self.assertIn("processing=oops", summary)


if __name__ == "__main__":
    unittest.main()

