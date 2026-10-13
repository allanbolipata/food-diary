"""FastAPI backend for the food diary dashboard.

Serves the static frontend and a small JSON API over data/food_diary.db,
reusing bin.db so the dashboard and the CLI always see the same data.

Run locally:   .venv/bin/uvicorn web.app:app --port 8877
In the container:  uvicorn web.app:app --host 0.0.0.0 --port 8000
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bin.db import add_food_entry, get_connection

app = FastAPI(title="Food Diary API", version="1.0")

DISPLAY_FIELDS = (
    "name",
    "serving_size",
    "calories",
    "protein",
    "fat_total",
    "fat_saturated",
    "sodium",
    "carbs_total",
    "fiber_total",
    "sugars_total",
    "added_sugars_total",
    "sugar_alcohols_total",
    "cholesterol",
)


class FoodIn(BaseModel):
    """A flattened catalog entry (same units as the bin.db columns)."""

    name: str = Field(min_length=1)
    serving_size: float = Field(gt=0, description="grams (or units) per serving")
    calories: float
    protein: float = Field(default=0.0, ge=0)
    fat_total: float = Field(default=0.0, ge=0)
    carbs_total: float = Field(default=0.0, ge=0)
    fiber_total: float = Field(default=0.0, ge=0)
    sugars_total: float = Field(default=0.0, ge=0)
    added_sugars_total: float = Field(default=0.0, ge=0)
    sugar_alcohols_total: float = Field(default=0.0, ge=0)
    sodium: float = Field(default=0.0, ge=0, description="milligrams")
    fat_saturated: float = Field(default=0.0, ge=0)
    cholesterol: float = Field(default=0.0, ge=0)


def _entry_from_payload(p: FoodIn) -> dict:
    """Build the canonical food.json entry shape from a flattened payload."""
    return {
        "name": p.name,
        "serving_size": p.serving_size,
        "nutritional_data": {
            "calories": p.calories,
            "protein": p.protein,
            "fat": {
                "total": p.fat_total,
                "saturated_fat": {"total": p.fat_saturated},
                "cholesterol": {"total": p.cholesterol},
            },
            "carbs": {
                "total": p.carbs_total,
                "dietary_fiber": {"total": p.fiber_total},
                "sugars": {
                    "total": p.sugars_total,
                    "added_sugars": {"total": p.added_sugars_total},
                    "sugar_alcohols": {"total": p.sugar_alcohols_total},
                },
            },
            "sodium": {"total": p.sodium},
        },
    }


def _row(conn, name: str):
    row = conn.execute(
        f"SELECT {', '.join(DISPLAY_FIELDS)} FROM foods WHERE name = ? AND raw_json IS NOT NULL",
        (name,),
    ).fetchone()
    return dict(row) if row else None


@app.get("/api/foods")
def list_foods(q: str | None = Query(default=None, max_length=100)):
    """All catalog entries, name-ordered; optional case-insensitive substring filter."""
    conn = get_connection()
    try:
        if q and q.strip():
            rows = conn.execute(
                f"SELECT {', '.join(DISPLAY_FIELDS)} FROM foods "
                "WHERE raw_json IS NOT NULL AND name LIKE ? "
                "ORDER BY name COLLATE NOCASE",
                (f"%{q.strip()}%",),
            )
        else:
            rows = conn.execute(
                f"SELECT {', '.join(DISPLAY_FIELDS)} FROM foods "
                "WHERE raw_json IS NOT NULL ORDER BY name COLLATE NOCASE"
            )
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/foods/{name}")
def get_food(name: str):
    conn = get_connection()
    try:
        row = _row(conn, name)
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Food '{name}' not found.")
    return row


@app.post("/api/foods", status_code=201)
def create_food(p: FoodIn):
    conn = get_connection()
    try:
        if conn.execute("SELECT 1 FROM foods WHERE name = ?", (p.name,)).fetchone():
            raise HTTPException(status_code=409, detail=f"Food '{p.name}' is already in the catalog.")
        try:
            add_food_entry(conn, _entry_from_payload(p))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        return _row(conn, p.name)
    finally:
        conn.close()


@app.get("/api/stats")
def stats():
    conn = get_connection()
    try:
        foods = conn.execute(
            "SELECT COUNT(*) FROM foods WHERE raw_json IS NOT NULL").fetchone()[0]
        days = conn.execute("SELECT COUNT(DISTINCT date) FROM meals").fetchone()[0]
        eaten = conn.execute(
            "SELECT COUNT(*) FROM meal_items WHERE weight > 0").fetchone()[0]
        return {"foods": foods, "days": days, "eaten_items": eaten}
    finally:
        conn.close()


STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
