# Docker Compose Files

[← Back to Main README](../README.md)

This document describes all Docker Compose files used to deploy the 5G network, application simulators, and load testing services. It covers every service definition, how the files relate to each other, how to launch them, and the design decisions behind the multi-file architecture.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Shared Infrastructure](#2-shared-infrastructure)
   - 2.1 [Docker Network](#21-docker-network)
   - 2.2 [Docker Volumes](#22-docker-volumes)
   - 2.3 [Docker Configs](#23-docker-configs)
   - 2.4 [Environment File](#24-environment-file)
3. [Basic Deployment — `docker-compose.yaml`](#3-basic-deployment--docker-composeyaml)
   - 3.1 [Services Overview](#31-services-overview)
   - 3.2 [Service Details](#32-service-details)
   - 3.3 [How to Launch](#33-how-to-launch)
4. [Network Slicing Deployment — `docker-compose.yaml`](#4-network-slicing-deployment--docker-composeyaml)
   - 4.1 [Services Overview](#41-services-overview)
   - 4.2 [Service Details](#42-service-details)
   - 4.3 [How to Launch](#43-how-to-launch)
5. [Use Case Simulators — `docker-compose.usecases.yaml`](#5-use-case-simulators--docker-composeusecasesyaml)
   - 5.1 [Services Overview](#51-services-overview)
   - 5.2 [Service Details](#52-service-details)
   - 5.3 [How to Launch](#53-how-to-launch)
6. [Application Services (Basic) — `docker-compose.apps.yaml`](#6-application-services-basic--docker-composeappsyaml)
7. [PacketRusher Load Testing — `docker-compose.packetrusher.yaml`](#7-packetrusher-load-testing--docker-composepacketrusheryaml)
   - 7.1 [Services Overview](#71-services-overview)
   - 7.2 [How to Launch](#72-how-to-launch)
8. [Multi-File Orchestration](#8-multi-file-orchestration)
9. [Container Startup Order](#9-container-startup-order)
10. [Complete Service Inventory](#10-complete-service-inventory)

---

## 1. Overview

The project uses multiple Docker Compose files to separate concerns. Each file manages a distinct layer of the system:

```
compose-files/
├── basic/
│   └── ueransim/
│       └── docker-compose.yaml              ← Basic 5G core + RAN + UEs (no slicing)
├── network-slicing/
│   ├── docker-compose.yaml                  ← Sliced 5G core + RAN + UEs
│   ├── docker-compose.usecases.yaml         ← IoT/Vehicle/Restricted simulators
│   └── docker-compose.packetrusher.yaml     ← PacketRusher load testing
└── apps/
    ├── docker-compose.apps.yaml             ← Application services (for basic mode)
    ├── mqtt/config/mosquitto.conf           ← MQTT broker configuration
    └── edge/app.py                          ← Edge server Flask application
```

**Why multiple files?** Each file can be started and stopped independently. You can bring up just the 5G core, then later add simulators, then add load testing — without restarting the core network. This also allows the basic and slicing deployments to coexist as separate stacks.

---

## 2. Shared Infrastructure

All Compose files share the same Docker network, volumes, and environment file. This is what allows containers from different Compose files to communicate with each other.

### 2.1 Docker Network

Every Compose file defines or references the same bridge network:

```yaml
networks:
  open5gs:
    name: open5gs
    driver: bridge
    driver_opts:
      com.docker.network.bridge.name: br-open5gs
    ipam:
      config:
        - subnet: 10.33.33.0/24
```

All containers get an IP in the `10.33.33.0/24` subnet. Docker DNS provides hostname resolution within this network — for example, `nrf.open5gs.org` resolves to the NRF container's IP. Some Compose files reference this as an external network (since another Compose file already created it):

```yaml
networks:
  open5gs:
    external: true
```

### 2.2 Docker Volumes

Two named volumes persist MongoDB data across restarts:

```yaml
volumes:
  db_data:
    name: open5gs_db_data
  db_config:
    name: open5gs_db_config
```

These ensure subscriber data (provisioned by `mongo-init.js`) survives `docker compose down && docker compose up` cycles. Without named volumes, all subscribers would be lost on restart.

### 2.3 Docker Configs

Open5GS and UERANSIM configs are mounted into containers using the Docker Compose `configs` feature. Each Compose file has a `configs:` section at the bottom that maps host files to container paths:

```yaml
configs:
  nrf_config:
    file: ../../configs/network-slicing/nrf.yaml
  amf_config:
    file: ../../configs/network-slicing/amf.yaml
  # ... one entry per NF/UE config
```

Services reference these configs to receive their YAML files:

```yaml
services:
  nrf:
    configs:
      - source: nrf_config
        target: /etc/open5gs/custom/nrf.yaml
```

### 2.4 Environment File

All Compose files consume `build-files/open5gs.env` via the `--env-file` flag. This provides version variables used in image tags:

```bash
docker compose -f docker-compose.yaml --env-file ../../build-files/open5gs.env up -d
```

Variables like `${OPEN5GS_VERSION}`, `${UERANSIM_VERSION}`, and `${MONGODB_VERSION}` are substituted into image names at runtime.

---

## 3. Basic Deployment — `docker-compose.yaml`

**Location:** `compose-files/basic/ueransim/docker-compose.yaml`

This file deploys a complete single-slice 5G network with UERANSIM as the RAN simulator.

### 3.1 Services Overview

| Service | Image | Role | Network Alias |
|---------|-------|------|---------------|
| `db` | `fgftk/mongodb:${MONGODB_VERSION}` | MongoDB for subscriber data | `db.open5gs.org` |
| `nrf` | `fgftk/nrf-open5gs:${OPEN5GS_VERSION}` | NF Repository Function | `nrf.open5gs.org` |
| `ausf` | `fgftk/ausf-open5gs:${OPEN5GS_VERSION}` | Authentication Server | `ausf.open5gs.org` |
| `udm` | `fgftk/udm-open5gs:${OPEN5GS_VERSION}` | Unified Data Management | `udm.open5gs.org` |
| `udr` | `fgftk/udr-open5gs:${OPEN5GS_VERSION}` | Unified Data Repository | `udr.open5gs.org` |
| `nssf` | `fgftk/nssf-open5gs:${OPEN5GS_VERSION}` | Network Slice Selection | `nssf.open5gs.org` |
| `bsf` | `fgftk/bsf-open5gs:${OPEN5GS_VERSION}` | Binding Support Function | `bsf.open5gs.org` |
| `pcf` | `fgftk/pcf-open5gs:${OPEN5GS_VERSION}` | Policy Control Function | `pcf.open5gs.org` |
| `smf` | `fgftk/smf-open5gs:${OPEN5GS_VERSION}` | Session Management | `smf.open5gs.org` |
| `upf` | `fgftk/upf-open5gs:${OPEN5GS_VERSION}` | User Plane Function | `upf.open5gs.org` |
| `amf` | `fgftk/amf-open5gs:${OPEN5GS_VERSION}` | Access & Mobility Mgmt | `amf.open5gs.org` |
| `gnb` | `fgftk/gnb-ueransim:${UERANSIM_VERSION}` | gNodeB (base station) | `gnb.ueransim.org` |
| `ue-iot-01` | `fgftk/ue-ueransim:${UERANSIM_VERSION}` | IoT UE 1 | — |
| `ue-iot-02` | `fgftk/ue-ueransim:${UERANSIM_VERSION}` | IoT UE 2 | — |
| `ue-iot-03` | `fgftk/ue-ueransim:${UERANSIM_VERSION}` | IoT UE 3 | — |
| `ue-veh-01` | `fgftk/ue-ueransim:${UERANSIM_VERSION}` | Vehicle UE 1 | — |
| `ue-veh-02` | `fgftk/ue-ueransim:${UERANSIM_VERSION}` | Vehicle UE 2 | — |
| `webui` | `fgftk/webui-open5gs:${OPEN5GS_VERSION}` | Open5GS Web UI | — |

**Total: 18 containers**

### 3.2 Service Details

#### Database (`db`)

```yaml
db:
  container_name: db
  image: "fgftk/mongodb:${MONGODB_VERSION}"
  command: "mongod --bind_ip 0.0.0.0 --port 27017"
  networks:
    open5gs:
      aliases:
        - db.open5gs.org
  volumes:
    - db_data:/data/db
    - db_config:/data/configdb
  ports:
    - "0.0.0.0:27017:27017/tcp"
```

MongoDB stores subscriber data (IMSI, authentication keys, slice assignments) and PCF policy data. Port 27017 is exposed to the host so the Open5GS WebUI can connect. The named volumes (`db_data`, `db_config`) persist data across container restarts.

#### Core NFs (NRF, AUSF, UDM, UDR, NSSF, BSF, PCF, SMF, AMF)

All core NFs follow the same pattern:

```yaml
nrf:
  container_name: nrf
  image: "fgftk/nrf-open5gs:${OPEN5GS_VERSION}"
  command: "-c /etc/open5gs/custom/nrf.yaml"
  networks:
    open5gs:
      aliases:
        - nrf.open5gs.org
  configs:
    - source: nrf_config
      target: /etc/open5gs/custom/nrf.yaml
```

Each NF receives its YAML config via the `configs` mechanism and registers a DNS alias on the `open5gs` network. The `command` flag tells Open5GS which config file to use.

#### UPF

The UPF requires special privileges because it creates a TUN interface (`ogstun`) for tunneling user traffic:

```yaml
upf:
  container_name: upf
  image: "fgftk/upf-open5gs:${OPEN5GS_VERSION}"
  command: "-c /etc/open5gs/custom/upf.yaml"
  privileged: true
  cap_add:
    - NET_ADMIN
  networks:
    open5gs:
      aliases:
        - upf.open5gs.org
```

The `privileged: true` and `cap_add: NET_ADMIN` are required for the UPF entrypoint script to create the TUN interface, configure IP addresses, and set up iptables MASQUERADE rules for NAT.

#### gNodeB

```yaml
gnb:
  container_name: gnb
  image: "fgftk/gnb-ueransim:${UERANSIM_VERSION}"
  command: "-c /UERANSIM/config/gnb.yaml"
  networks:
    open5gs:
      aliases:
        - gnb.ueransim.org
  configs:
    - source: gnb_config
      target: /UERANSIM/config/gnb.yaml
```

The gNB connects to AMF on startup (NGAP/SCTP) and waits for UEs to attach. It uses a different config path (`/UERANSIM/config/`) than Open5GS NFs.

#### UEs

Each UE is a separate container with its own config:

```yaml
ue-iot-01:
  container_name: ue-iot-01
  image: "fgftk/ue-ueransim:${UERANSIM_VERSION}"
  command: "-c /UERANSIM/config/ue-iot-01.yaml"
  cap_add:
    - NET_ADMIN
  networks:
    - open5gs
  configs:
    - source: ue_iot_01_config
      target: /UERANSIM/config/ue-iot-01.yaml
```

`NET_ADMIN` is needed because UERANSIM creates a `uesimtun0` TUN interface for the PDU session. Each UE has its own unique IMSI and config file.

#### WebUI

```yaml
webui:
  container_name: webui
  image: "fgftk/webui-open5gs:${OPEN5GS_VERSION}"
  environment:
    DB_URI: "mongodb://${HOST_IP_ADDRESS}:27017/open5gs"
  ports:
    - "9999:9999"
  depends_on:
    - db
```

The Open5GS WebUI provides a browser interface at `http://localhost:9999` for manually managing subscribers. It connects to MongoDB using the host IP (from the env file) because it needs to reach the database from the host network.

### 3.3 How to Launch

```bash
cd compose-files/basic/ueransim/
docker compose --env-file ../../../build-files/open5gs.env up -d
```

---

## 4. Network Slicing Deployment — `docker-compose.yaml`

**Location:** `compose-files/network-slicing/docker-compose.yaml`

This is the primary deployment used by the project. It extends the basic setup with three network slices, each with dedicated SMF and UPF instances.

### 4.1 Services Overview

**Shared Control Plane (same as basic):**

| Service | Role | Network Alias |
|---------|------|---------------|
| `db` | MongoDB | `db.open5gs.org` |
| `db-init` | Auto-provisioning (one-time) | — |
| `nrf` | NF Repository | `nrf.open5gs.org` |
| `ausf` | Authentication | `ausf.open5gs.org` |
| `udm` | Data Management | `udm.open5gs.org` |
| `udr` | Data Repository | `udr.open5gs.org` |
| `nssf` | Slice Selection | `nssf.open5gs.org` |
| `bsf` | Binding Support | `bsf.open5gs.org` |
| `pcf` | Policy Control | `pcf.open5gs.org` |
| `amf` | Access & Mobility | `amf.open5gs.org` |
| `webui` | Web UI | — |

**Per-Slice User Plane:**

| Service | Slice | Subnet | Network Alias |
|---------|-------|--------|---------------|
| `smf1` | 1 (IoT) | 10.45.0.0/16 | `smf1.open5gs.org` |
| `smf2` | 2 (Vehicle) | 10.46.0.0/16 | `smf2.open5gs.org` |
| `smf3` | 3 (Restricted) | 10.47.0.0/16 | `smf3.open5gs.org` |
| `upf1` | 1 (IoT) | 10.45.0.0/16 | `upf1.open5gs.org` |
| `upf2` | 2 (Vehicle) | 10.46.0.0/16 | `upf2.open5gs.org` |
| `upf3` | 3 (Restricted) | 10.47.0.0/16 | `upf3.open5gs.org` |

**RAN and UEs:**

| Service | Slice | IMSI | Network Alias |
|---------|-------|------|---------------|
| `gnb` | All 3 | — | `gnb.ueransim.org` |
| `ue1` | 1 (IoT) | 001010000000004 | — |
| `ue2` | 2 (Vehicle) | 001010000000002 | — |
| `ue3` | 3 (Restricted) | 001010000000001 | — |

**Total: 22 containers** (21 persistent + 1 one-time `db-init`)

### 4.2 Service Details

#### `db-init` — Auto-Provisioning Service

This is the key addition that doesn't exist in the basic setup:

```yaml
db-init:
  container_name: db-init
  image: "fgftk/mongodb:${MONGODB_VERSION}"
  depends_on:
    - db
  restart: "no"
  networks:
    - open5gs
  volumes:
    - ../../configs/network-slicing/mongo-init.js:/docker-entrypoint-initdb.d/mongo-init.js:ro
  entrypoint: ["/bin/sh", "-c"]
  command:
    - |
      echo "Waiting for MongoDB to be ready..."
      for i in $$(seq 1 30); do
        mongosh --host db.open5gs.org --port 27017 --eval "db.runCommand({ping:1})" >/dev/null 2>&1 && break
        echo "  Attempt $$i/30 - MongoDB not ready yet..."
        sleep 2
      done
      echo "MongoDB is ready. Provisioning subscribers..."
      mongosh --host db.open5gs.org --port 27017 /docker-entrypoint-initdb.d/mongo-init.js
      echo "Done. Container will exit now."
```

This container waits for MongoDB to be ready (up to 30 attempts, 2 seconds apart), then runs the `mongo-init.js` script to register all 3 UERANSIM subscribers and 18 PacketRusher subscribers. It uses `restart: "no"` so it runs once and exits — it's a one-time initialization job.

#### Per-Slice SMFs

Each slice gets its own SMF with a unique S-NSSAI and subnet:

```yaml
smf1:
  container_name: smf1
  image: "fgftk/smf-open5gs:${OPEN5GS_VERSION}"
  command: "-c /etc/open5gs/custom/smf1.yaml"
  networks:
    open5gs:
      aliases:
        - smf1.open5gs.org
  configs:
    - source: smf1_config
      target: /etc/open5gs/custom/smf1.yaml
```

SMF2 and SMF3 follow the same pattern with their own DNS aliases (`smf2.open5gs.org`, `smf3.open5gs.org`).

#### Per-Slice UPFs

Each UPF runs privileged for TUN interface creation:

```yaml
upf1:
  container_name: upf1
  image: "fgftk/upf-open5gs:${OPEN5GS_VERSION}"
  command: "-c /etc/open5gs/custom/upf1.yaml"
  privileged: true
  cap_add:
    - NET_ADMIN
  networks:
    open5gs:
      aliases:
        - upf1.open5gs.org
  configs:
    - source: upf1_config
      target: /etc/open5gs/custom/upf1.yaml
```

**UPF3 (Restricted Slice) — Internet Blocking:**

UPF3's config is identical to UPF1/UPF2, but the Docker Compose file adds iptables rules to block internet access while allowing internal Docker network traffic:

```yaml
upf3:
  # ... same as upf1/upf2 ...
  command: >
    sh -c "
    /open5gs/install/bin/open5gs-upfd -c /etc/open5gs/custom/upf3.yaml &
    sleep 2
    iptables -I FORWARD -s 10.47.0.0/16 -d 10.33.33.0/24 -j ACCEPT
    iptables -I FORWARD -s 10.47.0.0/16 -j DROP
    wait
    "
```

The first iptables rule allows traffic from UPF3's subnet (10.47.0.0/16) to the Docker network (10.33.33.0/24), so UE3 can reach MQTT and other internal services. The second rule drops all other traffic from UPF3's subnet, blocking internet access. Rule order matters — the ACCEPT rule must come before the DROP rule.

#### Sliced UEs

```yaml
ue1:
  container_name: ue1
  image: "fgftk/ue-ueransim:${UERANSIM_VERSION}"
  command: "-c /UERANSIM/config/ue1.yaml"
  cap_add:
    - NET_ADMIN
  networks:
    - open5gs
```

Each UE's config specifies which slice it belongs to via S-NSSAI. The AMF + NRF route the PDU session to the correct SMF/UPF based on this value.

### 4.3 How to Launch

```bash
cd compose-files/network-slicing/
docker compose --env-file ../../build-files/open5gs.env up -d
```

---

## 5. Use Case Simulators — `docker-compose.usecases.yaml`

**Location:** `compose-files/network-slicing/docker-compose.usecases.yaml`

This file defines the application-layer services that run on top of the 5G network. It includes MQTT broker, Node-RED dashboard, Edge server, and all IoT/Vehicle/Restricted simulators.

### 5.1 Services Overview

| Service | Image | UE / Slice | Role |
|---------|-------|------------|------|
| `mqtt` | `eclipse-mosquitto:2` | Direct network | MQTT broker (port 1883) |
| `nodered` | `nodered/node-red:latest` | Direct network | Dashboard (port 1880) |
| `edge` | Built from `apps/edge/Dockerfile` | Direct network | Edge computing server (port 5000) |
| `sim-iot-01` | `python:3.11-slim` | UE1 / Slice 1 | Temperature & Humidity sensor |
| `sim-iot-02` | `python:3.11-slim` | UE1 / Slice 1 | Air Quality sensor (CO₂, PM2.5) |
| `sim-iot-03` | `python:3.11-slim` | UE1 / Slice 1 | Multi-sensor (temp, pressure, battery) |
| `sim-veh-01` | `python:3.11-slim` | UE2 / Slice 2 | Vehicle GPS tracking |
| `sim-veh-02` | `python:3.11-slim` | UE2 / Slice 2 | Vehicle alerts (brake, overspeed) |
| `sim-restricted` | `python:3.11-slim` | UE3 / Slice 3 | Restricted IoT (no internet) |
| `sim-fallback` | `python:3.11-slim` | UE3 / Slice 3 | Resilience fallback (all topics) |

### 5.2 Service Details

#### Infrastructure Services (MQTT, Node-RED, Edge)

These services connect directly to the `open5gs` Docker network (not through any UE):

```yaml
mqtt:
  image: eclipse-mosquitto:2
  container_name: mqtt
  networks:
    open5gs:
      aliases:
        - mqtt
  volumes:
    - ../apps/mqtt/config/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
  ports:
    - "1883:1883"
```

```yaml
nodered:
  image: nodered/node-red:latest
  container_name: nodered
  networks:
    - open5gs
  ports:
    - "1880:1880"
```

```yaml
edge:
  container_name: edge
  build:
    context: ../apps/edge
  cap_add:
    - NET_ADMIN
  networks:
    - open5gs
  ports:
    - "5000:5000"
```

The Edge server needs `NET_ADMIN` capability for the priority-based QoS feature, which applies `tc` (traffic control) rules on its `eth0` interface to create a shared bandwidth bottleneck for demonstration purposes.

#### Simulator Services — The `network_mode: container:` Pattern

This is the most important design pattern in the entire project. Each simulator uses `network_mode: "container:ueX"` to share the UE container's network namespace:

```yaml
sim-iot-01:
  image: python:3.11-slim
  container_name: sim-iot-01
  network_mode: "container:ue1"    # ← Shares UE1's entire network stack
  volumes:
    - ../../apps/iot-scripts:/iot:ro
  command: sh -lc "pip install -q paho-mqtt && python /iot/ue-iot-01.py"
  restart: unless-stopped
```

**What `network_mode: "container:ue1"` means:**

- `sim-iot-01` does NOT get its own network namespace
- Instead, it shares UE1's `eth0`, `uesimtun0`, routing table, and DNS
- When the Python script connects to `mqtt:1883`, the traffic goes through UE1's `uesimtun0` → gNB → UPF1 → Docker network → MQTT broker
- This is what makes the traffic flow through the actual 5G network instead of bypassing it

**IoT simulators** (sim-iot-01/02/03) all share UE1's namespace (Slice 1) and publish directly to MQTT topics:

| Simulator | MQTT Topic | Data Published |
|-----------|------------|----------------|
| `sim-iot-01` | `iot/ue-iot-01` | Temperature (°C), Humidity (%) |
| `sim-iot-02` | `iot/ue-iot-02` | CO₂ (ppm), PM2.5 (µg/m³) |
| `sim-iot-03` | `iot/ue-iot-03` | Temperature (°C), Pressure (hPa), Battery (%) |

**Vehicle simulators** (sim-veh-01/02) share UE2's namespace (Slice 2) and send HTTP POST to the Edge server:

```yaml
sim-veh-01:
  image: python:3.11-slim
  container_name: sim-veh-01
  network_mode: "container:ue2"    # ← Shares UE2's network (Slice 2)
  volumes:
    - ../../apps/veh-scripts:/veh:ro
  environment:
    - EDGE_URL=http://edge:5000/telemetry
    - UE_NAME=ue-veh-01
  command: sh -lc "pip install -q requests && python /veh/ue-veh-01.py"
  restart: unless-stopped
```

| Simulator | Protocol | Destination | Data Published |
|-----------|----------|-------------|----------------|
| `sim-veh-01` | HTTP POST | `edge:5000/telemetry` | GPS (lat/lon), Speed (km/h) |
| `sim-veh-02` | HTTP POST | `edge:5000/telemetry` | Speed (km/h), Alerts (brake, overspeed, lane departure) |

The Edge server receives the HTTP POST, processes/aggregates the data, and publishes it to MQTT topic `veh/telemetry`.

**Restricted simulator** shares UE3's namespace (Slice 3):

```yaml
sim-restricted:
  image: python:3.11-slim
  container_name: sim-restricted
  network_mode: "container:ue3"    # ← Shares UE3's network (Slice 3, no internet)
  volumes:
    - ../../apps/iot-scripts:/iot:ro
  command: >
    sh -lc "pip install -q paho-mqtt && python -c \"
    import json, random, time
    from paho.mqtt import client as mqtt
    c = mqtt.Client(client_id='ue-restricted-01')
    c.connect('mqtt', 1883, 60)
    c.loop_start()
    while True:
        p = {'ue':'ue3-restricted','temperature_c':round(random.uniform(18,28),1),
             'humidity_percent':random.randint(30,80),'restricted':True,'ts':int(time.time())}
        c.publish('iot/restricted', json.dumps(p))
        time.sleep(3)
    \""
  restart: unless-stopped
```

This simulator can reach the MQTT broker (internal Docker network) but cannot reach the internet — proving that UPF3's iptables rules work correctly. It publishes to `iot/restricted` topic.

**Fallback simulator** also shares UE3's namespace and provides resilience:

```yaml
sim-fallback:
  image: python:3.11-slim
  container_name: sim-fallback
  network_mode: "container:ue3"    # ← Shares UE3's network (Slice 3)
  volumes:
    - ../../apps/iot-scripts:/iot:ro
  command: sh -lc "pip install -q paho-mqtt && python /iot/ue3-fallback.py"
  restart: unless-stopped
```

The fallback simulator publishes to ALL MQTT topics (`iot/ue-iot-01`, `iot/ue-iot-02`, `iot/ue-iot-03`, `veh/telemetry`). During normal operation it's not needed, but when Slice 1 and Slice 2 are stopped (for resilience testing), this simulator keeps the Node-RED dashboard populated with data via Slice 3.

### 5.3 How to Launch

```bash
cd compose-files/network-slicing/
docker compose -f docker-compose.usecases.yaml --env-file ../../build-files/open5gs.env up -d
```

To start individual simulators:

```bash
docker compose -f docker-compose.usecases.yaml up -d sim-iot-01 sim-veh-01
```

---

## 6. Application Services (Basic) — `docker-compose.apps.yaml`

**Location:** `compose-files/apps/docker-compose.apps.yaml`

This is the equivalent of `docker-compose.usecases.yaml` but for the basic (non-slicing) deployment. It defines the same application services (MQTT, Node-RED, Edge, simulators) but maps them to the basic UE containers (`ue-iot-01`, `ue-veh-01`, etc.) instead of the sliced UEs (`ue1`, `ue2`, `ue3`).

The key difference is the `network_mode` targets:

| Basic (`docker-compose.apps.yaml`) | Slicing (`docker-compose.usecases.yaml`) |
|-------------------------------------|------------------------------------------|
| `network_mode: "container:ue-iot-01"` | `network_mode: "container:ue1"` |
| `network_mode: "container:ue-veh-01"` | `network_mode: "container:ue2"` |
| No restricted/fallback simulators | Has `sim-restricted` and `sim-fallback` |

**How to launch:**

```bash
cd compose-files/apps/
docker compose -f docker-compose.apps.yaml --env-file ../../build-files/open5gs.env up -d
```

---

## 7. PacketRusher Load Testing — `docker-compose.packetrusher.yaml`

**Location:** `compose-files/network-slicing/docker-compose.packetrusher.yaml`

This file defines the PacketRusher load testing container and an iperf3 server for GTP throughput testing.

### 7.1 Services Overview

| Service | Image | Role |
|---------|-------|------|
| `packetrusher` | `fgftk/packetrusher:main` | Combined gNB + multi-UE simulator |
| `iperf-server` | `networkstatic/iperf3:latest` | iperf3 server for throughput testing |

**PacketRusher service:**

```yaml
packetrusher:
  container_name: packetrusher
  image: "fgftk/packetrusher:main"
  privileged: true
  networks:
    open5gs:
      aliases:
        - gnb.packetrusher.org
  volumes:
    - ../../configs/network-slicing/packetrusher.yaml:/PacketRusher/config/packetrusher.yaml:ro
  command: "--config /PacketRusher/config/packetrusher.yaml ue"
```

PacketRusher requires `privileged: true` because it uses the `gtp5g` kernel module to create real GTP-U tunnels. Unlike UERANSIM (which simulates the tunnel in userspace), PacketRusher creates actual kernel-level GTP tunnels. This is why the host machine must have the `gtp5g` kernel module loaded (`lsmod | grep gtp5g`).

The DNS alias `gnb.packetrusher.org` prevents conflicts with UERANSIM's `gnb.ueransim.org`.

**iperf3 server:**

```yaml
iperf-server:
  container_name: iperf-server
  image: networkstatic/iperf3:latest
  command: "-s"
  networks:
    open5gs:
      aliases:
        - test.iperf.org
```

The iperf3 server listens on the Docker network. During GTP throughput tests, the framework runs `iperf3 -c test.iperf.org` from inside the PacketRusher container — this traffic flows through the actual GTP-U tunnel via UPF, measuring real 5G user plane performance.

### 7.2 How to Launch

PacketRusher is typically launched by the framework's load testing module, not manually. But for manual testing:

```bash
cd compose-files/network-slicing/

# Start iperf server
docker compose -f docker-compose.packetrusher.yaml --env-file ../../build-files/open5gs.env up -d iperf-server

# Start PacketRusher with single UE
docker compose -f docker-compose.packetrusher.yaml --env-file ../../build-files/open5gs.env up -d packetrusher

# Multi-UE load test (run manually)
docker run --rm --name packetrusher \
  --network open5gs \
  --network-alias gnb.packetrusher.org \
  --privileged \
  -v $(pwd)/../../configs/network-slicing/packetrusher.yaml:/PacketRusher/config/packetrusher.yaml \
  fgftk/packetrusher:main \
  --config /PacketRusher/config/packetrusher.yaml \
  multi-ue -n 5 --timeBetweenRegistration 100
```

---

## 8. Multi-File Orchestration

The Compose files are designed to be layered. Here's the typical startup sequence for a full network slicing deployment:

**Step 1 — Start the 5G Core + RAN:**

```bash
cd compose-files/network-slicing/
docker compose --env-file ../../build-files/open5gs.env up -d
```

This starts 22 containers: MongoDB, all core NFs, gNB, 3 UEs, WebUI, and the `db-init` auto-provisioner.

**Step 2 — Start the Application Layer:**

```bash
docker compose -f docker-compose.usecases.yaml --env-file ../../build-files/open5gs.env up -d
```

This adds MQTT, Node-RED, Edge server, and all simulators. They connect to the already-running UE containers via `network_mode: "container:ueX"`.

**Step 3 — (Optional) Start Load Testing:**

```bash
docker compose -f docker-compose.packetrusher.yaml --env-file ../../build-files/open5gs.env up -d
```

Or use the framework's web UI at `http://localhost:8000/loadtest`.

**Step 4 — Start the Management Framework:**

```bash
cd ../../  # Back to project root
source .venv/bin/activate
python -m uvicorn framework.app:app --host 0.0.0.0 --port 8000 --reload
```

The framework runs on the host (not in Docker) and uses Docker CLI commands to manage all containers.

---

## 9. Container Startup Order

Docker Compose `depends_on` defines the startup order within each file. The implicit dependency chain across the system is:

```
MongoDB (db)
   ↓
db-init (auto-provisioning, then exits)
   ↓
NRF (service registry — must be first NF)
   ↓
AUSF, UDM, UDR, BSF, PCF, NSSF (register with NRF)
   ↓
SMF1, SMF2, SMF3 (register with NRF, connect to UPFs via PFCP)
   ↓
UPF1, UPF2, UPF3 (create TUN interfaces, accept PFCP from SMFs)
   ↓
AMF (last core NF — depends on all others being ready)
   ↓
gNodeB (connects to AMF via NGAP/SCTP)
   ↓
UE1, UE2, UE3 (connect to gNB, register with AMF)
   ↓
MQTT, Node-RED, Edge (application infrastructure)
   ↓
Simulators (attach to UE network namespaces)
```

Within the framework, the control module (`control.py`) implements proper startup ordering when restarting slices — UPF first, then SMF, then simulators. This ensures the data plane is ready before the UE tries to establish a PDU session.

---

## 10. Complete Service Inventory

### All Services Across All Compose Files

| Container | Compose File | Category | Ports (Host) |
|-----------|-------------|----------|--------------|
| `db` | network-slicing/docker-compose.yaml | Database | 27017 |
| `db-init` | network-slicing/docker-compose.yaml | Init (one-time) | — |
| `nrf` | network-slicing/docker-compose.yaml | Core NF | — |
| `ausf` | network-slicing/docker-compose.yaml | Core NF | — |
| `udm` | network-slicing/docker-compose.yaml | Core NF | — |
| `udr` | network-slicing/docker-compose.yaml | Core NF | — |
| `nssf` | network-slicing/docker-compose.yaml | Core NF | — |
| `bsf` | network-slicing/docker-compose.yaml | Core NF | — |
| `pcf` | network-slicing/docker-compose.yaml | Core NF | — |
| `amf` | network-slicing/docker-compose.yaml | Core NF | — |
| `smf1` | network-slicing/docker-compose.yaml | Core NF (Slice 1) | — |
| `smf2` | network-slicing/docker-compose.yaml | Core NF (Slice 2) | — |
| `smf3` | network-slicing/docker-compose.yaml | Core NF (Slice 3) | — |
| `upf1` | network-slicing/docker-compose.yaml | User Plane (Slice 1) | — |
| `upf2` | network-slicing/docker-compose.yaml | User Plane (Slice 2) | — |
| `upf3` | network-slicing/docker-compose.yaml | User Plane (Slice 3) | — |
| `gnb` | network-slicing/docker-compose.yaml | RAN | — |
| `ue1` | network-slicing/docker-compose.yaml | UE (Slice 1) | — |
| `ue2` | network-slicing/docker-compose.yaml | UE (Slice 2) | — |
| `ue3` | network-slicing/docker-compose.yaml | UE (Slice 3) | — |
| `webui` | network-slicing/docker-compose.yaml | Management | 9999 |
| `mqtt` | docker-compose.usecases.yaml | Application | 1883 |
| `nodered` | docker-compose.usecases.yaml | Application | 1880 |
| `edge` | docker-compose.usecases.yaml | Application | 5000 |
| `sim-iot-01` | docker-compose.usecases.yaml | Simulator (Slice 1) | — |
| `sim-iot-02` | docker-compose.usecases.yaml | Simulator (Slice 1) | — |
| `sim-iot-03` | docker-compose.usecases.yaml | Simulator (Slice 1) | — |
| `sim-veh-01` | docker-compose.usecases.yaml | Simulator (Slice 2) | — |
| `sim-veh-02` | docker-compose.usecases.yaml | Simulator (Slice 2) | — |
| `sim-restricted` | docker-compose.usecases.yaml | Simulator (Slice 3) | — |
| `sim-fallback` | docker-compose.usecases.yaml | Simulator (Slice 3) | — |
| `packetrusher` | docker-compose.packetrusher.yaml | Load Testing | — |
| `iperf-server` | docker-compose.packetrusher.yaml | Load Testing | — |

**Total: 33 containers** (32 persistent + 1 one-time init)

### Host Ports Summary

| Port | Service | Protocol | Purpose |
|------|---------|----------|---------|
| 1880 | Node-RED | HTTP | Dashboard UI |
| 1883 | MQTT | TCP | MQTT broker |
| 5000 | Edge | HTTP | Edge server API |
| 8000 | Framework | HTTP | Management Web UI (runs on host) |
| 9999 | WebUI | HTTP | Open5GS subscriber management |
| 27017 | MongoDB | TCP | Database access |

---

[← Back to Main README](../README.md) | [Previous: Configuration Files](config-files.md) | [Next: Use Cases & Test Cases →](use-cases-test-cases.md)