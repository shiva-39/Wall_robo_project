import time
from fastapi.testclient import TestClient
from robot_control_system import app

client = TestClient(app)


def test_websocket_abort_does_not_crash_server():
    """Open a websocket plan, receive some progress, then close the connection.
    The server should not raise unhandled exceptions and should remain responsive.
    """
    with client.websocket_connect("/ws/plan") as ws:
        # Send a plan likely to produce some points but not too large for test
        plan = {
            "wall_width": 10.0,
            "wall_height": 10.0,
            "tool_width": 0.5,
            "coverage_margin": 0.1,
            "obstacles": [],
        }
        ws.send_json(plan)
        # attempt to receive at least one message (progress or points)
        try:
            _ = ws.receive_json(timeout=2)
        except Exception:
            # If no message arrived quickly that's acceptable; close anyway
            pass
        # Exit the context to close the websocket abruptly (client side)

    # Give server a moment to process cancellation
    time.sleep(0.5)

    # Server should still respond to a health check
    r = client.get("/health")
    assert r.status_code == 200
