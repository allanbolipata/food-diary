import json
from collections import defaultdict

# Load nutritional data (food.json)
with open("data/food.json", "r") as food_file:
    food_data = json.load(food_file)

# Create a dictionary for quick lookup of nutritional values
nutrition_lookup = {item['name']: item for item in food_data}

# Function to calculate daily nutritional totals
def calculate_daily_totals(data):
    daily_totals = defaultdict(lambda: {"protein": 0, "fat": 0, "carbs": 0, "calories": 0})
    
    for entry in data:
        date = entry["date"]
        for meal in entry["meals"]:
            for food_item in meal["foods"]:
                food_name = food_item["food"]
                weight = food_item["weight"]
                
                # Skip foods with zero weight
                if weight == 0:
                    continue
                
                # Look up the nutritional values for the food
                if food_name in nutrition_lookup:
                    nutrition = nutrition_lookup[food_name]
                    daily_totals[date]["protein"] += ( nutrition["nutritional_data"]["protein"] / nutrition["serving_size"]) * weight
                    daily_totals[date]["fat"] += ( nutrition["nutritional_data"]["fat"]["total"] / nutrition["serving_size"]) * weight
                    daily_totals[date]["carbs"] += ( nutrition["nutritional_data"]["carbs"]["total"] / nutrition["serving_size"]) * weight
                    daily_totals[date]["calories"] += ( nutrition["nutritional_data"]["calories"] / nutrition["serving_size"]) * weight
                else:
                    print(f"Warning: Nutritional data for '{food_name}' not found.")

    return daily_totals

# Load meal data (combined JSON chunks)
with open("data/meals.json", "r") as meals_file:
    meals_data = json.load(meals_file)

# Calculate daily totals
daily_nutrition = calculate_daily_totals(meals_data)

# Display the results
print("Date-wise Nutritional Totals:")
for date, totals in sorted(daily_nutrition.items()):
    print(f"{date}: Protein: {totals['protein']:.2f}g, Fat: {totals['fat']:.2f}g, Carbs: {totals['carbs']:.2f}g, Calories: {totals['calories']:.2f} kcal")

import matplotlib.pyplot as plt

# Sort dates for proper chronological order
sorted_dates = sorted(daily_nutrition.keys())
protein = [daily_nutrition[date]["protein"] for date in sorted_dates]
fat = [daily_nutrition[date]["fat"] for date in sorted_dates]
carbs = [daily_nutrition[date]["carbs"] for date in sorted_dates]
calories = [daily_nutrition[date]["calories"] for date in sorted_dates]

# Plot protein, fat, and carbs
plt.figure(figsize=(10, 6))
plt.plot(sorted_dates, protein, label="Protein (g)", marker="o", color="blue")
plt.plot(sorted_dates, fat, label="Fat (g)", marker="o", color="red")
plt.plot(sorted_dates, carbs, label="Carbs (g)", marker="o", color="green")

# Customize the first plot
plt.title("Daily Nutritional Trends: Protein, Fat, and Carbs", fontsize=16)
plt.xlabel("Date (YYYYMMDD)", fontsize=14)
plt.ylabel("Grams", fontsize=14)
plt.xticks(rotation=45)
plt.legend()
plt.grid(visible=True, linestyle="--", alpha=0.6)
plt.tight_layout()

# Display the first graph
plt.show()

# Plot calories separately
plt.figure(figsize=(10, 6))
plt.plot(sorted_dates, calories, label="Calories", marker="o", color="orange")

# Customize the second plot
plt.title("Daily Calorie Trends", fontsize=16)
plt.xlabel("Date (YYYYMMDD)", fontsize=14)
plt.ylabel("Calories", fontsize=14)
plt.xticks(rotation=45)
plt.legend()
plt.grid(visible=True, linestyle="--", alpha=0.6)
plt.tight_layout()

# Display the second graph
plt.show()
