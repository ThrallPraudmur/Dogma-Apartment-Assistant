import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

from test_python import change

APP = Path(__file__).resolve().parents[1] / "app.py"


class InterfaceTests(unittest.TestCase):
    def create_app(self):
        app = AppTest.from_file(str(APP), default_timeout=20)
        app.run()
        self.assertFalse(app.exception)
        return app

    def test_manual_search_and_reset_without_key(self):
        app = self.create_app()
        app.radio[0].set_value("Фильтры").run()
        next(s for s in app.selectbox if s.label == "ЖК").set_value("ГРЕЙД")
        next(b for b in app.button if b.label == "Подобрать квартиры").click().run()
        self.assertFalse(app.exception)
        result = app.session_state["messages"][-1]["result"]
        self.assertEqual(result["total_matches"], 219)
        self.assertEqual(len(result["answer"]), 3)
        self.assertEqual(len(app.get("download_button")), 1)
        next(b for b in app.button if b.label == "Новый поиск").click().run()
        self.assertEqual(app.session_state["filters"], {})
        self.assertEqual(app.session_state["messages"], [])

    @patch("agent.extract")
    def test_chat_state_and_clarification(self, extraction):
        extraction.side_effect = [(change({"project": "ГРЕЙД", "budget_max": 7_000_000, "area_min": 30}), {"model": "mock:free", "cost": 0}), (change({"budget_max": 8_000_000}), {"model": "mock:free", "cost": 0}), (change(clarify=True), {"model": "mock:free", "cost": 0})]
        app = self.create_app()
        app.text_input(key="api_key_input").set_value("test-only-key").run()
        app.chat_input[0].set_value("Квартиру в ГРЕЙД до 7 млн, от 30 м²").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["filters"]["area_min"], 30)
        app.session_state["last_request"] = 0
        app.chat_input[0].set_value("А теперь до 8 млн").run()
        self.assertFalse(app.exception)
        expected = {"project": "ГРЕЙД", "budget_max": 8_000_000, "area_min": 30}
        self.assertEqual(app.session_state["filters"], expected)
        app.session_state["last_request"] = 0
        app.chat_input[0].set_value("А до 9?").run()
        self.assertEqual(app.session_state["filters"], expected)
        self.assertTrue(app.session_state["messages"][-1]["result"]["needs_clarification"])


if __name__ == "__main__":
    unittest.main()
