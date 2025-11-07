import os
import time
import pytest
import threading

pytestmark = pytest.mark.asyncio

MOSQUITTO_HOST = os.environ.get("MQTT_HOST")
MOSQUITTO_PORT = int(os.environ.get("MQTT_PORT", "1883"))


@pytest.mark.integration
@pytest.mark.skipif(not MOSQUITTO_HOST, reason="Mosquitto host not provided")
def test_mqtt_broker_publish_and_subscribe():
    """Integration test: subscribe to mosquitto and ensure app publishes.
    This test assumes a running mosquitto service on MOSQUITTO_HOST:MOSQUITTO_PORT.
    It will perform a small publish via paho to verify the broker works.
    """
    import paho.mqtt.client as mqtt

    received = []

    def on_message(client, userdata, msg):
        received.append(msg.payload.decode())

    client = mqtt.Client()
    client.connect(MOSQUITTO_HOST, MOSQUITTO_PORT, 60)
    client.loop_start()
    client.subscribe("test/topic")
    client.on_message = on_message

    # Publish a message
    client.publish("test/topic", "hello-from-ci")

    # wait shortly for message to be delivered
    time.sleep(1.5)
    client.loop_stop()
    client.disconnect()

    assert any("hello-from-ci" in r for r in received)

