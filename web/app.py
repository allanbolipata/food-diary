"""FastAPI backend for the food diary dashboard.

Serves the static frontend and a small JSON API over data/food_diary.db,
reusing bin.db so the dashboard and the CLI always see the same data.

Run locally:   .venv/bin/uvicorn web.app:app --port 8877
In the container:  uvicorn web.app:app --host 0.0.0.0 --port 8000
"""

import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bin.db import (
    add_food_entry,
    add_meal_item,
    daily_totals,
    get_connection,
    load_day,
    load_foods,
    remove_item,
)

app = FastAPI(title="Food Diary API", version="1.1")

# Single-user, local service: allow any origin so the Swagger UI (and any
# page opened under a different hostname — Tailscale name, localhost, or
# the tailnet IP) can call the API without the browser aborting it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_rejected_api_requests(request, call_next):
    """Log the body of rejected /api writes so client bugs (e.g. the
    iPhone shortcut) can be diagnosed from `podman logs food-dashboard`."""
    body = b""
    if request.method in ("POST", "PUT", "PATCH"):
        body = await request.body()
    response = await call_next(request)
    if request.url.path.startswith("/api/") and response.status_code >= 400 and body:
        print(
            f"[api-reject] {request.method} {request.url.path} "
            f"-> {response.status_code}\n"
            f"  body: {body.decode('utf-8', 'replace')[:800]}",
            flush=True,
        )
    return response

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

DATE_RE = re.compile(r"^\d{8}$")


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
def list_foods(
    q: str | None = Query(default=None, max_length=100),
    name: str | None = Query(
        default=None,
        max_length=100,
        description="Alias for q — use either one, not both (q wins if both are given).",
    ),
    limit: int = Query(default=500, ge=1, le=5000),
):
    """All catalog entries, name-ordered; optional case-insensitive substring filter."""
    term = q if (q and q.strip()) else name
    conn = get_connection()
    try:
        sql = (
            f"SELECT {', '.join(DISPLAY_FIELDS)} FROM foods "
            "WHERE raw_json IS NOT NULL"
        )
        params: list = []
        if term and term.strip():
            sql += " AND name LIKE ?"
            params.append(f"%{term.strip()}%")
        sql += " ORDER BY name COLLATE NOCASE LIMIT ?"
        params.append(limit)
        return [dict(r) for r in conn.execute(sql, params)]
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


def _check_date(date: str) -> None:
    if not DATE_RE.match(date):
        raise HTTPException(status_code=400, detail="Date must be YYYYMMDD.")


def _macros_for(entry: dict, weight: float) -> dict:
    """Per-serving nutrition scaled to the logged weight."""
    ss = float(entry["serving_size"])
    scale = weight / ss
    nd = entry["nutritional_data"]
    r = lambda v: round(v * scale, 1)
    return {
        "calories": r(nd["calories"]),
        "protein": r(nd["protein"]),
        "fat": r(nd["fat"]["total"]),
        "carbs": r(nd["carbs"]["total"]),
        "fiber": r(nd["carbs"]["dietary_fiber"]["total"]),
        "sodium": r(nd["sodium"]["total"]),
    }


@app.get("/api/days/{date}")
def get_day(date: str):
    """One day's meals with per-item macros and day totals (empty meals omitted)."""
    _check_date(date)
    conn = get_connection()
    try:
        meals = load_day(conn, date)
        foods = load_foods(conn)
        totals = {"calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}
        out_meals = []
        for meal in meals:
            items = []
            for f in meal["foods"]:
                entry = foods.get(f["food"])
                if entry is None:
                    items.append(
                        {"food": f["food"], "weight": f["weight"],
                         "serving_size": None, "macros": None, "stub": True}
                    )
                    continue
                macros = _macros_for(entry, f["weight"])
                for k in totals:
                    totals[k] += macros[k]
                items.append(
                    {"food": f["food"], "weight": f["weight"],
                     "serving_size": float(entry["serving_size"]),
                     "macros": macros, "stub": False}
                )
            if items:
                out_meals.append({"name": meal["name"], "items": items})
        return {"date": date, "meals": out_meals,
                "totals": {k: round(v, 1) for k, v in totals.items()}}
    finally:
        conn.close()


class ItemIn(BaseModel):
    food: str = Field(min_length=1)
    weight: float = Field(ge=0)
    meal: str = Field(min_length=1, default="Miscellaneous")


@app.post("/api/days/{date}/items", status_code=201)
def log_item(date: str, p: ItemIn):
    """Log one food to a day's meal (weight is in the food's serving_size units)."""
    _check_date(date)
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT serving_size FROM foods WHERE name = ? AND raw_json IS NOT NULL",
            (p.food,),
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"Food '{p.food}' is not in the catalog. Pick one from the search list.",
            )
        add_meal_item(conn, date, p.meal, p.food, p.weight)
        return {"food": p.food, "meal": p.meal, "weight": p.weight,
                "serving_size": float(row["serving_size"])}
    finally:
        conn.close()


class ItemRef(BaseModel):
    food: str = Field(min_length=1)
    meal: str = Field(min_length=1)
    weight: float | None = None


@app.delete("/api/days/{date}/items")
def remove_log_item(date: str, p: ItemRef):
    """Remove one logged item. If the food appears twice in the meal, 409 is
    returned and the client must resend with `weight` to pick one."""
    _check_date(date)
    conn = get_connection()
    try:
        try:
            n = remove_item(conn, date, p.meal, p.food, weight=p.weight)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        if n == 0:
            raise HTTPException(status_code=404,
                                detail=f"Item '{p.food}' not found in '{p.meal}'.")
        return {"removed": n}
    finally:
        conn.close()


@app.get("/api/trends")
def trends(
    date_from: str = Query(..., alias="from"),
    date_to: str = Query(..., alias="to"),
):
    """Per-day macro totals over a date range (days with no meals are absent),
    the same numbers trend.py plots."""
    _check_date(date_from)
    _check_date(date_to)
    conn = get_connection()
    try:
        totals, _missing = daily_totals(conn)
        days = [
            {"date": d, "calories": round(v["calories"], 1),
             "protein": round(v["protein"], 1), "fat": round(v["fat"], 1),
             "carbs": round(v["carbs"], 1)}
            for d, v in sorted(totals.items())
            if date_from <= d <= date_to
        ]
        return {"days": days}
    finally:
        conn.close()


class TrendTargetsIn(BaseModel):
    trend_targets: list[float] = Field(default_factory=list, max_length=2)
    protein_target: float | None = None


def _ensure_settings_table(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )


@app.get("/api/settings")
def get_settings():
    """Saved dashboard settings as a key→JSON-value map ({} if none saved)."""
    conn = get_connection()
    try:
        _ensure_settings_table(conn)
        out = {}
        for row in conn.execute("SELECT key, value FROM settings"):
            try:
                out[row["key"]] = json.loads(row["value"])
            except (ValueError, TypeError):
                out[row["key"]] = row["value"]
        return out
    finally:
        conn.close()


@app.put("/api/settings")
def put_settings(p: TrendTargetsIn):
    """Upsert dashboard settings; returns the full settings map."""
    for v in p.trend_targets:
        if v < 0:
            raise HTTPException(status_code=422, detail="targets must be non-negative")
    if p.protein_target is not None and p.protein_target < 0:
        raise HTTPException(status_code=422, detail="protein_target must be non-negative")
    conn = get_connection()
    try:
        _ensure_settings_table(conn)
        conn.execute(
            "INSERT INTO settings(key, value) VALUES('trend_targets', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (json.dumps([round(float(v), 1) for v in p.trend_targets]),),
        )
        if p.protein_target is not None:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES('protein_target', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (json.dumps(round(float(p.protein_target), 1)),),
            )
        else:
            conn.execute("DELETE FROM settings WHERE key='protein_target'")
        conn.commit()
        return get_settings()
    finally:
        conn.close()


STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
