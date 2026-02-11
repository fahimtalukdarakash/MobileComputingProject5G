import os, time, random, json
import requests

EDGE_URL = os.getenv("EDGE_URL", "http://edge:5000/telemetry")
UE_NAME = os.getenv("UE_NAME", "ue-veh-02")

alerts = ["none", "hard_brake", "overspeed", "lane_departure", "airbag_check"]

while True:
    speed = round(random.uniform(0, 140), 1)
    alert = random.choices(alerts, weights=[70,10,10,8,2])[0]

    payload = {
        "ue": UE_NAME,
        "type": "veh_alerts",
        "speed_kmh": speed,
        "alert": alert
    }
    r = requests.post(EDGE_URL, json=payload, timeout=3)
    print("sent:", json.dumps(payload), "resp:", r.status_code)
    time.sleep(2)