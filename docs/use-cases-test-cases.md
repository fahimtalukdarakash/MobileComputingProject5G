# Use Cases & Test Cases

[← Back to Main README](../README.md)

This document covers all the use case simulators and automated test cases implemented in the project. It describes the UERANSIM-based verification test suite, the six application-layer use case simulators that demonstrate real-world 5G network slicing scenarios, and the PacketRusher-based load testing and throughput measurement setup.

---

## Table of Contents
1. [Overview](#1-overview)
2. [Automated Verification Test Suite (UERANSIM)](#2-automated-verification-test-suite-ueransim)
   - 2.1 [Test Architecture](#21-test-architecture)
   - 2.2 [Network Connectivity Tests](#22-network-connectivity-tests)
   - 2.3 [Slice 3 Internet Isolation Tests](#23-slice-3-internet-isolation-tests)
   - 2.4 [Test API and Execution](#24-test-api-and-execution)
   - 2.5 [Test Results Format](#25-test-results-format)
3. [Use Case Simulators](#3-use-case-simulators)
   - 3.1 [Simulator Architecture](#31-simulator-architecture)
   - 3.2 [Slice 1 — IoT Simulators](#32-slice-1--iot-simulators)
   - 3.3 [Slice 2 — Vehicle Simulators](#33-slice-2--vehicle-simulators)
   - 3.4 [Application Backend Services](#34-application-backend-services)
   - 3.5 [Simulator Docker Compose Definition](#35-simulator-docker-compose-definition)
4. [Use Case Data Flows](#4-use-case-data-flows)
   - 4.1 [IoT → MQTT Flow (Slice 1)](#41-iot--mqtt-flow-slice-1)
   - 4.2 [Vehicle → Edge Flow (Slice 2)](#42-vehicle--edge-flow-slice-2)
   - 4.3 [Restricted Internal Flow (Slice 3)](#43-restricted-internal-flow-slice-3)
5. [PacketRusher Load Testing](#5-packetrusher-load-testing)
   - 5.1 [PacketRusher Architecture](#51-packetrusher-architecture)
   - 5.2 [Speed Test Deployment](#52-speed-test-deployment)
   - 5.3 [PacketRusher Configuration](#53-packetrusher-configuration)
   - 5.4 [iperf3 Throughput Testing](#54-iperf3-throughput-testing)
   - 5.5 [Load Test Compose File](#55-load-test-compose-file)
6. [Running Everything](#6-running-everything)
   - 6.1 [Running the Verification Tests](#61-running-the-verification-tests)
   - 6.2 [Running the Use Case Simulators](#62-running-the-use-case-simulators)
   - 6.3 [Running PacketRusher Load Tests](#63-running-packetrusher-load-tests)
7. [Test Summary Matrix](#7-test-summary-matrix)

---

## 1. Overview

The project implements three categories of testing and demonstration:

```
┌─────────────────────────────────────────────────────────────────┐
│                    TESTING & USE CASES                           │
│                                                                 │
│  ┌────────────────────┐  ┌──────────────────┐  ┌────────────┐  │
│  │  Automated Tests   │  │  Use Case Sims   │  │  Load Test │  │
│  │  (UERANSIM)        │  │  (6 simulators)  │  │ (PktRusher)│  │
│  │                    │  │                  │  │            │  │
│  │  • PDU sessions    │  │  • 3 IoT sensors │  │  • Multi-UE│  │
│  │  • Connectivity    │  │  • 2 Vehicles    │  │  • iperf3  │  │
│  │  • Slice isolation │  │  • 1 Restricted  │  │  • GTP     │  │
│  │  • Service health  │  │                  │  │  throughput│  │
│  └────────────────────┘  └──────────────────┘  └────────────┘  │
│         ↓                        ↓                     ↓        │
│   Verifies network         Demonstrates real       Measures     │
│   slicing works            5G slice use cases      performance  │
└─────────────────────────────────────────────────────────────────┘
```

All three categories run on top of the same 5G core (Open5GS) with UERANSIM providing the RAN simulation and PacketRusher providing an alternative RAN for load testing.

---

## 2. Automated Verification Test Suite (UERANSIM)

### 2.1 Test Architecture

The automated tests run from the **framework backend** (`framework/tests.py`) and use `docker exec` commands to execute connectivity checks from inside the UE containers. Each UE container (ue1, ue2, ue3) has a `uesimtun0` tunnel interface created by UERANSIM that carries traffic through the GTP-U tunnel to its assigned UPF.

```
┌──────────────┐
│   Framework  │
│  (tests.py)  │
│              │
│  docker exec │─────┐
│  ue1 ping    │     │    ┌──────┐   GTP-U   ┌──────┐
│  ...         │     ├───►│ UE1  │──────────►│ UPF1 │──► Internet ✓
│              │     │    └──────┘           └──────┘
│  docker exec │     │    ┌──────┐   GTP-U   ┌──────┐
│  ue2 ping    │     ├───►│ UE2  │──────────►│ UPF2 │──► Internet ✓
│  ...         │     │    └──────┘           └──────┘
│  docker exec │     │    ┌──────┐   GTP-U   ┌──────┐
│  ue3 ping    │     └───►│ UE3  │──────────►│ UPF3 │──✕ Internet ✗
│  8.8.8.8     │          └──────┘           └──────┘    (blocked)
└──────────────┘
```

**Source file:** `framework/tests.py`

```python
import subprocess
from typing import Dict, List

def run(cmd: List[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        return f"ERR: {' '.join(cmd)}\n{p.stderr.strip()}"
    return p.stdout.strip()

def ping_from(container: str, target: str, count: int = 2) -> str:
    return run(["docker", "exec", "-t", container,
                "sh", "-lc", f"ping -c {count} {target}"])

def test_suite() -> Dict[str, Dict[str, str]]:
    results = {
        "ue1": {
            "ping_mqtt": ping_from("ue1", "mqtt"),
            "ping_internet": ping_from("ue1", "8.8.8.8"),
        },
        "ue2": {
            "ping_mqtt": ping_from("ue2", "mqtt"),
            "ping_internet": ping_from("ue2", "8.8.8.8"),
        },
        "ue3": {
            "ping_mqtt": ping_from("ue3", "mqtt"),
            "ping_nodered": ping_from("ue3", "nodered"),
            "ping_internet_should_fail": ping_from("ue3", "8.8.8.8"),
        }
    }
    return results
```

The `run()` helper executes shell commands via `subprocess` and returns stdout on success or an error message on failure. The `ping_from()` function runs `ping` inside a specific UE container using `docker exec`. The test suite is exposed via a FastAPI endpoint.

### 2.2 Network Connectivity Tests

These tests verify that each UE can reach the services it should be able to access through its assigned network slice.

| Test           | Container | Target  | Expected     | What It Proves                                                 |
| -------------- | --------- | ------- | ------------ | -------------------------------------------------------------- |
| UE1 → MQTT     | ue1       | mqtt    | ✅ Reachable | Slice 1 IoT UE can reach the MQTT broker on the Docker network |
| UE1 → Internet | ue1       | 8.8.8.8 | ✅ Reachable | Slice 1 has internet access via UPF1 NAT                       |
| UE2 → MQTT     | ue2       | mqtt    | ✅ Reachable | Slice 2 Vehicle UE can reach internal services                 |
| UE2 → Internet | ue2       | 8.8.8.8 | ✅ Reachable | Slice 2 has internet access via UPF2 NAT                       |
| UE3 → MQTT     | ue3       | mqtt    | ✅ Reachable | Slice 3 Restricted UE can reach internal MQTT                  |
| UE3 → Node-RED | ue3       | nodered | ✅ Reachable | Slice 3 Restricted UE can reach internal Node-RED              |

Each ping test sends 2 ICMP packets (`ping -c 2`) and the result includes the raw ping output with RTT times or error messages. A successful test shows `0% packet loss` in the output.

**How the ping traverses the network:** When `ping` runs inside the UE container, it sends packets via the `uesimtun0` tunnel interface. The packet is encapsulated in GTP-U by the UERANSIM UE process, forwarded to the gNB over the simulated radio link, then sent to the assigned UPF via the N3 interface. The UPF decapsulates the GTP-U tunnel and forwards the packet to its destination (either the Docker network for internal services, or through NAT to the internet).

### 2.3 Slice 3 Internet Isolation Tests

The most important test validates that Slice 3 (Restricted) correctly blocks internet access while allowing internal service communication.

| Test           | Container | Target  | Expected   | What It Proves                          |
| -------------- | --------- | ------- | ---------- | --------------------------------------- |
| UE3 → Internet | ue3       | 8.8.8.8 | ❌ Blocked | Internet is blocked at UPF3 by iptables |

**How internet blocking works:**

1. UE3 establishes a normal PDU session and receives an IP in the `10.47.0.0/16` subnet
2. Traffic from UE3 travels through the GTP-U tunnel → gNB → UPF3
3. At UPF3, iptables rules inspect the destination:
   - Destination on Docker network (`10.33.33.0/24`) → **ALLOWED**
   - Destination is external (e.g., `8.8.8.8`) → **DROPPED**

The test expects `100% packet loss` or a timeout when UE3 pings `8.8.8.8`, while the UE3 → MQTT and UE3 → Node-RED tests above confirm internal connectivity still works. This proves the network slicing architecture can enforce different access policies per slice.

**Manual verification commands:**

```bash
# Should FAIL (100% packet loss)
docker exec ue3 ping -I uesimtun0 -c 3 8.8.8.8

# Should SUCCEED
docker exec ue3 ping -I uesimtun0 -c 3 mqtt

# Should SUCCEED
docker exec ue3 ping -I uesimtun0 -c 3 nodered
```

### 2.4 Test API and Execution

The test suite is exposed via the FastAPI backend:

```
POST /api/tests/run
```

The framework backend (`framework/app.py`) registers this endpoint:

```python
@app.post("/api/tests/run")
def run_tests() -> Dict:
    """Run verification tests (pings from ue1/ue2/ue3)."""
    return test_suite()
```

**Execution flow:**

1. User triggers tests via the web UI verify page or by calling the API directly
2. Framework executes `docker exec` commands sequentially against each UE container
3. Each ping runs with a 2-packet count (takes approximately 2–3 seconds per test)
4. Full suite completes in approximately 15–20 seconds
5. Results are returned as JSON

### 2.5 Test Results Format

The API returns a nested dictionary grouped by UE:

```json
{
  "ue1": {
    "ping_mqtt": "PING mqtt (10.33.33.X): 56 data bytes\n64 bytes from ...: icmp_seq=0 ttl=63 time=2.31 ms\n...\n--- mqtt ping statistics ---\n2 packets transmitted, 2 received, 0% packet loss",
    "ping_internet": "PING 8.8.8.8 (8.8.8.8): 56 data bytes\n64 bytes from 8.8.8.8: icmp_seq=0 ttl=111 time=12.4 ms\n...\n2 packets transmitted, 2 received, 0% packet loss"
  },
  "ue2": {
    "ping_mqtt": "...(success)...",
    "ping_internet": "...(success)..."
  },
  "ue3": {
    "ping_mqtt": "...(success)...",
    "ping_nodered": "...(success)...",
    "ping_internet_should_fail": "ERR: docker exec -t ue3 sh -lc ping -c 2 8.8.8.8\n..."
  }
}
```

A result starting with `"ERR:"` or containing `100% packet loss` indicates the ping failed. For the `ping_internet_should_fail` test on UE3, this failure is the **expected and correct** outcome.

---

## 3. Use Case Simulators

### 3.1 Simulator Architecture

The use case simulators are lightweight Python scripts that run inside Docker containers. Each simulator shares the network namespace of its parent UE container using Docker's `network_mode: "container:<ue-name>"` directive. This means the simulator's traffic flows through the UE's `uesimtun0` tunnel interface, traversing the full 5G network path.

```
┌─────────────────────────────────────────────────────────────────┐
│                  SIMULATOR ARCHITECTURE                          │
│                                                                 │
│  ┌──────────┐ shares net ┌──────────┐  GTP-U  ┌──────┐         │
│  │sim-iot-01│───────────►│ue-iot-01 │────────►│ UPF1 │──►MQTT  │
│  │ (Python) │ namespace  │(UERANSIM)│ tunnel  │      │         │
│  └──────────┘            └──────────┘         └──────┘         │
│                                                                 │
│  ┌──────────┐ shares net ┌──────────┐  GTP-U  ┌──────┐         │
│  │sim-veh-01│───────────►│ue-veh-01 │────────►│ UPF2 │──►Edge  │
│  │ (Python) │ namespace  │(UERANSIM)│ tunnel  │      │         │
│  └──────────┘            └──────────┘         └──────┘         │
│                                                                 │
│  Key: Simulator has no network of its own.                      │
│       It inherits eth0, uesimtun0, routing table from UE.       │
└─────────────────────────────────────────────────────────────────┘
```

**How `network_mode: "container:ue-iot-01"` works:**

The simulator container starts without its own network stack. Instead, it shares the network namespace (interfaces, IP addresses, routing table, DNS) of the named UE container. When the Python script inside the simulator opens a socket to `mqtt:1883`, the traffic exits through the UE's `uesimtun0` interface, is encapsulated in GTP-U, forwarded through the gNB to the UPF, and finally reaches the MQTT broker. The simulator literally uses the 5G network — it is not directly connected to the Docker bridge.

### 3.2 Slice 1 — IoT Simulators

Three IoT sensor simulators run on Slice 1, each sharing the network namespace of a dedicated UERANSIM UE. They publish sensor telemetry to the MQTT broker at regular intervals.

#### sim-iot-01 — Environmental Monitoring 🌡

| Property         | Value                           |
| ---------------- | ------------------------------- |
| Container        | `sim-iot-01`                    |
| Network Mode     | `container:ue-iot-01`           |
| Script           | `apps/iot-scripts/ue-iot-01.py` |
| Protocol         | MQTT                            |
| Broker           | `mqtt:1883`                     |
| Topic            | `iot/ue-iot-01`                 |
| Publish Interval | 3 seconds                       |

**Telemetry payload:**

```json
{
  "ue": "ue-iot-01",
  "temperature_c": 3.2,
  "humidity_percent": 67,
  "timestamp": 1709100000
}
```

| Field            | Type  | Range       | Unit    |
| ---------------- | ----- | ----------- | ------- |
| temperature_c    | float | -1.0 to 7.0 | °C      |
| humidity_percent | int   | 35 to 90    | %       |
| timestamp        | int   | Unix epoch  | seconds |

**Source code (`apps/iot-scripts/ue-iot-01.py`):**

```python
import json, random, time
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
```

#### sim-iot-02 — Smart City Air Quality 🏙

| Property         | Value                           |
| ---------------- | ------------------------------- |
| Container        | `sim-iot-02`                    |
| Network Mode     | `container:ue-iot-02`           |
| Script           | `apps/iot-scripts/ue-iot-02.py` |
| Protocol         | MQTT                            |
| Broker           | `mqtt:1883`                     |
| Topic            | `iot/ue-iot-02`                 |
| Publish Interval | 2 seconds                       |

**Telemetry payload:**

```json
{
  "ue": "ue-iot-02",
  "co2_ppm": 820,
  "pm2_5_ugm3": 15.3,
  "ts": 1709100000
}
```

| Field      | Type  | Range       | Unit    |
| ---------- | ----- | ----------- | ------- |
| co2_ppm    | int   | 400 to 1600 | ppm     |
| pm2_5_ugm3 | float | 2.0 to 40.0 | µg/m³   |
| ts         | int   | Unix epoch  | seconds |

#### sim-iot-03 — eHealth Sensor Station 🏥

| Property         | Value                           |
| ---------------- | ------------------------------- |
| Container        | `sim-iot-03`                    |
| Network Mode     | `container:ue-iot-03`           |
| Script           | `apps/iot-scripts/ue-iot-03.py` |
| Protocol         | MQTT                            |
| Broker           | `mqtt:1883`                     |
| Topic            | `iot/ue-iot-03`                 |
| Publish Interval | 3 seconds                       |

**Telemetry payload:**

```json
{
  "ue": "ue-iot-03",
  "temperature_c": 2.5,
  "pressure_hpa": 1013.2,
  "battery_percent": 78,
  "timestamp": 1709100000
}
```

| Field           | Type  | Range           | Unit    |
| --------------- | ----- | --------------- | ------- |
| temperature_c   | float | -2.0 to 8.0     | °C      |
| pressure_hpa    | float | 980.0 to 1030.0 | hPa     |
| battery_percent | int   | 40 to 100       | %       |
| timestamp       | int   | Unix epoch      | seconds |

### 3.3 Slice 2 — Vehicle Simulators

Two vehicle simulators run on Slice 2, sending telemetry via HTTP POST to the Edge server. They simulate connected vehicles sending GPS tracking data and emergency alerts.

#### sim-veh-01 — Vehicle GPS Tracking 🚗

| Property         | Value                           |
| ---------------- | ------------------------------- |
| Container        | `sim-veh-01`                    |
| Network Mode     | `container:ue-veh-01`           |
| Script           | `apps/veh-scripts/ue-veh-01.py` |
| Protocol         | HTTP POST                       |
| Endpoint         | `http://edge:5000/telemetry`    |
| Publish Interval | 2 seconds                       |

**Telemetry payload:**

```json
{
  "ue": "ue-veh-01",
  "type": "veh_gps",
  "speed_kmh": 67.3,
  "lat": 50.110612,
  "lon": 8.682394
}
```

| Field     | Type  | Range          | Unit    |
| --------- | ----- | -------------- | ------- |
| speed_kmh | float | 0 to 120       | km/h    |
| lat       | float | ~50.11 ± drift | degrees |
| lon       | float | ~8.68 ± drift  | degrees |

The GPS coordinates start at Frankfurt, Germany (50.1109, 8.6821) and drift by ±0.0003 degrees per sample, simulating a vehicle moving through the city. The `type` field is set to `"veh_gps"` to differentiate from alert payloads at the Edge server.

**Source code (`apps/veh-scripts/ue-veh-01.py`):**

```python
import os, time, random, json
import requests

EDGE_URL = os.getenv("EDGE_URL", "http://edge:5000/telemetry")
UE_NAME  = os.getenv("UE_NAME", "ue-veh-01")

lat, lon = 50.1109, 8.6821  # Frankfurt

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
```

#### sim-veh-02 — Vehicle Emergency Alerts 🚨

| Property         | Value                           |
| ---------------- | ------------------------------- |
| Container        | `sim-veh-02`                    |
| Network Mode     | `container:ue-veh-02`           |
| Script           | `apps/veh-scripts/ue-veh-02.py` |
| Protocol         | HTTP POST                       |
| Endpoint         | `http://edge:5000/telemetry`    |
| Publish Interval | 2 seconds                       |

**Telemetry payload:**

```json
{
  "ue": "ue-veh-02",
  "type": "veh_alerts",
  "speed_kmh": 95.4,
  "alert": "hard_brake"
}
```

| Field     | Type   | Range     | Unit |
| --------- | ------ | --------- | ---- |
| speed_kmh | float  | 0 to 140  | km/h |
| alert     | string | see below | —    |

**Alert types and probability weights:**

| Alert            | Weight | Probability |
| ---------------- | ------ | ----------- |
| `none`           | 70     | 70%         |
| `hard_brake`     | 10     | 10%         |
| `overspeed`      | 10     | 10%         |
| `lane_departure` | 8      | 8%          |
| `airbag_check`   | 2      | 2%          |

The alerts are selected using `random.choices()` with weighted probabilities, producing a realistic distribution where most messages report normal operation but occasional safety events occur.

### 3.4 Application Backend Services

The simulators communicate with three backend services that run on the Docker network:

**MQTT Broker (Mosquitto)**

| Property      | Value                              |
| ------------- | ---------------------------------- |
| Container     | `mqtt`                             |
| Image         | `eclipse-mosquitto:2`              |
| Port          | `1883` (TCP)                       |
| Auth          | Anonymous allowed                  |
| Persistence   | Enabled (`/mosquitto/data/`)       |
| Receives from | sim-iot-01, sim-iot-02, sim-iot-03 |

All three IoT simulators publish to the MQTT broker. The broker is configured with `allow_anonymous true` for simplicity in the lab environment.

**Edge Server (Flask)**

| Property      | Value                      |
| ------------- | -------------------------- |
| Container     | `edge`                     |
| Image         | `python:3.11-slim`         |
| Port          | `5000` (HTTP)              |
| Receives from | sim-veh-01, sim-veh-02     |
| Forwards to   | MQTT topic `veh/telemetry` |

The Edge server receives HTTP POST requests from vehicle simulators at `/telemetry`, adds a timestamp, and republishes the data to the MQTT broker on topic `veh/telemetry`. This demonstrates a common MEC (Multi-access Edge Computing) pattern where an edge application processes vehicle data before forwarding it.

```python
@app.post("/telemetry")
def telemetry():
    data = request.get_json(force=True, silent=True) or {}
    data["ts"] = time.time()
    payload = json.dumps(data)
    client.publish(MQTT_TOPIC, payload)
    return jsonify({"status": "ok", "published_to": MQTT_TOPIC})
```

**Node-RED Dashboard**

| Property  | Value                      |
| --------- | -------------------------- |
| Container | `nodered`                  |
| Image     | `nodered/node-red:latest`  |
| Port      | `1880` (HTTP)              |
| Dashboard | `http://localhost:1880/ui` |

Node-RED subscribes to the MQTT topics and provides a visual dashboard showing live sensor readings. It can be configured through its browser-based flow editor at `http://localhost:1880`.

### 3.5 Simulator Docker Compose Definition

All simulators and backend services are defined in `compose-files/apps/docker-compose.apps.yaml`:

```yaml
version: "3.9"

services:
  mqtt:
    image: eclipse-mosquitto:2
    container_name: mqtt
    ports:
      - "1883:1883"
    networks:
      - open5gs
    volumes:
      - ./mqtt/config/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
      - mqtt_data:/mosquitto/data
      - mqtt_log:/mosquitto/log

  nodered:
    image: nodered/node-red:latest
    container_name: nodered
    ports:
      - "1880:1880"
    networks:
      - open5gs
    volumes:
      - nodered_data:/data
    restart: unless-stopped

  edge:
    image: python:3.11-slim
    container_name: edge
    working_dir: /app
    volumes:
      - ./edge/app.py:/app/app.py:ro
    command: sh -lc "pip install -q flask paho-mqtt && python /app/app.py"
    environment:
      - MQTT_HOST=mqtt
      - MQTT_PORT=1883
      - MQTT_TOPIC=veh/telemetry
    ports:
      - "5000:5000"
    networks:
      - open5gs

  sim-iot-01:
    image: python:3.11-slim
    container_name: sim-iot-01
    network_mode: "container:ue-iot-01"
    volumes:
      - ../../apps/iot-scripts:/iot:ro
    command: sh -lc "pip install -q paho-mqtt && python /iot/ue-iot-01.py"
    restart: unless-stopped

  sim-iot-02:
    image: python:3.11-slim
    container_name: sim-iot-02
    network_mode: "container:ue-iot-02"
    volumes:
      - ../../apps/iot-scripts:/iot:ro
    command: sh -lc "pip install -q paho-mqtt && python /iot/ue-iot-02.py"
    restart: unless-stopped

  sim-iot-03:
    image: python:3.11-slim
    container_name: sim-iot-03
    network_mode: "container:ue-iot-03"
    volumes:
      - ../../apps/iot-scripts:/iot:ro
    command: sh -lc "pip install -q paho-mqtt && python /iot/ue-iot-03.py"
    restart: unless-stopped

  sim-veh-01:
    image: python:3.11-slim
    container_name: sim-veh-01
    network_mode: "container:ue-veh-01"
    volumes:
      - ../../apps/veh-scripts:/veh:ro
    environment:
      - EDGE_URL=http://edge:5000/telemetry
      - UE_NAME=ue-veh-01
    command: sh -lc "pip install -q requests && python /veh/ue-veh-01.py"
    restart: unless-stopped

  sim-veh-02:
    image: python:3.11-slim
    container_name: sim-veh-02
    network_mode: "container:ue-veh-02"
    volumes:
      - ../../apps/veh-scripts:/veh:ro
    environment:
      - EDGE_URL=http://edge:5000/telemetry
      - UE_NAME=ue-veh-02
    command: sh -lc "pip install -q requests && python /veh/ue-veh-02.py"
    restart: unless-stopped

volumes:
  mqtt_data:
  mqtt_log:
  nodered_data:

networks:
  open5gs:
    external: true
```

**Key design decisions:**

The simulators use `python:3.11-slim` as a base image and install their dependencies at startup via `pip install -q`. This avoids maintaining custom Docker images for lightweight scripts. The `restart: unless-stopped` policy ensures simulators automatically reconnect if the UE container restarts. Scripts are mounted read-only from the `apps/` directory so code changes take effect on next container restart without rebuilding images.

---

## 4. Use Case Data Flows

### 4.1 IoT → MQTT Flow (Slice 1)

This is the end-to-end path for IoT sensor data from a simulator through the 5G network to the MQTT broker:

```
sim-iot-01          ue-iot-01          gNB              UPF1            MQTT
(Python)         (uesimtun0)       (GTP-U)        (NAT/Forward)    (Mosquitto)
    │                 │                │                │               │
    │  MQTT CONNECT   │                │                │               │
    │────────────────►│  GTP-U encap   │                │               │
    │                 │───────────────►│  N3 forward    │               │
    │                 │                │───────────────►│  Decap + NAT  │
    │                 │                │                │──────────────►│
    │                 │                │                │               │
    │  MQTT PUBLISH   │                │                │               │
    │  iot/ue-iot-01  │                │                │               │
    │  {"temp": 3.2}  │                │                │               │
    │────────────────►│───────────────►│───────────────►│──────────────►│
    │                 │                │                │               │
    │        (repeats every 3 seconds)                                  │
```

The MQTT connection is established once when the simulator starts. Subsequent publishes reuse the persistent TCP connection.

### 4.2 Vehicle → Edge Flow (Slice 2)

Vehicle simulators send HTTP POST requests to the Edge server, which processes and re-publishes the data:

```
sim-veh-01          ue-veh-01          gNB              UPF2            Edge
(Python)         (uesimtun0)       (GTP-U)        (NAT/Forward)     (Flask)
    │                 │                │                │               │
    │  HTTP POST      │                │                │               │
    │  /telemetry     │  GTP-U encap   │  N3 forward    │  Decap + NAT  │
    │  {"speed":67}   │                │                │               │
    │────────────────►│───────────────►│───────────────►│──────────────►│
    │                 │                │                │               │
    │  HTTP 200 OK    │                │                │               │
    │  {"status":"ok"}│                │                │               │
    │◄────────────────│◄───────────────│◄───────────────│◄──────────────│
    │                 │                │                │               │
    │        (repeats every 2 seconds)                                  │
                                                                        │
                                                        Edge re-publishes
                                                        to MQTT topic:
                                                        veh/telemetry
```

Unlike the IoT simulators which use persistent MQTT connections, the vehicle simulators make individual HTTP requests. Each request-response pair traverses the full 5G path in both directions.

### 4.3 Restricted Internal Flow (Slice 3)

Slice 3 demonstrates restricted connectivity. The UE can reach internal services but not the internet:

```
UE3 (Slice 3)           gNB              UPF3
(uesimtun0)          (GTP-U)        (iptables)
    │                    │               │
    │  ping mqtt         │               │
    │  (10.33.33.X)      │               │
    │───────────────────►│──────────────►│──► Docker net ──► MQTT ✓
    │                    │               │
    │  ping 8.8.8.8      │               │
    │  (external)        │               │
    │───────────────────►│──────────────►│──✕ DROPPED (iptables)
    │                    │               │
    │  No response       │               │
    │  (timeout)         │               │
```

The UPF3 container has NAT disabled or iptables FORWARD rules that drop traffic destined for addresses outside the Docker network (`10.33.33.0/24`). The GTP tunnel and PDU session work normally — only the forwarding policy at the UPF prevents external access.

---

## 5. PacketRusher Load Testing

### 5.1 PacketRusher Architecture

PacketRusher is an alternative RAN simulator that combines gNB and UE functionality in a single binary. Unlike UERANSIM (which runs separate `nr-gnb` and `nr-ue` processes), PacketRusher is designed for load testing — it can register multiple UEs concurrently and establish PDU sessions in parallel.

```
┌─────────────────────────────────────────────────────────────┐
│                    PacketRusher Setup                         │
│                                                             │
│  ┌──────────────┐   NGAP (N2)    ┌──────┐                  │
│  │ PacketRusher │───────────────►│ AMF  │                  │
│  │              │   :38412       │      │                  │
│  │  gNB + UE    │                └──────┘                  │
│  │  combined    │   GTP-U (N3)   ┌──────┐    ┌──────────┐  │
│  │              │───────────────►│ UPF  │───►│ iperf3   │  │
│  │  Multi-UE    │   :2152        │      │    │ server   │  │
│  │  load gen    │                └──────┘    │ :5201    │  │
│  └──────────────┘                            └──────────┘  │
│                                                             │
│  Privileged mode required for:                              │
│  • gtp5g kernel module (GTP-U tunnel)                       │
│  • NET_ADMIN capability (network interfaces)                │
└─────────────────────────────────────────────────────────────┘
```

**Key differences from UERANSIM:**

PacketRusher and UERANSIM serve different purposes. UERANSIM runs persistent UEs for application-level testing (simulators), while PacketRusher is optimized for load testing — registering many UEs quickly and measuring throughput. The project uses both: UERANSIM for the network slicing deployment with use case simulators, and PacketRusher for the speed-test deployment with iperf3 throughput measurement.

### 5.2 Speed Test Deployment

The PacketRusher load testing uses a separate compose file (`compose-files/speed-test/docker-compose.yaml`) with a simplified 5G core — single SMF, single UPF, no network slicing:

| Service                                      | Purpose                                  |
| -------------------------------------------- | ---------------------------------------- |
| db, nrf, ausf, udm, udr, nssf, bsf, pcf, amf | Standard Open5GS 5G core                 |
| smf                                          | Single SMF (no per-slice split)          |
| upf                                          | Single UPF (no per-slice split)          |
| packetrusher                                 | Combined gNB + UE load generator         |
| iperf                                        | iperf3 server for throughput testing     |
| webui                                        | Open5GS web UI for subscriber management |

This deployment uses configs from `configs/speed-test/` which are tuned for single-slice operation. The core network is the same Open5GS stack, just without the multi-slice SMF/UPF split.

### 5.3 PacketRusher Configuration

**Configuration file:** `configs/speed-test/packetrusher.yaml`

```yaml
gnodeb:
  controlif:
    ip: "gnb.packetrusher.org"
    port: 38412
  dataif:
    ip: "gnb.packetrusher.org"
    port: 2152
  plmnlist:
    mcc: "001"
    mnc: "01"
    tac: "000001"
    gnbid: "000008"
  slicesupportlist:
    sst: "01"
    sd: "000001"

ue:
  hplmn:
    mcc: "001"
    mnc: "01"
  msin: "1234567891"
  routingindicator: "0000"
  protectionScheme: 0
  key: "00000000000000000000000000000000"
  opc: "00000000000000000000000000000000"
  amf: "8000"
  sqn: "00000000"
  dnn: "internet"
  snssai:
    sst: "01"
    sd: "000001"
  integrity:
    nia0: false
    nia1: false
    nia2: true
    nia3: false
  ciphering:
    nea0: true
    nea1: false
    nea2: true
    nea3: false

amfif:
  - ip: "amf.open5gs.org"
    port: 38412

logs:
  level: 4
```

**Key configuration details:**

The gNB section defines the N2 (control) and N3 (data) interface addresses using DNS names resolved within the Docker network. The UE section specifies the subscriber identity (MSIN `1234567891`), authentication credentials (key, OPC, AMF), and the requested slice (SST 1, SD 000001). The subscriber must be pre-provisioned in MongoDB with matching credentials for registration to succeed. The AMF interface section tells PacketRusher where to find the AMF for the initial NGAP connection.

### 5.4 iperf3 Throughput Testing

An iperf3 server runs alongside PacketRusher to measure actual GTP tunnel throughput:

```yaml
iperf:
  container_name: iperf
  image: "mlabbe/iperf3:latest"
  networks:
    open5gs:
      aliases:
        - test.iperf.org
```

**How throughput testing works:**

1. PacketRusher establishes a PDU session (creating a GTP-U tunnel)
2. From inside the PacketRusher container, run iperf3 in client mode through the tunnel
3. Traffic flows: PacketRusher → GTP-U tunnel → UPF → Docker network → iperf3 server
4. iperf3 measures bandwidth, jitter, and packet loss

**Manual iperf3 commands:**

```bash
# Upload test (UE → server)
docker exec packetrusher iperf3 -c test.iperf.org -t 5

# Download test (server → UE)
docker exec packetrusher iperf3 -c test.iperf.org -t 5 -R

# UDP test with target bandwidth
docker exec packetrusher iperf3 -c test.iperf.org -t 5 -u -b 100M
```

### 5.5 Load Test Compose File

The full PacketRusher compose setup is at `compose-files/speed-test/docker-compose.yaml`. The PacketRusher service definition:

```yaml
packetrusher:
  container_name: packetrusher
  image: "fgftk/packetrusher:${PACKETRUSHER_VERSION}"
  command: "--config /PacketRusher/config/packetrusher.yaml ue"
  restart: unless-stopped
  networks:
    open5gs:
      aliases:
        - gnb.packetrusher.org
  configs:
    - source: packetrusher_config
      target: /PacketRusher/config/packetrusher.yaml
  privileged: true
  cap_add:
    - ALL
  depends_on:
    - amf
    - smf
    - pcf
    - udr
```

**Why privileged mode?** PacketRusher needs to load the `gtp5g` kernel module and create GTP-U tunnel interfaces. This requires elevated privileges (`privileged: true`) and all Linux capabilities (`cap_add: ALL`). The `depends_on` ensures the core network functions are running before PacketRusher attempts to register.

---

## 6. Running Everything

### 6.1 Running the Verification Tests

Prerequisites: The network slicing deployment must be running with all UEs registered.

```bash
# 1. Start the 5G core (network slicing mode)
cd compose-files/network-slicing
docker compose up -d

# 2. Wait for UEs to register (~30 seconds)
# Check UE1 has a tunnel interface:
docker exec ue1 ip addr show uesimtun0

# 3. Start the apps layer (MQTT, Edge, Node-RED)
cd ../apps
docker compose -f docker-compose.apps.yaml up -d

# 4. Run tests via the framework API
curl -X POST http://localhost:8000/api/tests/run | python3 -m json.tool

# Or run individual tests manually:
docker exec ue1 ping -c 2 mqtt          # Should succeed
docker exec ue1 ping -c 2 8.8.8.8       # Should succeed
docker exec ue2 ping -c 2 mqtt          # Should succeed
docker exec ue3 ping -c 2 mqtt          # Should succeed
docker exec ue3 ping -c 2 8.8.8.8       # Should FAIL (blocked)
```

### 6.2 Running the Use Case Simulators

The simulators require the network slicing core + apps to be running:

```bash
# 1. Start core + apps (if not already running)
cd compose-files/network-slicing
docker compose up -d
cd ../apps
docker compose -f docker-compose.apps.yaml up -d

# 2. Verify simulators are running
docker ps --filter "name=sim-"

# 3. Watch simulator logs
docker logs -f sim-iot-01    # IoT environmental sensor
docker logs -f sim-veh-01    # Vehicle GPS tracking
docker logs -f sim-veh-02    # Vehicle emergency alerts

# 4. Subscribe to MQTT topics to see live data
docker exec mqtt mosquitto_sub -t "iot/#" -v
docker exec mqtt mosquitto_sub -t "veh/#" -v

# 5. Open Node-RED dashboard in browser
# http://localhost:1880/ui
```

### 6.3 Running PacketRusher Load Tests

PacketRusher uses a separate deployment from the UERANSIM-based setup:

```bash
# 1. Stop any running UERANSIM deployment first
cd compose-files/network-slicing
docker compose down

# 2. Start the speed-test deployment
cd ../speed-test
docker compose up -d

# 3. Wait for PacketRusher to register (~15 seconds)
docker logs packetrusher

# 4. Run iperf3 throughput test
docker exec packetrusher iperf3 -c test.iperf.org -t 10

# 5. Stop when done
docker compose down
```

**Important:** The UERANSIM (network slicing) and PacketRusher (speed-test) deployments cannot run simultaneously because they share the same Docker network name and MongoDB database. Always stop one before starting the other.

---

## 7. Test Summary Matrix

| Category         | Test/Simulator    | Slice | Source       | Target     | Protocol | Expected Result      |
| ---------------- | ----------------- | ----- | ------------ | ---------- | -------- | -------------------- |
| **Verification** | UE1 → MQTT        | 1     | ue1          | mqtt       | ICMP     | ✅ Reachable         |
| **Verification** | UE1 → Internet    | 1     | ue1          | 8.8.8.8    | ICMP     | ✅ Reachable         |
| **Verification** | UE2 → MQTT        | 2     | ue2          | mqtt       | ICMP     | ✅ Reachable         |
| **Verification** | UE2 → Internet    | 2     | ue2          | 8.8.8.8    | ICMP     | ✅ Reachable         |
| **Verification** | UE3 → MQTT        | 3     | ue3          | mqtt       | ICMP     | ✅ Reachable         |
| **Verification** | UE3 → Node-RED    | 3     | ue3          | nodered    | ICMP     | ✅ Reachable         |
| **Isolation**    | UE3 → Internet    | 3     | ue3          | 8.8.8.8    | ICMP     | ❌ Blocked           |
| **Use Case**     | Environmental IoT | 1     | sim-iot-01   | mqtt:1883  | MQTT     | Publishes every 3s   |
| **Use Case**     | Air Quality IoT   | 1     | sim-iot-02   | mqtt:1883  | MQTT     | Publishes every 2s   |
| **Use Case**     | eHealth IoT       | 1     | sim-iot-03   | mqtt:1883  | MQTT     | Publishes every 3s   |
| **Use Case**     | Vehicle GPS       | 2     | sim-veh-01   | edge:5000  | HTTP     | Posts every 2s       |
| **Use Case**     | Vehicle Alerts    | 2     | sim-veh-02   | edge:5000  | HTTP     | Posts every 2s       |
| **Load Test**    | UE Registration   | —     | packetrusher | amf:38412  | NGAP     | Registration success |
| **Load Test**    | GTP Throughput    | —     | packetrusher | iperf:5201 | TCP/UDP  | Measured Mbps        |

---

## File Locations

| File                                            | Description                                     |
| ----------------------------------------------- | ----------------------------------------------- |
| `framework/tests.py`                            | Automated verification test suite               |
| `framework/app.py`                              | FastAPI backend exposing test API               |
| `apps/iot-scripts/ue-iot-01.py`                 | Environmental monitoring simulator              |
| `apps/iot-scripts/ue-iot-02.py`                 | Air quality monitoring simulator                |
| `apps/iot-scripts/ue-iot-03.py`                 | eHealth sensor station simulator                |
| `apps/veh-scripts/ue-veh-01.py`                 | Vehicle GPS tracking simulator                  |
| `apps/veh-scripts/ue-veh-02.py`                 | Vehicle emergency alerts simulator              |
| `apps/edge/app.py`                              | Edge server (Flask) receiving vehicle telemetry |
| `compose-files/apps/docker-compose.apps.yaml`   | Apps + simulators compose file                  |
| `compose-files/apps/mqtt/config/mosquitto.conf` | MQTT broker configuration                       |
| `compose-files/speed-test/docker-compose.yaml`  | PacketRusher load test compose file             |
| `configs/speed-test/packetrusher.yaml`          | PacketRusher gNB + UE configuration             |
| `framework/templates/verify.html`               | Verification test UI page                       |
| `framework/templates/usecases.html`             | Use cases management UI page                    |
