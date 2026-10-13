"""SQLite storage layer for the food diary.

The database lives at data/food_diary.db and is the single source of truth
for the whole project (the former data/food.json and data/diary/*.json
files are import/export formats only):

  foods       the food catalog. Nutritional values are flattened into
              columns for SQL aggregation, and the original JSON document
              is kept in ``raw_json`` so the data is lossless.
  meals       one row per meal per diary day.
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


def day_items(conn: sqlite3.Connection, date: str) -> list:
    """Return the raw item rows for one day:
    ``[{"id", "meal_id", "meal_name", "food_id", "food_name", "weight"}, ...]``.
    Used by log.py to reconcile the database with a diary file."""
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT i.id AS id, m.id AS meal_id, m.name AS meal_name,
                   f.id AS food_id, f.name AS food_name, i.weight
            FROM meal_items i
            JOIN meals m ON m.id = i.meal_id
            JOIN foods f ON f.id = i.food_id
            WHERE m.date = ?
            ORDER BY m.sort_order, i.rowid
            """,
            (date,),
        )
    ]


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


def flatten_food(entry: dict) -> dict:
    """Extract the flattened column values for one food.json entry.
    Same extraction as the one-time migration script."""
    nutr = entry.get("nutritional_data", {})
    fat = nutr.get("fat", {})
    carbs = nutr.get("carbs", {})
    return {
        "serving_size": entry.get("serving_size"),
        "calories": nutr.get("calories"),
        "protein": nutr.get("protein"),
        "fat_total": fat.get("total"),
        "fat_saturated": fat.get("saturated_fat", {}).get("total"),
        "sodium": nutr.get("sodium", {}).get("total"),
        "carbs_total": carbs.get("total"),
        "fiber_total": carbs.get("dietary_fiber", {}).get("total"),
        "sugars_total": carbs.get("sugars", {}).get("total"),
        "added_sugars_total": carbs.get("sugars", {}).get("added_sugars", {}).get("total"),
        "sugar_alcohols_total": carbs.get("sugars", {}).get("sugar_alcohols", {}).get("total"),
        "cholesterol": nutr.get("cholesterol", {}).get("total"),
    }


REQUIRED_MACRO_PATHS = (
    ("calories",),
    ("protein",),
    ("fat", "total"),
    ("carbs", "total"),
    ("carbs", "dietary_fiber", "total"),
    ("sodium", "total"),
)


def _validate_food_entry(entry: dict) -> None:
    """Raise ``ValueError`` if the entry lacks data the readers require
    (``bin.Food`` indexes these keys strictly)."""
    name = entry.get("name") or "<unnamed>"
    size = entry.get("serving_size")
    if not size:
        raise ValueError(f"'{name}': serving_size is required and must be > 0.")
    nd = entry.get("nutritional_data") or {}
    for path in REQUIRED_MACRO_PATHS:
        cur = nd
        for key in path:
            if not isinstance(cur, dict) or cur.get(key) is None:
                raise ValueError(
                    f"'{name}': nutritional_data is missing {'.'.join(path)}.")
            cur = cur[key]


def add_food_entry(conn: sqlite3.Connection, entry: dict) -> None:
    """Insert one catalog entry (original food.json shape).
    Raises ``ValueError`` if the name is already in the catalog
    (use :func:`update_food_entry`) or the entry lacks required data."""
    _validate_food_entry(entry)
    name = entry["name"]
    if conn.execute("SELECT 1 FROM foods WHERE name = ?", (name,)).fetchone():
        raise ValueError(f"Food '{name}' is already in the catalog (use food-update).")
    conn.execute(
        """
        INSERT INTO foods (name, serving_size, calories, protein, fat_total,
                          fat_saturated, sodium, carbs_total, fiber_total,
                          sugars_total, added_sugars_total,
                          sugar_alcohols_total, cholesterol, raw_json)
        VALUES (:name, :serving_size, :calories, :protein, :fat_total,
                :fat_saturated, :sodium, :carbs_total, :fiber_total,
                :sugars_total, :added_sugars_total,
                :sugar_alcohols_total, :cholesterol, :raw_json)
        """,
        {"name": name, **flatten_food(entry), "raw_json": json.dumps(entry)},
    )
    conn.commit()


def update_food_entry(conn: sqlite3.Connection, entry: dict) -> None:
    """Replace the catalog entry with this name (original food.json shape).
    Raises ``ValueError`` if the entry lacks required data and
    ``LookupError`` if the name is not in the catalog."""
    _validate_food_entry(entry)
    name = entry["name"]
    row = conn.execute("SELECT id FROM foods WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise LookupError(name)
    conn.execute(
        """
        UPDATE foods SET serving_size = :serving_size, calories = :calories,
               protein = :protein, fat_total = :fat_total,
               fat_saturated = :fat_saturated, sodium = :sodium,
               carbs_total = :carbs_total, fiber_total = :fiber_total,
               sugars_total = :sugars_total,
               added_sugars_total = :added_sugars_total,
               sugar_alcohols_total = :sugar_alcohols_total,
               cholesterol = :cholesterol, raw_json = :raw_json
        WHERE id = :id
        """,
        {**flatten_food(entry), "raw_json": json.dumps(entry), "id": row["id"]},
    )
    conn.commit()


def remove_food(conn: sqlite3.Connection, name: str) -> None:
    """Remove a catalog entry.
    Raises ``LookupError`` if the name is unknown, ``ValueError`` if the
    food is referenced by diary items (remove those first)."""
    row = conn.execute("SELECT id FROM foods WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise LookupError(name)
    n = conn.execute(
        "SELECT COUNT(*) FROM meal_items WHERE food_id = ?", (row["id"],)
    ).fetchone()[0]
    if n:
        raise ValueError(f"'{name}' is used in {n} diary item(s); remove those first.")
    conn.execute("DELETE FROM foods WHERE id = ?", (row["id"],))
    conn.commit()


def catalog_entries(conn: sqlite3.Connection) -> list:
    """Return the catalog in the original food.json list-of-dicts shape,
    in insertion order. Stub entries (no nutritional data, ``raw_json``
    NULL) are omitted, matching :func:`load_foods`."""
    return [
        json.loads(row["raw_json"])
        for row in conn.execute(
            "SELECT raw_json FROM foods WHERE raw_json IS NOT NULL ORDER BY id"
        )
    ]


def _day_item_rows(conn: sqlite3.Connection, date: str, meal_name: str, food_name: str) -> list:
    """All item rows for one (day, meal, food) combination."""
    return conn.execute(
        """
        SELECT i.id AS id, i.weight
        FROM meal_items i
        JOIN meals m ON m.id = i.meal_id
        JOIN foods f ON f.id = i.food_id
        WHERE m.date = ? AND m.name = ? AND f.name = ?
        ORDER BY i.rowid
        """,
        (date, meal_name, food_name),
    ).fetchall()


def _shown(w) -> int | float:
    """Normalise a stored weight so 1.0 and 1 compare equal."""
    w = float(w)
    return int(w) if w.is_integer() else w


def item_weights(conn: sqlite3.Connection, date: str, meal_name: str, food_name: str) -> list:
    """Return the list of weights of all (date, meal, food) item rows."""
    return [r["weight"] for r in _day_item_rows(conn, date, meal_name, food_name)]


def set_item_weight(conn: sqlite3.Connection, date: str, meal_name: str,
                    food_name: str, weight: float, existing_weight=None) -> int:
    """Change the weight of a diary item in place.

    Matches (day, meal, food). If more than one row matches, ``existing_weight``
    must be given to pick one; otherwise ``ValueError`` lists the matches.
    Returns the number of rows updated (1).
    """
    rows = _day_item_rows(conn, date, meal_name, food_name)
    if not rows:
        raise LookupError(f"No item for {food_name!r} in {meal_name!r} on {date}.")
    if len(rows) > 1 and existing_weight is None:
        weights = [f"{_shown(r['weight'])} serving(s)" for r in rows]
        raise ValueError(
            f"Ambiguous: {food_name!r} appears {len(rows)} times in {meal_name!r} on {date} "
            f"({', '.join(weights)}). Pass --weight or use remove --all."
        )
    if existing_weight is not None:
        rows = [r for r in rows if _shown(r["weight"]) == _shown(existing_weight)]
        if not rows:
            raise LookupError(
                f"No {food_name!r} in {meal_name!r} on {date} with weight {existing_weight:g}.")
        # With an explicit weight, take one matching row (duplicates are
        # indistinguishable, so any of them works).
        rows = rows[:1]
    conn.execute("UPDATE meal_items SET weight = ? WHERE id = ?", (weight, rows[0]["id"]))
    conn.commit()
    return 1


def remove_item(conn: sqlite3.Connection, date: str, meal_name: str,
                food_name: str, weight=None, all: bool = False) -> int:
    """Remove diary item(s) for (day, meal, food).

    Without ``weight``/``all``: exactly one matching row must exist,
    otherwise ``ValueError`` lists the matches. With ``weight``: one row
    matching (food, weight) is removed. With ``all``: every matching row
    is removed. Returns the number of rows removed.
    """
    rows = _day_item_rows(conn, date, meal_name, food_name)
    if not rows:
        raise LookupError(f"No item for {food_name!r} in {meal_name!r} on {date}.")
    if weight is not None:
        rows = [r for r in rows if _shown(r["weight"]) == _shown(weight)]
        if not rows:
            raise LookupError(
                f"No {food_name!r} in {meal_name!r} on {date} with weight {weight:g}.")
        rows = rows[:1]
    elif not all and len(rows) > 1:
        weights = [f"{_shown(r['weight'])} serving(s)" for r in rows]
        raise ValueError(
            f"Ambiguous: {food_name!r} appears {len(rows)} times in {meal_name!r} on {date} "
            f"({', '.join(weights)}). Pass --weight or --all."
        )
    for r in rows:
        conn.execute("DELETE FROM meal_items WHERE id = ?", (r["id"],))
    conn.commit()
    return len(rows)


def remove_meal(conn: sqlite3.Connection, date: str, meal_name: str) -> int:
    """Remove a whole meal (its items cascade). Returns the number of meals
    removed (1). Raises ``LookupError`` if the meal does not exist."""
    row = conn.execute(
        "SELECT id, (SELECT COUNT(*) FROM meal_items WHERE meal_id = meals.id) AS n "
        "FROM meals WHERE date = ? AND name = ?", (date, meal_name)
    ).fetchone()
    if row is None:
        raise LookupError(f"No meal {meal_name!r} on {date}.")
    conn.execute("DELETE FROM meals WHERE id = ?", (row["id"],))
    conn.commit()
    return 1


def rename_meal(conn: sqlite3.Connection, date, from_name: str, to_name: str) -> int:
    """Rename meal(s) called ``from_name`` to ``to_name``.

    With ``date``: one day. Without: every day. If a meal already exists
    with the target name on that day, the source meal's items are merged
    into it and the source row is deleted. Returns the number of items
    affected. Raises ``LookupError`` if no such meal exists.
    """
    if from_name == to_name:
        return 0
    if date is None:
        src = conn.execute(
            "SELECT id, date FROM meals WHERE name = ?", (from_name,)).fetchall()
    else:
        src = conn.execute(
            "SELECT id, date FROM meals WHERE date = ? AND name = ?",
            (date, from_name)).fetchall()
    if not src:
        where = f" on {date}" if date else ""
        raise LookupError(f"No meal {from_name!r}{where}.")
    moved = 0
    for m in src:
        tgt = conn.execute(
            "SELECT id FROM meals WHERE date = ? AND name = ?",
            (m["date"], to_name)).fetchone()
        if tgt:
            n = conn.execute(
                "UPDATE meal_items SET meal_id = ? WHERE meal_id = ?",
                (tgt["id"], m["id"])).rowcount
            conn.execute("DELETE FROM meals WHERE id = ?", (m["id"],))
        else:
            conn.execute("UPDATE meals SET name = ? WHERE id = ?", (to_name, m["id"]))
            n = conn.execute(
                "SELECT COUNT(*) FROM meal_items WHERE meal_id = ?",
                (m["id"],)).fetchone()[0]
        moved += n
    conn.commit()
    return moved


def clear_day(conn: sqlite3.Connection, date: str) -> tuple:
    """Remove every meal for one day. Returns (meals_removed, items_removed)."""
    meals = conn.execute("SELECT id FROM meals WHERE date = ?", (date,)).fetchall()
    items = conn.execute(
        "SELECT COUNT(*) FROM meal_items i JOIN meals m ON m.id = i.meal_id WHERE m.date = ?",
        (date,),
    ).fetchone()[0]
    conn.execute("DELETE FROM meals WHERE date = ?", (date,))
    conn.commit()
    return len(meals), items


def day_json_text(conn: sqlite3.Connection, date: str) -> str:
    """Return the day's diary as JSON text in the original file shape
    (what :func:`export_day_json` would write, minus the trailing newline)."""
    meals = load_day(conn, date)
    text = json.dumps(meals, indent=2)
    # Match the hand-edited files' style for empty food lists: "foods": [ / ]
    text = re.sub(r'"foods": \[\s*\]', '"foods": [\n    ]', text)
    return text


def export_day_json(conn: sqlite3.Connection, date: str, path: Path) -> str:
    """Write the day's diary JSON file (original shape) from the database.
    Returns the text that was written."""
    text = day_json_text(conn, date) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return text


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


def backup_db(conn: sqlite3.Connection, dest: Path) -> Path:
    """Write an online backup of the database to ``dest`` (a regular
    SQLite file). Creates parent directories. Returns ``dest``."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dst = sqlite3.connect(dest)
    try:
        conn.backup(dst)
    finally:
        dst.close()
    return dest
