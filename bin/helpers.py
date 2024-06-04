from bin.food_obj import Food

def calc_food(weight, food_base):
    prop_protein = weight * food_base.prop_protein
    prop_fat = weight * food_base.prop_fat
    prop_carbs = weight * food_base.prop_carbs
    prop_sodium = weight * food_base.prop_sodium
    calories = weight * ( food_base.calories / food_base.serving_size )
    return {"protein": prop_protein, "fat": prop_fat,
            "carbs": prop_carbs, "sodium": prop_sodium,
            "calories": calories }
