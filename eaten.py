import json
import sys

from bin.food_obj import Food
from bin.recipe_obj import Recipe

fname = sys.argv[1]

DB = json.load(open("data/food.json", "r"))
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
            current_recipe.add_food(weight, FOOD[food_name])
        recipes.append(current_recipe)
    return recipes


def process_recipe(recipe):
    macros = dict(protein=0, fat=0, carbs=0, calories=0, sodium=0)   
    for key in recipe.prop_food:
        macros[key] = recipe.prop_food[key]
    print(macros)

if __name__ == '__main__':
    with open(fname, "r") as f:
        data = json.load(f)
        for meals in data:
            if "uneaten" not in meals["name"].lower():
                for meal_item in meals["foods"]:
                    weight = meal_item["weight"]
                    food = FOOD[meal_item["food"]]
                    if weight > 0:
                        print("---")
                        print(meal_item)
                        recipe = Recipe()
                        recipe.add_food(weight,food)
                        print(recipe)
                        print()
