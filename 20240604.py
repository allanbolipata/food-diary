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


eaten["Honey Nut Cheerios"] = 0
eaten["Planet Oat Oatmilk Original"] = 0

eaten["Lean Cuisine: Chicken Parmesan"] = 0

# Greek Yogurt Parfait
eaten["Chobani Greek Yogurt Nonfat Plain"] = 0
eaten["Bob's Red Mill Gluten Free Honey Oat Granola"] = 0
eaten["Dole Mixed Berries"] = 0

# 
eaten["Nature's Own 100% Whole Wheat Bread"] = 110.6
eaten["Smucker's Seedless Strawberry Jam"] = 45.9
eaten["Wegmans Creamy Reduced Fat Peanut Spread"] = 31.4


running = dict(prot=0, fat=0, carbs=0, calories=0, sodium=0)
for k in eaten:
    prop_food = calc_food(eaten[k], food[k])
    running["prot"] += prop_food["protein"]
    running["fat"] += prop_food["fat"]
    running["carbs"] += prop_food["carbs"]
    running["calories"] += prop_food["calories"]

print(running)
