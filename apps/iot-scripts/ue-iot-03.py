import json
import random
import time
from paho.mqtt import client as mqtt

MQTT_HOST = "mqtt"
MQTT_PORT = 1883
TOPIC = "iot/ue-iot-03"

client = mqtt.Client(client_id="ue-iot-03")
client.connect(MQTT_HOST, MQTT_PORT, 60)
client.loop_start()

while True:
    payload = {
        "ue": "ue-iot-03",
        "temperature_c": round(random.uniform(-2.0, 8.0), 1),
        "pressure_hpa": round(random.uniform(980.0, 1030.0), 1),
        "battery_percent": random.randint(40, 100),
        "timestamp": int(time.time())
    }

    msg = json.dumps(payload)
    client.publish(TOPIC, msg)
    print(f"Published -> {TOPIC}: {msg}", flush=True)
    time.sleep(3)
