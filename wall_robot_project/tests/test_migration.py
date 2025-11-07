import sqlite3
import json
import tempfile
from pathlib import Path
import os

import migrations.remove_legacy_column as mig


def create_legacy_db(path: str):
    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()
        # Create legacy trajectories table with trajectory_points JSON column
        cur.execute(
            """
            CREATE TABLE trajectories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wall_width REAL NOT NULL,
                wall_height REAL NOT NULL,
                obstacles TEXT NOT NULL,
                tool_width REAL NOT NULL,
                coverage_margin REAL NOT NULL,
                total_distance REAL,
                estimated_time REAL,
                coverage_percentage REAL,
                trajectory_points TEXT NOT NULL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        # Create points table
        cur.execute(
            """
            CREATE TABLE trajectory_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trajectory_id INTEGER NOT NULL,
                seq INTEGER NOT NULL,
                x REAL NOT NULL,
                y REAL NOT NULL
            );
            """
        )
        # Insert a sample trajectory row
        cur.execute(
            "INSERT INTO trajectories (wall_width, wall_height, obstacles, tool_width, coverage_margin, total_distance, estimated_time, coverage_percentage, trajectory_points) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (5.0, 5.0, json.dumps([]), 0.1, 0.05, 10.0, 1.0, 100.0, json.dumps([])),
        )
        traj_id = cur.lastrowid
        # Insert some points
        pts = [(traj_id, i, float(i) * 0.1, float(i) * 0.1) for i in range(50)]
        cur.executemany(
            "INSERT INTO trajectory_points (trajectory_id, seq, x, y) VALUES (?, ?, ?, ?)",
            pts,
        )
        conn.commit()
        return traj_id
    finally:
        conn.close()


def test_migration_removes_legacy_column(tmp_path):
    db_file = tmp_path / "legacy.db"
    db_path = str(db_file)
    traj_id = create_legacy_db(db_path)

    # Run migration
    mig.main(db_path)

    # Verify that the legacy column is gone and points preserved
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(trajectories)")
        cols = [r[1] for r in cur.fetchall()]
        assert "trajectory_points" not in cols

        cur.execute("SELECT COUNT(*) FROM trajectories")
        t_rows = cur.fetchone()[0]
        assert t_rows == 1

        cur.execute("SELECT COUNT(*) FROM trajectory_points")
        p_rows = cur.fetchone()[0]
        assert p_rows == 50
    finally:
        conn.close()
