import unittest
from unittest.mock import Mock, patch

from telegram_bot.deep_qa import (
    DeepQaPlan,
    RagEvidenceItem,
    _default_sub_queries,
    deep_qa_skips_web_enrichment,
    ensure_minimum_sub_queries,
    gather_rag_evidence,
    is_deep_qa_enabled,
    parse_planner_payload,
    plan_deep_qa,
    run_deep_qa,
    synthesize_from_evidence,
)
from telegram_bot.lightrag_client import LightRAGClient


class TestDeepQaParsing(unittest.TestCase):
    def test_parse_planner_payload_ok(self) -> None:
        plan = parse_planner_payload(
            {
                "task_type": "resume",
                "sub_queries": ["q1", "q2", "q3"],
                "synthesis_notes": "структура",
            }
        )
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.task_type, "resume")
        self.assertEqual(len(plan.sub_queries), 3)

    def test_parse_planner_payload_single_query_ok(self) -> None:
        plan = parse_planner_payload({"sub_queries": ["only one"], "task_type": "qa"})
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(len(plan.sub_queries), 1)

    def test_ensure_minimum_triad(self) -> None:
        result = ensure_minimum_sub_queries(["один запрос"], "как деплоить LightRAG на VPS")
        self.assertGreaterEqual(len(result), 3)
        joined = " ".join(result).lower()
        self.assertIn("суть", joined)
        self.assertIn("детал", joined)
        self.assertIn("источник", joined)

    def test_default_sub_queries_generic_has_triad(self) -> None:
        result = _default_sub_queries("как деплоить LightRAG на VPS")
        self.assertGreaterEqual(len(result), 3)

    def test_skip_web_for_resume(self) -> None:
        self.assertTrue(deep_qa_skips_web_enrichment("resume"))
        self.assertFalse(deep_qa_skips_web_enrichment("qa"))


class TestDeepQaPipeline(unittest.TestCase):
    @patch.dict("os.environ", {"BOT_ENABLE_DEEP_QA": "true"}, clear=False)
    def test_is_deep_qa_enabled_default_on(self) -> None:
        self.assertTrue(is_deep_qa_enabled())

    def test_gather_dedupes_identical_answers(self) -> None:
        client = Mock(spec=LightRAGClient)
        same = "одинаковый ответ из базы знаний " * 20
        client.ask_with_fallback.return_value = (True, same, "mix")
        plan = DeepQaPlan("qa", ("q1", "q2", "q3"))
        items = gather_rag_evidence(client, plan, primary_mode="mix", fallback_modes=("hybrid",))
        self.assertEqual(len(items), 1)
        self.assertEqual(client.ask_with_fallback.call_count, 3)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=False)
    def test_synthesize_from_evidence(self) -> None:
        client = Mock(spec=LightRAGClient)
        client.query_openai_chat.return_value = (True, "# Резюме\n\nФакт из БЗ.")
        evidence = [
            RagEvidenceItem("контакты", "mix", "телефон +7 902"),
            RagEvidenceItem("проекты", "hybrid", "LightRAG на VPS"),
        ]
        plan = DeepQaPlan("resume", ("контакты", "проекты"))
        ok, answer, err = synthesize_from_evidence(
            "составь резюме",
            plan,
            evidence,
            client=client,
        )
        self.assertTrue(ok)
        self.assertIn("Резюме", answer)
        self.assertEqual(err, "")

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=False)
    def test_run_deep_qa_end_to_end_mocked(self) -> None:
        client = Mock(spec=LightRAGClient)
        client.query_openai_json.return_value = (
            True,
            {
                "task_type": "resume",
                "sub_queries": ["урок OV05", "контакты introMain", "проекты github"],
                "synthesis_notes": "markdown",
            },
        )
        client.ask_with_fallback.side_effect = [
            (True, "рекомендации OV05: структура резюме " * 10, "mix"),
            (True, "телефон +7 (902) 510-95-19 " * 10, "hybrid"),
            (True, "LightRAG Telegram Zerocode2md " * 10, "global"),
            (True, "Иркутск ИГУ образование " * 10, "local"),
            (True, "Dynamics AX X++ " * 10, "naive"),
        ]
        client.query_openai_chat.return_value = (True, "# Александр Клычников\n\nИркутск")
        ok, outcome, _ = run_deep_qa(
            "составь резюме по OV05",
            "составь резюме Александр Клычников",
            client=client,
            primary_mode="mix",
            fallback_modes=("hybrid", "global"),
        )
        self.assertTrue(ok)
        assert outcome is not None
        self.assertEqual(outcome.task_type, "resume")
        self.assertIn("Александр", outcome.answer)
        self.assertGreaterEqual(outcome.evidence_count, 1)

    def test_plan_fallback_on_invalid_json(self) -> None:
        client = Mock(spec=LightRAGClient)
        client.query_openai_json.return_value = (False, "openai error")
        ok, plan, _ = plan_deep_qa(
            "составь резюме по рекомендациям урока OV05",
            client=client,
        )
        self.assertTrue(ok)
        assert plan is not None
        self.assertGreaterEqual(len(plan.sub_queries), 3)
        self.assertEqual(plan.task_type, "resume")

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=False)
    def test_plan_pads_single_planner_query_to_triad(self) -> None:
        client = Mock(spec=LightRAGClient)
        client.query_openai_json.return_value = (
            True,
            {"task_type": "qa", "sub_queries": ["единственный запрос"], "synthesis_notes": ""},
        )
        ok, plan, _ = plan_deep_qa("как настроен postgres для LightRAG", client=client)
        self.assertTrue(ok)
        assert plan is not None
        self.assertGreaterEqual(len(plan.sub_queries), 3)
