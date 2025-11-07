# -*- coding: utf-8 -*-
"""Quick DB check script (UTF-8). Prints trajectories schema and row counts.

Usage:
    python scripts\check_db.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("robot_trajectories.db")
if not DB_PATH.exists():
    raise SystemExit(f"DB not found: {DB_PATH}")

con = sqlite3.connect(str(DB_PATH))
try:
    cur = con.cursor()
    cur.execute("PRAGMA table_info(trajectories)")
    print(cur.fetchall())
    cur.execute("SELECT count(1) FROM trajectories")
    print('trajectories rows:', cur.fetchone()[0])
    try:
        cur.execute("SELECT count(1) FROM trajectory_points")
        print('trajectory_points rows:', cur.fetchone()[0])
    except sqlite3.OperationalError as e:
        print('trajectory_points table check failed:', e)
finally:
    con.close()
