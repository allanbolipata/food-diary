import sys
import json
from pprint import pprint

from bin.food_obj import Food
from bin.recipe_obj import Recipe
from bin.helpers import calc_food

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

if __name__ == '__main__':
    running = dict(protein=0, fat=0, carbs=0, calories=0, sodium=0)
    fname = sys.argv[1]
    data_recipe = json.load(open(fname, 'r'))

    recipes = load_recipes(data_recipe)
   
    for recipe in recipes:
        if recipe.prop_food:
            for key in recipe.prop_food:
                running[key] += recipe.prop_food[key]
    
    pprint(running)
