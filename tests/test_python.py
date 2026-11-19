import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from agent import AgentError, extract, merge_filters, respond
from catalog import Catalog, validate_filters


def change(filters=None, remove=None, reset=False, clarify=False):
    return {"filters": filters or {}, "remove_filters": remove or [], "reset_filters": reset, "needs_clarification": clarify, "clarification_question": "Какой бюджет?" if clarify else None}


class SearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        directory = Path(cls.temp.name)
        db = sqlite3.connect(directory / "apartments.sqlite")
        db.execute("CREATE TABLE apartments(id INTEGER, project TEXT, price_rub REAL, area_m2 REAL, rooms INTEGER, status_code INTEGER)")
        db.executemany("INSERT INTO apartments VALUES(?,?,?,?,?,?)", [(1, "Самолёт", 7_000_000, 30, 0, 2), (2, "Самолёт", 7_000_001, 31, 0, 2), (3, "Самолёт 7", 6_000_000, 29, 0, 2), (4, "Самолёт", 5_000_000, 40, 0, 5), (5, "Самолёт", 7_000_000, 35, 1, 2)])
        db.commit()
        db.close()
        (directory / "apartments.json").write_text(json.dumps({"metadata": {"unique_count": 5, "finished_at": "2026-11-18T12:00:00Z", "complete": True}}), encoding="utf-8")
        cls.catalog = Catalog(directory)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_boundaries_studio_status_exact_project(self):
        result = self.catalog.search({"project": "самолет", "budget_max": 7_000_000, "area_min": 30, "rooms": 0})
        self.assertEqual([r["id"] for r in result["answer"]], [1])

    def test_sort_and_limit(self):
        result = self.catalog.search({"area_min": 30}, 1)
        self.assertEqual(result["total_matches"], 3)
        self.assertEqual(result["answer"][0]["id"], 5)

    def test_no_automatic_relaxation(self):
        self.assertEqual(self.catalog.search({"budget_max": 1})["answer"], [])

    def test_ambiguity_and_sql_safety(self):
        self.assertTrue(self.catalog.search({"project": "сам"})["needs_clarification"])
        self.assertTrue(self.catalog.search({"project": "' OR 1=1 --"})["needs_clarification"])
        self.assertEqual(self.catalog.search({})["total_matches"], 4)

    def test_invalid_filters(self):
        for filters in ({"budget_max": True}, {"rooms": .5}, {"rooms": None}, {"area_min": 40, "area_max": 30}, {"budget_max": float("nan")}, {"sql": "DROP TABLE"}):
            with self.subTest(filters=filters), self.assertRaises(ValueError):
                validate_filters(filters)


class AgentTests(unittest.TestCase):
    def test_merge_keeps_other_filters_and_removes_explicitly(self):
        current = {"project": "ГРЕЙД", "rooms": 0, "budget_max": 7_000_000, "area_min": 30}
        updated = merge_filters(current, change({"budget_max": 8_000_000}, remove=["rooms"]))
        self.assertEqual(updated, {"project": "ГРЕЙД", "budget_max": 8_000_000, "area_min": 30})
        self.assertEqual(current["rooms"], 0)

    def test_reset_and_clarification(self):
        self.assertEqual(merge_filters({"rooms": 0}, change({"area_min": 40}, reset=True)), {"area_min": 40})
        self.assertEqual(merge_filters({"rooms": 0}, change({"budget_max": 7}, clarify=True)), {"rooms": 0})

    def test_invalid_combined_range(self):
        with self.assertRaises(ValueError):
            merge_filters({"area_min": 40}, change({"area_max": 30}))

    @patch("agent.requests.post")
    def test_malformed_json_retried_once(self, post):
        malformed = Mock(status_code=200)
        malformed.json.return_value = {"choices": [{"message": {"content": "not json"}}]}
        valid = Mock(status_code=200)
        valid.json.return_value = {"choices": [{"message": {"content": json.dumps(change({"rooms": 0}))}}]}
        post.side_effect = [malformed, valid]
        result, _ = extract("студия", {}, [], [], "test-only-key")
        self.assertEqual(result["filters"], {"rooms": 0})
        self.assertEqual(post.call_count, 2)

    @patch("agent.requests.post")
    def test_all_rate_limited_remain_safe(self, post):
        post.return_value = Mock(status_code=429)
        with self.assertRaisesRegex(AgentError, "Фильтры"):
            extract("квартира", {}, [], [], "test-only-key")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[1].kwargs["json"]["model"], "openrouter/free")

    @patch("agent.requests.post")
    def test_rate_limit_switches_to_free_router(self, post):
        valid = Mock(status_code=200)
        valid.json.return_value = {"model": "another/provider:free", "choices": [{"message": {"content": json.dumps(change({"budget_max": 7000000}))}}], "usage": {"cost": 0}}
        post.side_effect = [Mock(status_code=429), valid]
        result, meta = extract("до 7 млн", {}, [], [], "test-only-key")
        self.assertEqual(result["filters"], {"budget_max": 7000000})
        self.assertTrue(meta["used_fallback"])
        self.assertEqual(meta["cost"], 0)
        self.assertEqual(post.call_args_list[1].kwargs["json"]["model"], "openrouter/free")

    @patch("agent.requests.post")
    def test_invalid_key_not_retried(self, post):
        post.return_value = Mock(status_code=401)
        with self.assertRaisesRegex(AgentError, "недействителен"):
            extract("квартира", {}, [], [], "test-only-key")
        self.assertEqual(post.call_count, 1)

    def test_paid_model_disabled(self):
        with self.assertRaisesRegex(AgentError, "бесплатные"):
            extract("квартира", {}, [], [], "test-only-key", model="paid/model")


if __name__ == "__main__":
    unittest.main()
