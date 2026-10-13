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
- **`trend.py`** — plots daily macro trends from the database (run with the
  project venv: `.venv/bin/python trend.py`). `--from` / `--to` limit the
  range, `--save DIR` writes headless PNGs (`macros.png`, `calories.png`);
  each chart includes a 7-day rolling average.
- **`log.py`** — the maintenance CLI (below).
- **`bin/`** — Python helpers: `db.py` (the SQLite layer), `food_obj.py`,
  `recipe_obj.py`, `helpers.py`.
- **`tests/`** — unit tests for the database layer; run from the repo root
  with `python -m unittest discover` (no third-party dependencies).
- **`web/`** — the dashboard: `app.py` (FastAPI backend over `bin.db`),
  `static/` (vanilla HTML/CSS/JS frontend), `requirements.txt`
  (fastapi + uvicorn). See "Web dashboard" below.
- **`Dockerfile`** / **`compose.yaml`** — container build and podman compose
  deployment for the dashboard.
- **`data/food_diary.db`** — the database:
  - `foods` — the catalog. Nutritional values are flattened into columns for
    SQL aggregation, and the original JSON document is kept in `raw_json`, so
    the data is lossless. Rows without `raw_json` are "stub" entries (name
    only, no nutrition data).
  - `meals` — one row per meal per day.
  - `meal_items` — one row per food entry in a meal (`weight` is in the
    food's `serving_size` units).
- **`data/backups/`** — online backups made by `log.py backup` (git-ignored).
- **`scripts/check_calories.py`** / **`scripts/check_diary_calories.py`** —
  verify that stored calories match the macros (4/4/9 cal per gram, plus
  2.5 for sugar alcohols). Default tolerance 40 cal; alcohol-containing
  drinks are expected to deviate.

## Using log.py

From the repo root:

```bash
# Record / fix a day (weights are in the catalog's `serving_size` units:
# grams for foods measured by weight, one unit for whole-portion entries;
# omit the weight to log one serving; default meal is "Miscellaneous";
# default date is today)
python log.py add "Oikos Triple Zero Strawberry Greek Yogurt" 150 --meal Breakfast
python log.py meal "Korean BBQ" "Bulgogi 80" "White Rice 180" "Blue Ribbon Orange Popsicle"
python log.py set-weight "Oikos ..." --weight 200 --was 150
python log.py remove "Oikos ..." --weight 150
python log.py move "Oikos ..." --to Lunch
python log.py rename-meal "Makeshift Sanwich" "Makeshift Sandwich"   # all days
python log.py rename-meal Lunch Dinner --date 20261012               # one day
python log.py remove-meal Lunch
python log.py clear --date 20261012 --yes

# When a food appears more than once in a meal, commands that could match
# several rows refuse and list the matches; pass --weight N to pick one,
# or --all to take every.

# Show / export / backup
python log.py day 20261012
python log.py week 20261006                    # 7-day window + weekly totals
python log.py export --date 20261012           # prints JSON to stdout
python log.py export --all --out /tmp/diary_export   # one <date>.json per day
python log.py backup [--keep 20]               # data/backups/food_diary-<ts>.db

# Catalog maintenance (a full entry shape is data/template_food.json;
# entries missing serving_size, calories, protein, fat, carbs, fiber or
# sodium are rejected)
python log.py food-add --name "New Food" --data @data/template_food.json
python log.py food-update --name "New Food" --data @data/template_food.json
python log.py food-remove "New Food"     # refuses if the food is used in the diary
python log.py food-search yogurt
```

`python log.py import FILE` is a one-shot reconciliation tool for legacy diary
JSON files: it imports items the file lists that are missing from the
database and removes items the database has that are no longer in the file,
per meal name. Foods in the file but not in the catalog become stub rows.
It never writes the file.

## Web dashboard

A small single-user web UI for browsing and adding catalog foods. It reads
and writes the same `data/food_diary.db` as the CLI tools, so the two never
disagree. No authentication — it is a single-user, local service.

Features:
- table of all catalog entries (name, serving size, calories, protein, fat,
  carbs, fiber, sugar, sodium) with sortable columns
- live search (client-side instant + debounced server-side `q=` filter)
- "Add food" modal — validates required fields and rejects duplicates
  (409), mirroring the `log.py food-add` rules
- header stats: catalog size and days logged

Run locally (project venv):

```bash
.venv/bin/pip install -r web/requirements.txt
.venv/bin/uvicorn web.app:app --port 8877    # then open http://localhost:8877
```

Deploy with podman compose (builds the image, runs the container with
`./data` mounted, port 8877):

```bash
podman compose up -d --build
podman compose logs -f food-dashboard   # follow logs
podman compose down                     # stop
```

The container and the host CLI share the live database through the `./data`
volume; avoid running both at once against it (single-user use, no
concurrency handling). To bind only to the Tailscale interface, change the
port mapping in `compose.yaml` to `100.127.136.124:8877:8000`.

## Notes

- Conventions: a diary item's `weight` is in the catalog's `serving_size`
  units — grams for foods measured by weight, one unit for whole-portion
  entries (`serving_size` 1, e.g. a full restaurant plate). A catalog entry
  has `serving_size` (grams or units per serving) and `calories` (per
  serving); macros scale as `weight / serving_size * per-serving value`.
- Meals whose name contains "uneaten" are skipped by `eaten.py` but counted
  by `app.py` and `trend.py` (they contribute zero anyway, since their items
  have weight 0).
- Zero-weight items are how a regular meal is logged on a day you don't eat
  it (e.g. "Meal Prep Rice" at 0 g); item counts therefore overstate intake,
  so filter on `weight > 0` when analysing frequency.
- `bin/db.py` exposes the database helpers (`daily_totals`, `load_day`,
  `day_items`, `load_foods`, `add_meal_item`, `item_weights`,
  `set_item_weight`, `remove_item`, `remove_meal`, `rename_meal`,
  `clear_day`, `day_json_text`, `export_day_json`, `catalog_entries`,
  `add_food_entry`, `update_food_entry`, `remove_food`, `backup_db`,
  `get_connection`).
- The catalog contains two Factor_ items with the same base name: "Factor
  Mushroom Mozzarella Melt Burger" (371 g) and "Factor Mushroom Mozzarella
  Melt Burger (340 g)" — they are distinct products, so the names must not be
  de-duplicated.
- Dependencies: `requirements.txt` lists `matplotlib` (needed by
  `trend.py`); `web/requirements.txt` lists `fastapi` and `uvicorn`
  (needed by the dashboard). Both live in the project venv (`.venv`).
- `data/food_diary.db` is git-ignored: it stays on disk as the single source
  of truth but is never committed or pushed. Restore points come from
  `log.py backup` (see next).
- Backups: `log.py backup` writes an online copy to `data/backups/`
  (git-ignored).
