import os, json, time
from flask import Flask, request, jsonify
import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "veh/telemetry")

app = Flask(__name__)

client = mqtt.Client()
client.connect(MQTT_HOST, MQTT_PORT, 60)
client.loop_start()

@app.get("/")
def ok():
    return "edge ok\n"

@app.post("/telemetry")
def telemetry():
    data = request.get_json(force=True, silent=True) or {}
    data["ts"] = time.time()
    payload = json.dumps(data)
    client.publish(MQTT_TOPIC, payload)
    return jsonify({"status": "ok", "published_to": MQTT_TOPIC})

