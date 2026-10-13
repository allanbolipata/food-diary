"""Print the food entries and totals for one diary day.

Usage:
    python app.py 20261012
    python app.py data/diary/20261012.json   # legacy path; the date is taken
                                              # from the filename, and the
                                              # file content is ignored

Both forms read the catalog and the diary from data/food_diary.db, the
single source of truth for the project.
"""

import re
import sys
from pathlib import Path

from bin.db import get_connection, load_day, load_foods
from bin.food_obj import Food
from bin.recipe_obj import Recipe

REPO_ROOT = Path(__file__).resolve().parent


def resolve_day(arg: str) -> str:
    """Accept a bare date (YYYYMMDD) or a legacy diary path whose name
    ends in <date>.json. Returns the date string, or exits with an error."""
    if re.fullmatch(r"\d{8}", arg):
        return arg
    if Path(arg).suffix == ".json":
        stem = Path(arg).stem
        if re.fullmatch(r"\d{8}", stem):
            return stem
    print(f"Error: could not find a diary date in {arg!r} "
          "(expected YYYYMMDD or a path like data/diary/YYYYMMDD.json).")
    sys.exit(1)


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    day = resolve_day(sys.argv[1])
    conn = get_connection()
    meals = load_day(conn, day)
    foods = {name: food for name, food in load_foods(conn).items()}
    conn.close()

    recipes = []
    for meal in meals:
        recipe = Recipe()
        for item in meal["foods"]:
            food_name = item["food"]
            weight = item["weight"]
            if food_name not in foods:
                print(f"Warning: Nutritional data for '{food_name}' not found.")
                continue
            recipe.add_food(weight, Food(foods[food_name]))
        recipes.append(recipe)

    running = dict(protein=0, fat=0, carbs=0, calories=0, sodium=0, fiber=0,
                   sugar=0, added_sugars=0, cholesterol=0)
    for recipe in recipes:
        if recipe.prop_food:
            for key in recipe.prop_food:
                running[key] += recipe.prop_food[key]

    for key, value in running.items():
        print(f"{key}: {round(value, 1)}")


if __name__ == "__main__":
    main()
