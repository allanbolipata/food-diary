import json
import sys

fname = sys.argv[1]

with open(fname, "r") as f:
    data = json.load(f)
    for meals in data:
        for meal_item in meals["foods"]:
            weight = meal_item["weight"]
            if weight > 0:
                print(meal_item)
