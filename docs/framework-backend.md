# Framework Backend

[← Back to Main README](../README.md)

This document describes each Python module in the `framework/` folder. The framework backend is a FastAPI application that provides a REST API for managing the 5G network — topology visualization, container control, automated testing, QoS management, use case orchestration, load testing, and call simulation. All modules interact with Docker containers via `subprocess` calls to the Docker CLI.

---

## Table of Contents

1. [Overview](#1-overview)
2. [app.py — FastAPI Main Application](#2-apppy--fastapi-main-application)
   - 2.1 [Application Setup](#21-application-setup)
   - 2.2 [API Endpoint Reference](#22-api-endpoint-reference)
3. [topology.py — Container Topology](#3-topologypy--container-topology)
4. [control.py — Container Lifecycle Control](#4-controlpy--container-lifecycle-control)
5. [tests.py — Automated Verification Tests](#5-testspy--automated-verification-tests)
6. [dockerctl.py — Low-Level Docker CLI Wrapper](#6-dockerctlpy--low-level-docker-cli-wrapper)
7. [transport.py — QoS and Traffic Control](#7-transportpy--qos-and-traffic-control)
   - 7.1 [QoS Profiles](#71-qos-profiles)
   - 7.2 [Slice Mapping](#72-slice-mapping)
   - 7.3 [Traffic Control Functions](#73-traffic-control-functions)
   - 7.4 [Auto-Configuration](#74-auto-configuration)
8. [usecases.py — Use Case Simulator Management](#8-usecasespy--use-case-simulator-management)
9. [loadtest.py — PacketRusher Load Testing](#9-loadtestpy--packetrusher-load-testing)
   - 9.1 [Subscriber Provisioning](#91-subscriber-provisioning)
   - 9.2 [PacketRusher Lifecycle](#92-packetrusher-lifecycle)
   - 9.3 [Load Test Execution](#93-load-test-execution)
   - 9.4 [GTP Throughput Testing](#94-gtp-throughput-testing)
10. [callsim.py — Call Simulation](#10-callsimpy--call-simulation)
    - 10.1 [Call Profiles](#101-call-profiles)
    - 10.2 [Call Lifecycle](#102-call-lifecycle)
    - 10.3 [Signaling Logs](#103-signaling-logs)
    - 10.4 [MQTT Proof of Communication](#104-mqtt-proof-of-communication)
11. [Module Dependency Graph](#11-module-dependency-graph)

---

## 1. Overview

The framework backend consists of 9 Python modules (plus an empty `__init__.py`):

```
framework/
├── __init__.py          ← Empty (makes framework a Python package)
├── app.py               ← FastAPI main app — all API endpoints
├── topology.py          ← Reads container topology via docker inspect
├── control.py           ← Start/stop/restart via docker compose
├── tests.py             ← Automated verification (ping tests)
├── dockerctl.py         ← Low-level Docker CLI wrapper
├── transport.py         ← QoS profiles, tc rules, iptables (per slice)
├── usecases.py          ← Use case simulator start/stop management
├── loadtest.py          ← PacketRusher multi-UE load testing
├── callsim.py           ← Voice/Video/Emergency call simulation
└── templates/           ← HTML templates (covered in frontend doc)
```

**Common pattern:** Every module defines a `run()` helper that wraps `subprocess.run()` to execute Docker CLI commands. The modules are designed to be stateless (except `transport.py` and `callsim.py` which keep in-memory state for active rules and calls). All functions return dictionaries suitable for JSON serialization.

**How to run the backend:**

```bash
cd <project-root>
uvicorn framework.app:app --host 0.0.0.0 --port 8000 --reload
```

---

## 2. app.py — FastAPI Main Application

**File:** `framework/app.py`

This is the entry point for the framework backend. It creates the FastAPI application instance, configures CORS middleware, and registers all API endpoints. It imports functions from all other modules and exposes them as HTTP endpoints.

### 2.1 Application Setup

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from framework.topology import get_full_topology
from framework.control import up_all, down_all, restart_service
from framework.tests import test_suite
from framework.transport import (
    get_all_transport_status, get_tc_status, apply_tc_rules,
    clear_tc_rules, clear_all_rules, apply_dscp_marking,
    auto_configure_qos, QOS_PROFILES
)
from framework.loadtest import (
    get_pr_status, start_packetrusher, stop_packetrusher,
    run_multi_ue_test, run_gtp_throughput_test, get_loadtest_summary
)
from framework.callsim import (
    initiate_call, terminate_call, get_call_status, get_call_profiles
)

app = FastAPI(title="5G Framework Backend", version="0.1.0")
```

CORS is configured to allow the frontend (running on ports 3000 or 5173 for development) to call the API:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:5173", "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 2.2 API Endpoint Reference

| Method | Path | Module | Description |
|--------|------|--------|-------------|
| GET | `/health` | app.py | Health check — returns `{"status": "ok"}` |
| **Topology** ||||
| GET | `/api/topology` | app.py (inline) | Lightweight container list (name + status) |
| GET | `/api/topology/full` | topology.py | Full topology with images, state, network IPs |
| **Control** ||||
| POST | `/api/control/up` | control.py | Start 5G core + apps (`docker compose up -d`) |
| POST | `/api/control/down` | control.py | Stop apps + core (`docker compose down`) |
| POST | `/api/control/restart/{name}` | control.py | Restart a single container by name |
| **Tests** ||||
| POST | `/api/tests/run` | tests.py | Run full verification test suite |
| **Transport** ||||
| GET | `/api/transport/status` | transport.py | QoS status for all 3 slices |
| GET | `/api/transport/status/{slice_id}` | transport.py | QoS status for one slice |
| GET | `/api/transport/profiles` | transport.py | List available QoS profiles |
| POST | `/api/transport/apply/{slice_id}` | transport.py | Apply QoS rules to a slice |
| POST | `/api/transport/clear/{slice_id}` | transport.py | Clear tc rules for a slice |
| POST | `/api/transport/clear-all` | transport.py | Clear all transport rules |
| POST | `/api/transport/dscp/{slice_id}` | transport.py | Apply DSCP packet marking |
| POST | `/api/transport/auto-configure` | transport.py | Auto-apply QoS per active use cases |
| **Use Cases** ||||
| GET | `/api/usecases` | usecases.py | List all use cases with status |
| POST | `/api/usecases/start/{uc_id}` | usecases.py | Start a specific use case |
| POST | `/api/usecases/stop/{uc_id}` | usecases.py | Stop a specific use case |
| POST | `/api/usecases/start-all` | usecases.py | Start all simulators + auto QoS |
| POST | `/api/usecases/stop-all` | usecases.py | Stop all simulators + clear QoS |
| GET | `/api/usecases/logs/{uc_id}` | usecases.py | Last 30 lines of simulator logs |
| **Load Test** ||||
| GET | `/api/loadtest/status` | loadtest.py | PacketRusher status + subscriber count |
| GET | `/api/loadtest/summary` | loadtest.py | Full load test dashboard data |
| POST | `/api/loadtest/start` | loadtest.py | Start PacketRusher (single UE) |
| POST | `/api/loadtest/stop` | loadtest.py | Stop PacketRusher |
| POST | `/api/loadtest/multi-ue` | loadtest.py | Run multi-UE registration test |
| POST | `/api/loadtest/throughput` | loadtest.py | Run iperf3 GTP throughput test |
| **Call Simulation** ||||
| GET | `/api/calls/profiles` | callsim.py | Available call types (Voice/Video/Emergency) |
| GET | `/api/calls/status` | callsim.py | Current/recent call status + logs |
| POST | `/api/calls/initiate` | callsim.py | Start a call between UEs |
| POST | `/api/calls/terminate` | callsim.py | End the active call |

The lightweight `/api/topology` endpoint is implemented directly in `app.py` using an inline `_run()` helper:

```python
@app.get("/api/topology")
def topology_simple():
    out = _run(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"])
    containers = []
    for line in out.splitlines():
        if not line.strip():
            continue
        name, status = line.split("\t", 1)
        containers.append({"name": name.strip(), "status": status.strip()})
    containers.sort(key=lambda x: x["name"])
    return {"containers": containers}
```

---

## 3. topology.py — Container Topology

**File:** `framework/topology.py`

Provides detailed container topology information by running `docker ps` to list containers and `docker inspect` on each to extract networking details.

**Exported function:**

```python
def get_full_topology() -> Dict[str, Any]:
```

**How it works:**

1. Runs `docker ps --format "{{.Names}}"` to get all running container names
2. For each container, runs `docker inspect <name>` and parses the JSON output
3. Extracts: container name, state (running/stopped), image name, and network info
4. Network info per container includes: network name, IP address, gateway, MAC address

**Return format:**

```json
{
  "containers": [
    {
      "name": "amf",
      "state": "running",
      "image": "fgftk/amf-open5gs:v2.7.5",
      "networks": [
        {
          "network": "open5gs",
          "ip": "10.33.33.5",
          "gateway": "10.33.33.1",
          "mac": "02:42:0a:21:21:05"
        }
      ]
    }
  ]
}
```

The containers are sorted alphabetically by name. This data powers the topology visualization page, which displays all containers as nodes with their IP addresses and connections.

---

## 4. control.py — Container Lifecycle Control

**File:** `framework/control.py`

Manages starting, stopping, and restarting the entire 5G deployment using Docker Compose commands.

**Constants:**

```python
NETWORK_SLICE_COMPOSE = "compose-files/network-slicing/docker-compose.yaml"
APPS_COMPOSE = "compose-files/apps/docker-compose.apps.yaml"
ENV_FILE = "build-files/open5gs.env"
```

**Exported functions:**

`up_all()` — Brings up the full deployment in two stages: first the 5G core (network slicing compose), then the application services (MQTT, Node-RED, Edge). Returns the stdout from both compose commands.

```python
def up_all() -> Dict[str, str]:
    out1 = run(["docker", "compose", "-f", NETWORK_SLICE_COMPOSE,
                "--env-file", ENV_FILE, "up", "-d"])
    out2 = run(["docker", "compose", "-f", APPS_COMPOSE,
                "--env-file", ENV_FILE, "up", "-d", "mqtt", "nodered", "edge"])
    return {"core": out1, "apps": out2}
```

`down_all()` — Stops everything in reverse order: apps first, then core. This ensures simulators depending on UE containers are stopped before the UEs themselves.

`restart_service(name)` — Restarts a single container by name using `docker restart <name>`. Useful for recovering a crashed service without disrupting the rest.

---

## 5. tests.py — Automated Verification Tests

**File:** `framework/tests.py`

Runs connectivity verification tests by executing `ping` commands inside UE containers.

**Exported functions:**

`ping_from(container, target, count=2)` — Runs `docker exec -t <container> sh -lc "ping -c <count> <target>"` and returns the raw output. Successful tests show RTT times and `0% packet loss`. Failed tests return an error message or `100% packet loss`.

`test_suite()` — Runs the full test suite across all 3 UEs and returns grouped results:

```python
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

The key test is `ue3.ping_internet_should_fail` — this must fail (timeout or 100% loss) to prove Slice 3 internet blocking works. All other tests should succeed.

---

## 6. dockerctl.py — Low-Level Docker CLI Wrapper

**File:** `framework/dockerctl.py`

A utility module providing basic Docker operations. Used by other modules when they need simple container listing without the full topology inspection.

**Exported functions:**

`run(cmd)` — Wraps `subprocess.run()` with error handling. Raises `RuntimeError` on failure with stdout, stderr, and exit code details.

`list_containers()` — Returns a sorted list of `{name, status}` dictionaries for all running containers. Uses `docker ps --format "{{.Names}}\t{{.Status}}"`.

---

## 7. transport.py — QoS and Traffic Control

**File:** `framework/transport.py`

The most complex module. Manages per-slice Quality of Service using Linux `tc` (traffic control) for bandwidth shaping and latency simulation, and `iptables` for DSCP packet marking. All commands run inside Docker containers via `docker exec`.

### 7.1 QoS Profiles

Six predefined profiles covering common 5G use cases:

| Profile ID | Name | ↓ Bandwidth | ↑ Bandwidth | Latency | Jitter | Loss | Priority |
|------------|------|-------------|-------------|---------|--------|------|----------|
| `iot-default` | IoT Default | 5 Mbit | 2 Mbit | 50 ms | 10 ms | 0% | 3 |
| `vehicle-default` | Vehicle / URLLC | 50 Mbit | 25 Mbit | 5 ms | 2 ms | 0% | 1 |
| `restricted-default` | Restricted Internal | 2 Mbit | 1 Mbit | 20 ms | 5 ms | 0% | 4 |
| `embb` | Enhanced Mobile Broadband | 100 Mbit | 50 Mbit | 10 ms | 3 ms | 0% | 2 |
| `emergency` | Emergency / Mission-Critical | 30 Mbit | 15 Mbit | 2 ms | 1 ms | 0% | 0 |
| `degraded` | Degraded Network Simulation | 1 Mbit | 512 kbit | 200 ms | 50 ms | 5% | 5 |

Each profile is a dictionary stored in `QOS_PROFILES`. Custom values can override any profile parameter.

### 7.2 Slice Mapping

The `SLICE_MAP` dictionary maps each slice to its UPF container, tunnel interface, IP subnet, and UE container:

```python
SLICE_MAP = {
    "slice1": {"upf": "upf1", "interface": "ogstun", "subnet": "10.45.0.0/16", "ue": "ue1"},
    "slice2": {"upf": "upf2", "interface": "ogstun", "subnet": "10.46.0.0/16", "ue": "ue2"},
    "slice3": {"upf": "upf3", "interface": "ogstun", "subnet": "10.47.0.0/16", "ue": "ue3"},
}
```

Traffic shaping is applied at two points: the UPF's `ogstun` interface (download direction) and the UE's `uesimtun0` interface (upload direction).

### 7.3 Traffic Control Functions

`apply_tc_rules(slice_id, profile_id, bandwidth_down, bandwidth_up, latency_ms, jitter_ms, loss_pct)` — The main function. Applies tc rules to a slice. Workflow:

1. Clear any existing rules on both UPF and UE
2. Create HTB (Hierarchical Token Bucket) qdisc on UPF `ogstun` for download bandwidth limiting
3. Add `netem` qdisc for latency/jitter/loss simulation
4. Create HTB qdisc on UE `uesimtun0` for upload bandwidth limiting
5. Store active rules in `_active_rules` dict for status reporting

The `tc` commands executed inside containers:

```bash
# Download shaping (inside UPF container)
tc qdisc add dev ogstun root handle 1: htb default 10
tc class add dev ogstun parent 1: classid 1:10 htb rate 5mbit ceil 5mbit
tc qdisc add dev ogstun parent 1:10 handle 10: netem delay 50ms 10ms

# Upload shaping (inside UE container)
tc qdisc add dev uesimtun0 root handle 1: htb default 10
tc class add dev uesimtun0 parent 1: classid 1:10 htb rate 2mbit ceil 2mbit
```

`clear_tc_rules(slice_id)` — Removes all tc qdiscs from both UPF and UE interfaces.

`apply_dscp_marking(slice_id, dscp_value)` — Uses iptables mangle table to mark packets with a DSCP value for prioritization (EF=46 for voice, AF41=34 for video, etc.).

`get_tc_status(slice_id)` — Queries current tc rules on both UPF and UE and returns the raw output along with the active profile information.

`get_all_transport_status()` — Returns status for all 3 slices, available profiles, and active rules.

### 7.4 Auto-Configuration

`auto_configure_qos(use_case_ids)` — Automatically applies the correct QoS profile for each slice based on active use cases:

```python
USE_CASE_QOS_MAP = {
    "iot-environment":  {"slice": "slice1", "profile": "iot-default"},
    "smart-city":       {"slice": "slice1", "profile": "iot-default"},
    "ehealth":          {"slice": "slice1", "profile": "iot-default"},
    "vehicle-gps":      {"slice": "slice2", "profile": "vehicle-default"},
    "vehicle-alerts":   {"slice": "slice2", "profile": "emergency"},
    "restricted-iot":   {"slice": "slice3", "profile": "restricted-default"},
}
```

When multiple use cases share the same slice, the function selects the highest priority profile (lowest priority number). For example, if both `vehicle-gps` (priority 1) and `vehicle-alerts` (priority 0) are active on Slice 2, the emergency profile is applied.

---

## 8. usecases.py — Use Case Simulator Management

**File:** `framework/usecases.py`

Manages the lifecycle of use case simulator containers (sim-iot-01, sim-iot-02, sim-iot-03, sim-veh-01, sim-veh-02). Each use case maps to one or more Docker containers.

**Key data structure:**

```python
USE_CASES = {
    "iot-environment":  {"name": "Environmental IoT", "services": ["sim-iot-01"], "slice": "slice1", "icon": "🌡"},
    "smart-city":       {"name": "Smart City Air",    "services": ["sim-iot-02"], "slice": "slice1", "icon": "🏙"},
    "ehealth":          {"name": "eHealth Sensors",   "services": ["sim-iot-03"], "slice": "slice1", "icon": "🏥"},
    "vehicle-gps":      {"name": "Vehicle GPS",       "services": ["sim-veh-01"], "slice": "slice2", "icon": "🚗"},
    "vehicle-alerts":   {"name": "Emergency Alerts",  "services": ["sim-veh-02"], "slice": "slice2", "icon": "🚨"},
}
```

**Exported functions:**

`start_usecase(uc_id)` — Starts the Docker containers for a specific use case using `docker compose up -d <service-names>`.

`stop_usecase(uc_id)` — Stops and removes the simulator containers using `docker stop` + `docker rm`.

`start_all_usecases()` — Starts all simulators and then calls `auto_configure_qos()` from `transport.py` to apply matching QoS profiles automatically.

`stop_all_usecases()` — Stops all simulators and calls `clear_all_rules()` from `transport.py` to remove QoS shaping.

`get_usecase_logs(uc_id, lines=30)` — Returns the last N lines of container logs using `docker logs --tail <n>`.

The module uses lazy imports for `transport.py` to avoid circular dependencies, since both modules reference each other's data structures.

---

## 9. loadtest.py — PacketRusher Load Testing

**File:** `framework/loadtest.py`

Integrates PacketRusher for performance and stress testing. While UERANSIM verifies that network slicing works correctly, PacketRusher answers the question: how many UEs can the network handle and how fast?

**Constants:**

```python
PROJECT_ROOT = Path(__file__).parent.parent
PR_COMPOSE = str(PROJECT_ROOT / "compose-files/network-slicing/docker-compose.packetrusher.yaml")
ENV_FILE = str(PROJECT_ROOT / "build-files/open5gs.env")
BASE_IMSI_NUM = 100    # Starting MSIN: 0000000100
PR_KEY = "00000000000000000000000000000000"
PR_OPC = "00000000000000000000000000000000"
```

### 9.1 Subscriber Provisioning

`provision_subscribers(count)` — Registers PacketRusher UE subscribers in MongoDB before load testing. For each UE, it executes a `mongosh` command inside the `db` container to upsert a subscriber record with the correct IMSI, authentication keys, and slice configuration. IMSIs start at `001010000000100` and increment (100, 101, 102, ...).

`get_subscriber_count()` — Counts how many PacketRusher subscribers exist in the database using a regex query on the IMSI field.

### 9.2 PacketRusher Lifecycle

`get_pr_status()` — Checks if the PacketRusher and iperf-server containers are running, returns their status along with recent logs and subscriber count.

`start_packetrusher(mode)` — Provisions a subscriber, stops any existing instance, then starts PacketRusher via `docker compose up -d`.

`stop_packetrusher()` — Stops and removes the PacketRusher container. Keeps the iperf-server running for subsequent tests.

### 9.3 Load Test Execution

`run_multi_ue_test(num_ues)` — The core load test function:

1. Provisions N subscribers in MongoDB
2. Stops any existing PacketRusher instance
3. Ensures iperf-server is running
4. Runs PacketRusher in `multi-ue` mode with `docker run` (foreground, captures output)
5. Parses the output for registration successes and errors using regex
6. Returns metrics: elapsed time, registrations detected, errors, average registration time per UE

The PacketRusher multi-ue command:

```bash
docker run --rm --privileged --network open5gs \
  fgftk/packetrusher:main \
  --config /PacketRusher/config/packetrusher.yaml \
  multi-ue -n <count> --timeBetweenRegistration 100
```

### 9.4 GTP Throughput Testing

`run_gtp_throughput_test(duration)` — Measures actual GTP tunnel throughput using iperf3:

1. Verifies both PacketRusher and iperf-server are running
2. Runs iperf3 upload test from inside the PacketRusher container (JSON output mode)
3. Runs iperf3 download test (reverse mode)
4. Parses JSON results to extract Mbps, bytes transferred, and retransmits

Traffic flows through the real GTP-U tunnel: PacketRusher → GTP tunnel → UPF → Docker network → iperf-server. This measures actual 5G user plane performance, not just Docker networking.

---

## 10. callsim.py — Call Simulation

**File:** `framework/callsim.py`

Simulates Voice, Video, and Emergency calls between UEs using MQTT as the transport layer for proof of communication. Calls generate realistic 5G NAS/SIP signaling logs and exchange real MQTT messages during the call.

### 10.1 Call Profiles

Three call types with different QoS characteristics:

| Call Type | 5QI | QFI | Bandwidth | Codec | Setup Time | Packet Interval | Priority |
|-----------|-----|-----|-----------|-------|------------|-----------------|----------|
| `voice` | 1 | 1 | 64 kbps | AMR-WB | 1800 ms | 200 ms | 5 |
| `video` | 2 | 2 | 2 Mbps | H.264 720p | 2200 ms | 50 ms | 4 |
| `emergency` | 69 | 3 | 64 kbps | AMR-WB (Priority) | 500 ms | 150 ms | 0 |

Emergency calls connect in 500 ms (vs. 1800 ms for voice) and have the highest priority (0), demonstrating 5G's priority-based QoS handling.

### 10.2 Call Lifecycle

`initiate_call(caller, callee, call_type)` — Starts a call in a background thread:

1. **Phase 1 — Signaling setup**: Generates 5G NAS/SIP signaling log entries with realistic timing based on the call profile's `setup_time_ms`
2. **Phase 2 — Active call**: Continuously exchanges MQTT messages between caller and callee at the profile's `packet_interval`. Each message carries the call metadata (sequence number, codec, size).
3. Call state is tracked in `_calls` dict (thread-safe via `_call_lock`)

`terminate_call(call_id)` — Ends the active call, generates termination logs (SIP BYE, QoS flow release), publishes termination event to MQTT, and returns final statistics (packets sent/received, bytes, duration).

`get_call_status(call_id)` — Returns the current call state, logs, and live statistics. If no call_id is provided, returns the most recent call.

### 10.3 Signaling Logs

The module generates realistic 5G signaling logs for each call type. For voice/video calls:

```
[NAS] Service Request from UE1
[AMF] Authentication: 5G-AKA — OK
[SMF] QoS Flow Request — 5QI=1 QFI=1 Priority=5
[SMF] Dedicated Bearer: 64 kbps AMR-WB
[UPF] GTP-U tunnel: UE1 ↔ UE2 TEID=45678
[IMS] INVITE sip:UE2@ims.open5gs.org
[IMS] 180 Ringing — UE2
[IMS] 200 OK — Call Connected (1800ms)
[RTP] Media session: AMR-WB 64 kbps — QFI=1
```

For emergency calls, the logs show bypassed authentication and priority pre-emption:

```
[NAS] ⚡ Emergency Service Request from UE1 — Dialing 112
[AMF] Emergency registration — BYPASSING normal authentication
[AMF] Priority Level: 0 (HIGHEST) — Pre-emption ENABLED
[SMF] Emergency QoS Flow — 5QI=69 QFI=3 ARP Priority=1
[IMS] ⚡ 112 Emergency — Connected in 500ms (priority bypass)
```

### 10.4 MQTT Proof of Communication

During an active call, actual MQTT messages are exchanged via the `mqtt` container using `mosquitto_pub`. This provides real proof of communication through the 5G network:

```python
def _mqtt_publish(topic: str, payload: dict) -> bool:
    msg = json.dumps(payload)
    r = subprocess.run(
        ["docker", "exec", "mqtt", "mosquitto_pub", "-t", topic, "-m", msg],
        capture_output=True, text=True, timeout=5,
    )
    return r.returncode == 0
```

MQTT topics follow the pattern `call/<type>/<caller>/to/<callee>` (e.g., `call/voice/ue1/to/ue2`). ACK messages go in the reverse direction. Every 10 packets, a summary log is added showing running totals.

---

## 11. Module Dependency Graph

```
                         app.py
                       (FastAPI)
                     /    |    \     \        \
                    /     |     \     \        \
            topology  control  tests  transport  usecases  loadtest  callsim
               .py      .py    .py      .py       .py       .py       .py
                                         ↑          |
                                         |          |
                                         +----------+
                                    usecases imports
                                    auto_configure_qos
                                    from transport
                         
            dockerctl.py  ← utility module (used by app.py inline)
```

All modules use `subprocess` to call Docker CLI commands. The only cross-module dependency is between `usecases.py` and `transport.py` — when starting all use cases, the usecases module calls `auto_configure_qos()` from transport to apply matching QoS profiles. This import is done lazily (inside the function) to avoid circular dependency issues.

---

## File Locations

| File | Lines | Description |
|------|-------|-------------|
| `framework/__init__.py` | 0 | Empty package init |
| `framework/app.py` | ~100 | FastAPI app + all endpoint registrations |
| `framework/topology.py` | ~35 | Container topology via `docker inspect` |
| `framework/control.py` | ~30 | Compose up/down/restart |
| `framework/tests.py` | ~30 | Ping-based verification tests |
| `framework/dockerctl.py` | ~25 | Low-level Docker wrapper |
| `framework/transport.py` | ~280 | QoS profiles, tc rules, iptables, auto-config |
| `framework/usecases.py` | ~100 | Simulator lifecycle management |
| `framework/loadtest.py` | ~230 | PacketRusher provisioning + load tests |
| `framework/callsim.py` | ~260 | Call simulation with MQTT exchange |