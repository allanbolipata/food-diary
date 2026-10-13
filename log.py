#!/usr/bin/env python3
"""CLI for the food-diary database (data/food_diary.db — single source of truth).

Usage (from the repo root):
    python log.py add FOOD [weight] [--date YYYYMMDD] [--meal NAME]
    python log.py set-weight FOOD --weight N [--date D] [--meal M] [--was OLD]
    python log.py remove FOOD [--date D] [--meal M] [--weight N] [--all]
    python log.py move FOOD --to MEAL [--date D] [--meal M] [--weight N]
    python log.py remove-meal MEAL [--date D]
    python log.py clear --date D --yes
    python log.py import FILE [--date D]
    python log.py export [--date D | --all] [--out DIR]
    python log.py day [DATE]
    python log.py food-add --name NAME --data JSON_OR_FILE
    python log.py food-update --name NAME --data JSON_OR_FILE
    python log.py food-remove NAME
    python log.py food-search TEXT

Notes:
  - Weights are in the catalog's `serving_size` units (grams for foods
    measured by weight, one unit for whole-portion entries); default
    1 = one serving.
  - When a food appears more than once in a meal (e.g. two servings with
    different weights), commands that could match several rows refuse and
    list the matches; pass --weight N to pick one, or --all to take every.
  - ``import`` is a one-shot reconciliation tool for legacy diary JSON:
    it imports items the file lists that are missing from the database and
    removes items the database has that are no longer in the file, per
    meal name. Foods in the file but not in the catalog become stub
    catalog rows. It never writes the file.
  - ``export`` produces JSON in the original file shape, for reading and
    backups.
"""

import argparse
import difflib
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

from bin.db import (
    add_food_entry,
    add_meal_item,
    clear_day,
    daily_totals,
    day_items,
    day_json_text,
    export_day_json,
    get_connection,
    item_weights,
    load_day,
    remove_food,
    remove_item,
    remove_meal,
    set_item_weight,
    update_food_entry,
)

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_MEAL = "Miscellaneous"


def parse_date(s: str | None) -> str:
    s = s or date.today().strftime("%Y%m%d")
    try:
        return datetime.strptime(s, "%Y%m%d").strftime("%Y%m%d")
    except ValueError:
        raise SystemExit(f"Invalid date '{s}' (expected YYYYMMDD).")


def _shown(w) -> int | float:
    """Normalise a stored weight so 1.0 and 1 compare equal."""
    w = float(w)
    return int(w) if w.is_integer() else w


def _suggest_close(conn, name: str) -> None:
    names = [r["name"] for r in conn.execute("SELECT name FROM foods")]
    lower_to_orig = {}
    for n in names:
        lower_to_orig.setdefault(n.lower(), n)
    close = [lower_to_orig[l] for l in
             difflib.get_close_matches(name.lower(), list(lower_to_orig), n=5)]
    print(f"Error: '{name}' is not in the food catalog.")
    if close:
        print("Did you mean one of:")
        for n in close:
            print(f"  {n}")
    sys.exit(1)


def _day_totals_line(conn, day: str) -> None:
    totals, missing = daily_totals(conn)
    t = totals.get(day, {"calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0})
    print(f"Totals for {day} (incl. uneaten meals): "
          f"calories {t['calories']:.1f}, protein {t['protein']:.1f}g, "
          f"fat {t['fat']:.1f}g, carbs {t['carbs']:.1f}g")
    for name, n in missing:
        print(f"Warning: no nutritional data for '{name}' (x{n})")


def cmd_add(conn, args) -> None:
    day = parse_date(args.date)
    if args.weight < 0:
        raise SystemExit("Weight must be >= 0.")
    try:
        add_meal_item(conn, day, args.meal, args.food, args.weight)
    except LookupError:
        _suggest_close(conn, args.food)
    print(f"Added {args.food!r} ({args.weight:g} serving(s)) to {args.meal!r} on {day}.")
    _day_totals_line(conn, day)


def cmd_set_weight(conn, args) -> None:
    day = parse_date(args.date)
    try:
        set_item_weight(conn, day, args.meal, args.food, args.weight, args.was)
    except (LookupError, ValueError) as e:
        raise SystemExit(str(e))
    print(f"Set weight of {args.food!r} in {args.meal!r} on {day} to {args.weight:g}.")


def cmd_remove(conn, args) -> None:
    day = parse_date(args.date)
    try:
        n = remove_item(conn, day, args.meal, args.food, weight=args.weight, all=args.all)
    except LookupError as e:
        raise SystemExit(str(e))
    except ValueError as e:
        raise SystemExit(f"{e} Pass --weight N or --all.")
    print(f"Removed {n} item(s) of {args.food!r} from {args.meal!r} on {day}.")


def cmd_move(conn, args) -> None:
    day = parse_date(args.date)
    weights = item_weights(conn, day, args.meal, args.food)
    if not weights:
        raise SystemExit(f"No item for {args.food!r} in {args.meal!r} on {day}.")
    if args.weight is not None:
        weights = [w for w in weights if _shown(w) == _shown(args.weight)]
        if not weights:
            raise SystemExit(f"No {args.food!r} in {args.meal!r} on {day} with weight {args.weight:g}.")
    elif len({_shown(w) for w in weights}) > 1:
        shown = ", ".join(f"{_shown(w)}" for w in weights)
        raise SystemExit(f"Ambiguous: {args.food!r} appears with weights ({shown}) in "
                         f"{args.meal!r}; pass --weight N to pick one.")
    for w in weights:
        remove_item(conn, day, args.meal, args.food, weight=w, all=True)
        add_meal_item(conn, day, args.to, args.food, w)
    print(f"Moved {args.food!r} from {args.meal!r} to {args.to!r} on {day} "
          f"({', '.join(f'{_shown(w)}' for w in weights)}).")


def cmd_remove_meal(conn, args) -> None:
    day = parse_date(args.date)
    try:
        remove_meal(conn, day, args.meal)
    except LookupError as e:
        raise SystemExit(str(e))
    print(f"Removed meal {args.meal!r} on {day}.")


def cmd_clear(conn, args) -> None:
    day = parse_date(args.date)
    if not args.yes:
        raise SystemExit("Refusing to clear a day without --yes.")
    meals, items = clear_day(conn, day)
    print(f"Cleared {day}: removed {meals} meal(s), {items} item(s).")


def reconcile_from_file(conn, day: str, path: Path) -> dict:
    """Reconcile the database with a legacy diary JSON file (one-shot import).

    After this, per meal name the database contains exactly the items the
    file lists: file-only items are imported (unknown foods become stub
    rows), database-only items are removed, shared items are untouched.
    Returns ``{"added": [...], "removed": [...], "skipped": bool}``.
    """
    db_items = day_items(conn, day)
    file_meals = json.loads(path.read_text(encoding="utf-8"))

    db_counts = {}
    for it in db_items:
        key = (it["food_name"], _shown(it["weight"]))
        c = db_counts.setdefault(it["meal_name"], {})
        c[key] = c.get(key, 0) + 1

    file_counts = {}
    n_file_items = 0
    for m in file_meals:
        for item in m["foods"]:
            key = (item["food"], _shown(item["weight"]))
            c = file_counts.setdefault(m["name"], {})
            c[key] = c.get(key, 0) + 1
            n_file_items += 1

    # Safety: an empty file must not wipe a day that still has items.
    if n_file_items == 0 and db_items:
        print(f"Warning: {path.name} lists no items but the database has "
              f"{len(db_items)} for {day}; nothing was removed.")
        return {"added": [], "removed": [], "skipped": True}

    added, removed = [], []
    for m in file_meals:
        db_c = db_counts.get(m["name"], {})
        for item in m["foods"]:
            key = (item["food"], _shown(item["weight"]))
            for _ in range(max(file_counts[m["name"]][key] - db_c.get(key, 0), 0)):
                try:
                    add_meal_item(conn, day, m["name"], item["food"], item["weight"])
                except LookupError:
                    conn.execute("INSERT INTO foods (name) VALUES (?)", (item["food"],))
                    conn.commit()
                    add_meal_item(conn, day, m["name"], item["food"], item["weight"])
                    print(f"Note: '{item['food']}' was added to the catalog without nutritional data.")
                added.append(item["food"])

    remaining = {m: dict(c) for m, c in db_counts.items()}
    for it in db_items:
        key = (it["food_name"], _shown(it["weight"]))
        if remaining[it["meal_name"]].get(key, 0) <= file_counts.get(it["meal_name"], {}).get(key, 0):
            continue
        remaining[it["meal_name"]][key] -= 1
        conn.execute("DELETE FROM meal_items WHERE id = ?", (it["id"],))
        removed.append(it["food_name"])

    file_meal_names = {m["name"] for m in file_meals}
    for mname in db_counts:
        if mname not in file_meal_names:
            conn.execute("DELETE FROM meals WHERE date = ? AND name = ?", (day, mname))

    conn.commit()
    return {"added": added, "removed": removed, "skipped": False}


def cmd_import(conn, args) -> None:
    path = Path(args.file).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"No such file: {path}")
    day = parse_date(args.date) if args.date else (
        path.stem if re.fullmatch(r"\d{8}", path.stem) else None
    )
    if day is None:
        raise SystemExit(f"Could not determine a date from {path.name}; pass --date YYYYMMDD.")
    try:
        report = reconcile_from_file(conn, day, path)
    except (json.JSONDecodeError, KeyError) as e:
        raise SystemExit(f"Could not parse {path.name}: {e}")
    if report["skipped"]:
        return
    if report["added"]:
        print(f"Imported {len(report['added'])} item(s): {', '.join(report['added'])}")
    if report["removed"]:
        print(f"Removed {len(report['removed'])} item(s) no longer in the file: {', '.join(report['removed'])}")
    if not report["added"] and not report["removed"]:
        print(f"Nothing to do: {path.name} already matches the database for {day}.")


def cmd_export(conn, args) -> None:
    if args.all:
        if not args.out:
            raise SystemExit("--all requires --out DIR.")
        out = Path(args.out).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        dates = [r["date"] for r in conn.execute("SELECT DISTINCT date FROM meals ORDER BY date")]
        for d in dates:
            export_day_json(conn, d, out / f"{d}.json")
        print(f"Exported {len(dates)} days to {out}.")
    else:
        day = parse_date(args.date)
        print(day_json_text(conn, day))


def cmd_day(conn, args) -> None:
    day = parse_date(args.date)
    meals = load_day(conn, day)
    if not meals:
        print(f"No diary entries for {day}.")
        return
    for m in meals:
        print(f"--- {m['name']}")
        for it in m["foods"]:
            print(f"  {it['food']}  ({_shown(it['weight'])} serving(s))")
    _day_totals_line(conn, day)


def _load_food_data(s: str) -> dict:
    """Parse a --data argument: raw JSON text, or '@path' to a JSON file."""
    if s.startswith("@"):
        p = Path(s[1:]).expanduser()
        if not p.is_file():
            raise SystemExit(f"No such file: {p}")
        raw = p.read_text(encoding="utf-8")
    else:
        raw = s
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"Could not parse food data as JSON: {e}")
    if not isinstance(data, dict):
        raise SystemExit("Food data must be a JSON object.")
    return data


def cmd_food_add(conn, args) -> None:
    data = _load_food_data(args.data)
    try:
        add_food_entry(conn, data)
    except ValueError as e:
        raise SystemExit(str(e))
    print(f"Added catalog entry {data['name']!r}.")


def cmd_food_update(conn, args) -> None:
    data = _load_food_data(args.data)
    try:
        update_food_entry(conn, data)
    except (ValueError, LookupError) as e:
        raise SystemExit(str(e))
    print(f"Updated catalog entry {data['name']!r}.")


def cmd_food_remove(conn, args) -> None:
    try:
        remove_food(conn, args.name)
    except (LookupError, ValueError) as e:
        raise SystemExit(str(e))
    print(f"Removed catalog entry {args.name!r}.")


def cmd_food_search(conn, args) -> None:
    rows = conn.execute(
        "SELECT name, serving_size, calories FROM foods "
        "WHERE name LIKE ? ORDER BY name",
        (f"%{args.text}%",),
    ).fetchall()
    if not rows:
        print(f"No catalog entries match {args.text!r}.")
        return
    for r in rows:
        print(f"{r['name']}  (serving {r['serving_size']:g}, {r['calories']:g} cal)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="add a food to a diary day")
    p_add.add_argument("food", help="exact food name from the catalog")
    p_add.add_argument("weight", nargs="?", type=float, default=1.0,
                       help="amount in serving units (default 1)")
    p_add.add_argument("--date", help="YYYYMMDD (default: today)")
    p_add.add_argument("--meal", default=DEFAULT_MEAL,
                       help=f"meal name (default: {DEFAULT_MEAL})")

    p_sw = sub.add_parser("set-weight", help="change an item's weight")
    p_sw.add_argument("food", help="food name in the meal")
    p_sw.add_argument("--weight", type=float, required=True, help="new weight")
    p_sw.add_argument("--was", type=float, default=None,
                      help="old weight, to disambiguate when the food appears twice")
    p_sw.add_argument("--date", help="YYYYMMDD (default: today)")
    p_sw.add_argument("--meal", default=DEFAULT_MEAL)

    p_rm = sub.add_parser("remove", help="remove an item from a diary day")
    p_rm.add_argument("food", help="food name in the meal")
    p_rm.add_argument("--weight", type=float, default=None,
                      help="weight of the item to remove (disambiguates duplicates)")
    p_rm.add_argument("--all", action="store_true",
                      help="remove every matching item, even if several exist")
    p_rm.add_argument("--date", help="YYYYMMDD (default: today)")
    p_rm.add_argument("--meal", default=DEFAULT_MEAL)

    p_mv = sub.add_parser("move", help="move an item to another meal")
    p_mv.add_argument("food", help="food name in the meal")
    p_mv.add_argument("--to", required=True, dest="to", help="destination meal name")
    p_mv.add_argument("--weight", type=float, default=None,
                      help="weight of the item(s) to move")
    p_mv.add_argument("--date", help="YYYYMMDD (default: today)")
    p_mv.add_argument("--meal", default=DEFAULT_MEAL, help="source meal name")

    p_rmmeal = sub.add_parser("remove-meal", help="remove a whole meal")
    p_rmmeal.add_argument("meal", help="meal name")
    p_rmmeal.add_argument("--date", help="YYYYMMDD (default: today)")

    p_clear = sub.add_parser("clear", help="remove every meal for a day")
    p_clear.add_argument("--date", help="YYYYMMDD (default: today)")
    p_clear.add_argument("--yes", action="store_true", help="required to actually clear")

    p_imp = sub.add_parser("import", help="one-shot reconcile of a legacy diary JSON")
    p_imp.add_argument("file", help="path to a diary JSON file")
    p_imp.add_argument("--date", help="YYYYMMDD (default: from the filename)")

    p_exp = sub.add_parser("export", help="export a day (or all days) as JSON")
    p_exp.add_argument("--date", help="YYYYMMDD (default: today); prints to stdout")
    p_exp.add_argument("--all", action="store_true",
                       help="write every day to --out DIR as <date>.json")
    p_exp.add_argument("--out", help="output directory for --all")

    p_day = sub.add_parser("day", help="show a diary day from the database")
    p_day.add_argument("date", nargs="?", help="YYYYMMDD (default: today)")

    p_fadd = sub.add_parser("food-add", help="add a food to the catalog")
    p_fadd.add_argument("--name", required=True)
    p_fadd.add_argument("--data", required=True,
                        help="JSON object text, or @path/to/file.json")

    p_fupd = sub.add_parser("food-update", help="replace a catalog entry")
    p_fupd.add_argument("--name", required=True)
    p_fupd.add_argument("--data", required=True,
                        help="JSON object text, or @path/to/file.json")

    p_frm = sub.add_parser("food-remove", help="remove a food from the catalog")
    p_frm.add_argument("name")

    p_fsearch = sub.add_parser("food-search", help="search the catalog by substring")
    p_fsearch.add_argument("text")

    args = parser.parse_args()
    conn = get_connection()
    try:
        {
            "add": cmd_add,
            "set-weight": cmd_set_weight,
            "remove": cmd_remove,
            "move": cmd_move,
            "remove-meal": cmd_remove_meal,
            "clear": cmd_clear,
            "import": cmd_import,
            "export": cmd_export,
            "day": cmd_day,
            "food-add": cmd_food_add,
            "food-update": cmd_food_update,
            "food-remove": cmd_food_remove,
            "food-search": cmd_food_search,
        }[args.cmd](conn, args)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
