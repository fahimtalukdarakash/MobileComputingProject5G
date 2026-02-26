"""
Slice 3 Fallback Simulator
============================
Runs on UE3 (Slice 3 — Restricted/Backup). Publishes to the SAME MQTT topics
as Slice 1 (IoT) and Slice 2 (Vehicle) simulators, providing redundancy
when those slices are down.

This proves slice resilience: even when Slice 1+2 fail, data continues
flowing through Slice 3.

Topics published:
  - iot/ue-iot-01  (temperature, humidity)
  - iot/ue-iot-02  (CO2, PM2.5)
  - iot/ue-iot-03  (temperature, pressure, battery)
  - veh/telemetry  (GPS, speed, alerts)
"""

import json
import random
import time
import threading
from paho.mqtt import client as mqtt

MQTT_HOST = "mqtt"
MQTT_PORT = 1883
FALLBACK_TAG = "slice3-fallback"

client = mqtt.Client(client_id="ue3-fallback")
client.connect(MQTT_HOST, MQTT_PORT, 60)
client.loop_start()

print(f"[FALLBACK] Slice 3 fallback simulator started", flush=True)
print(f"[FALLBACK] Publishing to: iot/ue-iot-01, iot/ue-iot-02, iot/ue-iot-03, veh/telemetry", flush=True)


def publish_iot_01():
    """Environment monitoring — same as sim-iot-01"""
    while True:
        payload = {
            "ue": "ue-iot-01",
            "temperature_c": round(random.uniform(-1.0, 7.0), 1),
            "humidity_percent": random.randint(35, 90),
            "timestamp": int(time.time()),
            "source": FALLBACK_TAG,
        }
        msg = json.dumps(payload)
        client.publish("iot/ue-iot-01", msg)
        print(f"[FALLBACK] iot/ue-iot-01: temp={payload['temperature_c']}°C hum={payload['humidity_percent']}%", flush=True)
        time.sleep(3)


def publish_iot_02():
    """Smart city air quality — same as sim-iot-02"""
    while True:
        payload = {
            "ue": "ue-iot-02",
            "co2_ppm": random.randint(400, 1600),
            "pm2_5_ugm3": round(random.uniform(2.0, 40.0), 1),
            "ts": int(time.time()),
            "source": FALLBACK_TAG,
        }
        msg = json.dumps(payload)
        client.publish("iot/ue-iot-02", msg)
        print(f"[FALLBACK] iot/ue-iot-02: co2={payload['co2_ppm']}ppm pm2.5={payload['pm2_5_ugm3']}µg", flush=True)
        time.sleep(2)


def publish_iot_03():
    """eHealth/environment — same as sim-iot-03"""
    while True:
        payload = {
            "ue": "ue-iot-03",
            "temperature_c": round(random.uniform(-2.0, 8.0), 1),
            "pressure_hpa": round(random.uniform(980.0, 1030.0), 1),
            "battery_percent": random.randint(40, 100),
            "timestamp": int(time.time()),
            "source": FALLBACK_TAG,
        }
        msg = json.dumps(payload)
        client.publish("iot/ue-iot-03", msg)
        print(f"[FALLBACK] iot/ue-iot-03: temp={payload['temperature_c']}°C press={payload['pressure_hpa']}hPa", flush=True)
        time.sleep(3)


def publish_veh():
    """Vehicle telemetry — same as sim-veh-01 + sim-veh-02"""
    lat, lon = 50.1109, 8.6821
    alerts = ["none", "hard_brake", "overspeed", "lane_departure", "airbag_check"]

    while True:
        speed = round(random.uniform(0, 120), 1)
        lat += random.uniform(-0.0003, 0.0003)
        lon += random.uniform(-0.0003, 0.0003)
        alert = random.choices(alerts, weights=[70, 10, 10, 8, 2])[0]

        # GPS data (like sim-veh-01)
        gps_payload = {
            "ue": "ue-veh-01",
            "type": "veh_gps",
            "speed_kmh": speed,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "ts": time.time(),
            "source": FALLBACK_TAG,
        }
        client.publish("veh/telemetry", json.dumps(gps_payload))
        print(f"[FALLBACK] veh/telemetry: gps speed={speed}km/h lat={round(lat,4)} lon={round(lon,4)}", flush=True)

        time.sleep(1)

        # Alert data (like sim-veh-02)
        alert_payload = {
            "ue": "ue-veh-02",
            "type": "veh_alerts",
            "speed_kmh": round(random.uniform(0, 140), 1),
            "alert": alert,
            "ts": time.time(),
            "source": FALLBACK_TAG,
        }
        client.publish("veh/telemetry", json.dumps(alert_payload))
        if alert != "none":
            print(f"[FALLBACK] veh/telemetry: alert={alert} speed={alert_payload['speed_kmh']}km/h", flush=True)

        time.sleep(2)


# Start all publishers as threads
threads = [
    threading.Thread(target=publish_iot_01, daemon=True),
    threading.Thread(target=publish_iot_02, daemon=True),
    threading.Thread(target=publish_iot_03, daemon=True),
    threading.Thread(target=publish_veh, daemon=True),
]

for t in threads:
    t.start()

print(f"[FALLBACK] All 4 publisher threads running. Slice 3 providing full redundancy.", flush=True)

# Keep main thread alive
while True:
    time.sleep(60)