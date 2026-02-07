#!/usr/bin/env python3
"""
scripts/check_diary_calories.py

Checks calorie consistency only for foods listed in a diary file.
Usage:
    python scripts/check_diary_calories.py path/to/diary.json [--tolerance 1.5]
"""

import argparse
import json
import sys
from pathlib import Path


def calc_calories(protein: float, carbs: float, fat: float) -> float:
    """Return calories from macros."""
    return protein * 4 + carbs * 4 + fat * 9


def load_food_db() -> dict:
    """Return a mapping from food name → nutritional_data."""
    food_path = Path(__file__).resolve().parents[1] / "data" / "food.json"
    with open(food_path, "r", encoding="utf-8") as f:
        foods = json.load(f)
    return {food["name"]: food.get("nutritional_data", {}) for food in foods}


def load_diary(diary_path: Path) -> set:
    """Return a set of food names that appear in the diary."""
    with open(diary_path, "r", encoding="utf-8") as f:
        diary = json.load(f)
    names = set()
    for entry in diary:
        for item in entry.get("foods", []):
            names.add(item["food"])
    return names


def parse_args():
    parser = argparse.ArgumentParser(
        description="Check calorie consistency for foods listed in a diary JSON."
    )
    parser.add_argument(
        "diary_path",
        help="Path to the diary JSON file (e.g., data/diary/20260207.json)"
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1.0,
        help="Maximum allowed difference (in calories) between stored and computed values.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    diary_file = Path(args.diary_path).expanduser().resolve()

    if not diary_file.is_file():
        print(f"❌  File not found: {diary_file}")
        sys.exit(1)

    food_db = load_food_db()
    diary_foods = load_diary(diary_file)

    mismatches = []
    for name in diary_foods:
        data = food_db.get(name)
        if not data:
            print(f"⚠️  Food '{name}' not found in database.")
            continue
        protein = float(data.get("protein", 0))
        carbs   = float(data.get("carbs", {}).get("total",0))
        fat     = float(data.get("fat", {}).get("total", 0))

        computed = calc_calories(protein, carbs, fat)
        stored   = float(data.get("calories", 0))

        if abs(computed - stored) > args.tolerance:
            mismatches.append({
                "name": name,
                "stored": stored,
                "computed": round(computed, 2),
                "diff": round(stored - computed, 2)
            })

    print(f"Checked {len(diary_foods)} foods from diary.")
    if mismatches:
        print(f"{len(mismatches)} foods have a calorie mismatch > {args.tolerance} cal:")
        for m in mismatches:
            print(f"  - {m['name']}: stored={m['stored']} cal, computed={m['computed']} cal, diff={m['diff']}")
    else:
        print("No mismatches found (within tolerance).")

if __name__ == "__main__":
    main()
