import os
import sys
from pprint import pprint

from bin.db import get_connection, load_day, load_foods
from bin.food_obj import Food
from bin.recipe_obj import Recipe

fname = sys.argv[1]

conn = get_connection()
FOOD = dict()
for name, data in load_foods(conn).items():
    FOOD[name] = Food(data)

date = os.path.basename(fname).removesuffix(".json")
meals = load_day(conn, date)
if not meals:
    sys.exit(f"No diary entries found for date '{date}' in the database.")

def process_recipes(recipes):
    running = dict(protein=0, fat=0, carbs=0, calories=0, sodium=0, fiber=0, sugar=0, added_sugars=0, cholesterol = 0)
    for recipe in recipes:
        if recipe.prop_food:
            for key in recipe.prop_food:
                running[key] += recipe.prop_food[key]
    pprint(running)
    return running

if __name__ == '__main__':
    recipes_eaten = list()
    for meal in meals:
        if "uneaten" not in meal["name"].lower():
            print("--- %s" % meal["name"])
            for meal_item in meal["foods"]:
                weight = meal_item["weight"]
                food_name = meal_item["food"]
                if weight > 0:
                    if food_name not in FOOD:
                        print(f"Warning: Nutritional data for '{food_name}' not found.")
                        continue
                    food = FOOD[food_name]
                    pprint(meal_item)
                    recipe = Recipe()
                    recipe.add_food(weight, food)
                    recipes_eaten.append(recipe)
                    print(recipe)
                    print()
    print("--- Macros for eaten so far ---")
    process_recipes(recipes_eaten)
