import json
import random
import time
from paho.mqtt import client as mqtt

MQTT_HOST = "mqtt"
MQTT_PORT = 1883
TOPIC = "iot/ue-iot-01"

client = mqtt.Client(client_id="ue-iot-01")
client.connect(MQTT_HOST, MQTT_PORT, 60)
client.loop_start()

while True:
    payload = {
        "ue": "ue-iot-01",
        "temperature_c": round(random.uniform(-1.0, 7.0), 1),
        "humidity_percent": random.randint(35, 90),
        "timestamp": int(time.time())
    }

    msg = json.dumps(payload)
    client.publish(TOPIC, msg)
    print(f"Published -> {TOPIC}: {msg}", flush=True)
    time.sleep(3)
