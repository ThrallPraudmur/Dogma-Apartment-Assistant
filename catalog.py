"""Validated filters and parameterized, read-only SQLite search."""
import json
import math
import sqlite3
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIELDS = {"budget_min", "budget_max", "area_min", "area_max", "project", "rooms"}


def validate_filters(filters):
    if not isinstance(filters, dict) or set(filters) - FIELDS:
        raise ValueError("Неизвестные параметры поиска.")
    for key, value in filters.items():
        if key == "project":
            if not isinstance(value, str) or not value.strip() or len(value) > 200:
                raise ValueError("Укажите название ЖК.")
        elif (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
            raise ValueError(f"Некорректное значение: {key}.")
        elif key == "rooms" and (int(value) != value or value > 20):
            raise ValueError("Количество комнат должно быть целым числом от 0 до 20.")
    for low, high in (("budget_min", "budget_max"), ("area_min", "area_max")):
        if low in filters and high in filters and filters[low] > filters[high]:
            raise ValueError("Нижняя граница диапазона больше верхней. Уточните условия.")
    return dict(filters)


def canonical(text):
    return " ".join(text.casefold().replace("ё", "е").split())


def money(value):
    return f"{value:,.0f}".replace(",", " ") + " ₽"


class Catalog:
    def __init__(self, directory=ROOT / "data"):
        directory = Path(directory)
        self.db_path = directory / "apartments.sqlite"
        if not self.db_path.is_file():
            raise FileNotFoundError("Не найдена база квартир. Выполните npm run scrape.")
        with (directory / "apartments.json").open(encoding="utf-8-sig") as file:
            self.metadata = json.load(file)["metadata"]
        with closing(self.connect()) as db:
            self.projects = [r[0] for r in db.execute("SELECT DISTINCT project FROM apartments ORDER BY project")]
            self.count = db.execute("SELECT COUNT(*) FROM apartments").fetchone()[0]
        if self.count != self.metadata["unique_count"]:
            raise ValueError("JSON и SQLite относятся к разным снимкам. Обновите оба файла.")

    def connect(self):
        db = sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        return db

    def resolve_project(self, name):
        q = canonical(name)
        # Explicit aliases for names with Latin/Cyrillic lettering in the source.
        aliases = {"догма парк": "DОГМА ПАРК", "dogma park": "DОГМА ПАРК", "самолет": "МКР Самолёт"}
        exact = [p for p in self.projects if canonical(p) == q]
        if exact:
            return exact
        if q in aliases and aliases[q] in self.projects:
            return [aliases[q]]
        return [p for p in self.projects if q in canonical(p)]

    def search(self, filters, limit=3):
        filters = validate_filters(filters)
        if type(limit) is not int or not 1 <= limit <= 5:
            raise ValueError("Лимит должен быть от 1 до 5.")
        common = {"filters": filters, "snapshot_at": self.metadata["finished_at"], "snapshot_complete": self.metadata["complete"]}
        if "project" in filters:
            matches = self.resolve_project(filters["project"])
            if len(matches) != 1:
                explanation = "Уточните ЖК: " + ", ".join(matches) if matches else "ЖК не найден. Укажите название из списка в боковой панели."
                return {**common, "answer": [], "explanation": explanation, "needs_clarification": True, "project_candidates": matches, "total_matches": 0}
            filters["project"] = matches[0]
        clauses, values = ["status_code = ?"], [2]
        for field, column, op in (("budget_min", "price_rub", ">="), ("budget_max", "price_rub", "<="), ("area_min", "area_m2", ">="), ("area_max", "area_m2", "<="), ("rooms", "rooms", "="), ("project", "project", "=")):
            if field in filters:
                clauses.append(f"{column} {op} ?")
                values.append(filters[field])
        where = " AND ".join(clauses)
        with closing(self.connect()) as db:
            total = db.execute(f"SELECT COUNT(*) FROM apartments WHERE {where}", values).fetchone()[0]
            rows = db.execute(f"SELECT * FROM apartments WHERE {where} ORDER BY price_rub ASC, area_m2 DESC, id ASC LIMIT ?", [*values, limit]).fetchall()
        answer = []
        for row in rows:
            lot = dict(row)
            reasons = [f"ЖК «{lot['project']}»", f"Цена {money(lot['price_rub'])}", f"Площадь {lot['area_m2']:g} м²"]
            if "budget_max" in filters:
                reasons.append(f"не дороже {money(filters['budget_max'])}")
            if "area_min" in filters:
                reasons.append(f"не меньше {filters['area_min']:g} м²")
            if "rooms" in filters:
                reasons.append("студия" if lot["rooms"] == 0 else f"комнат: {lot['rooms']}")
            lot["explanation"] = "; ".join(reasons) + "."
            answer.append(lot)
        return {**common, "filters": filters, "answer": answer, "explanation": "Варианты по возрастанию цены, затем по убыванию площади." if total else "Точных совпадений нет. Условия поиска не изменялись. Можно увеличить бюджет или изменить площадь и ЖК.", "total_matches": total, "needs_clarification": False}
