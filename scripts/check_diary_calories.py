#!/usr/bin/env python3
"""
scripts/check_diary_calories.py

Checks calorie consistency only for foods listed in a diary file.
Usage:
    python scripts/check_diary_calories.py path/to/diary.json [--tolerance 40]
"""

import argparse
import json
import sys
from pathlib import Path

from check_calories import calc_label_calories


def load_diary(diary_path: Path) -> set:
    """Return a set of food names that appear in the diary."""
    with open(diary_path, "r", encoding="utf-8") as f:
        diary = json.load(f)
    names = set()
    for entry in diary:
        for item in entry.get("foods", []):
            names.add(item["food"])
    return names


def main():
    parser = argparse.ArgumentParser(
        description="Check calorie consistency for foods listed in a diary JSON."
    )
    parser.add_argument("diary_path",
                        help="Path to the diary JSON file (e.g., data/diary/20260207.json)")
    parser.add_argument("--tolerance", type=float, default=40.0,
                        help="Maximum allowed difference in calories")
    args = parser.parse_args()

    diary_file = Path(args.diary_path).expanduser().resolve()
    if not diary_file.is_file():
        print(f"File not found: {diary_file}")
        sys.exit(1)

    repo_root = Path(__file__).resolve().parents[1]
    with open(repo_root / "data" / "food.json", "r", encoding="utf-8") as f:
        foods = {food["name"]: food.get("nutritional_data", {}) for food in json.load(f)}

    names = load_diary(diary_file)
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
