import json
import random
import time
from paho.mqtt import client as mqtt

MQTT_HOST = "mqtt"
MQTT_PORT = 1883
TOPIC = "iot/ue-iot-02"

client = mqtt.Client(client_id="ue-iot-02")
client.connect(MQTT_HOST, MQTT_PORT, 60)
client.loop_start()

while True:
    payload = {
        "ue": "ue-iot-02",
        "co2_ppm": random.randint(400, 1600),
        "pm2_5_ugm3": round(random.uniform(2.0, 40.0), 1),
        "ts": int(time.time())
    }
    msg = json.dumps(payload)
    client.publish(TOPIC, msg)
    print(f"Published -> {TOPIC}: {msg}", flush=True)
    time.sleep(2)
