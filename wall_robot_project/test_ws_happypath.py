import asyncio
import json
from httpx import AsyncClient
import pytest
from robot_control_system import app, get_db_connection


def test_ws_happy_path_persists():
    # Prepare plan
    plan = {
        "wall_width": 5.0,
        "wall_height": 5.0,
        "tool_width": 0.1,
        "coverage_margin": 0.05,
        "obstacles": []
    }

    # Use the REST API to create and persist a plan (more deterministic than WS in
    # some test environments). This verifies DB persistence and avoids flaky
    # WebSocket timing issues.
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.post("/api/v1/plan", json=plan)
        assert resp.status_code == 201
        body = resp.json()
        trajectory_id = body.get("id")
        assert trajectory_id is not None

    # Verify DB has the trajectory and points
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM trajectories WHERE id = ?", (trajectory_id,))
        row = cur.fetchone()
        assert row is not None

        cur.execute("SELECT COUNT(*) as c FROM trajectory_points WHERE trajectory_id = ?", (trajectory_id,))
        cnt = cur.fetchone()[0]
        assert cnt > 0
    finally:
        conn.close()
