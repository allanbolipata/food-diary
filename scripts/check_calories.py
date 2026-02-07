#!/usr/bin/env python3
"""
scripts/check_calories.py

Checks that the calorie value stored in data/food.json matches the
calories computed from protein, carbs, and fat.

Usage:
    python scripts/check_calories.py
"""

import json
import os
from pathlib import Path
from pprint import pprint

def calc_calories(protein: float, carbs: float, fat: float) -> float:
    """Return calories from macros."""
    return protein * 4 + carbs * 4 + fat * 9

def main():
    # Locate the JSON file
    repo_root = Path(__file__).resolve().parents[1]  # two levels up from scripts/
    food_path = repo_root / "data" / "food.json"

    with open(food_path, "r", encoding="utf-8") as f:
        foods = json.load(f)

    mismatches = []
    for food in foods:
        name = food.get("name", "UNKNOWN")
        data = food.get("nutritional_data", {})
        pprint(data)
        protein = float(data.get("protein", 0))
        carbs   = float(data.get("carbs", {}).get("total",0))
        fat     = float(data.get("fat", {}).get("total", 0))
        computed = calc_calories(protein, carbs, fat)
        stored   = float(data.get("calories", 0))

        if abs(computed - stored) > 1.0:   # tolerance of 1 cal
            mismatches.append({
                "name": name,
                "stored": stored,
                "computed": round(computed, 2),
                "diff": round(stored - computed, 2)
            })

    # Output results
    print(f"Checked {len(foods)} foods.")
    if mismatches:
        print(f"{len(mismatches)} foods have a calorie mismatch > 1 cal:")
        for m in mismatches:
            print(f"  - {m['name']}: stored={m['stored']} cal, computed={m['computed']} cal, diff={m['diff']}")
    else:
        print("No mismatches found (within 1 cal tolerance).")

if __name__ == "__main__":
    main()
