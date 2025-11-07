"""
Safe migration to remove legacy `trajectory_points` JSON column from `trajectories` table.
This script creates a new table without the column, copies data across, drops the old table
and renames the new one. It makes a backup copy of the original DB file first.

Usage:
    python migrations/remove_legacy_column.py
"""

import sqlite3
import shutil
from pathlib import Path

import argparse


def main(db_path: str):
    DB_PATH = Path(db_path)
    BACKUP = DB_PATH.with_suffix(DB_PATH.suffix + ".bak")

    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}")
        raise SystemExit(1)

    print(f"Backing up DB to {BACKUP}")
    shutil.copy2(DB_PATH, BACKUP)

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()

        # Check if legacy column exists
        cur.execute("PRAGMA table_info(trajectories)")
        cols = [r[1] for r in cur.fetchall()]
        if "trajectory_points" not in cols:
            print("No legacy column found; nothing to do.")
            return

        print("Legacy column found; performing safe table rewrite...")

        # Get existing schema for columns we want to keep
        keep_cols = [c for c in cols if c != "trajectory_points"]
        cols_sql = ", ".join(keep_cols)

        # Create new table (keep a conservative subset of columns)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS trajectories_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wall_width REAL NOT NULL,
            wall_height REAL NOT NULL,
            obstacles TEXT NOT NULL,
            tool_width REAL NOT NULL,
            coverage_margin REAL NOT NULL,
            total_distance REAL,
            estimated_time REAL,
            coverage_percentage REAL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Copy data
        cur.execute(
            f"INSERT INTO trajectories_new ({cols_sql}) SELECT {cols_sql} FROM trajectories;"
        )
        conn.commit()

        # Drop old table and rename
        cur.execute("DROP TABLE trajectories;")
        cur.execute("ALTER TABLE trajectories_new RENAME TO trajectories;")
        conn.commit()

        print("Migration complete. Original DB backed up to", BACKUP)
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remove legacy trajectory_points column")
    parser.add_argument("--db-path", dest="db_path", default=str(Path(__file__).resolve().parents[1] / "robot_trajectories.db"), help="Path to the SQLite DB")
    args = parser.parse_args()
    main(args.db_path)
