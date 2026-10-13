#!/usr/bin/env python3
"""Log diary entries into the food diary database.

Usage (from the repo root):
    python log.py add "Food Name" [weight] [--date YYYYMMDD] [--meal NAME]
    python log.py day [date]

Behaviour of ``add``:
  - Writes to data/food_diary.db (the source used by eaten.py/trend.py).
  - Reconciles data/diary/<date>.json against the database, so that the
    database ends up containing exactly the items the file lists, per
    meal name:
      * items in the JSON file but not in the DB are imported,
      * items in the DB but no longer in the JSON file are removed,
      * items present in both are left untouched.
    A weight changed by hand in the file therefore replaces the old
    weight, and an item moved between meals ends up in the new meal.
  - Foods that are in the file but not in the catalog are imported as
    stub rows (no nutritional data), keeping the diary intact.
  - The JSON file is rewritten from the database afterwards, so app.py
    (JSON) and eaten.py/trend.py (DB) always agree.
  - Weight is in the same units as the catalog's serving_size (grams);
    the default of 1 means "one serving".
  - Safety: if the file lists no items at all but the database still has
    items for that day, nothing is removed — an empty (corrupt) file must
    not wipe the database.

Foods must exist in the catalog; if a name is not found, close matches
from the catalog are suggested.
"""

import argparse
import difflib
import json
import sys
from datetime import date, datetime
from pathlib import Path

from bin.db import (
    add_meal_item,
    daily_totals,
    day_items,
    export_day_json,
    get_connection,
    load_day,
)

REPO_ROOT = Path(__file__).resolve().parent
DIARY_DIR = REPO_ROOT / "data" / "diary"


def parse_date(s: str | None, default: str) -> str:
    s = s or default
    try:
        return datetime.strptime(s, "%Y%m%d").strftime("%Y%m%d")
    except ValueError:
        raise SystemExit(f"Invalid date '{s}' (expected YYYYMMDD).")


def _shown(w) -> int | float:
    """Normalise a stored weight so 1.0 and 1 compare equal."""
    w = float(w)
    return int(w) if w.is_integer() else w


def sync_day(conn, day: str, path: Path) -> dict:
    """Reconcile the database with the diary JSON file.

    After this function the database contains exactly the (food, weight)
    items the file lists, per meal name: items only in the file are
    imported (unknown foods become stub catalog rows), items only in the
    database are removed, and items in both are untouched. The file is
    then rewritten from the database.

    Returns ``{"added": [...], "removed": [...], "skipped": bool}``.
    """
    db_items = day_items(conn, day)
    file_meals = json.loads(path.read_text()) if path.exists() else []

    # Multiset of (food, weight) per meal name, for the DB and the file.
    db_counts = {}
    for it in db_items:
        key = (it["food_name"], _shown(it["weight"]))
        c = db_counts.setdefault(it["meal_name"], {})
        c[key] = c.get(key, 0) + 1

    file_counts = {}
    n_file_items = 0
    for m in file_meals:
        for item in m["foods"]:
            key = (item["food"], _shown(item["weight"]))
            c = file_counts.setdefault(m["name"], {})
            c[key] = c.get(key, 0) + 1
            n_file_items += 1

    # Safety: an empty file must not wipe a day that still has items.
    if path.exists() and n_file_items == 0 and db_items:
        print(f"Warning: {path.name} lists no items but the database has "
              f"{len(db_items)} for {day}; nothing was removed. Fix the "
              f"file and re-run to sync.")
        return {"added": [], "removed": [], "skipped": True}

    added, removed = [], []

    # Import items the file lists beyond what the database has.
    for m in file_meals:
        db_c = db_counts.get(m["name"], {})
        for item in m["foods"]:
            key = (item["food"], _shown(item["weight"]))
            for _ in range(max(file_counts[m["name"]][key] - db_c.get(key, 0), 0)):
                try:
                    add_meal_item(conn, day, m["name"], item["food"], item["weight"])
                except LookupError:
                    # Food not in the catalog: create a stub row so the
                    # diary stays intact (same behaviour as
                    # migrate_to_sqlite.py).
                    conn.execute("INSERT INTO foods (name) VALUES (?)", (item["food"],))
                    conn.commit()
                    add_meal_item(conn, day, m["name"], item["food"], item["weight"])
                    print(f"Note: '{item['food']}' was added to the catalog without nutritional data.")
                added.append(item["food"])

    # Remove items the database has beyond what the file lists.
    remaining = {m: dict(c) for m, c in db_counts.items()}
    for it in db_items:
        key = (it["food_name"], _shown(it["weight"]))
        if remaining[it["meal_name"]].get(key, 0) <= file_counts.get(it["meal_name"], {}).get(key, 0):
            continue
        remaining[it["meal_name"]][key] -= 1
        conn.execute("DELETE FROM meal_items WHERE id = ?", (it["id"],))
        removed.append(it["food_name"])

    # Drop meals that exist in the database but not in the file
    # (their items were already removed above).
    file_meal_names = {m["name"] for m in file_meals}
    for mname in db_counts.keys():
        if mname not in file_meal_names:
            conn.execute("DELETE FROM meals WHERE date = ? AND name = ?", (day, mname))

    conn.commit()
    export_day_json(conn, day, path)
    return {"added": added, "removed": removed, "skipped": False}


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

    report = sync_day(conn, day, DIARY_DIR / f"{day}.json")
    print(f"Added {args.food!r} ({args.weight:g} serving(s)) to {args.meal!r} on {day}.")
    if report["added"]:
        print(f"Imported from the diary JSON (in the file, not in the DB): {', '.join(report['added'])}")
    if report["removed"]:
        print(f"Removed from the database (no longer in the diary file): {', '.join(report['removed'])}")
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
