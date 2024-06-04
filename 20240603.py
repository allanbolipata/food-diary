import json

from bin.food_obj import Food
from bin.helpers import calc_food

data = json.load(open("data/food.json", "r")) 

# load food "database" json
food = dict()
for i in data:
    food[i["name"]] = Food(i)

# what I ate today in grams/ml
eaten = dict()

# Ate for breakfast and dinner
eaten["Honey Nut Cheerios"] = 68 * 2
eaten["Planet Oat Oatmilk Original"] = 153.4 * 2

eaten["Lean Cuisine: Chicken Parmesan"] = 308

# Greek Yogurt Parfait
eaten["Chobani Greek Yogurt Nonfat Plain"] = 113.333
eaten["Bob's Red Mill Gluten Free Honey Oat Granola"] = 25
eaten["Dole Mixed Berries"] = 35

# Note - was missing four slices of bread, peanut butter and jelly

running = dict(prot=0, fat=0, carbs=0, calories=0, sodium=0)
for k in eaten:
    prop_food = calc_food(eaten[k], food[k])
    running["prot"] += prop_food["protein"]
    running["fat"] += prop_food["fat"]
    running["carbs"] += prop_food["carbs"]
    running["calories"] += prop_food["calories"]

print(running)
