#!/usr/bin/env python3
"""One-time migration: data/food.json + data/diary/*.json -> data/food_diary.db

Rebuilds the SQLite database from the JSON files. Idempotent: any existing
database file is removed and recreated, so it is safe to re-run after
editing the JSON (though once the DB is the source of truth you would not).

Usage (from the repo root):
    python scripts/migrate_to_sqlite.py
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bin.db import DB_PATH, get_connection, init_db  # noqa: E402

DATE_FILE_RE = re.compile(r"^\d{8}\.json$")


def flatten_food(entry: dict) -> dict:
    """Extract the flattened column values for one food.json entry."""
    nutr = entry.get("nutritional_data", {})
    fat = nutr.get("fat", {})
    carbs = nutr.get("carbs", {})
    return {
        "serving_size": entry.get("serving_size"),
        "calories": nutr.get("calories"),
        "protein": nutr.get("protein"),
        "fat_total": fat.get("total"),
        "fat_saturated": fat.get("saturated_fat", {}).get("total"),
        "sodium": nutr.get("sodium", {}).get("total"),
        "carbs_total": carbs.get("total"),
        "fiber_total": carbs.get("dietary_fiber", {}).get("total"),
        "sugars_total": carbs.get("sugars", {}).get("total"),
        "added_sugars_total": carbs.get("sugars", {}).get("added_sugars", {}).get("total"),
        "sugar_alcohols_total": carbs.get("sugars", {}).get("sugar_alcohols", {}).get("total"),
        "cholesterol": nutr.get("cholesterol", {}).get("total"),
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    food_path = root / "data" / "food.json"
    diary_dir = root / "data" / "diary"

    # Start from a fresh database.
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = get_connection()
    init_db(conn)

    # --- 1. Food catalog -------------------------------------------------
    # ON CONFLICT ... UPDATE gives "last entry wins" on duplicate names,
    # matching the old `FOOD[i["name"]] = Food(i)` dict behaviour.
    foods = json.load(open(food_path))
    conn.executemany(
        """
        INSERT INTO foods (name, serving_size, calories, protein, fat_total,
                          fat_saturated, sodium, carbs_total, fiber_total,
                          sugars_total, added_sugars_total,
                          sugar_alcohols_total, cholesterol, raw_json)
        VALUES (:name, :serving_size, :calories, :protein, :fat_total,
                :fat_saturated, :sodium, :carbs_total, :fiber_total,
                :sugars_total, :added_sugars_total, :sugar_alcohols_total,
                :cholesterol, :raw_json)
        ON CONFLICT(name) DO UPDATE SET
            serving_size = excluded.serving_size,
            calories = excluded.calories,
            protein = excluded.protein,
            fat_total = excluded.fat_total,
            fat_saturated = excluded.fat_saturated,
            sodium = excluded.sodium,
            carbs_total = excluded.carbs_total,
            fiber_total = excluded.fiber_total,
            sugars_total = excluded.sugars_total,
            added_sugars_total = excluded.added_sugars_total,
            sugar_alcohols_total = excluded.sugar_alcohols_total,
            cholesterol = excluded.cholesterol,
            raw_json = excluded.raw_json
        """,
        [{"name": e["name"], **flatten_food(e), "raw_json": json.dumps(e)} for e in foods],
    )
    food_ids = {
        row["name"]: row["id"]
        for row in conn.execute("SELECT name, id FROM foods")
    }

    # --- 2. Diary days ----------------------------------------------------
    n_meals = 0
    n_items = 0
    missing_from_catalog = set()
    for fname in sorted(os.listdir(diary_dir)):
        if not DATE_FILE_RE.match(fname):
            continue
        date = fname[:8]
        with open(os.path.join(diary_dir, fname)) as f:
            data = json.load(f)
        for sort_order, meal in enumerate(data):
            meal_id = conn.execute(
                "INSERT INTO meals (date, name, sort_order) VALUES (?, ?, ?)",
                (date, meal["name"], sort_order),
            ).lastrowid
            n_meals += 1
            for item in meal["foods"]:
                name = item["food"]
                if name not in food_ids:
                    # Diary references a food not in the catalog. Store it
                    # with no nutritional data so the meal history stays
                    # intact; consumers will treat it as "not found".
                    missing_from_catalog.add(name)
                    food_ids[name] = conn.execute(
                        "INSERT INTO foods (name) VALUES (?)", (name,)
                    ).lastrowid
                conn.execute(
                    "INSERT INTO meal_items (meal_id, food_id, weight) VALUES (?, ?, ?)",
                    (meal_id, food_ids[name], item["weight"]),
                )
                n_items += 1

    conn.commit()

    # --- 3. Report ---------------------------------------------------------
    print(f"Database written to {DB_PATH}")
    print(f"  foods:     {len(food_ids)}")
    print(f"  days:      {conn.execute('SELECT COUNT(DISTINCT date) FROM meals').fetchone()[0]}")
    print(f"  meals:     {n_meals}")
    print(f"  items:     {n_items}")

    no_nutrition = [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM foods WHERE serving_size IS NULL ORDER BY name"
        )
    ]
    if no_nutrition:
        print(f"  foods without nutritional data ({len(no_nutrition)}):")
        for name in no_nutrition:
            print(f"    - {name}")
    zero_serving = [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM foods WHERE serving_size = 0 ORDER BY name"
        )
    ]
    if zero_serving:
        print(f"  WARNING: zero serving_size (division by zero): {zero_serving}")

    if missing_from_catalog:
        print(f"  diary entries referencing foods not in food.json: {sorted(missing_from_catalog)}")

    conn.close()


if __name__ == "__main__":
    main()
