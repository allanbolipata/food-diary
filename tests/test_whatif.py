"""Unit tests for the dashboard's POST /api/what-if basket endpoint.

Run from the repo root:

    python -m unittest discover

Each test uses its own throwaway database file (tmp dir), so the real
data/food_diary.db is never touched. The endpoint itself writes nothing;
`test_what_if_writes_nothing` proves that, and
`test_basket_math_matches_day_view_math` proves the basket's numbers are
the same numbers the day view shows once an item is logged.
"""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bin.db as db

# web/app.py needs fastapi; TestClient needs httpx. Some fastapi versions
# raise RuntimeError (not ImportError) when httpx is missing, so probe with
# find_spec instead of a bare try/except import.
if importlib.util.find_spec("fastapi") and importlib.util.find_spec("httpx"):
    import web.app as web_app
    from fastapi.testclient import TestClient
else:  # web deps not installed in this interpreter
    web_app = None
    TestClient = None

from tests.test_db import full_entry


class TempDbWhatIfTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if web_app is None or TestClient is None:
            raise unittest.SkipTest(
                "fastapi/httpx not installed; install web/requirements.txt "
                "plus httpx to run the /api/what-if tests")
        import tempfile as _tf
        cls.tmp_path = Path(_tf.mkdtemp(prefix="food_diary_whatif_"))

    def setUp(self):
        assert web_app is not None and TestClient is not None
        self.dbpath = self.tmp_path / f"test_{self._testMethodName}.db"
        conn = db.get_connection(self.dbpath)
        db.init_db(conn)
        db.add_food_entry(conn, full_entry(
            name="Basket A", serving_size=100.0, calories=120.0,
            protein=10.0, fat=5.0, carbs=10.0, fiber=1.0, sodium=200.0))
        db.add_food_entry(conn, full_entry(
            name="Basket B", serving_size=50.0, calories=200.0,
            protein=20.0, fat=8.0, carbs=30.0, fiber=2.0, sodium=400.0))
        conn.close()
        # Point the API at the throwaway db and silence the reject logger so
        # the 4xx test cases do not write into the real data/ directory.
        patchers = [
            patch.object(web_app, "get_connection",
                         lambda: db.get_connection(self.dbpath)),
            patch.object(web_app, "append_reject", lambda *a, **k: None),
        ]
        for p in patchers:
            p.start()
            self.addCleanup(p.stop)
        self.client = TestClient(web_app.app)

    def tearDown(self):
        self.client.close()

    def _whatif(self, items):
        return self.client.post("/api/what-if", json={"items": items})

    def test_single_item_macros_scale_to_weight(self):
        r = self._whatif([{"food": "Basket A", "weight": 250}])
        self.assertEqual(r.status_code, 200)
        data = r.json()
        item = data["items"][0]
        self.assertFalse(item["stub"])
        self.assertEqual(item["serving_size"], 100.0)
        # 2.5 servings of a 120 cal / 10 g protein serving
        self.assertEqual(item["macros"]["calories"], 300.0)
        self.assertEqual(item["macros"]["protein"], 25.0)
        self.assertEqual(item["macros"]["fat"], 12.5)
        self.assertEqual(item["macros"]["carbs"], 25.0)
        self.assertEqual(item["macros"]["sodium"], 500.0)
        self.assertEqual(data["totals"]["calories"], 300.0)

    def test_two_items_tally_into_totals(self):
        r = self._whatif([{"food": "Basket A", "weight": 100},
                          {"food": "Basket B", "weight": 100}])
        self.assertEqual(r.status_code, 200)
        totals = r.json()["totals"]
        # 100 g of A = 1 serving (120 cal); 100 g of B = 2 servings (400 cal)
        self.assertEqual(totals["calories"], 520.0)   # 120 + 2*200
        self.assertEqual(totals["protein"], 50.0)     # 10 + 2*20
        self.assertEqual(totals["fat"], 21.0)         # 5 + 2*8
        self.assertEqual(totals["carbs"], 70.0)       # 10 + 2*30
        self.assertEqual(totals["sodium"], 1000.0)    # 200 + 2*400

    def test_unknown_food_is_stub_out_of_totals(self):
        r = self._whatif([{"food": "No Such Food", "weight": 10},
                          {"food": "Basket A", "weight": 100}])
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["items"][0]["stub"])
        self.assertIsNone(data["items"][0]["macros"])
        self.assertIsNone(data["items"][0]["serving_size"])
        self.assertEqual(data["totals"]["calories"], 120.0)  # stub excluded

    def test_empty_basket_rejected(self):
        self.assertEqual(self._whatif([]).status_code, 422)

    def test_nonpositive_weight_rejected(self):
        self.assertEqual(
            self._whatif([{"food": "Basket A", "weight": 0}]).status_code, 422)
        self.assertEqual(
            self._whatif([{"food": "Basket A", "weight": -5}]).status_code, 422)

    def test_what_if_writes_nothing(self):
        self._whatif([{"food": "Basket A", "weight": 250},
                      {"food": "No Such Food", "weight": 10}])
        conn = db.get_connection(self.dbpath)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM meals").fetchone()[0], 0)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM meal_items").fetchone()[0], 0)
        conn.close()

    def test_basket_math_matches_day_view_math(self):
        # Log Basket A at 250 g, then check the basket's tally for the same
        # item equals the per-item macros the day view shows.
        r = self.client.post("/api/days/20261110/items",
                             json={"food": "Basket A", "weight": 250,
                                   "meal": "Breakfast"})
        self.assertEqual(r.status_code, 201)
        day = self.client.get("/api/days/20261110").json()
        logged = day["meals"][0]["items"][0]["macros"]
        basket = self._whatif([{"food": "Basket A", "weight": 250}]).json()
        self.assertEqual(basket["items"][0]["macros"], logged)
        self.assertEqual(basket["totals"]["calories"], day["totals"]["calories"])

    # ---- ad-hoc rough macros (estimate a non-catalog food) ----

    ADHOC = {"name": "Mystery Burrito", "serving_size": 250.0,
             "calories": 600.0, "protein": 30.0, "fat_total": 20.0,
             "carbs_total": 60.0, "fiber_total": 5.0, "sodium": 800.0}

    def test_adhoc_estimation_before_log(self):
        # Rough macros make an unknown food estimable — the point of the
        # basket: see the numbers first, log only if you want.
        r = self._whatif([{"food": "Mystery Burrito", "weight": 250,
                           "nutrition": self.ADHOC}])
        self.assertEqual(r.status_code, 200)
        data = r.json()
        item = data["items"][0]
        self.assertTrue(item["ad_hoc"])
        self.assertFalse(item["stub"])
        self.assertEqual(item["serving_size"], 250.0)
        self.assertEqual(item["macros"]["calories"], 600.0)
        self.assertEqual(item["macros"]["protein"], 30.0)
        self.assertEqual(data["totals"]["calories"], 600.0)
        self.assertEqual(data["totals"]["fiber"], 5.0)
        conn = db.get_connection(self.dbpath)
        # ...and the estimate itself stored nothing anywhere.
        self.assertEqual(conn.execute(
            "SELECT COUNT(*) FROM foods").fetchone()[0], 2)
        self.assertEqual(conn.execute(
            "SELECT COUNT(*) FROM meals").fetchone()[0], 0)
        conn.close()

    def test_adhoc_scales_like_catalog(self):
        # 150 g of a 250 g serving = 0.6x the per-serving estimate.
        r = self._whatif([{"food": "Mystery Burrito", "weight": 150,
                           "nutrition": self.ADHOC}])
        self.assertEqual(r.json()["items"][0]["macros"]["calories"], 360.0)

    def test_catalog_wins_over_supplied_nutrition(self):
        r = self._whatif([{"food": "Basket A", "weight": 100,
                           "nutrition": {"name": "Basket A",
                                         "serving_size": 100.0,
                                         "calories": 9999.0}}])
        item = r.json()["items"][0]
        self.assertFalse(item["ad_hoc"])
        self.assertFalse(item["stub"])
        self.assertEqual(item["macros"]["calories"], 120.0)  # catalog value

    def test_estimate_then_log_then_catalog_tally_matches(self):
        # The estimate-before invariant: what the basket projected equals
        # exactly what the day view shows once logged (logging creates the
        # catalog entry, as the dashboard does).
        est = self._whatif([{"food": "Mystery Burrito", "weight": 250,
                             "nutrition": self.ADHOC}]).json()
        r = self.client.post("/api/foods", json=self.ADHOC)
        self.assertEqual(r.status_code, 201)
        r = self.client.post("/api/days/20261110/items",
                             json={"food": "Mystery Burrito", "weight": 250,
                                   "meal": "Dinner"})
        self.assertEqual(r.status_code, 201)
        day = self.client.get("/api/days/20261110").json()
        logged = day["meals"][0]["items"][0]["macros"]
        self.assertEqual(est["items"][0]["macros"], logged)
        # After logging, a plain (nutrition-free) basket tally gives the
        # same numbers from the catalog alone.
        after = self._whatif([{"food": "Mystery Burrito", "weight": 250}])
        item = after.json()["items"][0]
        self.assertFalse(item["ad_hoc"])
        self.assertEqual(item["macros"], logged)


if __name__ == "__main__":
    unittest.main()
