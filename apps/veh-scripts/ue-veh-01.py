import os, time, random, json
import requests

EDGE_URL = os.getenv("EDGE_URL", "http://edge:5000/telemetry")
UE_NAME = os.getenv("UE_NAME", "ue-veh-01")

lat, lon = 50.1109, 8.6821  # Frankfurt-ish

while True:
    speed = round(random.uniform(0, 120), 1)
    lat += random.uniform(-0.0003, 0.0003)
    lon += random.uniform(-0.0003, 0.0003)

    payload = {
        "ue": UE_NAME,
        "type": "veh_gps",
        "speed_kmh": speed,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
    }
    r = requests.post(EDGE_URL, json=payload, timeout=3)
    print("sent:", json.dumps(payload), "resp:", r.status_code)
    time.sleep(2)