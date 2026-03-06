# Architecture & Design

[← Back to Main README](../README.md)

This document describes the complete system architecture and design of the 5G Network Framework. It explains how the system is structured, how the 5G components connect and communicate, and the design decisions behind both deployment modes.

---

## Table of Contents

1. [High-Level System Architecture](#1-high-level-system-architecture)
2. [Docker Network Design](#2-docker-network-design)
3. [Basic Deployment Architecture](#3-basic-deployment-architecture)
4. [Network Slicing Deployment Architecture](#4-network-slicing-deployment-architecture)
5. [5G Core Network Functions](#5-5g-core-network-functions)
6. [3GPP Interfaces and Protocols](#6-3gpp-interfaces-and-protocols)
7. [Radio Access Network (RAN)](#7-radio-access-network-ran)
8. [User Equipment (UE)](#8-user-equipment-ue)
9. [Application Layer](#9-application-layer)
10. [Data Flow Paths](#10-data-flow-paths)
11. [Network Slicing Design](#11-network-slicing-design)
12. [Internet Blocking (Slice 3)](#12-internet-blocking-slice-3)
13. [Subscriber Provisioning Design](#13-subscriber-provisioning-design)
14. [Transport Network and QoS Design](#14-transport-network-and-qos-design)
15. [Load Testing Architecture (PacketRusher)](#15-load-testing-architecture-packetrusher)
16. [Call Simulation Design](#16-call-simulation-design)
17. [Framework (Web UI) Architecture](#17-framework-web-ui-architecture)

---

## 1. High-Level System Architecture

The system is organized into five layers, each running as Docker containers on a shared bridge network:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│   LAYER 5: Management Framework                                         │
│   ┌───────────────────────────────────────────────────────────────────┐ │
│   │  FastAPI Backend (:8000)                                          │ │
│   │  topology.py │ control.py │ tests.py │ transport.py │ callsim.py │ │
│   │  ─────────────────────────────────────────────────────────────── │ │
│   │  Web UI: Topology │ Control │ Verify │ UseCases │ Monitor │ Load │ │
│   └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│   LAYER 4: Application Layer                                            │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │
│   │ MQTT Broker   │  │ Edge Server  │  │ Node-RED     │                 │
│   │ (Mosquitto)   │  │ (Flask)      │  │ (Dashboard)  │                 │
│   │ :1883         │  │ :5000        │  │ :1880        │                 │
│   └──────────────┘  └──────────────┘  └──────────────┘                 │
│   ┌──────────────────────────────────────────────────┐                  │
│   │ Simulators: sim-iot-01/02/03, sim-veh-01/02      │                  │
│   │ (run inside UE network namespaces)               │                  │
│   └──────────────────────────────────────────────────┘                  │
│                                                                         │
│   LAYER 3: 5G Core Network (Open5GS)                                   │
│   ┌─────────────────────────────────────────────────────────────┐      │
│   │ Control Plane: NRF │ AMF │ AUSF │ UDM │ UDR │ NSSF │ BSF │ PCF │  │
│   ├─────────────────────────────────────────────────────────────┤      │
│   │ User Plane:                                                  │      │
│   │   Slice 1: SMF1 ↔ UPF1 (10.45.0.0/16)                     │      │
│   │   Slice 2: SMF2 ↔ UPF2 (10.46.0.0/16)                     │      │
│   │   Slice 3: SMF3 ↔ UPF3 (10.47.0.0/16) [no internet]       │      │
│   └─────────────────────────────────────────────────────────────┘      │
│                                                                         │
│   LAYER 2: Radio Access Network (UERANSIM)                              │
│   ┌──────────────────────────────────────────────────┐                  │
│   │ gNodeB (Base Station)                            │                  │
│   └──────────┬──────────────┬──────────────┬─────────┘                  │
│              │              │              │                             │
│   LAYER 1: User Equipment (UERANSIM)                                    │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐                             │
│   │ UE1      │  │ UE2      │  │ UE3      │                             │
│   │ (IoT)    │  │ (Vehicle)│  │(Restrict.)│                             │
│   │ Slice 1  │  │ Slice 2  │  │ Slice 3  │                             │
│   └──────────┘  └──────────┘  └──────────┘                             │
│                                                                         │
│   ═══════════════════════════════════════════════════════════           │
│   Docker Network: open5gs (10.33.33.0/24, bridge: br-ogs)              │
└─────────────────────────────────────────────────────────────────────────┘
```

**Why this layered design?** Each layer can be started, stopped, and debugged independently. The 5G core can run without the application layer, the framework can run without simulators, and slices can be stopped individually without affecting others. This modularity makes it easy to demonstrate specific features in isolation.

---

## 2. Docker Network Design

All containers communicate over a single Docker bridge network:

| Property | Value |
|----------|-------|
| Network Name | `open5gs` |
| Subnet | `10.33.33.0/24` |
| Bridge Interface | `br-ogs` |
| Gateway | `10.33.33.1` |
| Driver | `bridge` |

This network is created by the Docker Compose files. Every container (core NFs, gNB, UEs, apps, infrastructure) gets an IP address in the `10.33.33.0/24` range for inter-container communication.

**Important distinction — Docker Network vs UE PDU Session Subnets:**

The `10.33.33.0/24` network is the Docker infrastructure network. It is how the containers talk to each other. The UE PDU session subnets (`10.45.0.0/16`, `10.46.0.0/16`, `10.47.0.0/16`) are the 5G data plane subnets assigned by each UPF. When a UE establishes a PDU session, it gets an IP from its slice's subnet on its `uesimtun0` tunnel interface. Traffic from the UE's `uesimtun0` goes through the GTP-U tunnel to the UPF, which then NATs it to the Docker network (or the internet).

```
UE Container Network Interfaces:
├── eth0: 10.33.33.X/24          ← Docker bridge (infrastructure)
└── uesimtun0: 10.45/46/47.X.X  ← 5G PDU session (data plane via GTP-U tunnel)
```

---

## 3. Basic Deployment Architecture

The basic deployment is a single-slice 5G network with no network slicing. It uses one SMF and one UPF shared by all UEs.

```
                                    ┌─────────┐
                                    │   NRF   │ ← NF Discovery
                                    └────┬────┘
                         SBI             │           SBI
          ┌──────────────────────────────┼──────────────────────────┐
          │              │               │              │           │
     ┌────┴───┐    ┌────┴───┐     ┌─────┴────┐   ┌────┴───┐  ┌───┴──┐
     │  AUSF  │    │  UDM   │     │   AMF    │   │  NSSF  │  │ PCF  │
     │  Auth  │    │  Sub.  │     │ Mobility │   │ Slice  │  │Policy│
     └────────┘    └───┬────┘     └────┬─────┘   └────────┘  └──┬───┘
                       │               │                         │
                  ┌────┴───┐           │ N2 (NGAP)          ┌───┴───┐
                  │  UDR   │           │                     │  SMF  │
                  │  Data  ├──┐        │              N4     │Session│
                  └────────┘  │   ┌────┴────┐    (PFCP)     └───┬───┘
                              │   │  gNodeB │                   │
                         ┌────┴─┐ │  (gNB)  │              ┌───┴───┐
                         │Mongo │ └──┬──┬───┘   N3 (GTP-U) │  UPF  │
                         │  DB  │    │  │  │  ────────────► │  NAT  │
                         └──────┘    │  │  │                └───┬───┘
                                     │  │  │                    │
                               NR-Uu │  │  │ NR-Uu              │ IP
                                     │  │  │                    │
        ┌────────────────────────────┼──┼──┼───────┐       ┌───┴───────┐
        │                            │  │  │       │       │   Apps    │
   ┌────┴─────┐ ┌─────────┐ ┌──────┴┐ │ ┌┴──────┐│       │MQTT, Edge │
   │UE-IoT-01 │ │UE-IoT-02│ │UE-IoT │ │ │UE-Veh ││       │ Node-RED  │
   │Temp/Humid│ │AirQualit│ │  -03  │ │ │ -01/02││       └───────────┘
   └──────────┘ └─────────┘ └───────┘ │ └───────┘│
                                       │          │
                                  ┌────┴─────┐    │
                                  │ UE-Veh-02│    │
                                  └──────────┘    │
                                                  │
```

**Components:** 10 Core NFs + 1 gNB + 5 UEs + 5 Simulators + 3 Apps + MongoDB + WebUI = 26 containers

**Design Decision — Why basic mode?** The basic mode provides a simpler starting point for understanding 5G architecture before moving to the complexity of network slicing. During the presentation, we first show the basic topology and Node-RED dashboard working, then stop the basic setup and start the network slicing setup to demonstrate the additional features.

---

## 4. Network Slicing Deployment Architecture

The network slicing deployment creates three independent data paths, each with its own SMF and UPF:

```
                                    ┌─────────┐
                                    │   NRF   │ ← All NFs register here
                                    └────┬────┘
                                         │ SBI
       ┌─────────┬──────────┬────────────┼────────────┬──────────┬─────────┐
       │         │          │            │            │          │         │
  ┌────┴──┐ ┌───┴──┐ ┌────┴──┐   ┌─────┴────┐  ┌───┴──┐  ┌───┴──┐ ┌───┴──┐
  │ AUSF  │ │ UDM  │ │  UDR  │   │   AMF    │  │ NSSF │  │ BSF  │ │ PCF  │
  └───────┘ └──────┘ └───┬───┘   └────┬─────┘  └──────┘  └──────┘ └──┬───┘
                         │             │                               │
                    ┌────┴──┐          │ N2 (NGAP)                     │
                    │MongoDB│          │                               │
                    └───────┘     ┌────┴────┐                          │
                                  │  gNodeB │                          │
                                  └┬───┬───┬┘                          │
                                   │   │   │                           │
                      NR-Uu Radio  │   │   │                           │
                    ┌──────────────┘   │   └──────────────┐            │
                    │                  │                   │            │
  ╔═════════════════╧══════════════════╧═══════════════════╧═══════════╧═══╗
  ║                                                                        ║
  ║  SLICE 1 — IoT (SST:1, SD:000001)              Subnet: 10.45.0.0/16  ║
  ║  ┌──────┐          ┌──────┐    N4     ┌──────┐                        ║
  ║  │ UE1  │          │ SMF1 │◄─────────►│ UPF1 │──► Internet + MQTT    ║
  ║  │(IoT) │          │      │   (PFCP)  │ NAT  │                        ║
  ║  └──────┘          └──────┘           └──────┘                        ║
  ║   IMSI: 001010000000004                  │ N3 (GTP-U)                  ║
  ║   IP: 10.45.0.X                      gNB ◄──────────────────          ║
  ║                                                                        ║
  ╠════════════════════════════════════════════════════════════════════════╣
  ║                                                                        ║
  ║  SLICE 2 — Vehicle (SST:1, SD:000002)          Subnet: 10.46.0.0/16  ║
  ║  ┌──────┐          ┌──────┐    N4     ┌──────┐                        ║
  ║  │ UE2  │          │ SMF2 │◄─────────►│ UPF2 │──► Internet + Edge    ║
  ║  │(Veh.)│          │      │   (PFCP)  │ NAT  │                        ║
  ║  └──────┘          └──────┘           └──────┘                        ║
  ║   IMSI: 001010000000002                  │ N3 (GTP-U)                  ║
  ║   IP: 10.46.0.X                      gNB ◄──────────────────          ║
  ║                                                                        ║
  ╠════════════════════════════════════════════════════════════════════════╣
  ║                                                                        ║
  ║  SLICE 3 — Restricted (SST:1, SD:000003)       Subnet: 10.47.0.0/16  ║
  ║  ┌──────┐          ┌──────┐    N4     ┌──────┐                        ║
  ║  │ UE3  │          │ SMF3 │◄─────────►│ UPF3 │──✕ Internet BLOCKED   ║
  ║  │(Rest)│          │      │   (PFCP)  │ NAT  │──► Internal only       ║
  ║  └──────┘          └──────┘           └──────┘    (MQTT, Node-RED)    ║
  ║   IMSI: 001010000000001                  │ N3 (GTP-U)                  ║
  ║   IP: 10.47.0.X                      gNB ◄──────────────────          ║
  ║                                                                        ║
  ╚════════════════════════════════════════════════════════════════════════╝
```

**Key Design Principle:** The AMF, gNB, NRF, and control plane NFs are shared across all slices. Only the session management (SMF) and user plane (UPF) are per-slice. This follows the 3GPP network slicing architecture where the control plane is shared but the user plane is isolated per slice.

---

## 5. 5G Core Network Functions

### 5.1 Shared Control Plane NFs

These network functions are shared across all slices. They run as single instances regardless of the deployment mode.

| NF | Full Name | Role | Why It Exists |
|----|-----------|------|---------------|
| **NRF** | Network Repository Function | NF discovery and registration | Every NF registers with NRF on startup. When AMF needs to find a SMF for a specific slice, it queries NRF. NRF is the "phone book" of the 5G core. |
| **AMF** | Access and Mobility Management Function | UE registration, connection management, mobility | The first core NF that a UE contacts (via gNB). AMF handles the NAS (Non-Access Stratum) signaling: registration, authentication, security, and slice selection. There is one shared AMF for all slices. |
| **AUSF** | Authentication Server Function | UE authentication | When a UE registers, AMF asks AUSF to verify the UE's identity using 5G-AKA (Authentication and Key Agreement). AUSF retrieves authentication vectors from UDM. |
| **UDM** | Unified Data Management | Subscriber data management | Manages subscriber profiles — which slices a UE is allowed to access, authentication credentials, and session management data. UDM retrieves raw data from UDR. |
| **UDR** | Unified Data Repository | Subscriber data storage | The actual database interface. UDR reads/writes subscriber records in MongoDB. It stores IMSI, keys, OPC, allowed S-NSSAI, and APN configurations. |
| **NSSF** | Network Slice Selection Function | Slice selection | When AMF receives a registration request with S-NSSAI, it asks NSSF which SMF instance should handle that slice. NSSF returns the appropriate SMF based on SST/SD values. |
| **BSF** | Binding Support Function | Session binding | Helps route service requests to the correct PCF instance when there are multiple PCF deployments. In our setup with a single PCF, BSF provides binding support for session continuity. |
| **PCF** | Policy Control Function | Policy and QoS decisions | Provides policy rules to SMFs — QoS parameters, charging rules, and access control policies. SMFs query PCF when creating PDU sessions. PCF stores policy data in MongoDB. |

### 5.2 Per-Slice User Plane NFs

In the network slicing deployment, each slice has its own SMF and UPF pair:

| NF | Slice | Subnet | DNN | Internet | Description |
|----|-------|--------|-----|----------|-------------|
| **SMF1** | Slice 1 (IoT) | 10.45.0.0/16 | internet | ✅ Yes | Manages PDU sessions for IoT UEs. Assigns IPs from 10.45.x.x range. Controls UPF1 via PFCP. |
| **UPF1** | Slice 1 (IoT) | 10.45.0.0/16 | internet | ✅ Yes | Forwards data packets for Slice 1. Performs NAT for internet access. Receives GTP-U tunneled packets from gNB and forwards to destination. |
| **SMF2** | Slice 2 (Vehicle) | 10.46.0.0/16 | internet | ✅ Yes | Manages PDU sessions for Vehicle UEs. Assigns IPs from 10.46.x.x range. |
| **UPF2** | Slice 2 (Vehicle) | 10.46.0.0/16 | internet | ✅ Yes | Forwards data packets for Slice 2. Performs NAT. Vehicle telemetry exits here toward the Edge server. |
| **SMF3** | Slice 3 (Restricted) | 10.47.0.0/16 | internet | ❌ No | Manages PDU sessions for Restricted UEs. Assigns IPs from 10.47.x.x range. |
| **UPF3** | Slice 3 (Restricted) | 10.47.0.0/16 | internet | ❌ No | Forwards packets but internet is blocked by iptables rules on the container. UE3 can only reach internal Docker network services (MQTT, Node-RED, Edge). |

In the basic deployment, there is just a single `smf` and `upf` shared by all UEs.

---

## 6. 3GPP Interfaces and Protocols

The following 3GPP-defined interfaces are used in the system:

### 6.1 Control Plane Interfaces

| Interface | Between | Protocol | Purpose |
|-----------|---------|----------|---------|
| **SBI** | All NFs ↔ NRF | HTTP/2 (REST API) | Service-Based Interface. Every NF registers with NRF and discovers other NFs through REST API calls. This is the 5G Service-Based Architecture (SBA). |
| **N1** | UE ↔ AMF | NAS | Non-Access Stratum signaling. Registration, authentication, security mode, PDU session requests. Carried transparently through the gNB. |
| **N2** | AMF ↔ gNB | NGAP (over SCTP) | Next Generation Application Protocol. Carries N1 NAS messages between AMF and gNB, plus RAN-level control (handover, paging, UE context). |
| **N4** | SMF ↔ UPF | PFCP (over UDP) | Packet Forwarding Control Protocol. SMF tells UPF how to handle packets — which tunnels to create, which rules to apply, where to forward data. |
| **N11** | AMF ↔ SMF | SBI (HTTP/2) | AMF requests SMF to create/modify/release PDU sessions on behalf of UEs. |
| **N12** | AMF ↔ AUSF | SBI (HTTP/2) | Authentication request/response during UE registration. |
| **N8/N10** | UDM ↔ AMF/SMF | SBI (HTTP/2) | Subscriber data retrieval for registration and session management. |
| **N13** | UDM ↔ UDR | SBI (HTTP/2) | Raw subscriber data read/write from MongoDB. |
| **N22** | AMF ↔ NSSF | SBI (HTTP/2) | Slice selection — AMF asks NSSF which SMF should handle a given S-NSSAI. |

### 6.2 User Plane Interfaces

| Interface | Between | Protocol | Purpose |
|-----------|---------|----------|---------|
| **NR-Uu** | UE ↔ gNB | 5G NR Radio | The radio interface between UE and base station. In UERANSIM, this is simulated over the Docker network, but logically represents the wireless link. |
| **N3** | gNB ↔ UPF | GTP-U (over UDP) | GPRS Tunneling Protocol — User Plane. User data from UEs is encapsulated in GTP-U tunnels between gNB and UPF. Each UE/PDU session has a unique tunnel (TEID). |
| **N6** | UPF ↔ Data Network | IP | The exit point from the 5G network to the data network (internet or internal services). UPF performs NAT here. |

### 6.3 How a UE Connects (Registration + PDU Session Flow)

This is the step-by-step signaling flow when a UE powers on:

```
UE              gNB             AMF            AUSF    UDM/UDR    NSSF    SMF     UPF
│                │               │               │       │         │       │       │
│── Registration ──►             │               │       │         │       │       │
│   Request     │── N2 (NGAP) ──►               │       │         │       │       │
│               │               │── N12 ────────►│       │         │       │       │
│               │               │   Auth Request │── N13 ►│         │       │       │
│               │               │               │◄──────│         │       │       │
│               │               │◄──────────────│       │         │       │       │
│               │               │                                  │       │       │
│◄─ Auth Challenge ─────────────│                                  │       │       │
│── Auth Response ──────────────►                                  │       │       │
│               │               │── N22 ─────────────────────────►│       │       │
│               │               │   Slice Selection               │       │       │
│               │               │◄────────────────────────────────│       │       │
│               │               │                                          │       │
│◄─ Registration ───────────────│   (UE is now registered)                 │       │
│   Accept      │               │                                          │       │
│               │               │                                          │       │
│── PDU Session ─►              │                                          │       │
│   Est. Request│── N2 ────────►│── N11 (SBI) ────────────────────────────►│       │
│               │               │   Create Session                         │       │
│               │               │                                          │── N4 ─►│
│               │               │                                          │ PFCP   │
│               │               │                                          │ Create │
│               │               │                                          │◄──────│
│               │               │◄─────────────────────────────────────────│       │
│◄─ PDU Session ────────────────│                                          │       │
│   Accepted    │               │                                          │       │
│               │               │                                          │       │
│═══ GTP-U Tunnel (N3) ════════════════════════════════════════════════════════════►│
│   User data now flows through the tunnel                                         │
```

After this flow completes, the UE has:
1. A `uesimtun0` interface with an IP from its slice's subnet
2. A GTP-U tunnel through the gNB to its slice's UPF
3. The ability to send/receive data through the 5G network

---

## 7. Radio Access Network (RAN)

The RAN consists of a single gNodeB (gNB) simulated by UERANSIM:

| Property | Value |
|----------|-------|
| Container | `gnb` |
| Software | UERANSIM gNB |
| MCC/MNC | 001/01 |
| TAC | 1 |
| Link to AMF | N2 (NGAP over SCTP) |
| Link to UPFs | N3 (GTP-U over UDP) |
| Supported Slices | All three (SST:1/SD:000001, 000002, 000003) |

**Why a single gNB?** In a real network, there would be many gNBs covering different geographic areas. In our simulation, all UEs are "in range" of the same gNB. The gNB connects to the AMF for control plane signaling and to each UPF for user plane data tunneling.

**How the gNB routes data:** When a UE sends data, the gNB looks up the GTP-U tunnel associated with that UE's PDU session. Each tunnel has a unique TEID (Tunnel Endpoint Identifier). The gNB encapsulates the UE's IP packet in a GTP-U header and forwards it to the correct UPF based on the TEID.

---

## 8. User Equipment (UE)

### 8.1 UERANSIM UEs (Network Slicing)

| UE | Container | IMSI | Slice (SST/SD) | PDU Session IP | Purpose |
|----|-----------|------|-----------------|----------------|---------|
| UE1 | `ue1` | 001010000000004 | 1/000001 | 10.45.0.X | IoT sensor data |
| UE2 | `ue2` | 001010000000002 | 1/000002 | 10.46.0.X | Vehicle telemetry |
| UE3 | `ue3` | 001010000000001 | 1/000003 | 10.47.0.X | Restricted (no internet) |

### 8.2 UERANSIM UEs (Basic)

| UE | Container | Purpose |
|----|-----------|---------|
| UE-IoT-01 | `ue-iot-01` | Temperature/Humidity sensor |
| UE-IoT-02 | `ue-iot-02` | CO₂/PM2.5 air quality sensor |
| UE-IoT-03 | `ue-iot-03` | Temperature/Pressure/Battery |
| UE-Veh-01 | `ue-veh-01` | Vehicle 1 GPS/Speed/Alerts |
| UE-Veh-02 | `ue-veh-02` | Vehicle 2 GPS/Speed/Alerts |

### 8.3 PacketRusher UEs (Load Testing)

| Property | Value |
|----------|-------|
| IMSI Range | 001010000000100 – 001010000000149 |
| Slice | SST:1, SD:000001 (Slice 1) |
| Count | Configurable 1–50+ |
| Key/OPC | Same as UERANSIM UEs |
| Purpose | Multi-UE load testing + call simulation |

### 8.4 UE Network Interfaces

Each UERANSIM UE container has two network interfaces:

```
UE Container
├── eth0:       10.33.33.X     ← Docker bridge (how UERANSIM talks to core NFs)
└── uesimtun0:  10.45/46/47.X  ← PDU session tunnel (how user data flows through 5G)
```

The `uesimtun0` interface is created dynamically when the PDU session is established. All application data (MQTT publish, HTTP POST, ping) goes through `uesimtun0`, which means it travels through the GTP-U tunnel → gNB → UPF → destination.

---

## 9. Application Layer

The application layer consists of three services and five simulators that generate realistic traffic through the 5G network:

```
                                    ┌────────────────┐
                                    │   Node-RED     │
                                    │   Dashboard    │◄── subscribes to MQTT topics
                                    │   :1880        │    iot/*, veh/*
                                    └────────────────┘
                                           ▲
                                           │ MQTT Subscribe
                                    ┌──────┴─────────┐
   IoT Simulators ──── MQTT ──────►│  MQTT Broker   │◄──── MQTT ──── Edge Server
   (sim-iot-01/02/03)   publish     │  (Mosquitto)   │      publish   (aggregated
   Topics: iot/ue-iot-*             │  :1883         │      veh/*      telemetry)
                                    └────────────────┘                    ▲
                                                                          │ HTTP POST
                                                              Vehicle Simulators
                                                              (sim-veh-01/02)
                                                              → http://edge:5000/telemetry
```

### 9.1 MQTT Broker (Mosquitto)

The central message hub. All IoT data and aggregated vehicle data passes through here.

**MQTT Topics:**
| Topic | Publisher | Subscriber | Data |
|-------|-----------|------------|------|
| `iot/ue-iot-01` | sim-iot-01 | Node-RED | Temperature, Humidity |
| `iot/ue-iot-02` | sim-iot-02 | Node-RED | CO₂, PM2.5 |
| `iot/ue-iot-03` | sim-iot-03 | Node-RED | Temperature, Pressure, Battery |
| `veh/telemetry` | Edge Server | Node-RED | Aggregated vehicle data |

### 9.2 Edge Server (Flask)

Receives HTTP POST requests from vehicle simulators. Validates, aggregates, and republishes the data to MQTT.

**Why an Edge server?** Vehicles send raw telemetry (GPS, speed, fuel, RPM, alerts) via HTTP. The Edge server processes this data — it could filter, aggregate, or trigger alerts — before publishing to MQTT. This demonstrates an edge computing pattern where processing happens close to the data source.

### 9.3 Node-RED Dashboard

Subscribes to all MQTT topics and displays real-time data with gauges, charts, and alert indicators. Accessible at `http://localhost:1880`.

### 9.4 Simulator Network Mode

Simulators use Docker's `network_mode: "container:ue-XXX"` to share the UE's network namespace. This means:

- The simulator sees the UE's `uesimtun0` interface
- When the simulator publishes to MQTT, the traffic goes through the 5G tunnel
- The simulator's traffic is indistinguishable from the UE's own traffic
- This is how we prove data actually flows through the 5G network

---

## 10. Data Flow Paths

### 10.1 IoT Data Flow (Slice 1)

```
sim-iot-01         UE1              gNB              UPF1            MQTT          Node-RED
(Python)       (uesimtun0)       (GTP-U)          (NAT)          (Mosquitto)     (Dashboard)
    │               │               │                │               │               │
    │── MQTT ──────►│               │                │               │               │
    │  publish      │── GTP-U ─────►│                │               │               │
    │  iot/ue-iot-01│  (N3 tunnel)  │── GTP-U ──────►│               │               │
    │               │               │  (N3 tunnel)   │── IP ────────►│               │
    │               │               │                │  (port 1883)  │── MQTT ──────►│
    │               │               │                │               │  subscribe    │
    │               │               │                │               │               │── Display
```

### 10.2 Vehicle Data Flow (Slice 2)

```
sim-veh-01         UE2              gNB              UPF2            Edge           MQTT        Node-RED
(Python)       (uesimtun0)       (GTP-U)          (NAT)          (Flask)        (Mosquitto)   (Dashboard)
    │               │               │                │               │               │            │
    │── HTTP POST ─►│               │                │               │               │            │
    │  /telemetry   │── GTP-U ─────►│                │               │               │            │
    │               │  (N3 tunnel)  │── GTP-U ──────►│               │               │            │
    │               │               │                │── IP ────────►│               │            │
    │               │               │                │  (port 5000)  │── MQTT ──────►│            │
    │               │               │                │               │  veh/telemetry│── MQTT ───►│
    │               │               │                │               │               │  subscribe │
```

### 10.3 Restricted Data Flow (Slice 3)

```
sim-restricted     UE3              gNB              UPF3
(Python)       (uesimtun0)       (GTP-U)          (iptables)
    │               │               │                │
    │── MQTT ──────►│               │                │
    │  publish      │── GTP-U ─────►│── GTP-U ──────►│──► MQTT (10.33.33.X)  ✅ ALLOWED
    │               │               │                │──► 8.8.8.8 (internet)  ❌ BLOCKED
    │               │               │                │──► Node-RED            ✅ ALLOWED
```

---

## 11. Network Slicing Design

### 11.1 S-NSSAI Configuration

Each slice is identified by an S-NSSAI (Single Network Slice Selection Assistance Information):

| Parameter | Slice 1 | Slice 2 | Slice 3 |
|-----------|---------|---------|---------|
| SST (Slice/Service Type) | 1 | 1 | 1 |
| SD (Slice Differentiator) | 000001 | 000002 | 000003 |
| Combined S-NSSAI | SST:1, SD:000001 | SST:1, SD:000002 | SST:1, SD:000003 |

SST=1 means "eMBB" (enhanced Mobile Broadband) for all slices. The SD value differentiates between them.

### 11.2 How Slice Selection Works

1. UE sends Registration Request with its **Requested NSSAI** (list of S-NSSAIs it wants)
2. AMF receives the request and queries **NSSF** with the UE's requested S-NSSAI
3. NSSF checks its policy and returns the **Allowed NSSAI** for this UE
4. When the UE requests a PDU session with a specific S-NSSAI, AMF queries **NRF** to find the SMF that serves that S-NSSAI
5. NRF returns the correct SMF (e.g., SMF1 for SD:000001)
6. AMF sends the PDU session create request to that SMF
7. SMF creates the session and configures the UPF via PFCP

### 11.3 Slice Isolation

Each slice has its own:
- **SMF** — independent session management
- **UPF** — independent data forwarding with separate subnet
- **IP range** — UEs in different slices get IPs from different subnets (10.45/46/47)
- **GTP-U tunnel** — separate tunnel per UE/PDU session

This means a failure in Slice 1 (e.g., UPF1 crash) does not affect Slices 2 or 3. The resilience test proves this by stopping Slices 1 and 2 and verifying Slice 3 continues operating.

---

## 12. Internet Blocking (Slice 3)

UE3 (Slice 3) has an active PDU session and can send/receive data, but internet access is blocked at the UPF3 container level using iptables:

**How it works:**

1. UE3 establishes a normal PDU session and gets IP `10.47.0.X`
2. Traffic from UE3 travels through GTP-U tunnel → gNB → UPF3
3. At UPF3, iptables rules inspect the destination:
   - If destination is on the Docker network (`10.33.33.0/24`) → **ALLOWED** (MQTT, Node-RED, Edge)
   - If destination is external (e.g., `8.8.8.8`) → **DROPPED**

**Verification:**
- `docker exec ue3 ping -I uesimtun0 8.8.8.8` → **FAIL** (100% packet loss)
- `docker exec ue3 ping -I uesimtun0 mqtt` → **SUCCESS**

This demonstrates that network slicing can enforce different access policies per slice.

---

## 13. Subscriber Provisioning Design

Each UE needs a subscriber record in MongoDB before it can register with the 5G core. The provisioning includes IMSI, authentication keys, and allowed slice information.

### 13.1 Auto-Provisioning (db-init)

When `docker compose up` runs the network slicing setup, a `db-init` service executes `mongo-init.js` automatically:

```
docker compose up
    │
    ├── MongoDB starts first (depends_on)
    │
    └── db-init service starts
        └── Runs: mongosh mongodb://db/open5gs mongo-init.js
            ├── Registers UE1 (IMSI 001010000000004) → Slice 1
            ├── Registers UE2 (IMSI 001010000000002) → Slice 2
            ├── Registers UE3 (IMSI 001010000000001) → Slice 3
            └── Registers 18 PacketRusher UEs (IMSI 001010000000100–117)
```

**Why upsert?** The script uses `updateOne` with `upsert: true`. This means:
- If the subscriber doesn't exist → INSERT it
- If the subscriber already exists → UPDATE it
- This makes it safe to run multiple times (idempotent)

### 13.2 Subscriber Data Fields

Each subscriber record contains:

| Field | Example (UE1) | Purpose |
|-------|---------------|---------|
| IMSI | 001010000000004 | Unique subscriber identity (MCC:001, MNC:01, MSIN:0000000004) |
| Key (K) | 465B5CE8 B199B49F AA5F0A2E E238A6BC | 128-bit authentication key |
| OPC | E8ED289D EBA952E4 283B54E8 8E6183CA | Operator variant key |
| AMF | 8000 | Authentication Management Field |
| DNN | internet | Data Network Name (APN equivalent) |
| S-NSSAI | SST:1, SD:000001 | Allowed network slice |
| Session Type | IPv4 | PDU session type |

---

## 14. Transport Network and QoS Design

### 14.1 QoS Profile System

QoS is implemented using Linux `tc` (traffic control) commands applied to UE container interfaces. The `tc` tool allows us to shape traffic by limiting bandwidth, adding latency, and introducing packet loss.

**Implementation approach:** We use `tc qdisc` with two queuing disciplines:
- **HTB (Hierarchical Token Bucket)** — for bandwidth limiting (rate/ceil)
- **netem (Network Emulator)** — for latency and packet loss

Rules are applied to the `uesimtun0` interface inside UE containers, which means they affect traffic going through the 5G tunnel.

### 14.2 Priority-Based QoS

For demonstrating bandwidth allocation under congestion, we use HTB on the Edge server's `eth0` interface to create a shared bottleneck:

```
Edge Server eth0 (shared 20 Mbps bottleneck)
├── HTB Root (rate: 20 Mbps)
│   ├── Class 1:10 — IoT traffic
│   │   rate: 14 Mbps, ceil: 18 Mbps, prio: 1
│   │   (filter: source IP from 10.45.0.0/16)
│   │
│   └── Class 1:20 — Vehicle traffic
│       rate: 4 Mbps, ceil: 15 Mbps, prio: 2
│       (filter: source IP from 10.46.0.0/16)
```

**How it works:** When both IoT and Vehicle are competing for the same 20 Mbps link:
- The higher-priority class gets its guaranteed rate first
- Leftover bandwidth is shared based on ceil values
- Under heavy load, the lower-priority class gets throttled

---

## 15. Load Testing Architecture (PacketRusher)

PacketRusher is a 5G core network tester that can simulate multiple UEs simultaneously. Unlike UERANSIM, PacketRusher uses the `gtp5g` kernel module to establish **real GTP-U tunnels** through the UPF.

```
PacketRusher                        AMF                 SMF1               UPF1
    │                                │                   │                  │
    │── Register UE #1 (NAS) ──────►│                   │                  │
    │── Register UE #2 (NAS) ──────►│                   │                  │
    │── Register UE #3 (NAS) ──────►│   (concurrent)    │                  │
    │── ...                         │                   │                  │
    │── Register UE #N (NAS) ──────►│                   │                  │
    │                                │                   │                  │
    │◄─ Registration Accept ────────│                   │                  │
    │                                │                   │                  │
    │── PDU Session Request ────────►│── Create Session ►│── PFCP Create ──►│
    │                                │                   │                  │
    │◄─ PDU Session Accept ─────────│                   │                  │
    │                                │                   │                  │
    │════ GTP-U Tunnel (real kernel tunnel via gtp5g) ═══════════════════►│
    │    iperf3 / user data through actual GTP-U                           │
```

**Why PacketRusher in addition to UERANSIM?**

| Feature | UERANSIM | PacketRusher |
|---------|----------|-------------|
| UE simulation | Yes (1 UE per container) | Yes (many UEs in 1 container) |
| Registration | Realistic NAS signaling | Realistic NAS signaling |
| GTP-U tunnel | Simulated (userspace TUN) | Real (kernel gtp5g module) |
| iperf3 throughput | Through Docker bridge | Through actual GTP-U tunnel |
| Multi-UE stress test | Need many containers | Single container, many UEs |
| Scalability | Limited (1 UE = 1 container) | High (50+ UEs in 1 container) |

---

## 16. Call Simulation Design

Call simulation demonstrates Voice, Video, and Emergency calls between UEs registered via PacketRusher. It runs on top of the load testing infrastructure.

### 16.1 Call Types and 5QI

| Call Type | 5QI | QoS Characteristics | Priority | Bitrate |
|-----------|-----|---------------------|----------|---------|
| Voice | 1 | GBR, delay 100ms, error 10⁻² | 5 | 64 kbps (AMR-WB) |
| Video | 2 | GBR, delay 150ms, error 10⁻³ | 4 | 2 Mbps (H.264 720p) |
| Emergency 112 | 69 | GBR, delay 60ms, error 10⁻² | 0 (highest) | 64 kbps (AMR-WB) |

### 16.2 Call Flow

```
Caller UE           5G Core              Callee UE           MQTT Broker
    │                  │                     │                    │
    │── Call Request ──►                     │                    │
    │  (5QI, codec)    │── Dedicated Bearer ►│                    │
    │                  │   (QoS flow setup)  │                    │
    │◄─ Call Accept ───│◄── Accept ──────────│                    │
    │                  │                     │                    │
    │── MQTT Publish ──────────────────────────────────────────►│
    │  "CALL_PROOF"    │                     │                    │
    │                  │                     │◄── MQTT Deliver ──│
    │                  │                     │   "CALL_PROOF"     │
    │                  │                     │                    │
    │◄═══════════ RTP Media Stream (simulated) ═════════════════►│
```

**Why MQTT for proof?** Since we can't set up real VoLTE/IMS infrastructure in a simulation, we use MQTT messages as proof that data actually flows between the UEs through the 5G network. Each call publishes a `CALL_PROOF` message that the other side receives.

### 16.3 Call Simulation Gating

Call simulation is **disabled by default** on the Load Test page. It only becomes enabled after running a successful Multi-UE Load Test. This is because calls require registered UEs with actual IP addresses — the dropdowns are populated from real PacketRusher test results.

---

## 17. Framework (Web UI) Architecture

The management framework uses a client-server architecture:

```
Browser (Client)                    Server (FastAPI)              Docker Engine
┌──────────────┐                   ┌──────────────┐              ┌──────────┐
│ HTML + CSS   │    HTTP/JSON      │  app.py      │   Docker CLI │ Containers│
│ JavaScript   │◄────────────────►│  50+ API     │◄────────────►│ 20+ NFs   │
│ vis-network  │  fetch() calls    │  endpoints   │  docker exec │ UEs, Apps │
│              │                   │              │  docker ps   │           │
│ 7 Pages:     │                   │ Modules:     │  docker logs │           │
│ - topology   │                   │ - topology   │              │           │
│ - control    │                   │ - control    │              │           │
│ - verify     │                   │ - tests      │   MongoDB    │           │
│ - usecases   │                   │ - transport  │◄────────────►│ subscriber│
│ - monitoring │                   │ - loadtest   │  mongosh     │ data      │
│ - loadtest   │                   │ - callsim    │              │           │
│ - basic-topo │                   │ - monitoring │              │           │
└──────────────┘                   └──────────────┘              └──────────┘
```

**Design decisions:**
- **No React/Angular build step:** The frontend uses vanilla HTML/CSS/JavaScript served directly by FastAPI's Jinja2 templates. This keeps deployment simple — no npm, no webpack, no build step.
- **vis-network for topology:** The vis.js library handles interactive graph rendering, zooming, panning, and click events for the topology visualization.
- **REST API pattern:** All data exchange uses JSON over REST endpoints. The frontend polls or fetches on-demand, keeping the architecture stateless.
- **Docker CLI for control:** The backend executes Docker CLI commands (`docker ps`, `docker exec`, `docker inspect`) to interact with containers. This avoids the complexity of the Docker SDK while providing full control.

For detailed descriptions of each backend module, see [Framework Backend](framework-backend.md).
For detailed descriptions of each frontend page, see [Framework Frontend](framework-frontend.md).

---

[← Back to Main README](../README.md) | [Next: Configuration Files →](config-files.md)