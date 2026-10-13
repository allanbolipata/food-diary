# Roadmap & known weaknesses

Honest assessment of the project as of 2026-10-13, written by the agent that
built the DB layer and dashboard. Use it as a backlog: the "Criticism"
section lists real problems (with severity), the "Future updates" section is
a prioritized backlog. Items reference the code they touch.

## Criticism

### Data integrity (the important ones)

1. **Stub entries and near-duplicate food names** (medium, largely historical).
   Referential integrity is actually in place: `meal_items.food_id` is a
   real `REFERENCES foods(id)` FK (enforced — `bin.db.get_connection`
   sets `PRAGMA foreign_keys = ON`), and `db.remove_food` refuses to
   delete a food still used by diary items. The real historical problem
   is that sparse entries could be created before write-time validation
   existed: e.g. a data-less stub "Taco Bell: Steak Quesadilla"
   (colon) coexisted with the real "Taco Bell Steak Quesadilla", and a
   diary item pointed at the stub, so its calories silently dropped from
   that day's totals (warning only). Fixed 2026-10-13 by repointing the
   item and removing the stub. Residual exposure: any remaining
   data-less stubs still referenced by diary items — check with
   `SELECT f.name FROM foods f JOIN meal_items mi ON mi.food_id = f.id
   WHERE f.raw_json IS NULL` (currently empty). The catalog also contains
   multi-food entries ("Combined Intake (Oats, Orgain Protein, ...)")
   that double as diary references — a data-model quirk, not a bug.

2. **No write concurrency protection** (medium, low probability for one
   user). The CLI and the container write the same file. SQLite serializes
   writers, but without `busy_timeout` a collision is a hard
   `database is locked` error, and without WAL, readers block writers.
   Fix: `PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;` in
   `bin/db.get_connection` — a two-line change that would make the
   CLI/container overlap safe.

3. **Backups are manual** (medium). `log.py backup` exists, but nothing
   runs it. One fat-fingered `clear --yes` or a bad migration is a real
   data-loss window. Fix: a systemd timer or podman compose sidecar that
   runs a daily backup with retention into `data/backups/`.

### Consistency between the old scripts

4. **`app.py` and `eaten.py` disagree with each other** (medium).
   `eaten.py` correctly counts only `weight > 0` items, but `app.py`
   includes zero-weight items and adds a `+ 1` per empty meal
   ("unknown food" hack). For days with uneaten meals or empty meal rows
   (~350 of them in the history) the two scripts print different totals
   for the same day. Fix: make `app.py`'s summary use the same
   `weight > 0` rule as `eaten.py` and drop the `+ 1` hack.

5. **`eaten.py` hardcodes the last 7 days** (low). No date arguments; it
   is the one script that can't be pointed at a range. Trivial to fix with
   two optional `--from/--to` args reusing `trend.py`'s parsing.

### Dashboard gaps

6. **No food editing or recipes in the UI** (low-medium). `log.py
   food-update` exists but there is no `PUT /api/foods/{name}`; recipes
   (`bin/recipe_obj.py`, `data/template_recipe.json`) have no API or UI at
   all.
7. **Trends have no rolling average** (low). `trend.py` draws a 7-day
   moving average; the browser chart doesn't. The math is one function to
   port (`trend.py moving_avg`).
8. **Day log shows no per-meal subtotals** (low). Per-item and day totals
   exist; a per-meal calorie line would make multi-meal days easier to
   eyeball.
9. **No meal management in the UI** (low). Items can be removed, but whole
   meals can't be renamed or deleted (CLI has both).
10. **"Today" is computed in the browser** (low). If the machine clock is
    wrong or the app is viewed from another timezone, the default day can
    differ from the day the CLI would use. Fix: have `/api/days/today`
    return the server's date.
11. **No API tests** (low-medium). `tests/` covers `bin/db.py` (22 tests),
    but the web layer is only exercised manually. FastAPI's `TestClient`
    makes this cheap.

### Packaging / ops

12. **Loose dependency pins** (low). `>=` ranges in both requirements
    files; pin exact versions (or a lockfile) for reproducible container
    builds.
13. **No container healthcheck** (low). Add a `HEALTHCHECK` hitting
    `/api/stats` so `podman compose` reports a dead server instead of
    "running".
14. **Binds 0.0.0.0 with no auth by design** (accepted). Fine on a private
    machine, but if this box ever gets a public IP or the tailnet widens,
    put a reverse proxy with a password in front or bind to
    `100.127.136.124` only (already documented in `compose.yaml`).
15. **Zero-weight items are a marker, not a feature** (design debt).
    ~3,117 zero-weight items encode "logged but uneaten". Every consumer
    has to remember to filter `weight > 0`. A boolean `eaten` column would
    be cleaner, but migrating 5,125 rows to retrofit it is a cost/benefit
    call — only worth it if the "uneaten" workflow keeps growing.

## Future updates (suggested order)

**P1 — data safety (do first, all small):**
- WAL + `busy_timeout` in `bin.db.get_connection` (criticism 2).
- Sweep for any remaining data-less stub entries and merge/remove them
  (criticism 1) — none are referenced as of 2026-10-13.
- Daily automatic backup (systemd timer or compose sidecar, criticism 3).
- API tests with `TestClient` (criticism 11).

**P2 — consistency & dashboard completeness:**
- Align `app.py` totals with `eaten.py` (`weight > 0`, no `+1` hack);
  deprecate the `+1` behavior explicitly in the README (criticism 4).
- `PUT /api/foods/{name}` + edit modal in the catalog tab (criticism 6).
- 7-day rolling average line on the trends charts (criticism 7).
- Per-meal subtotals in the day tab (criticism 8).
- Rename/remove meal from the day tab (criticism 9).
- Server-provided "today" (criticism 10).
- `eaten.py --from/--to` (criticism 5).

**P3 — quality of life & scale:**
- Recipes in the API + a recipes tab (build on `bin/recipe_obj.py`).
- Calorie/macro targets with progress bars on the day tab (e.g. "2,388 /
  2,800 kcal, 85%").
- PWA: manifest + service worker so it installs on a phone and loads
  offline (read-only cache).
- Integer `food_id` FK refactor + data migration (criticism 1, full fix).
- Food search with nutrition filtering (min protein, max sodium, ...).
- Meal templates ("reheat yesterday's lunch") and quick-log presets.
- Dark mode behind a toggle.
- Pin dependency versions / lockfile (criticism 12), container healthcheck
  (criticism 13).

## What is already solid

- Single source of truth: DB only; UI, CLI, and scripts share `bin.db`.
- Catalog validation at write time (no sparse entries can corrupt totals).
- Referential integrity: enforced `food_id` FK from `meal_items` to
  `foods`, and `db.remove_food` refuses to delete foods in use.
- Weight-unit conventions enforced (`serving_size` units, unit-aware output).
- 22 passing unit tests on throwaway DBs; `backup_db()` online backups.
- Verified round-trips: UI→DB and container→DB changes appear in the CLI.
