# 5G Network Framework

**Mobile Computing WS 2025/26 — Group M**

A comprehensive 5G network management framework built on **Open5GS** (5G Core) and **UERANSIM** (RAN Simulator), fully containerized with Docker.

### UERANSIM — Functional Network Slicing & Use Cases

Using UERANSIM, we built a complete 5G network with three dedicated network slices, each with its own SMF and UPF pair. **Slice 1 (IoT)** connects three IoT sensor UEs that publish temperature, humidity, CO₂, PM2.5, and pressure data via MQTT through the 5G network to a Node-RED dashboard. **Slice 2 (Vehicle)** connects two vehicle UEs that send GPS, speed, and alert telemetry via HTTP to an Edge server, which aggregates and forwards data to MQTT. **Slice 3 (Restricted)** demonstrates a UE with an active PDU session but blocked internet access — it can only reach internal services. The framework provides an interactive web UI with live topology visualization, a control dashboard for managing containers and configurations, 20 automated test cases verifying health, connectivity, slice isolation and performance, transport network control with 6 QoS profiles and priority-based traffic shaping (HTB), slice resilience testing with automatic MQTT failover, and real-time monitoring of Docker stats and MQTT streams.

### PacketRusher — Load Testing & Call Simulation

Using PacketRusher, we extended the framework with multi-UE load testing and call simulation capabilities. PacketRusher registers up to 50+ UEs simultaneously against the 5G core, establishing real GTP-U tunnels through the UPF — unlike UERANSIM's iperf3 which routes through the Docker bridge. This enables measuring actual GTP tunnel throughput and stress-testing the core network's registration capacity. On top of the load testing, we implemented call simulation between the registered UEs with three call types: **Voice Calls** (5QI=1, 64 kbps AMR-WB), **Video Calls** (5QI=2, 2 Mbps H.264 720p), and **Emergency 112 Calls** (5QI=69, highest priority with pre-emption). Each call generates realistic 5G NAS/SIP signaling logs and exchanges actual MQTT messages as proof of communication. Emergency calls demonstrate priority handling with 3.6× faster connection setup compared to regular voice calls.

---

## Key Features

- **Two Deployment Modes:** Basic single-slice architecture and advanced 3-slice network slicing
- **Interactive Web UI:** 7 pages — Topology, Control, Verify, Use Cases, Monitor, Load Test, Basic Topology
- **Network Slicing:** 3 dedicated slices (IoT, Vehicle, Restricted) with independent SMF/UPF pairs
- **Automated Testing:** 20 automated test cases covering health, connectivity, isolation, and performance
- **Transport Network Control:** Linux `tc` traffic shaping with 6 QoS profiles and priority-based HTB rules
- **Load Testing:** PacketRusher integration for multi-UE stress testing with real GTP-U tunnels
- **Call Simulation:** Voice, Video, and Emergency 112 calls with real MQTT message exchange
- **Slice Resilience:** Automated failover testing with MQTT fallback mechanisms
- **Auto-Provisioning:** Subscribers automatically registered in MongoDB on startup
- **Live Monitoring:** Docker stats, MQTT streams, and UE metrics in real-time

---

## Documentation

| # | Document | Description |
|---|----------|-------------|
| 1 | [Project Structure](docs/project-structure.md) | Complete folder and file structure of the repository |
| 2 | [Architecture & Design](docs/architecture-design.md) | System architecture, network design, and component overview |
| 3 | [Configuration Files](docs/config-files.md) | Description of all Open5GS and UERANSIM config YAML files |
| 4 | [Docker Compose Files](docs/compose-files.md) | Description of all Docker Compose files and services |
| 5 | [Use Cases & Test Cases](docs/use-cases-test-cases.md) | All use cases (IoT, Vehicle, Load Test, Calls) and test cases |
| 6 | [Framework Backend](docs/framework-backend.md) | Description of each Python module in the `framework/` folder |
| 7 | [Framework Frontend](docs/framework-frontend.md) | Description of each HTML template in `framework/templates/` |
| 8 | [User Manual](docs/user-manual.md) | Step-by-step guide for setup, usage, and demonstration |

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| 5G Core Network | Open5GS |
| RAN Simulator | UERANSIM |
| Load Tester | PacketRusher |
| Container Runtime | Docker + Docker Compose |
| Backend Framework | FastAPI (Python) |
| Frontend | HTML5, CSS3, JavaScript, vis-network |
| Message Broker | Eclipse Mosquitto (MQTT) |
| Dashboard | Node-RED |
| Database | MongoDB |
| Traffic Control | Linux tc (HTB, netem), iptables |

---

## Ports

| Port | Service |
|------|---------|
| 8000 | Framework Web UI |
| 1880 | Node-RED Dashboard |
| 1883 | MQTT Broker |
| 5000 | Edge Server |
| 9999 | Open5GS WebUI |
| 27017 | MongoDB |

---

*Mobile Computing WS 2025/26 — Group M*