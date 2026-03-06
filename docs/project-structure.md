# Project Structure

[← Back to Main README](../README.md)

This document describes the complete folder and file structure of the 5G Network Framework repository. Each directory and file is explained with its purpose and role in the project.

---

## Top-Level Overview

```
mobcomproject25-26-group-m/
├── apps/                          # Application scripts (IoT sensors, vehicle telemetry)
├── build-files/                   # Docker build configurations and environment files
├── compose-files/                 # Docker Compose files for all deployment modes
├── configs/                       # Open5GS and UERANSIM configuration YAML files
├── framework/                     # Web-based management framework (backend + frontend)
├── provision-subscribers.sh       # Standalone script for manual MongoDB provisioning
└── README.md                      # Main project documentation with links
```

---

## Directory Details

### `apps/` — Application Layer Scripts

This directory contains all the Python scripts that simulate real-world IoT and vehicle applications. These scripts run inside Docker containers and communicate through the 5G network.

```
apps/
├── edge/                          # Edge computing server
│   ├── app.py                     # Flask server that receives vehicle telemetry via HTTP,
│   │                              #   aggregates it, and publishes to MQTT topic veh/telemetry
│   ├── Dockerfile                 # Docker image for the edge server (Python 3.11-slim)
│   └── edge.py                    # Alternative/legacy edge computing script
│
├── iot-scripts/                   # IoT sensor simulation scripts
│   ├── ue-iot-01.py               # Simulates a Temperature & Humidity sensor.
│   │                              #   Publishes random values to MQTT topic iot/ue-iot-01
│   │                              #   every few seconds through UE1's uesimtun0 interface.
│   │
│   ├── ue-iot-02.py               # Simulates an Air Quality sensor (CO₂ and PM2.5).
│   │                              #   Publishes to MQTT topic iot/ue-iot-02.
│   │
│   ├── ue-iot-03.py               # Simulates a multi-sensor device (Temperature, Pressure,
│   │                              #   Battery level). Publishes to MQTT topic iot/ue-iot-03.
│   │
│   └── ue3-fallback.py            # Resilience fallback simulator. Runs on Slice 3 and takes
│                                  #   over publishing to ALL MQTT topics (iot/ue-iot-01,
│                                  #   iot/ue-iot-02, iot/ue-iot-03, veh/telemetry) when
│                                  #   Slices 1 and 2 are stopped. Ensures Node-RED dashboard
│                                  #   continues showing data during slice failures.
│
└── veh-scripts/                   # Vehicle telemetry simulation scripts
    ├── ue-veh-01.py               # Simulates Vehicle 1 sending GPS coordinates, speed,
    │                              #   fuel level, engine RPM, and alerts via HTTP POST
    │                              #   to the Edge server at http://edge:5000/telemetry.
    │
    └── ue-veh-02.py               # Simulates Vehicle 2 with same telemetry format.
                                   #   Sends data through UE-Veh-02's network namespace.
```

**How IoT simulators work:** Each sim-iot container uses `network_mode: "container:ue-iot-XX"`, which means it shares the UE container's network namespace. When the script publishes to MQTT, the traffic goes through the UE's `uesimtun0` interface → gNodeB → UPF → MQTT broker, traveling through the actual 5G network.

**How Vehicle simulators work:** Similarly, sim-veh containers share the vehicle UE's network namespace. They send HTTP POST requests to the Edge server, which goes through the 5G network. The Edge server then publishes aggregated data to MQTT.

---

### `build-files/` — Build Configurations

```
build-files/
└── open5gs.env                    # Environment variables for Docker Compose.
                                   #   Defines version numbers:
                                   #   - OPEN5GS_VERSION (e.g., 2.7.x)
                                   #   - UERANSIM_VERSION (e.g., 3.2.x)
                                   #   - MONGODB_VERSION
                                   #   - HOST_IP_ADDRESS
                                   #   Referenced by docker-compose.yaml files using
                                   #   ${OPEN5GS_VERSION}, ${UERANSIM_VERSION}, etc.
```

---

### `compose-files/` — Docker Compose Definitions

This directory contains all Docker Compose files that define how the containers are created, connected, and configured. There are separate files for the basic setup, network slicing setup, applications, and load testing.

```
compose-files/
├── apps/                                    # Application layer services
│   ├── docker-compose.apps.yaml             # Defines: mqtt, nodered, edge, sim-iot-01/02/03,
│   │                                        #   sim-veh-01/02. Used with the basic deployment.
│   │                                        #   Simulators use network_mode: "container:ue-XXX"
│   │                                        #   to share UE network namespaces.
│   ├── mqtt/
│   │   └── config/
│   │       └── mosquitto.conf               # Mosquitto MQTT broker configuration.
│   │                                        #   Configures listener on port 1883,
│   │                                        #   allows anonymous connections.
│   └── edge/
│       └── app.py                           # Edge server Flask app mounted into container.
│
├── basic/
│   └── ueransim/
│       └── docker-compose.yaml              # Basic 5G deployment (no slicing).
│                                            #   Defines all core NFs (nrf, amf, smf, upf,
│                                            #   ausf, udm, udr, nssf, bsf, pcf), single gnb,
│                                            #   5 UEs (ue-iot-01/02/03, ue-veh-01/02),
│                                            #   db (MongoDB), webui.
│                                            #   All on open5gs network (10.33.33.0/24).
│
└── network-slicing/
    ├── docker-compose.yaml                  # Network slicing 5G deployment.
    │                                        #   Defines all core NFs plus slice-specific
    │                                        #   SMF1/2/3 and UPF1/2/3 pairs, single gnb,
    │                                        #   3 UEs (ue1, ue2, ue3), db, webui, db-init
    │                                        #   (auto-provisioning). Each slice has its own
    │                                        #   subnet (10.45/46/47.0.0/16).
    │
    ├── docker-compose.usecases.yaml         # Use case simulators for network slicing.
    │                                        #   Defines: mqtt, nodered, edge, sim-iot-01/02/03,
    │                                        #   sim-veh-01/02, sim-restricted, sim-fallback.
    │                                        #   Simulators attached to sliced UEs (ue1, ue2, ue3).
    │
    └── docker-compose.packetrusher.yaml     # PacketRusher load testing service.
                                             #   Defines the packetrusher container with
                                             #   gtp5g kernel module support for real GTP-U
                                             #   tunnel establishment.
```

For detailed descriptions of each Compose file's services, see [Docker Compose Files](compose-files.md).

---

### `configs/` — Configuration YAML Files

All Open5GS network function and UERANSIM configuration files. These YAML files define IP addresses, PLMN IDs, S-NSSAI values, APN/DNN settings, and other 5G parameters.

```
configs/
├── basic/
│   ├── packetrusher/
│   │   └── packetrusher.yaml                # PacketRusher config for basic setup
│   │
│   └── ueransim/                            # Basic (single-slice) configurations
│       ├── amf.yaml                         # AMF config — PLMN (001/01), single slice,
│       │                                    #   NGAP bind address, SBI interface
│       ├── ausf.yaml                        # AUSF config — SBI interface for authentication
│       ├── bsf.yaml                         # BSF config — SBI interface for session binding
│       ├── gnb.yaml                         # gNodeB config — connects to AMF, radio params
│       ├── nrf.yaml                         # NRF config — SBI interface for NF discovery
│       ├── nssf.yaml                        # NSSF config — slice selection policies
│       ├── pcf.yaml                         # PCF config — policy control, connects to DB
│       ├── smf.yaml                         # SMF config — single session management
│       ├── udm.yaml                         # UDM config — subscriber data management
│       ├── udr.yaml                         # UDR config — subscriber data repository, DB URI
│       ├── upf.yaml                         # UPF config — single user plane, NAT enabled
│       ├── ue.yaml                          # Default UE template
│       ├── ue-iot-01.yaml                   # UE config for IoT device 1 — IMSI, key, OPC,
│       │                                    #   S-NSSAI, DNN. Uses network_mode: container
│       ├── ue-iot-02.yaml                   # UE config for IoT device 2
│       ├── ue-iot-03.yaml                   # UE config for IoT device 3
│       ├── ue-veh-01.yaml                   # UE config for Vehicle 1
│       ├── ue-veh-02.yaml                   # UE config for Vehicle 2
│       ├── ue-bulk-01.yaml                  # Bulk UE config template 1
│       └── ue-bulk-02.yaml                  # Bulk UE config template 2
│
├── network-slicing/                         # Network slicing configurations
│   ├── amf.yaml                             # AMF config — supports 3 slices (SST/SD pairs),
│   │                                        #   PLMN (001/01), NGAP binding
│   ├── ausf.yaml                            # AUSF config for sliced deployment
│   ├── bsf.yaml                             # BSF config for sliced deployment
│   ├── gnb.yaml                             # gNodeB config — connects to sliced AMF,
│   │                                        #   supports all 3 slices
│   ├── nrf.yaml                             # NRF config for sliced deployment
│   ├── nssf.yaml                            # NSSF config — slice selection rules mapping
│   │                                        #   SST/SD to specific SMF instances
│   ├── pcf.yaml                             # PCF config for sliced deployment
│   ├── udm.yaml                             # UDM config for sliced deployment
│   ├── udr.yaml                             # UDR config for sliced deployment
│   ├── smf1.yaml                            # SMF for Slice 1 (IoT) — manages PDU sessions
│   │                                        #   for subnet 10.45.0.0/16, DNN: internet
│   ├── smf2.yaml                            # SMF for Slice 2 (Vehicle) — subnet 10.46.0.0/16
│   ├── smf3.yaml                            # SMF for Slice 3 (Restricted) — subnet 10.47.0.0/16
│   ├── upf1.yaml                            # UPF for Slice 1 — NAT enabled, forwards to internet
│   ├── upf2.yaml                            # UPF for Slice 2 — NAT enabled, forwards to internet
│   ├── upf3.yaml                            # UPF for Slice 3 — NAT enabled but internet blocked
│   │                                        #   by iptables rules at container level
│   ├── ue1.yaml                             # UE1 config — IMSI 001010000000004, Slice 1
│   │                                        #   (SST:1, SD:000001)
│   ├── ue2.yaml                             # UE2 config — IMSI 001010000000002, Slice 2
│   │                                        #   (SST:1, SD:000002)
│   ├── ue3.yaml                             # UE3 config — IMSI 001010000000001, Slice 3
│   │                                        #   (SST:1, SD:000003)
│   ├── packetrusher.yaml                    # PacketRusher config for sliced setup — connects
│   │                                        #   to AMF, uses Slice 1 S-NSSAI
│   └── mongo-init.js                        # Auto-provisioning script — runs on startup via
│                                            #   db-init service. Registers 3 UERANSIM + 18
│                                            #   PacketRusher subscribers using updateOne with
│                                            #   upsert:true (idempotent, safe to re-run).
│
├── roaming/                                 # Roaming scenario configs (pre-existing)
│   └── packetrusher.yaml
│
├── scp/                                     # SCP (Service Communication Proxy) configs
│   └── ...                                  #   (pre-existing, not used in our deployment)
│
└── speed-test/                              # Speed test scenario configs (pre-existing)
    ├── amf.yaml, ausf.yaml, bsf.yaml
    ├── nrf.yaml, nssf.yaml, pcf.yaml
    ├── smf.yaml, udm.yaml, udr.yaml
    ├── upf.yaml
    └── packetrusher.yaml
```

For detailed descriptions of each config file's contents, see [Configuration Files](config-files.md).

---

### `framework/` — Web-Based Management Framework

The core of the project. A FastAPI backend with HTML/JS frontend that provides a complete web UI for managing, monitoring, testing, and visualizing the 5G network.

```
framework/
├── __init__.py                    # Python package marker (empty file)
│
├── app.py                         # Main FastAPI application. Defines all HTTP routes
│                                  #   and API endpoints (50+ endpoints). Serves HTML
│                                  #   pages and provides REST API for all features.
│                                  #   Entry point: python -m uvicorn framework.app:app
│
├── topology.py                    # Network slicing topology module. Contains static
│                                  #   definitions of all nodes (20+ NFs, UEs, apps) and
│                                  #   edges (40+ connections with 3GPP interface names).
│                                  #   Merges with live Docker state to show real IPs.
│
├── basic_topology.py              # Basic topology module (same concept as topology.py
│                                  #   but for the single-slice basic deployment).
│                                  #   Defines 25+ nodes including 5 UEs and 5 simulators.
│
├── control.py                     # Container lifecycle management. Start/stop/restart
│                                  #   individual containers or entire slices. Implements
│                                  #   proper startup ordering (UPF → SMF → simulators).
│                                  #   Also contains resilience test orchestration.
│
├── tests.py                       # Automated test suite with 20 test cases. Tests cover
│                                  #   service health, PDU sessions, connectivity, slice
│                                  #   isolation, use cases (MQTT, Node-RED), and
│                                  #   performance (iperf3 throughput).
│
├── usecases.py                    # Use case simulator management. Start/stop individual
│                                  #   simulators (sim-iot-01/02/03, sim-veh-01/02,
│                                  #   sim-restricted). Provides log retrieval.
│
├── monitoring.py                  # Live monitoring data collection. Docker stats (CPU,
│                                  #   memory, network I/O), MQTT message snapshots,
│                                  #   UE metrics. Used by the monitoring dashboard.
│
├── transport.py                   # Transport network control using Linux tc and iptables.
│                                  #   6 QoS profiles (Default, IoT Optimized, Vehicle
│                                  #   Optimized, Low Latency, Congested, Satellite).
│                                  #   Priority-based QoS with HTB and 4 presets.
│                                  #   DSCP marking per slice.
│
├── loadtest.py                    # PacketRusher integration for multi-UE load testing.
│                                  #   Provisions subscribers in MongoDB, runs PacketRusher,
│                                  #   parses results (registrations, PDU sessions, IPs),
│                                  #   generates topology data for visualization.
│
├── callsim.py                     # Call simulation module. Simulates Voice (5QI=1),
│                                  #   Video (5QI=2), and Emergency 112 (5QI=69) calls.
│                                  #   Generates 5G NAS/SIP signaling logs and exchanges
│                                  #   real MQTT messages as proof of communication.
│
├── dockerctl.py                   # Low-level Docker command helpers. Wrapper functions
│                                  #   for docker exec, docker inspect, docker logs, etc.
│
└── templates/                     # HTML frontend pages
    ├── topology.html              # Network slicing topology visualization.
    │                              #   Interactive vis-network graph with live Docker data.
    │                              #   Sidebar with status, filters, slice info, node details.
    │
    ├── basic-topology.html        # Basic (no slicing) topology visualization.
    │                              #   Same style as topology.html but for basic deployment.
    │                              #   Shows all 5 UEs, simulators, and application layer.
    │
    ├── control.html               # Control dashboard with 4 tabs:
    │                              #   - Container Management (start/stop/restart/logs)
    │                              #   - Configuration Editor (view/edit YAML files)
    │                              #   - Priority QoS (presets + iperf3 benchmark)
    │                              #   - Resilience Testing (slice stop/start + auto test)
    │
    ├── verify.html                # Automated testing page. Runs 20 tests with real-time
    │                              #   progress, shows pass/fail grid, expandable details.
    │
    ├── usecases.html              # Use case management. Cards for each simulator with
    │                              #   start/stop buttons and live log viewer.
    │
    ├── monitoring.html            # Live monitoring dashboard. Auto-refreshing Docker
    │                              #   stats, MQTT message stream, UE metrics display.
    │
    └── loadtest.html              # Load testing and call simulation page.
                                   #   UERANSIM vs PacketRusher comparison, GTP throughput
                                   #   test, multi-UE load test with topology visualization,
                                   #   call simulation (Voice/Video/Emergency 112).
```

For detailed descriptions of each Python module, see [Framework Backend](framework-backend.md).
For detailed descriptions of each HTML template, see [Framework Frontend](framework-frontend.md).

---

### Root Files

```
mobcomproject25-26-group-m/
├── provision-subscribers.sh       # Standalone shell script for manually provisioning
│                                  #   subscribers in MongoDB. Can be run independently
│                                  #   if the db-init service didn't execute. Uses mongosh
│                                  #   to insert/update subscriber documents.
│
├── README.md                      # Main project README with summary, feature list,
│                                  #   and links to all documentation files.
│
└── docs/                          # Documentation directory
    ├── project-structure.md       # This file
    ├── architecture-design.md     # Architecture and design description
    ├── config-files.md            # Configuration file descriptions
    ├── compose-files.md           # Docker Compose file descriptions
    ├── use-cases-test-cases.md    # Use cases and test cases
    ├── framework-backend.md       # Framework Python module descriptions
    ├── framework-frontend.md      # Framework HTML template descriptions
    └── user-manual.md             # User manual
```

---

## File Count Summary

| Directory | Files | Purpose |
|-----------|-------|---------|
| `apps/` | 8 | IoT/Vehicle simulator scripts + Edge server |
| `build-files/` | 1 | Environment variables |
| `compose-files/` | 6 | Docker Compose definitions |
| `configs/basic/` | 19 | Basic deployment configs |
| `configs/network-slicing/` | 18 | Network slicing configs |
| `framework/` (Python) | 11 | Backend modules |
| `framework/templates/` | 7 | Frontend HTML pages |
| `Root` | 2 | README + provisioning script |
| `docs/` | 8 | Documentation files |
| **Total** | **~80** | |

---

[← Back to Main README](../README.md) | [Next: Architecture & Design →](architecture-design.md)