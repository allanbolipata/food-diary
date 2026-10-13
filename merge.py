#!/usr/bin/env python3
"""Write data/meals.json: all diary days in one file.

Reads from data/food_diary.db (the source of truth), so the merged file
always matches what eaten.py / trend.py report. Re-run after any change
to the database.
"""

import json
from pathlib import Path

from bin.db import get_connection, load_day

REPO_ROOT = Path(__file__).resolve().parent


def main():
    conn = get_connection()
    try:
        dates = [r[0] for r in conn.execute("SELECT DISTINCT date FROM meals ORDER BY date")]
        combined = [{"date": d, "meals": load_day(conn, d)} for d in dates]
    finally:
        conn.close()

    out = REPO_ROOT / "data" / "meals.json"
    with open(out, "w") as f:
        json.dump(combined, f, indent=4)
        f.write("\n")
    print(f"Wrote {len(combined)} days to {out}")


if __name__ == "__main__":
    main()
