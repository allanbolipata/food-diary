from bin.db import daily_totals, get_connection

conn = get_connection()
daily_nutrition, missing = daily_totals(conn)

# Foods referenced in the diary but lacking nutritional data.
for name, count in missing:
    for _ in range(count):
        print(f"Warning: Nutritional data for '{name}' not found.")

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
