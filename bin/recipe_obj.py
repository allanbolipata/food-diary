from bin.food_obj import Food
from bin.helpers import calc_food

class Recipe:
    def __init__(self):
        self.foods = list()

    def add_food(self, weight, food):
        self.foods.append([weight, food])
        self._calc_total()

    def _calc_total(self):
        self.prop_food = dict(protein=0, fat=0, calories=0, carbs = 0, sodium = 0)
        for food_data in self.foods:
            weight = food_data[0]
            food = food_data[1]
            prop_food = calc_food(weight, food)
            for key in prop_food:
                self.prop_food[key] += prop_food[key]

    def __str__(self):
        return str(self.prop_food)
