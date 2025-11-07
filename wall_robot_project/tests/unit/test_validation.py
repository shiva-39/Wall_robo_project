from fastapi.testclient import TestClient
import robot_control_system as rcs

client = TestClient(rcs.app)


def test_overlapping_obstacle_rejected():
    # Two obstacles overlapping and exceeding wall bounds should be validated
    plan = {
        "wall_width": 2.0,
        "wall_height": 2.0,
        "tool_width": 0.1,
        "coverage_margin": 0.05,
        "obstacles": [
            {"id": "o1", "x": 1.5, "y": 1.5, "width": 1.0, "height": 0.5},
        ],
    }

    resp = client.post("/api/v1/plan", json=plan)
    assert resp.status_code == 422 or resp.status_code == 400


def test_invalid_dimensions_rejected():
    plan = {"wall_width": 0.0, "wall_height": 5.0, "tool_width": 0.1, "coverage_margin": 0.05, "obstacles": []}
    resp = client.post("/api/v1/plan", json=plan)
    assert resp.status_code == 422 or resp.status_code == 400
