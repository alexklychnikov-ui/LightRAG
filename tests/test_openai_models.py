import unittest
from unittest.mock import Mock, patch

from telegram_bot import openai_models


class TestOpenAIModels(unittest.TestCase):
    def setUp(self) -> None:
        openai_models._available_models = ()
        openai_models._catalog_by_id = {}
        openai_models._last_refresh_note = "not loaded"

    def test_default_model_is_o4_mini(self) -> None:
        with patch.dict("os.environ", {}, clear=False):
            openai_models.os.environ.pop("BOT_OPENAI_MODEL", None)
            self.assertEqual(openai_models.default_openai_model(), "o4-mini")

    def test_price_label_format(self) -> None:
        info = openai_models.OpenAIModelInfo("o4-mini", 50, 1.1, 4.4)
        self.assertEqual(info.price_label(), "$1.1/$4.4")

    def test_refresh_without_api_key_uses_static_top5(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            models = openai_models.refresh_openai_models_catalog()
        self.assertEqual(len(models), 5)
        self.assertEqual(models[0].model_id, "gpt-5.5")
        self.assertEqual(models[4].model_id, "o4-mini")

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=False)
    @patch("telegram_bot.openai_models.requests.get")
    def test_refresh_intersects_with_api(self, get_mock: Mock) -> None:
        get_mock.return_value.status_code = 200
        get_mock.return_value.json.return_value = {
            "data": [
                {"id": "o4-mini"},
                {"id": "gpt-5.4-mini-2025-04-16"},
                {"id": "o3"},
            ]
        }
        models = openai_models.refresh_openai_models_catalog()
        ids = [m.model_id for m in models]
        self.assertIn("o4-mini", ids)
        self.assertIn("gpt-5.4-mini", ids)
        self.assertIn("o3", ids)
        self.assertNotIn("gpt-5.5", ids)

    def test_resolve_prefers_override_when_allowed(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            openai_models.refresh_openai_models_catalog()
        resolved = openai_models.resolve_openai_model("gpt-5.4")
        self.assertEqual(resolved, "gpt-5.4")

    def test_resolve_falls_back_to_default(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            openai_models.refresh_openai_models_catalog()
        resolved = openai_models.resolve_openai_model(None)
        self.assertEqual(resolved, "o4-mini")

    def test_best_catalog_match_prefers_longest_prefix(self) -> None:
        catalog = openai_models._build_catalog()
        info = openai_models._best_catalog_match("o3-mini-2025-01-31", catalog)
        self.assertIsNotNone(info)
        self.assertEqual(info.model_id, "o3-mini")
        info_pro = openai_models._best_catalog_match("gpt-5.5-pro-2025-03-01", catalog)
        self.assertEqual(info_pro.model_id, "gpt-5.5-pro")

    def test_openai_model_supports_temperature(self) -> None:
        self.assertFalse(openai_models.openai_model_supports_temperature("o4-mini"))
        self.assertFalse(openai_models.openai_model_supports_temperature("gpt-5.4"))
        self.assertTrue(openai_models.openai_model_supports_temperature("gpt-4o-mini"))

    def test_is_allowed_rejects_unknown(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            openai_models.refresh_openai_models_catalog()
        self.assertFalse(openai_models.is_allowed_openai_model("gpt-99"))


if __name__ == "__main__":
    unittest.main()
