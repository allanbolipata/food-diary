#!/usr/bin/env python3
"""Plot daily macro trends from data/food_diary.db.

Usage (from the repo root):
    python trend.py [--from YYYYMMDD] [--to YYYYMMDD] [--save DIR]

Without --save the charts are shown with matplotlib; with --save they are
written as PNG files into DIR (useful on machines without a display).
Totals include uneaten meals (same semantics as daily_totals). Each chart
also shows a dashed 7-day rolling average taken over the last seven
*logged* days, so gap days are not treated as zero.
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt

from bin.db import daily_totals, get_connection


def moving_avg(values: list, window: int = 7) -> list:
    """Trailing moving average; early points average over what exists."""
    return [
        sum(values[max(0, i - window + 1):i + 1]) / min(i + 1, window)
        for i in range(len(values))
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot daily macro trends from data/food_diary.db.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--from", dest="date_from", default=None,
                        help="first date YYYYMMDD (default: all days)")
    parser.add_argument("--to", dest="date_to", default=None,
                        help="last date YYYYMMDD (default: all days)")
    parser.add_argument("--save", metavar="DIR", default=None,
                        help="save PNGs to DIR instead of showing them")
    args = parser.parse_args()

    conn = get_connection()
    try:
        daily_nutrition, missing = daily_totals(conn)
    finally:
        conn.close()

    for name, count in missing:
        print(f"Warning: Nutritional data for '{name}' not found (x{count}).")

    if args.date_from or args.date_to:
        daily_nutrition = {
            d: t for d, t in daily_nutrition.items()
            if (not args.date_from or d >= args.date_from)
            and (not args.date_to or d <= args.date_to)
        }

    if not daily_nutrition:
        print("No days to plot.")
        return

    print("Date-wise Nutritional Totals:")
    for date, totals in sorted(daily_nutrition.items()):
        print(f"{date}: Protein: {totals['protein']:.2f}g, Fat: {totals['fat']:.2f}g, "
              f"Carbs: {totals['carbs']:.2f}g, Calories: {totals['calories']:.2f} kcal")

    sorted_dates = sorted(daily_nutrition.keys())
    protein = [daily_nutrition[d]["protein"] for d in sorted_dates]
    fat = [daily_nutrition[d]["fat"] for d in sorted_dates]
    carbs = [daily_nutrition[d]["carbs"] for d in sorted_dates]
    calories = [daily_nutrition[d]["calories"] for d in sorted_dates]

    fig1, ax1 = plt.subplots(figsize=(10, 6))
    ax1.plot(sorted_dates, protein, label="Protein (g)", marker="o", color="blue")
    ax1.plot(sorted_dates, fat, label="Fat (g)", marker="o", color="red")
    ax1.plot(sorted_dates, carbs, label="Carbs (g)", marker="o", color="green")
    for values, color, label in (
        (moving_avg(protein), "blue", "Protein 7-day avg"),
        (moving_avg(fat), "red", "Fat 7-day avg"),
        (moving_avg(carbs), "green", "Carbs 7-day avg"),
    ):
        ax1.plot(sorted_dates, values, label=label, linestyle="--",
                 alpha=0.7, color=color)
    ax1.set_title("Daily Nutritional Trends: Protein, Fat, and Carbs", fontsize=16)
    ax1.set_xlabel("Date (YYYYMMDD)", fontsize=14)
    ax1.set_ylabel("Grams", fontsize=14)
    ax1.set_xticks(sorted_dates)
    ax1.tick_params(axis="x", rotation=45)
    ax1.legend()
    ax1.grid(visible=True, linestyle="--", alpha=0.6)
    fig1.tight_layout()

    fig2, ax2 = plt.subplots(figsize=(10, 6))
    ax2.plot(sorted_dates, calories, label="Calories", marker="o", color="orange")
    ax2.plot(sorted_dates, moving_avg(calories), label="Calories 7-day avg",
             linestyle="--", alpha=0.7, color="orange")
    ax2.set_title("Daily Calorie Trends", fontsize=16)
    ax2.set_xlabel("Date (YYYYMMDD)", fontsize=14)
    ax2.set_ylabel("Calories", fontsize=14)
    ax2.set_xticks(sorted_dates)
    ax2.tick_params(axis="x", rotation=45)
    ax2.legend()
    ax2.grid(visible=True, linestyle="--", alpha=0.6)
    fig2.tight_layout()

    if args.save:
        out = Path(args.save)
        out.mkdir(parents=True, exist_ok=True)
        p1, p2 = out / "macros.png", out / "calories.png"
        fig1.savefig(p1)
        fig2.savefig(p2)
        print(f"Saved {p1} and {p2}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
