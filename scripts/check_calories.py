#!/usr/bin/env python3
"""
scripts/check_calories.py

Checks that the calorie value stored in the food catalog (data/food_diary.db)
matches the calories implied by the macro values, using the factors nutrition
labels use: 4 cal/g protein & carbs, 9 cal/g fat, 2.5 cal/g sugar alcohols.

The default tolerance is 40 cal: label macros are rounded to the gram, so
small gaps are expected noise. Entries that exceed it are worth a manual
look. Note that drinks containing alcohol are expected to deviate, since
alcohol calories (7 cal/g) are not covered by the macro values.

Usage:
    python scripts/check_calories.py [--tolerance 40]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bin.db import catalog_entries, get_connection


def calc_label_calories(nd: dict) -> float:
    """Calories implied by the macro values in a nutritional_data dict."""
    protein = nd.get("protein", 0) or 0
    carbs = (nd.get("carbs") or {}).get("total", 0) or 0
    fat = (nd.get("fat") or {}).get("total", 0) or 0
    sugar_alcohols = ((nd.get("carbs") or {}).get("sugars") or {}).get(
        "sugar_alcohols", {}).get("total", 0) or 0
    return 4 * protein + 4 * carbs + 9 * fat + 2.5 * sugar_alcohols


def find_mismatches(foods: list, tolerance: float) -> list:
    mismatches = []
    for food in foods:
        name = food.get("name", "UNKNOWN")
        nd = food.get("nutritional_data", {})
        if not nd:
            continue
        stored = float(nd.get("calories", 0))
        computed = calc_label_calories(nd)
        diff = stored - computed
        if abs(diff) > tolerance:
            mismatches.append({
                "name": name,
                "stored": round(stored, 1),
                "computed": round(computed, 1),
                "diff": round(diff, 1),
            })
    mismatches.sort(key=lambda m: abs(m["diff"]), reverse=True)
    return mismatches


def main():
    parser = argparse.ArgumentParser(
        description="Check calorie consistency for all foods in the catalog "
                    "(data/food_diary.db)."
    )
    parser.add_argument("--tolerance", type=float, default=40.0,
                        help="maximum allowed difference in calories")
    args = parser.parse_args()

    conn = get_connection()
    try:
        foods = catalog_entries(conn)
    finally:
        conn.close()

    mismatches = find_mismatches(foods, args.tolerance)

    print(f"Checked {len(foods)} foods (tolerance {args.tolerance:g} cal).")
    if mismatches:
        print(f"{len(mismatches)} foods deviate by more than {args.tolerance:g} cal:")
        for m in mismatches[:25]:
            print(f"  - {m['name']}: stored={m['stored']:.1f}, "
                  f"computed={m['computed']:.1f}, diff={m['diff']:+.1f}")
        if len(mismatches) > 25:
            print(f"  ... and {len(mismatches) - 25} more (adjust --tolerance to see them)")
    else:
        print("No mismatches found (within tolerance).")


if __name__ == "__main__":
    main()
