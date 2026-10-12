"""SQLite storage layer for the food diary.

The database lives at data/food_diary.db and holds:

  foods       the food catalog (formerly data/food.json). Nutritional
              values are flattened into columns for SQL aggregation, and
              the original JSON document is kept in ``raw_json`` so the
              data is lossless.
  meals       one row per meal per diary day (formerly one
              data/diary/YYYYMMDD.json file per day).
  meal_items  one row per food entry within a meal.

The loaders reconstruct the legacy JSON shapes, so the existing
bin.Food / bin.Recipe objects keep working unchanged.
"""

import json
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "food_diary.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS foods (
    id                    INTEGER PRIMARY KEY,
    name                  TEXT NOT NULL UNIQUE,
    serving_size          REAL,
    calories              REAL,
    protein               REAL,
    fat_total             REAL,
    fat_saturated         REAL,
    sodium                REAL,
    carbs_total           REAL,
    fiber_total           REAL,
    sugars_total          REAL,
    added_sugars_total    REAL,
    sugar_alcohols_total  REAL,
    cholesterol           REAL,
    raw_json              TEXT
);

CREATE TABLE IF NOT EXISTS meals (
    id          INTEGER PRIMARY KEY,
    date        TEXT NOT NULL,
    name        TEXT NOT NULL,
    sort_order  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_meals_date ON meals(date);

CREATE TABLE IF NOT EXISTS meal_items (
    id        INTEGER PRIMARY KEY,
    meal_id   INTEGER NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
    food_id   INTEGER NOT NULL REFERENCES foods(id),
    weight    REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_meal_items_meal ON meal_items(meal_id);
CREATE INDEX IF NOT EXISTS idx_meal_items_food ON meal_items(food_id);
"""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Open (and create if needed) the diary database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables and indexes if they do not exist yet."""
    conn.executescript(SCHEMA)
    conn.commit()


def load_foods(conn: sqlite3.Connection) -> dict:
    """Return ``{food_name: food_dict}`` in the original food.json shape,
    i.e. each value is a dict that can be passed straight to ``bin.Food``.

    Foods referenced in the diary but never added to the catalog
    (``raw_json`` is NULL) are omitted, matching the old behaviour of
    looking them up in a dict built from food.json.
    """
    return {
        row["name"]: json.loads(row["raw_json"])
        for row in conn.execute("SELECT name, raw_json FROM foods WHERE raw_json IS NOT NULL")
    }


def load_day(conn: sqlite3.Connection, date: str) -> list:
    """Return the meals for one day in the original diary JSON shape:
    ``[{"name": ..., "foods": [{"food": ..., "weight": ...}]}, ...]``.

    Meals come back in the order they were recorded; a day that is not in
    the database yields an empty list.
    """
    rows = conn.execute(
        """
        SELECT m.id AS meal_id, m.name AS meal_name,
               f.name AS food_name, i.weight
        FROM meals m
        LEFT JOIN meal_items i ON i.meal_id = m.id
        LEFT JOIN foods f ON f.id = i.food_id
        WHERE m.date = ?
        ORDER BY m.sort_order, i.rowid
        """,
        (date,),
    ).fetchall()

    meals = []
    for row in rows:
        if not meals or meals[-1]["_id"] != row["meal_id"]:
            meals.append({"_id": row["meal_id"], "name": row["meal_name"], "foods": []})
        if row["food_name"] is not None:
            # Weights are stored as REAL; restore int display for whole
            # values so output matches the original JSON files.
            weight = row["weight"]
            weight = int(weight) if float(weight).is_integer() else weight
            meals[-1]["foods"].append({"food": row["food_name"], "weight": weight})
    for meal in meals:
        del meal["_id"]
    return meals


def ensure_meal(conn: sqlite3.Connection, date: str, name: str) -> int:
    """Return the id of the named meal for ``date``, creating it if needed
    (with the next free sort_order)."""
    row = conn.execute("SELECT id FROM meals WHERE date = ? AND name = ?", (date, name)).fetchone()
    if row:
        return row["id"]
    nxt = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM meals WHERE date = ?", (date,)
    ).fetchone()[0]
    new_id = conn.execute(
        "INSERT INTO meals (date, name, sort_order) VALUES (?, ?, ?)", (date, name, nxt)
    ).lastrowid
    assert new_id is not None
    return new_id


def add_meal_item(conn: sqlite3.Connection, date: str, meal_name: str, food_name: str, weight: float) -> None:
    """Insert one diary item. Raises ``LookupError`` if the food is not in
    the catalog (no nutritional data)."""
    row = conn.execute("SELECT id FROM foods WHERE name = ?", (food_name,)).fetchone()
    if row is None:
        raise LookupError(food_name)
    meal_id = ensure_meal(conn, date, meal_name)
    conn.execute(
        "INSERT INTO meal_items (meal_id, food_id, weight) VALUES (?, ?, ?)",
        (meal_id, row["id"], weight),
    )
    conn.commit()


def export_day_json(conn: sqlite3.Connection, date: str, path: Path) -> str:
    """Write the day's diary JSON file (original shape) from the database.
    Returns the text that was written."""
    meals = load_day(conn, date)
    text = json.dumps(meals, indent=2)
    # Match the hand-edited files' style for empty food lists: "foods": [ / ]
    text = re.sub(r'"foods": \[\s*\]', '"foods": [\n    ]', text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")
    return text + "\n"


def daily_totals(conn: sqlite3.Connection) -> tuple:
    """Compute per-day macro totals in SQL, matching the old trend.py
    semantics: zero-weight items contribute nothing, and foods without
    nutritional data are skipped.

    Returns ``(totals, missing)`` where ``totals`` is
    ``{date: {"protein", "fat", "carbs", "calories"}}`` and ``missing`` is a
    list of ``(food_name, occurrence_count)`` for foods referenced in the
    diary but lacking nutritional data.
    """
    totals = {
        row["date"]: {
            "protein": row["protein"] or 0.0,
            "fat": row["fat"] or 0.0,
            "carbs": row["carbs"] or 0.0,
            "calories": row["calories"] or 0.0,
        }
        for row in conn.execute(
            """
            SELECT m.date AS date,
                   SUM(i.weight * f.protein / f.serving_size) AS protein,
                   SUM(i.weight * f.fat_total / f.serving_size) AS fat,
                   SUM(i.weight * f.carbs_total / f.serving_size) AS carbs,
                   SUM(i.weight * f.calories / f.serving_size) AS calories
            FROM meal_items i
            JOIN meals m ON m.id = i.meal_id
            JOIN foods f ON f.id = i.food_id
            GROUP BY m.date
            ORDER BY m.date
            """
        )
    }
    missing = [
        (row["name"], row["n"])
        for row in conn.execute(
            """
            SELECT f.name AS name, COUNT(*) AS n
            FROM meal_items i
            JOIN foods f ON f.id = i.food_id
            WHERE f.serving_size IS NULL
            GROUP BY f.name
            ORDER BY f.name
            """
        )
    ]
    return totals, missing
