#!/usr/bin/env python3
"""
scripts/check_diary_calories.py

Checks calorie consistency only for the foods listed in one diary day.
The argument is a date (YYYYMMDD, read from data/food_diary.db) or a
legacy diary JSON path (read from the file).

Usage:
    python scripts/check_diary_calories.py 20260207 [--tolerance 40]
    python scripts/check_diary_calories.py path/to/diary.json [--tolerance 40]
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bin.db import catalog_entries, get_connection, load_day
from check_calories import calc_label_calories


def load_names_from_db(day: str) -> set:
    conn = get_connection()
    try:
        names = set()
        for meal in load_day(conn, day):
            for item in meal["foods"]:
                names.add(item["food"])
        return names
    finally:
        conn.close()


def load_names_from_file(path: Path) -> set:
    with open(path, "r", encoding="utf-8") as f:
        diary = json.load(f)
    names = set()
    for entry in diary:
        for item in entry.get("foods", []):
            names.add(item["food"])
    return names


def main():
    parser = argparse.ArgumentParser(
        description="Check calorie consistency for the foods listed in one diary day."
    )
    parser.add_argument("target",
                        help="a date (YYYYMMDD) or a path to a diary JSON file")
    parser.add_argument("--tolerance", type=float, default=40.0,
                        help="Maximum allowed difference in calories")
    args = parser.parse_args()

    if re.fullmatch(r"\d{8}", args.target):
        names = load_names_from_db(args.target)
    else:
        diary_file = Path(args.target).expanduser().resolve()
        if not diary_file.is_file():
            print(f"File not found: {diary_file}")
            sys.exit(1)
        names = load_names_from_file(diary_file)

    conn = get_connection()
    try:
        foods = {food["name"]: food.get("nutritional_data", {})
                 for food in catalog_entries(conn)}
    finally:
        conn.close()

    mismatches = []
    for name in sorted(names):
        nd = foods.get(name)
        if not nd:
            print(f"Food '{name}' not found in the catalog.")
            continue
        stored = float(nd.get("calories", 0))
        computed = calc_label_calories(nd)
        if abs(stored - computed) > args.tolerance:
            mismatches.append({
                "name": name,
                "stored": round(stored, 1),
                "computed": round(computed, 1),
                "diff": round(stored - computed, 1),
            })
    mismatches.sort(key=lambda m: abs(m["diff"]), reverse=True)

    print(f"Checked {len(names)} foods from diary (tolerance {args.tolerance:g} cal).")
    if mismatches:
        print(f"{len(mismatches)} foods deviate by more than {args.tolerance:g} cal:")
        for m in mismatches:
            print(f"  - {m['name']}: stored={m['stored']:.1f}, "
                  f"computed={m['computed']:.1f}, diff={m['diff']:+.1f}")
    else:
        print("No mismatches found (within tolerance).")


if __name__ == "__main__":
    main()
