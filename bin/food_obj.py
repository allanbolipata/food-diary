class Food:
    def __init__(self, data):
        self.data = data
        self._load_data(data)
        self._calc_prop()

    def _load_data(self, data):
        self.name = data["name"]
        self.serving_size = data["serving_size"]
        self.nutr_data = data["nutritional_data"]
        self.calories = self.nutr_data["calories"]
        self.protein = self.nutr_data["protein"]
        self.fat = self.nutr_data["fat"]
        self.fat_total = self.fat["total"]
        self.carbs = self.nutr_data["carbs"] 
        self.fiber = self.carbs["dietary_fiber"]["total"]
        self.carbs_total = self.carbs["total"]
        self.sugar = self.carbs.get("sugars", {}).get("total", 0)
        self.added_sugars= self.carbs.get("sugars", {}).get("added_sugars", {}).get("total", 0)
        self.sugar_alcohols = self.carbs.get("sugars", {}).get("sugar_alcohols", {}).get("total", 0)
        self.carbs_net = self.carbs_total - self.sugar_alcohols
        self.sodium = self.nutr_data["sodium"]
        self.sodium_total = self.sodium["total"]
        self.cholesterol = self.nutr_data.get("cholesterol", {}).get("total", 0)

    def _calc_prop(self):
        self.prop_protein = float(self.protein / self.serving_size)
        self.prop_fat = float(self.fat_total / self.serving_size)
        self.prop_carbs = float(self.carbs_total / self.serving_size)
        self.prop_sodium = float(self.sodium_total / self.serving_size)
        self.prop_fiber = float(self.fiber / self.serving_size)
        self.prop_sugar = float(self.sugar / self.serving_size)
        self.prop_added_sugars = float(self.added_sugars / self.serving_size)
        self.prop_cholesterol =float(self.cholesterol / self.serving_size)


    def __str__(self):
        return str(self.data)
