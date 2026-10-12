#!/usr/bin/env python3
"""Log diary entries into the food diary database.

Usage (from the repo root):
    python log.py add "Food Name" [weight] [--date YYYYMMDD] [--meal NAME]
    python log.py day [date]

Behaviour of ``add``:
  - Writes to data/food_diary.db (the source used by eaten.py/trend.py).
  - Keeps data/diary/<date>.json in sync: any item present in the JSON
    file but missing from the database is imported into the database,
    and the JSON file is rewritten from the database if the two had
    diverged. So app.py (JSON) and eaten.py/trend.py (DB) always agree.
  - Weight is in the same units as the catalog's serving_size (grams);
    the default of 1 means "one serving".

Foods must exist in the catalog; if a name is not found, close matches
from the catalog are suggested.
"""

import argparse
import difflib
import json
import re
import sys
from datetime import date
from pathlib import Path

from bin.db import (
    add_meal_item,
    daily_totals,
    export_day_json,
    get_connection,
    load_day,
)

REPO_ROOT = Path(__file__).resolve().parent
DIARY_DIR = REPO_ROOT / "data" / "diary"


def parse_date(s: str | None, default: str) -> str:
    s = s or default
    if not re.fullmatch(r"\d{8}", s):
        raise SystemExit(f"Invalid date '{s}' (expected YYYYMMDD).")
    return s


def sync_day(conn, day: str, path: Path) -> list:
    """Import items that exist in the JSON file but not in the DB, then
    rewrite the JSON file from the DB if the two had diverged. Returns
    the list of food names imported (possibly empty)."""
    db_meals = load_day(conn, day)
    imported = []
    if path.exists():
        file_meals = json.loads(path.read_text())
        for meal in file_meals:
            db_items = {
                (it["food"], it["weight"])
                for m in db_meals
                if m["name"] == meal["name"]
                for it in m["foods"]
            }
            for item in meal["foods"]:
                if (item["food"], item["weight"]) in db_items:
                    continue
                try:
                    add_meal_item(conn, day, meal["name"], item["food"], item["weight"])
                except LookupError:
                    # Food not in the catalog: create a stub row so the diary
                    # stays intact (same behaviour as migrate_to_sqlite.py).
                    conn.execute("INSERT INTO foods (name) VALUES (?)", (item["food"],))
                    conn.commit()
                    add_meal_item(conn, day, meal["name"], item["food"], item["weight"])
                    print(f"Note: '{item['food']}' was added to the catalog without nutritional data.")
                imported.append(item["food"])
    # The DB just gained at least one item (or the file had extras imported
    # above), so rewrite the file from the DB to keep both views in sync.
    export_day_json(conn, day, path)
    return imported


def cmd_add(conn, args) -> None:
    day = parse_date(args.date, date.today().strftime("%Y%m%d"))
    if args.weight < 0:
        raise SystemExit("Weight must be >= 0.")
    try:
        add_meal_item(conn, day, args.meal, args.food, args.weight)
    except LookupError:
        names = [r["name"] for r in conn.execute("SELECT name FROM foods")]
        # Case-insensitive fuzzy match; map back to the original names.
        lower_to_orig = {}
        for n in names:
            lower_to_orig.setdefault(n.lower(), n)
        close = [lower_to_orig[l] for l in
                 difflib.get_close_matches(args.food.lower(), list(lower_to_orig), n=5)]
        print(f"Error: '{args.food}' is not in the food catalog.")
        if close:
            print("Did you mean one of:")
            for n in close:
                print(f"  {n}")
        sys.exit(1)

    imported = sync_day(conn, day, DIARY_DIR / f"{day}.json")
    print(f"Added {args.food!r} ({args.weight:g} serving(s)) to {args.meal!r} on {day}.")
    if imported:
        print(f"Imported from the diary JSON (was in the file but not the DB): {', '.join(imported)}")
    totals, _ = daily_totals(conn)
    t = totals.get(day)
    if t:
        print(f"Totals for {day} (incl. uneaten meals): "
              f"calories {t['calories']:.1f}, protein {t['protein']:.1f}g, "
              f"fat {t['fat']:.1f}g, carbs {t['carbs']:.1f}g")


def cmd_day(conn, args) -> None:
    day = parse_date(args.date, date.today().strftime("%Y%m%d"))
    meals = load_day(conn, day)
    if not meals:
        print(f"No diary entries for {day}.")
        return
    for m in meals:
        print(f"--- {m['name']}")
        for it in m["foods"]:
            print(f"  {it['food']}  ({it['weight']} serving(s))")
    totals, missing = daily_totals(conn)
    t = totals.get(day, {"calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0})
    print("--- Totals (incl. uneaten meals, trend.py semantics)")
    print(f"calories {t['calories']:.1f}, protein {t['protein']:.1f}g, "
          f"fat {t['fat']:.1f}g, carbs {t['carbs']:.1f}g")
    for name, n in missing:
        print(f"Warning: no nutritional data for '{name}' (x{n})")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="add a food to a diary day")
    p_add.add_argument("food", help="exact food name from the catalog")
    p_add.add_argument("weight", nargs="?", type=float, default=1.0,
                       help="amount in serving units (default 1)")
    p_add.add_argument("--date", help="YYYYMMDD (default: today)")
    p_add.add_argument("--meal", default="Miscellaneous",
                       help="meal name (default: Miscellaneous)")

    p_day = sub.add_parser("day", help="show a diary day from the database")
    p_day.add_argument("date", nargs="?", help="YYYYMMDD (default: today)")

    args = parser.parse_args()
    conn = get_connection()
    try:
        if args.cmd == "add":
            cmd_add(conn, args)
        else:
            cmd_day(conn, args)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
