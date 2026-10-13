"""Unit tests for bin.db (the SQLite layer) — run from the repo root:

    python -m unittest discover

Each test uses its own throwaway database file (tmp_path), so the real
data/food_diary.db is never touched. No third-party dependencies.
"""

import json
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bin.db as db


def full_entry(name="Test Food", serving_size=100.0, calories=120.0,
               protein=10.0, fat=5.0, carbs=10.0, fiber=1.0,
               sodium=200.0) -> dict:
    """A complete catalog entry in the original food.json shape."""
    return {
        "name": name,
        "serving_size": serving_size,
        "nutritional_data": {
            "calories": calories,
            "protein": protein,
            "fat": {"total": fat, "saturated_fat": {"total": 0.5}},
            "carbs": {
                "total": carbs,
                "dietary_fiber": {"total": fiber},
                "sugars": {"total": 2.0, "added_sugars": {"total": 0.0}},
            },
            "sodium": {"total": sodium},
            "cholesterol": {"total": 10.0},
        },
    }


class TempDbTest(unittest.TestCase):
    def setUp(self):
        self.dbpath = self.tmp_path / f"test_{self._testMethodName}.db"
        self.conn = db.get_connection(self.dbpath)
        db.init_db(self.conn)

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.tmp_path = Path(tempfile.mkdtemp(prefix="food_diary_test_"))

    def tearDown(self):
        self.conn.close()

    def _add_food(self, **kw):
        entry = full_entry(**kw)
        db.add_food_entry(self.conn, entry)
        return entry

    # --- catalog validation -------------------------------------------------

    def test_add_rejects_sparse_entry(self):
        sparse = {"name": "Sparse", "serving_size": 100}
        with self.assertRaises(ValueError):
            db.add_food_entry(self.conn, sparse)
        self.assertIsNone(self.conn.execute(
            "SELECT 1 FROM foods WHERE name = 'Sparse'").fetchone())

    def test_add_rejects_missing_fiber(self):
        entry = full_entry(name="No Fiber")
        del entry["nutritional_data"]["carbs"]["dietary_fiber"]
        with self.assertRaises(ValueError):
            db.add_food_entry(self.conn, entry)

    def test_update_rejects_sparse_entry(self):
        self._add_food(name="Existing")
        entry = full_entry(name="Existing")
        del entry["nutritional_data"]["protein"]
        with self.assertRaises(ValueError):
            db.update_food_entry(self.conn, entry)
        # The stored entry must be untouched.
        row = self.conn.execute(
            "SELECT protein FROM foods WHERE name = 'Existing'").fetchone()
        self.assertEqual(row["protein"], 10.0)

    def test_update_unknown_food_raises(self):
        with self.assertRaises(LookupError):
            db.update_food_entry(self.conn, full_entry(name="Ghost"))

    def test_add_duplicate_raises(self):
        self._add_food(name="Dup")
        with self.assertRaises(ValueError):
            db.add_food_entry(self.conn, full_entry(name="Dup"))

    def test_remove_food_refused_while_used(self):
        self._add_food(name="Used")
        db.add_meal_item(self.conn, "20990101", "Lunch", "Used", 100)
        with self.assertRaises(ValueError):
            db.remove_food(self.conn, "Used")

    def test_remove_food_ok_when_unused(self):
        self._add_food(name="Unused")
        db.remove_food(self.conn, "Unused")
        self.assertIsNone(self.conn.execute(
            "SELECT 1 FROM foods WHERE name = 'Unused'").fetchone())

    # --- diary item operations ---------------------------------------------

    def test_add_meal_item_unknown_food_raises(self):
        with self.assertRaises(LookupError):
            db.add_meal_item(self.conn, "20990101", "Lunch", "Ghost", 100)

    def test_set_weight_ambiguous_without_disambiguator(self):
        self._add_food(name="Dups")
        db.add_meal_item(self.conn, "20990101", "Lunch", "Dups", 50)
        db.add_meal_item(self.conn, "20990101", "Lunch", "Dups", 100)
        with self.assertRaises(ValueError):
            db.set_item_weight(self.conn, "20990101", "Lunch", "Dups", 75)
        db.set_item_weight(self.conn, "20990101", "Lunch", "Dups", 75, existing_weight=50)
        self.assertEqual(sorted(db.item_weights(self.conn, "20990101", "Lunch", "Dups")),
                         [75, 100])

    def test_remove_ambiguous_without_disambiguator(self):
        self._add_food(name="Dups")
        db.add_meal_item(self.conn, "20990101", "Lunch", "Dups", 50)
        db.add_meal_item(self.conn, "20990101", "Lunch", "Dups", 100)
        with self.assertRaises(ValueError):
            db.remove_item(self.conn, "20990101", "Lunch", "Dups")
        n = db.remove_item(self.conn, "20990101", "Lunch", "Dups", weight=50)
        self.assertEqual(n, 1)
        self.assertEqual(db.item_weights(self.conn, "20990101", "Lunch", "Dups"), [100])

    def test_remove_all(self):
        self._add_food(name="Dups")
        db.add_meal_item(self.conn, "20990101", "Lunch", "Dups", 50)
        db.add_meal_item(self.conn, "20990101", "Lunch", "Dups", 100)
        n = db.remove_item(self.conn, "20990101", "Lunch", "Dups", all=True)
        self.assertEqual(n, 2)
        self.assertEqual(db.item_weights(self.conn, "20990101", "Lunch", "Dups"), [])

    def test_remove_meal_cascades_items(self):
        self._add_food(name="Cascaded")
        db.add_meal_item(self.conn, "20990101", "Lunch", "Cascaded", 100)
        db.remove_meal(self.conn, "20990101", "Lunch")
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM meal_items").fetchone()[0], 0)
        self.assertIsNone(self.conn.execute(
            "SELECT 1 FROM meals WHERE date = '20990101'").fetchone())

    def test_clear_day(self):
        self._add_food(name="Clear Me")
        db.add_meal_item(self.conn, "20990101", "Lunch", "Clear Me", 100)
        db.add_meal_item(self.conn, "20990101", "Snack", "Clear Me", 50)
        meals, items = db.clear_day(self.conn, "20990101")
        self.assertEqual((meals, items), (2, 2))
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM meals").fetchone()[0], 0)

    # --- rename_meal ---------------------------------------------------------

    def test_rename_meal_simple(self):
        self._add_food(name="Renamed")
        db.add_meal_item(self.conn, "20990101", "Breakfast", "Renamed", 100)
        n = db.rename_meal(self.conn, "20990101", "Breakfast", "Morning")
        self.assertEqual(n, 1)
        self.assertIsNone(self.conn.execute(
            "SELECT 1 FROM meals WHERE name = 'Breakfast'").fetchone())
        self.assertEqual(db.load_day(self.conn, "20990101")[0]["name"], "Morning")

    def test_rename_meal_merges_into_existing(self):
        self._add_food(name="Merge Me")
        db.add_meal_item(self.conn, "20990101", "Lunch", "Merge Me", 100)
        db.add_meal_item(self.conn, "20990101", "Dinner", "Merge Me", 50)
        n = db.rename_meal(self.conn, "20990101", "Lunch", "Dinner")
        self.assertEqual(n, 1)
        meals = self.conn.execute(
            "SELECT name FROM meals WHERE date = '20990101'").fetchall()
        self.assertEqual([m["name"] for m in meals], ["Dinner"])
        self.assertEqual(sorted(db.item_weights(self.conn, "20990101", "Dinner", "Merge Me")),
                         [50, 100])

    def test_rename_meal_all_days(self):
        self._add_food(name="Typos")
        for d in ("20990101", "20990102"):
            db.add_meal_item(self.conn, d, "Makeshift Sanwich", "Typos", 10)
        n = db.rename_meal(self.conn, None, "Makeshift Sanwich", "Makeshift Sandwich")
        self.assertEqual(n, 2)
        names = {r["name"] for r in self.conn.execute("SELECT name FROM meals")}
        self.assertEqual(names, {"Makeshift Sandwich"})

    def test_rename_meal_missing_raises(self):
        with self.assertRaises(LookupError):
            db.rename_meal(self.conn, "20990101", "Ghost", "Also Ghost")

    # --- totals / export / backup -------------------------------------------

    def test_daily_totals_weight_scaling(self):
        # 200 g of a 100 g serving at 120 cal -> 240 cal.
        self._add_food(name="Scaled", serving_size=100.0, calories=120.0)
        db.add_meal_item(self.conn, "20990101", "Lunch", "Scaled", 200)
        # Zero-weight item must not contribute.
        db.add_meal_item(self.conn, "20990101", "Snack", "Scaled", 0)
        totals, missing = db.daily_totals(self.conn)
        self.assertEqual(totals["20990101"]["calories"], 240.0)
        self.assertEqual(totals["20990101"]["protein"], 20.0)
        self.assertEqual(missing, [])

    def test_load_day_int_weight_display(self):
        self._add_food(name="Shown")
        db.add_meal_item(self.conn, "20990101", "Lunch", "Shown", 100.0)
        db.add_meal_item(self.conn, "20990101", "Lunch", "Shown", 76.1)
        foods = db.load_day(self.conn, "20990101")[0]["foods"]
        self.assertEqual([f["weight"] for f in foods], [100, 76.1])

    def test_export_and_day_json_text(self):
        self._add_food(name="Exported")
        db.add_meal_item(self.conn, "20990101", "Lunch", "Exported", 100)
        path = self.tmp_path / "export" / "20990101.json"
        db.export_day_json(self.conn, "20990101", path)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data, [{"name": "Lunch",
                                  "foods": [{"food": "Exported", "weight": 100}]}])
        text = db.day_json_text(self.conn, "20990101")
        self.assertEqual(json.loads(text), data)

    def test_backup_writes_readable_db(self):
        self._add_food(name="Backed Up")
        dest = self.tmp_path / "backups" / "test-1234.db"
        db.backup_db(self.conn, dest)
        conn2 = sqlite3.connect(dest)
        try:
            n = conn2.execute("SELECT COUNT(*) FROM foods").fetchone()[0]
        finally:
            conn2.close()
        self.assertEqual(n, 1)

    def test_integrity_check(self):
        self._add_food(name="Integrity")
        db.add_meal_item(self.conn, "20990101", "Lunch", "Integrity", 100)
        self.assertEqual(self.conn.execute("PRAGMA integrity_check").fetchone()[0],
                         "ok")


if __name__ == "__main__":
    unittest.main()
