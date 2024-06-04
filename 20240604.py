import json
from pprint import pprint

from bin.food_obj import Food
from bin.recipe_obj import Recipe
from bin.helpers import calc_food

data = json.load(open("data/food.json", "r")) 

# load food "database" json
food = dict()
for i in data:
    food[i["name"]] = Food(i)

# what I ate today in grams/ml
eaten = dict()

# 
eaten["Nature's Own 100% Whole Wheat Bread"] = 110.6
eaten["Smucker's Seedless Strawberry Jam"] = 45.9
eaten["Wegmans Creamy Reduced Fat Peanut Spread"] = 31.4

# ----- HAVEN'T EATEN THESE YET

recipes = list()
# my slop
slop_recipe = Recipe()
slop_recipe.add_food(60, food["Naked PB"])
slop_recipe.add_food(7, food["Sugar Cube"])
slop_recipe.add_food(70, food["Quaker Oats Organic: Quick 1-Minute"])
recipes.append(slop_recipe)

# protein shake
eaten["Naked PB"] = 60 

# Greek Yogurt Parfait
greek_yogurt_parfait = Recipe()
greek_yogurt_parfait.add_food(113.333,food["Chobani Greek Yogurt Nonfat Plain"])
greek_yogurt_parfait.add_food(25,food["Bob's Red Mill Gluten Free Honey Oat Granola"])
greek_yogurt_parfait.add_food(35,food["Dole Mixed Berries"])
recipes.append(greek_yogurt_parfait)

eaten["Lean Cuisine: Vermont White Cheddar Mac & Cheese"] = 226
eaten["Lean Cuisine: Alfredo Pasta with Chicken & Broccoli"] = 283

# ------

running = dict(protein=0, fat=0, carbs=0, calories=0, sodium=0)
for k in eaten:
    prop_food = calc_food(eaten[k], food[k])
    running["protein"] += prop_food["protein"]
    running["fat"] += prop_food["fat"]
    running["carbs"] += prop_food["carbs"]
    running["calories"] += prop_food["calories"]
    running["sodium"] += prop_food["sodium"]

for recipe in recipes:
    for key in recipe.prop_food:
        running[key] += recipe.prop_food[key]

pprint(running)
