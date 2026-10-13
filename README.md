# Food Diary

A small personal food-tracking project. Everything — the food catalog and the
diary — lives in one SQLite database: **`data/food_diary.db`**. The old
`data/food.json` and `data/diary/YYYYMMDD.json` files are gone; the database
is the single source of truth. Use `log.py export` to produce JSON of any day
(if you ever want a file copy).

## Files

- **`app.py YYYYMMDD`** — prints the total macros for a diary day, rounded to
  one decimal. A legacy `data/diary/YYYYMMDD.json` path is also accepted
  (the date is taken from the filename; the file itself is not read). Foods
  not in the catalog are skipped with a warning.
- **`eaten.py [YYYYMMDD]`** — prints per-meal detail plus day totals.
  Mealtimes whose name contains "uneaten" are skipped (e.g. "Uneaten
  Lunch").
- **`trend.py`** — plots daily calorie/protein trends from the database.
  `--from` / `--to` limit the range, `--save FILE.png` writes a headless PNG.
- **`log.py`** — the maintenance CLI (below).
- **`bin/`** — Python helpers: `db.py` (the SQLite layer), `food_obj.py`,
  `recipe_obj.py`, `helpers.py`.
- **`data/food_diary.db`** — the database:
  - `foods` — the catalog. Nutritional values are flattened into columns for
    SQL aggregation, and the original JSON document is kept in `raw_json`, so
    the data is lossless. Rows without `raw_json` are "stub" entries (name
    only, no nutrition data).
  - `meals` — one row per meal per day.
  - `meal_items` — one row per food entry in a meal (`weight` is in grams).
- **`scripts/check_calories.py`** / **`scripts/check_diary_calories.py`** —
  verify that stored calories match the macros (4/4/9 cal per gram, plus
  2.5 for sugar alcohols). Default tolerance 40 cal; alcohol-containing
  drinks are expected to deviate.

## Using log.py

From the repo root:

```bash
# Record / fix a day (weights are in the catalog's `serving_size` units:
# grams for foods measured by weight, one unit for whole-portion entries;
# default meal is "Miscellaneous"; default date is today)
python log.py add "Oikos Triple Zero Strawberry Greek Yogurt" 150 --meal Breakfast
python log.py set-weight "Oikos ..." --weight 200 --was 150
python log.py remove "Oikos ..." --weight 150
python log.py move "Oikos ..." --to Lunch
python log.py remove-meal Lunch
python log.py clear --date 20261012 --yes

# When a food appears more than once in a meal, commands that could match
# several rows refuse and list the matches; pass --weight N to pick one,
# or --all to take every.

# Show / export
python log.py day 20261012
python log.py export --date 20261012            # prints JSON to stdout
python log.py export --all --out /tmp/diary_export   # one <date>.json per day

# Catalog maintenance
python log.py food-add --name "New Food" --data '{"name": "New Food", "serving_size": 100, "nutritional_data": {"calories": 100, "protein": 10, "fat": {"total": 2}, "carbs": {"total": 5}}}'
python log.py food-update --name "New Food" --data '...'
python log.py food-remove "New Food"     # refuses if the food is used in the diary
python log.py food-search yogurt
```

`python log.py import FILE` is a one-shot reconciliation tool for legacy diary
JSON files: it imports items the file lists that are missing from the
database and removes items the database has that are no longer in the file,
per meal name. Foods in the file but not in the catalog become stub rows.
It never writes the file.

## Notes

- Conventions: a diary item's `weight` is in the catalog's `serving_size`
  units — grams for foods measured by weight, one unit for whole-portion
  entries (`serving_size` 1, e.g. a full restaurant plate). A catalog entry
  has `serving_size` (grams or units per serving) and `calories` (per
  serving); macros scale as `weight / serving_size * per-serving value`.
- Meals whose name contains "uneaten" are skipped by `eaten.py` but counted
  by `app.py` and `trend.py` (they contribute zero anyway, since their items
  have weight 0).
- `bin/db.py` exposes the database helpers (`daily_totals`, `load_day`,
  `day_items`, `load_foods`, `add_meal_item`, `item_weights`,
  `set_item_weight`, `remove_item`, `remove_meal`, `clear_day`,
  `day_json_text`, `export_day_json`, `catalog_entries`,
  `add_food_entry`, `update_food_entry`, `remove_food`, `get_connection`).
- The catalog contains two Factor_ items with the same base name: "Factor
  Mushroom Mozzarella Melt Burger" (371 g) and "Factor Mushroom Mozzarella
  Melt Burger (340 g)" — they are distinct products, so the names must not be
  de-duplicated.
- `requirements.txt` lists the only third-party dependency: `matplotlib`
  (needed by `trend.py`).
