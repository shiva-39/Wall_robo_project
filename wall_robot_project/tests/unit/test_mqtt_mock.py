import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import robot_control_system as rcs


def test_create_plan_triggers_mqtt_publish(monkeypatch):
    # Prepare a dummy plan
    plan = {
        "wall_width": 1.0,
        "wall_height": 1.0,
        "obstacles": [],
        "tool_width": 0.1,
        "coverage_margin": 0.05,
    }

    # Ensure app.state.mqtt_client is a mock
    mock_client = MagicMock()
    rcs.app.state.mqtt_client = mock_client

    client = TestClient(rcs.app)

    # Provide required config: ensure API key/jwt are not required
    resp = client.post("/api/v1/plan", json=plan)
    assert resp.status_code == 201
    # Assert publish was attempted
    assert mock_client.publish.called

