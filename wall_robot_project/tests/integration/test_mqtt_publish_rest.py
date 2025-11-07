import os
import time
import pytest

pytestmark = pytest.mark.asyncio

MOSQUITTO_HOST = os.environ.get("MQTT_HOST")
MOSQUITTO_PORT = int(os.environ.get("MQTT_PORT", "1883"))


@pytest.mark.integration
@pytest.mark.skipif(not MOSQUITTO_HOST, reason="Mosquitto host not provided")
def test_app_publishes_mqtt_on_plan_post():
    """Start an MQTT subscriber, post a plan to the running app TestClient,
    and assert that the MQTT message is received. This test expects the
    app to create an MQTT client in its lifespan when MQTT_ENABLED env var
    is set (CI integration job sets that)."""
    import paho.mqtt.client as mqtt
    from fastapi.testclient import TestClient
    import robot_control_system as rcs

    received = []

    def on_message(client, userdata, msg):
        try:
            received.append(msg.payload.decode())
        except Exception:
            pass

    sub = mqtt.Client()
    sub.connect(MOSQUITTO_HOST, MOSQUITTO_PORT, 60)
    sub.on_message = on_message
    sub.subscribe(rcs.settings.mqtt_topic)
    sub.loop_start()

    # Set MQTT_ENABLED so the app's lifespan attempts to connect
    os.environ["MQTT_ENABLED"] = "1"

    client = TestClient(rcs.app)

    plan = {
        "wall_width": 2.0,
        "wall_height": 2.0,
        "tool_width": 0.1,
        "coverage_margin": 0.05,
        "obstacles": []
    }

    r = client.post("/api/v1/plan", json=plan)
    assert r.status_code == 201

    # Give the broker a moment to deliver the message
    time.sleep(1.5)

    sub.loop_stop()
    sub.disconnect()

    assert any("metrics" in m or "trajectory" in m or m for m in received)
