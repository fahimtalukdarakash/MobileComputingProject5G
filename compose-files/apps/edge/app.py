from flask import Flask, request, jsonify
import os, json, time

# MQTT is optional here; if it fails, HTTP still works
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "veh/telemetry")

mqtt_client = None
try:
    import paho.mqtt.client as mqtt
    mqtt_client = mqtt.Client()
    mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
    mqtt_client.loop_start()
    print(f"[edge] MQTT connected to {MQTT_HOST}:{MQTT_PORT}, topic={MQTT_TOPIC}", flush=True)
except Exception as e:
    print(f"[edge] MQTT not enabled/failed: {e}", flush=True)

app = Flask(__name__)

@app.get("/")
def health():
    return "edge ok\n"

@app.post("/telemetry")
def telemetry():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"status":"error", "reason":"invalid json"}), 400

    print(f"[{time.strftime('%H:%M:%S')}] telemetry: {json.dumps(data)}", flush=True)

    # publish to MQTT if possible
    if mqtt_client:
        try:
            mqtt_client.publish(MQTT_TOPIC, json.dumps(data))
        except Exception as e:
            print(f"[edge] mqtt publish failed: {e}", flush=True)

    return jsonify({"status":"ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)