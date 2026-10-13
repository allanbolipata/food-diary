import json
import sys
from pathlib import Path
from pprint import pprint

from bin.food_obj import Food
from bin.recipe_obj import Recipe

REPO_ROOT = Path(__file__).resolve().parent

DB = json.load(open(REPO_ROOT / "data" / "food.json", "r"))
FOOD = dict()
for i in DB:
    FOOD[i["name"]] = Food(i)

def load_recipes(data):
    recipes = list()
    for i in data:
        current_recipe = Recipe()
        for j in i["foods"]:
            food_name = j["food"]
            weight = j["weight"]
            if food_name not in FOOD:
                print(f"Warning: Nutritional data for '{food_name}' not found.")
                continue
            current_recipe.add_food(weight, FOOD[food_name])
        recipes.append(current_recipe)
    return recipes

def process_recipes(recipes):
    running = dict(protein=0, fat=0, carbs=0, calories=0, sodium=0, fiber=0, sugar=0, added_sugars=0, cholesterol=0)
    for recipe in recipes:
        if recipe.prop_food:
            for key in recipe.prop_food:
                running[key] += recipe.prop_food[key]
    pprint({k: round(v, 1) for k, v in running.items()})
    return running

if __name__ == '__main__':
    fname = sys.argv[1]
    data_recipe = json.load(open(fname, 'r'))

    recipes = load_recipes(data_recipe)

    process_recipes(recipes)
