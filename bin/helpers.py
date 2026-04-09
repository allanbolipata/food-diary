from bin.food_obj import Food

def calc_food(weight, food_base):
    prop_protein = weight * food_base.prop_protein
    prop_fat = weight * food_base.prop_fat
    prop_carbs = weight * food_base.prop_carbs
    prop_sodium = weight * food_base.prop_sodium 
    calories = weight * ( food_base.calories / food_base.serving_size )
    prop_fiber = weight * food_base.prop_fiber
    prop_sugar = weight * food_base.prop_sugar
    prop_added_sugars = weight * food_base.prop_added_sugars
    prop_cholesterol = weight * food_base.prop_cholesterol
    return {"protein": prop_protein, "fat": prop_fat,
            "carbs": prop_carbs, "sodium": prop_sodium, "fiber": prop_fiber, "sugar": prop_sugar, "added_sugars": prop_added_sugars,
            "cholesterol": prop_cholesterol,
            "calories": calories }
