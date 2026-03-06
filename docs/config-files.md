# Configuration Files

[← Back to Main README](../README.md)

This document describes all the Open5GS, UERANSIM, and PacketRusher configuration YAML files used in the project. It covers both the **basic** (no slicing) and **network slicing** deployments, explaining what each file configures, what the key parameters mean, and how they relate to each other.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Common Configuration Concepts](#2-common-configuration-concepts)
3. [How Configs Are Loaded](#3-how-configs-are-loaded)
4. [Basic Deployment Configs](#4-basic-deployment-configs)
   - 4.1 [Core NF Configs (Open5GS)](#41-core-nf-configs-open5gs)
   - 4.2 [RAN and UE Configs (UERANSIM)](#42-ran-and-ue-configs-ueransim)
   - 4.3 [PacketRusher Config (Basic)](#43-packetrusher-config-basic)
5. [Network Slicing Configs](#5-network-slicing-configs)
   - 5.1 [Shared Control Plane NFs](#51-shared-control-plane-nfs)
   - 5.2 [Per-Slice SMF Configs](#52-per-slice-smf-configs)
   - 5.3 [Per-Slice UPF Configs](#53-per-slice-upf-configs)
   - 5.4 [NSSF — Slice Selection Rules](#54-nssf--slice-selection-rules)
   - 5.5 [gNodeB Config](#55-gnodeb-config)
   - 5.6 [UE Configs (Per-Slice)](#56-ue-configs-per-slice)
   - 5.7 [PacketRusher Config (Slicing)](#57-packetrusher-config-slicing)
   - 5.8 [mongo-init.js — Auto-Provisioning Script](#58-mongo-initjs--auto-provisioning-script)
6. [Key Differences: Basic vs Slicing](#6-key-differences-basic-vs-slicing)
7. [MQTT Broker Config](#7-mqtt-broker-config)
8. [Environment File](#8-environment-file)
9. [Config File Locations Summary](#9-config-file-locations-summary)

---

## 1. Overview

Configuration files are stored in the `configs/` directory with separate folders for each deployment mode:

```
configs/
├── basic/
│   ├── ueransim/       ← Basic deployment (single slice)
│   └── packetrusher/   ← PacketRusher for basic setup
└── network-slicing/    ← Network slicing deployment (3 slices)
```

All Open5GS NF config files use the same YAML structure defined by Open5GS. UERANSIM configs follow the UERANSIM YAML format. These files are mounted into Docker containers as volumes — the Docker Compose files map each config to the expected path inside the container.

---

## 2. Common Configuration Concepts

Before diving into individual files, here are the key concepts that appear across multiple configs:

### 2.1 PLMN (Public Land Mobile Network)

Every config references the same PLMN identity:

| Parameter | Value | Meaning |
|-----------|-------|---------|
| MCC | 001 | Mobile Country Code (test network) |
| MNC | 01 | Mobile Network Code (test operator) |
| Combined | 001/01 | This is the standard test PLMN used by Open5GS and UERANSIM |

### 2.2 S-NSSAI (Network Slice Selection Assistance Information)

Slices are identified by two values:

| Parameter | Description | Our Values |
|-----------|-------------|------------|
| SST (Slice/Service Type) | Type of service (1=eMBB, 2=URLLC, 3=MIoT) | 1 (eMBB for all slices) |
| SD (Slice Differentiator) | Distinguishes slices with the same SST | 000001, 000002, 000003 |

### 2.3 DNN (Data Network Name)

The DNN is equivalent to the 4G APN (Access Point Name). All our slices use DNN `internet`. This is the data network the UE wants to connect to when it creates a PDU session.

### 2.4 SBI (Service Based Interface)

Every 5G core NF exposes an HTTP/2 REST API on its SBI interface. The config specifies which address and port to bind to. In our Docker setup, NFs use their Docker DNS alias as the SBI address (e.g., `nrf.open5gs.org`, `amf.open5gs.org`, `smf1.open5gs.org`). Docker's built-in DNS resolves these to the container's current IP address automatically, so configs never need hardcoded IP addresses.

### 2.5 Authentication Keys

Every subscriber needs three authentication values:

| Parameter | Description | Our Value |
|-----------|-------------|-----------|
| K (Key) | 128-bit permanent key shared between UE and network | `465B5CE8B199B49FAA5F0A2EE238A6BC` |
| OPC | Operator variant of OP, derived from K and OP | `E8ED289DEBA952E4283B54E88E6183CA` |
| AMF (Auth Mgmt Field) | 16-bit field, set to `8000` for 5G | `8000` |

These same values must appear in both the UE config (UERANSIM side) and the subscriber database (MongoDB, provisioned by mongo-init.js).

---

## 3. How Configs Are Loaded

Docker Compose uses the `configs` feature to mount YAML files into containers at specific paths. Each service receives its config through this mechanism:

**Open5GS NFs** receive configs at `/etc/open5gs/custom/`:

```yaml
# In docker-compose.yaml:
services:
  amf:
    image: "fgftk/amf-open5gs:${OPEN5GS_VERSION}"
    command: "-c /etc/open5gs/custom/amf.yaml"      # ← Tells Open5GS which config to use
    configs:
      - source: amf_config
        target: /etc/open5gs/custom/amf.yaml         # ← Mounts the config inside container

configs:
  amf_config:
    file: ../../configs/network-slicing/amf.yaml      # ← Path to the actual config file on host
```

**UERANSIM components** (gNB, UEs) receive configs at `/UERANSIM/config/`:

```yaml
  gnb:
    image: "fgftk/gnb-ueransim:${UERANSIM_VERSION}"
    command: "-c /UERANSIM/config/gnb.yaml"
    configs:
      - source: gnb_config
        target: /UERANSIM/config/gnb.yaml
```

This means you can **edit the config files on the host machine** and they take effect after restarting the container — no Docker image rebuild is needed.

---

## 4. Basic Deployment Configs

Location: `configs/basic/ueransim/`

The basic deployment uses a single-slice architecture with one SMF and one UPF.

### 4.1 Core NF Configs (Open5GS)

#### `nrf.yaml` — Network Repository Function

The NRF is the first NF to start. All other NFs register with it.

**Key parameters:**
| Parameter | Value | Purpose |
|-----------|-------|---------|
| `sbi.server.address` | `nrf.open5gs.org` | Address where NRF listens for SBI requests |
| `sbi.server.port` | 80 | Port for NRF's SBI interface |

**What it does:** NRF provides a service registry. When AMF needs to find a SMF, it queries NRF's REST API. NRF returns the address of the matching SMF based on the requested S-NSSAI and DNN.

#### `amf.yaml` — Access and Mobility Management Function

**Key parameters:**
| Parameter | Value | Purpose |
|-----------|-------|---------|
| `ngap.server.address` | `amf.open5gs.org` | Address for N2 interface (toward gNB), SCTP protocol |
| `sbi.server.address` | `amf.open5gs.org` | Address for SBI interface (toward other NFs) |
| `sbi.client.nrf` | `http://nrf.open5gs.org:80` | NRF URI for discovery |
| `guami.plmn_id` | MCC:001, MNC:01 | Globally Unique AMF Identifier |
| `tai.plmn_id` | MCC:001, MNC:01 | Tracking Area Identity |
| `tai.tac` | 1 | Tracking Area Code |
| `s_nssai` | SST:1 | Supported slice(s) — basic mode only has one |
| `security.integrity_order` | NIA2, NIA1, NIA0 | Preferred integrity algorithms |
| `security.ciphering_order` | NEA0, NEA1, NEA2 | Preferred ciphering algorithms |

**What it does:** AMF is the first core NF the UE contacts. It handles registration, authentication (by calling AUSF), and slice selection (by calling NSSF). The `ngap.server.address` is where the gNB connects to send NAS messages.

#### `smf.yaml` — Session Management Function (Single)

**Key parameters:**
| Parameter | Value | Purpose |
|-----------|-------|---------|
| `sbi.server.address` | `smf.open5gs.org` | SBI interface address |
| `sbi.client.nrf` | `http://nrf.open5gs.org:80` | NRF URI for discovery |
| `pfcp.server.address` | `smf.open5gs.org` | N4 interface address (toward UPF) |
| `pfcp.client.upf.address` | `upf.open5gs.org` | Which UPF to control |
| `gtpu.server.address` | `smf.open5gs.org` | GTP-U tunnel endpoint |
| `session.subnet` | 10.45.0.0/16 | IP pool for PDU sessions |
| `session.gateway` | 10.45.0.1 | Default gateway for UEs |
| `dns` | 8.8.8.8, 8.8.4.4 | DNS servers pushed to UEs |
| `info.s_nssai.sst` | 1 | Slice this SMF serves |
| `info.s_nssai.dnn` | internet | Data network name |

**What it does:** When AMF forwards a PDU session request, SMF allocates an IP from the `subnet` pool and instructs UPF (via PFCP on N4) to create forwarding rules. The UE gets an IP like `10.45.0.2` on its `uesimtun0` interface.

#### `upf.yaml` — User Plane Function (Single)

**Key parameters:**
| Parameter | Value | Purpose |
|-----------|-------|---------|
| `pfcp.server.address` | `upf.open5gs.org` | N4 interface (listens for PFCP from SMF) |
| `gtpu.server.address` | `upf.open5gs.org` | N3 interface (receives GTP-U from gNB) |
| `session.subnet` | 10.45.0.0/16 | Must match SMF's subnet |
| `session.gateway` | 10.45.0.1 | Gateway for the subnet |

**What it does:** UPF is the data plane. It receives GTP-U encapsulated packets from the gNB (N3), decapsulates them, and forwards to the destination (NAT to internet or route to Docker network). Return traffic is encapsulated back into GTP-U and sent to the gNB.

**NAT:** The UPF container runs with `privileged: true` and `cap_add: NET_ADMIN` in Docker Compose. The entrypoint script creates a TUN interface (`ogstun`), assigns the gateway IP, and sets up iptables MASQUERADE rules for NAT. This allows UE traffic (e.g., 10.45.x.x) to reach the internet through the container's eth0.

#### Other Core NFs

These NFs have simpler configs — primarily just SBI address/port and connections to NRF:

| File | NF | SBI Address | Key Config |
|------|-----|-------------|-----------|
| `ausf.yaml` | AUSF | `ausf.open5gs.org` | Only SBI. Connects to NRF for discovery, called by AMF for authentication. |
| `udm.yaml` | UDM | `udm.open5gs.org` | Only SBI. Called by AUSF to retrieve auth vectors, by AMF for subscriber data. |
| `udr.yaml` | UDR | `udr.open5gs.org` | SBI + `db_uri: mongodb://db.open5gs.org/open5gs`. Reads/writes subscriber data from MongoDB. |
| `nssf.yaml` | NSSF | `nssf.open5gs.org` | SBI + slice mappings. In basic mode, simple single-slice config. |
| `bsf.yaml` | BSF | `bsf.open5gs.org` | Only SBI. Provides binding support for session continuity. |
| `pcf.yaml` | PCF | `pcf.open5gs.org` | SBI + `db_uri: mongodb://db.open5gs.org/open5gs`. Provides policy rules to SMFs. |

**UDR and PCF need MongoDB** because they store/retrieve subscriber data and policy data. Other NFs are stateless and only need SBI connectivity to NRF.

### 4.2 RAN and UE Configs (UERANSIM)

#### `gnb.yaml` — gNodeB (Base Station)

**Key parameters:**
| Parameter | Value | Purpose |
|-----------|-------|---------|
| `mcc` | 001 | Must match AMF's PLMN |
| `mnc` | 01 | Must match AMF's PLMN |
| `nci` | 0x000000010 | NR Cell Identity |
| `idLength` | 32 | Cell ID bit length |
| `tac` | 1 | Tracking Area Code — must match AMF's TAI |
| `linkIp` | `gnb.ueransim.org` | Address for radio link simulation |
| `ngapIp` | `gnb.ueransim.org` | Address for N2 connection to AMF |
| `gtpIp` | `gnb.ueransim.org` | Address for N3 GTP-U connection to UPF |
| `amfConfigs.address` | `amf.open5gs.org` | Where to find the AMF |
| `slices` | SST:1 | Supported slices |

**What it does:** The gNB connects to AMF via NGAP (N2) for control plane and to UPFs via GTP-U (N3) for user plane. The `tac` must match AMF's tracking area config or the gNB won't be able to register.

#### `ue-iot-01.yaml` through `ue-veh-02.yaml` — UE Configs

Each UE has its own config file. Example structure for `ue-iot-01.yaml`:

**Key parameters:**
| Parameter | Value | Purpose |
|-----------|-------|---------|
| `supi` | imsi-001010000000004 | Subscriber permanent identity (IMSI) |
| `mcc` | 001 | Must match network PLMN |
| `mnc` | 01 | Must match network PLMN |
| `key` | 465B5CE8B199B49FAA5F0A2EE238A6BC | Authentication key K |
| `op` | E8ED289DEBA952E4283B54E88E6183CA | OPC value |
| `opType` | OPC | Indicates this is OPC (not raw OP) |
| `amf` | 8000 | Authentication Management Field |
| `gnbSearchList` | `gnb.ueransim.org` | Where to find the gNB |
| `sessions.type` | IPv4 | PDU session type |
| `sessions.apn` | internet | DNN for the session |
| `sessions.slice.sst` | 1 | Requested slice SST |
| `integrity` | IA1, IA2, IA3: true | Supported integrity algorithms |
| `ciphering` | EA1, EA2, EA3: true | Supported encryption algorithms |

**What it does:** When the UE container starts, UERANSIM reads this config, connects to the gNB, and initiates registration + PDU session establishment using these parameters. The IMSI and keys must match what's provisioned in MongoDB.

**UE Config Files in Basic Mode:**

| File | IMSI | Purpose |
|------|------|---------|
| `ue-iot-01.yaml` | 001010000000004 | IoT sensor 1 |
| `ue-iot-02.yaml` | 001010000000005 | IoT sensor 2 |
| `ue-iot-03.yaml` | 001010000000006 | IoT sensor 3 |
| `ue-veh-01.yaml` | 001010000000007 | Vehicle 1 |
| `ue-veh-02.yaml` | 001010000000008 | Vehicle 2 |
| `ue.yaml` | Default template | Template for generic UE |
| `ue-bulk-01.yaml` | Bulk range | For bulk UE testing |
| `ue-bulk-02.yaml` | Bulk range | For bulk UE testing |

### 4.3 PacketRusher Config (Basic)

Location: `configs/basic/packetrusher/packetrusher.yaml`

**Key parameters:**
| Parameter | Value | Purpose |
|-----------|-------|---------|
| `gnodeb.controlif.ip` | `packetrusher` | N2 interface toward AMF |
| `gnodeb.dataif.ip` | `packetrusher` | N3 interface toward UPF |
| `gnodeb.plmnlist.mcc` | 001 | Must match AMF's PLMN |
| `gnodeb.plmnlist.mnc` | 01 | Must match AMF's PLMN |
| `gnodeb.plmnlist.tac` | 000001 | Tracking Area Code |
| `gnodeb.plmnlist.gnbid` | 000002 | Different from UERANSIM gNB to avoid conflicts |
| `amfif.ip` | `amf.open5gs.org` | AMF address |
| `ue.msin` | 0000000100 | Starting MSIN (IMSI = MCC+MNC+MSIN) |
| `ue.key` | 465B5CE8... | Same auth key as UERANSIM UEs |
| `ue.opc` | E8ED289D... | Same OPC as UERANSIM UEs |
| `ue.amf` | 8000 | Auth Management Field |
| `ue.sst` | 1 | Slice SST |
| `ue.sd` | 000001 | Slice SD |
| `ue.dnn` | internet | DNN |

**What it does:** PacketRusher acts as both gNB and UE simultaneously. It connects to AMF for registration, then establishes real GTP-U tunnels through UPF using the `gtp5g` kernel module. Unlike UERANSIM, PacketRusher can simulate many UEs from a single container.

**PacketRusher's gNB ID (`000002`)** is different from the UERANSIM gNB's ID. This prevents conflicts when both are running simultaneously — the AMF treats them as two separate base stations.

---

## 5. Network Slicing Configs

Location: `configs/network-slicing/`

The network slicing deployment extends the basic config with slice-specific SMFs, UPFs, and UE configs.

### 5.1 Shared Control Plane NFs

The control plane NFs (`nrf.yaml`, `ausf.yaml`, `udm.yaml`, `udr.yaml`, `bsf.yaml`, `pcf.yaml`) are similar to the basic configs. The main difference is in `amf.yaml`:

#### `amf.yaml` — AMF with Multi-Slice Support

The network slicing AMF config differs from basic in that it supports **three S-NSSAIs**:

**Key difference from basic:**
```yaml
amf:
  plmn_support:
    - plmn_id:
        mcc: 001
        mnc: 01
      s_nssai:
        - sst: 1
          sd: 000001    # Slice 1 — IoT
        - sst: 1
          sd: 000002    # Slice 2 — Vehicle
        - sst: 1
          sd: 000003    # Slice 3 — Restricted
```

This tells the AMF that it should accept UEs requesting any of these three slices. When a UE registers with S-NSSAI `SST:1, SD:000001`, the AMF knows this is valid and proceeds to find the correct SMF via NRF.

### 5.2 Per-Slice SMF Configs

Each slice has its own SMF with a unique subnet and S-NSSAI:

#### `smf1.yaml` — SMF for Slice 1 (IoT)

**Key parameters:**
| Parameter | Value | Purpose |
|-----------|-------|---------|
| `sbi.server.address` | `smf1.open5gs.org` | Unique SBI address for this SMF |
| `sbi.client.nrf` | `http://nrf.open5gs.org:80` | NRF for discovery |
| `pfcp.server.address` | `smf1.open5gs.org` | N4 listen address |
| `pfcp.client.upf.address` | `upf1.open5gs.org` | Controls UPF1 only |
| `gtpu.server.address` | `smf1.open5gs.org` | GTP-U tunnel endpoint |
| `session.subnet` | **10.45.0.0/16** | IP pool for Slice 1 UEs |
| `session.gateway` | 10.45.0.1 | Default gateway |
| `dns` | 8.8.8.8, 8.8.4.4 | DNS servers |
| `info.s_nssai.sst` | 1 | Slice SST |
| `info.s_nssai.sd` | **000001** | Slice 1 differentiator |
| `info.s_nssai.dnn` | internet | Data network name |

**What it does:** SMF1 only handles PDU sessions for Slice 1 (SD:000001). When AMF routes a session request for Slice 1, NRF returns SMF1's address. SMF1 allocates an IP from `10.45.0.0/16` and tells UPF1 to create forwarding rules.

#### `smf2.yaml` — SMF for Slice 2 (Vehicle)

| Parameter | Value |
|-----------|-------|
| `sbi.server.address` | `smf2.open5gs.org` |
| `pfcp.client.upf.address` | `upf2.open5gs.org` |
| `session.subnet` | **10.46.0.0/16** |
| `info.s_nssai.sd` | **000002** |
| Everything else | Same structure as SMF1 |

#### `smf3.yaml` — SMF for Slice 3 (Restricted)

| Parameter | Value |
|-----------|-------|
| `sbi.server.address` | `smf3.open5gs.org` |
| `pfcp.client.upf.address` | `upf3.open5gs.org` |
| `session.subnet` | **10.47.0.0/16** |
| `info.s_nssai.sd` | **000003** |
| Everything else | Same structure as SMF1 |

**Critical point:** Each SMF must have a **unique subnet** and a **unique S-NSSAI SD value**. The NRF uses the S-NSSAI to route session requests to the correct SMF.

### 5.3 Per-Slice UPF Configs

#### `upf1.yaml` — UPF for Slice 1 (IoT)

**Key parameters:**
| Parameter | Value | Purpose |
|-----------|-------|---------|
| `pfcp.server.address` | `upf1.open5gs.org` | Listens for PFCP from SMF1 |
| `gtpu.server.address` | `upf1.open5gs.org` | Receives GTP-U from gNB |
| `session.subnet` | **10.45.0.0/16** | Must match SMF1's subnet |
| `session.gateway` | 10.45.0.1 | Gateway for the subnet |

#### `upf2.yaml` — UPF for Slice 2 (Vehicle)

| Parameter | Value |
|-----------|-------|
| `pfcp.server.address` | `upf2.open5gs.org` |
| `gtpu.server.address` | `upf2.open5gs.org` |
| `session.subnet` | **10.46.0.0/16** |
| `session.gateway` | 10.46.0.1 |

#### `upf3.yaml` — UPF for Slice 3 (Restricted)

| Parameter | Value |
|-----------|-------|
| `pfcp.server.address` | `upf3.open5gs.org` |
| `gtpu.server.address` | `upf3.open5gs.org` |
| `session.subnet` | **10.47.0.0/16** |
| `session.gateway` | 10.47.0.1 |

**Note:** UPF3's config itself allows internet access (NAT is enabled). The internet blocking is done at the **Docker container level** using iptables rules applied by the Docker Compose file, not in the UPF config. This is an important design detail — the UPF config is identical to UPF1/UPF2, but the container has additional firewall rules.

### 5.4 NSSF — Slice Selection Rules

#### `nssf.yaml` — Network Slice Selection Function

The NSSF config is one of the most important for network slicing. It defines the rules for mapping S-NSSAI values to specific network resources.

**Key configuration sections:**

**Supported S-NSSAIs:**
```yaml
s_nssai:
  - sst: 1
    sd: 000001
  - sst: 1
    sd: 000002
  - sst: 1
    sd: 000003
```

This tells NSSF that these three slices are available in the network. When AMF queries NSSF with a UE's requested S-NSSAI, NSSF checks if it's in this list. If yes, NSSF returns it as part of the Allowed NSSAI.

**NSI (Network Slice Instance) mappings:** The NSSF config maps each S-NSSAI to the corresponding NRF that manages that slice's resources. In our setup with a single NRF, all slices point to the same NRF, which then returns the correct SMF based on the S-NSSAI in the NRF's service registration.

**Why NSSF matters:** Without NSSF, the AMF wouldn't know which slices are valid. NSSF acts as the policy engine for slice access — it could reject a UE's requested slice if the UE isn't authorized (though in our setup all UEs get their requested slices).

### 5.5 gNodeB Config

#### `gnb.yaml` — gNodeB with Multi-Slice Support

**Key difference from basic:**
```yaml
slices:
  - sst: 1
    sd: 000001
  - sst: 1
    sd: 000002
  - sst: 1
    sd: 000003
```

The gNB must be configured with all three slices so it can handle UEs requesting any of them. The gNB doesn't make slice routing decisions itself — it passes the UE's S-NSSAI to the AMF, which handles the selection.

All other parameters (MCC, MNC, TAC, linkIp, ngapIp, gtpIp, amfConfigs) remain the same as the basic gNB config.

### 5.6 UE Configs (Per-Slice)

Each UE is configured with a specific slice:

#### `ue1.yaml` — UE1 (IoT, Slice 1)

**Key parameters:**
| Parameter | Value | Purpose |
|-----------|-------|---------|
| `supi` | **imsi-001010000000004** | UE1's unique IMSI |
| `key` | 465B5CE8B199B49FAA5F0A2EE238A6BC | Auth key (must match MongoDB) |
| `op` | E8ED289DEBA952E4283B54E88E6183CA | OPC value (must match MongoDB) |
| `opType` | OPC | Using OPC (not raw OP) |
| `amf` | 8000 | Auth Management Field |
| `gnbSearchList` | `gnb.ueransim.org` | Where to find the gNB |
| `sessions.apn` | internet | DNN |
| `sessions.slice.sst` | 1 | **Requested SST** |
| `sessions.slice.sd` | **000001** | **Requested SD → routes to SMF1/UPF1** |
| `configured-nssai` | SST:1, SD:000001 | Slices this UE is allowed to use |
| `default-nssai` | SST:1, SD:000001 | Default slice if none specified |

**What happens:** When UE1 starts, it sends a Registration Request with Requested NSSAI containing `SST:1, SD:000001`. The AMF verifies this against NSSF, then when UE1 requests a PDU session, AMF queries NRF for a SMF serving `SD:000001` → gets SMF1 → SMF1 assigns IP from `10.45.0.0/16`.

**`configured-nssai` vs `default-nssai`:** The `configured-nssai` is the list of slices the UE is allowed to use (set by the operator). The `default-nssai` is which slice the UE requests by default if no specific slice is requested. In our setup, each UE only has one slice in both lists.

#### `ue2.yaml` — UE2 (Vehicle, Slice 2)

| Parameter | Value |
|-----------|-------|
| `supi` | **imsi-001010000000002** |
| `sessions.slice.sd` | **000002** |
| `configured-nssai` | SST:1, SD:000002 |
| `default-nssai` | SST:1, SD:000002 |
| Everything else | Same structure as UE1 |

**Result:** UE2 gets routed to SMF2/UPF2, receives IP from `10.46.0.0/16`.

#### `ue3.yaml` — UE3 (Restricted, Slice 3)

| Parameter | Value |
|-----------|-------|
| `supi` | **imsi-001010000000001** |
| `sessions.slice.sd` | **000003** |
| `configured-nssai` | SST:1, SD:000003 |
| `default-nssai` | SST:1, SD:000003 |
| Everything else | Same structure as UE1 |

**Result:** UE3 gets routed to SMF3/UPF3, receives IP from `10.47.0.0/16`. Internet is blocked at UPF3 container level.

### 5.7 PacketRusher Config (Slicing)

Location: `configs/network-slicing/packetrusher.yaml`

Same structure as the basic PacketRusher config, but configured for the slicing AMF:

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `gnodeb.controlif.ip` | `packetrusher` | N2 interface |
| `gnodeb.dataif.ip` | `packetrusher` | N3 interface |
| `gnodeb.plmnlist.gnbid` | 000002 | Different from UERANSIM gNB |
| `gnodeb.slicesupport.sst` | 1 | Slice support |
| `gnodeb.slicesupport.sd` | 000001 | Uses Slice 1 |
| `amfif.ip` | `amf.open5gs.org` | Points to slicing AMF |
| `ue.msin` | 0000000100 | Starting IMSI suffix |
| `ue.sst` | 1 | Slice 1 (IoT) |
| `ue.sd` | 000001 | SD for Slice 1 |
| `ue.dnn` | internet | DNN |

PacketRusher UEs register on Slice 1 and get IPs from `10.45.0.0/16`. Up to 50 simultaneous UEs can be created for load testing.

### 5.8 mongo-init.js — Auto-Provisioning Script

Location: `configs/network-slicing/mongo-init.js`

This is a JavaScript file executed by `mongosh` (MongoDB Shell) during `docker compose up`. It runs inside the `db-init` service container and registers all subscribers in the Open5GS MongoDB database.

**What it provisions:**

**3 UERANSIM Subscribers:**
| IMSI | Slice (SST/SD) | Key | OPC |
|------|----------------|-----|-----|
| 001010000000004 | 1/000001 | 465B5CE8... | E8ED289D... |
| 001010000000002 | 1/000002 | 465B5CE8... | E8ED289D... |
| 001010000000001 | 1/000003 | 465B5CE8... | E8ED289D... |

**18 PacketRusher Subscribers:**
| IMSI Range | Slice (SST/SD) | Key | OPC |
|------------|----------------|-----|-----|
| 001010000000100 – 001010000000117 | 1/000001 | 465B5CE8... | E8ED289D... |

**How it works:**

1. The `db-init` container starts after MongoDB is ready
2. It waits for MongoDB to accept connections (up to 30 attempts, 2 seconds apart)
3. It runs `mongosh` with `mongo-init.js` against the `open5gs` database
4. For each subscriber, it calls `db.subscribers.updateOne()` with `upsert: true`
5. The subscriber document includes:
   - IMSI (unique identifier)
   - Authentication data (K, OPC, AMF)
   - Default APN configuration (DNN, session type)
   - Allowed S-NSSAI with QoS parameters (5QI, ARP)
   - AMBR (Aggregate Maximum Bit Rate) — uplink and downlink limits
6. After provisioning, the container exits (it's a one-time job)

**Why `upsert: true`?** This makes the script idempotent:
- First run: subscribers don't exist → INSERT new documents
- Subsequent runs: subscribers already exist → UPDATE existing documents
- This means `docker compose down && docker compose up` won't fail because of duplicate subscribers

**Subscriber document structure (simplified):**
```javascript
db.subscribers.updateOne(
  { imsi: "001010000000004" },     // Find by IMSI
  { $set: {
      imsi: "001010000000004",
      security: {
        k: "465B5CE8B199B49FAA5F0A2EE238A6BC",
        opc: "E8ED289DEBA952E4283B54E88E6183CA",
        amf: "8000"
      },
      slice: [{
        sst: 1, sd: "000001",
        default_indicator: true,
        session: [{
          name: "internet",
          type: 3,                 // IPv4
          qos: { index: 9, arp: { priority_level: 8 } },
          ambr: { uplink: { value: 1, unit: 3 },      // 1 Gbps
                  downlink: { value: 1, unit: 3 } }    // 1 Gbps
        }]
      }]
    }
  },
  { upsert: true }
);
```

---

## 6. Key Differences: Basic vs Slicing

| Aspect | Basic Config | Network Slicing Config |
|--------|-------------|----------------------|
| **AMF s_nssai** | Single: `SST:1` | Three: `SST:1/SD:000001`, `000002`, `000003` |
| **SMF** | One `smf.yaml` (subnet: 10.45.0.0/16) | Three: `smf1.yaml`, `smf2.yaml`, `smf3.yaml` with different subnets |
| **UPF** | One `upf.yaml` | Three: `upf1.yaml`, `upf2.yaml`, `upf3.yaml` |
| **gNB slices** | Single: `SST:1` | Three: `SST:1/SD:000001/000002/000003` |
| **UE configs** | 5 UEs: `ue-iot-01` through `ue-veh-02` | 3 UEs: `ue1`, `ue2`, `ue3` with per-slice SD |
| **UE slice SD** | Not specified (uses default) | Each UE specifies unique SD |
| **NSSF** | Minimal config | Full slice mapping rules |
| **DB provisioning** | Manual or via provision script | Automatic via `mongo-init.js` + `db-init` service |
| **UPF3 internet** | N/A | Blocked by iptables at container level |

**The fundamental change:** In basic mode, all traffic goes through one SMF/UPF. In slicing mode, the S-NSSAI SD value in the UE config determines which SMF/UPF handles that UE's traffic. This is what creates the slice isolation — different UEs get different data paths based on their configured slice.

---

## 7. MQTT Broker Config

Location: `compose-files/apps/mqtt/config/mosquitto.conf`

This file configures the Eclipse Mosquitto MQTT broker used by all IoT and vehicle simulators.

```
listener 1883
allow_anonymous true
```

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `listener` | 1883 | Listens on port 1883 (standard MQTT port) on all interfaces |
| `allow_anonymous` | true | No username/password required for MQTT connections |

**Why anonymous access?** In this simulation environment, the 5G network itself provides the security layer. The MQTT broker runs on the internal Docker network (`open5gs`) and is only reachable by services on that network — either through the 5G UPF (for UE traffic) or directly on the Docker bridge (for the Edge server, Node-RED, and the framework). In a production environment, MQTT authentication and TLS would be required.

---

## 8. Environment File

Location: `build-files/open5gs.env`

This file defines version numbers and host-specific configuration used by all Docker Compose files via variable substitution.

**Key variables:**

| Variable | Example Value | Used By |
|----------|---------------|---------|
| `OPEN5GS_VERSION` | `2.7.2` | All Open5GS container image tags (amf, smf, upf, etc.) |
| `UERANSIM_VERSION` | `3.2.6` | All UERANSIM container image tags (gnb, ue) |
| `MONGODB_VERSION` | `6.0` | MongoDB container image tag |
| `HOST_IP_ADDRESS` | `192.168.x.x` | WebUI MongoDB connection string |

Docker Compose substitutes these variables using `${VARIABLE_NAME}` syntax in the compose files. For example:

```yaml
image: "fgftk/amf-open5gs:${OPEN5GS_VERSION}"
# becomes: fgftk/amf-open5gs:2.7.2
```

**How to use:** Pass the env file when running Docker Compose:

```bash
docker compose -f docker-compose.yaml --env-file ../../build-files/open5gs.env up -d
```

This keeps version numbers in a single place — updating `OPEN5GS_VERSION` in the env file upgrades all Open5GS containers at once.

---

## 9. Config File Locations Summary

### Basic Deployment

| File | Path | Mounted Into |
|------|------|-------------|
| nrf.yaml | `configs/basic/ueransim/nrf.yaml` | nrf container |
| amf.yaml | `configs/basic/ueransim/amf.yaml` | amf container |
| smf.yaml | `configs/basic/ueransim/smf.yaml` | smf container |
| upf.yaml | `configs/basic/ueransim/upf.yaml` | upf container |
| ausf.yaml | `configs/basic/ueransim/ausf.yaml` | ausf container |
| udm.yaml | `configs/basic/ueransim/udm.yaml` | udm container |
| udr.yaml | `configs/basic/ueransim/udr.yaml` | udr container |
| nssf.yaml | `configs/basic/ueransim/nssf.yaml` | nssf container |
| bsf.yaml | `configs/basic/ueransim/bsf.yaml` | bsf container |
| pcf.yaml | `configs/basic/ueransim/pcf.yaml` | pcf container |
| gnb.yaml | `configs/basic/ueransim/gnb.yaml` | gnb container |
| ue-iot-01.yaml | `configs/basic/ueransim/ue-iot-01.yaml` | ue-iot-01 container |
| ue-iot-02.yaml | `configs/basic/ueransim/ue-iot-02.yaml` | ue-iot-02 container |
| ue-iot-03.yaml | `configs/basic/ueransim/ue-iot-03.yaml` | ue-iot-03 container |
| ue-veh-01.yaml | `configs/basic/ueransim/ue-veh-01.yaml` | ue-veh-01 container |
| ue-veh-02.yaml | `configs/basic/ueransim/ue-veh-02.yaml` | ue-veh-02 container |
| packetrusher.yaml | `configs/basic/packetrusher/packetrusher.yaml` | packetrusher container |

### Network Slicing Deployment

| File | Path | Mounted Into |
|------|------|-------------|
| nrf.yaml | `configs/network-slicing/nrf.yaml` | nrf container |
| amf.yaml | `configs/network-slicing/amf.yaml` | amf container |
| smf1.yaml | `configs/network-slicing/smf1.yaml` | smf1 container |
| smf2.yaml | `configs/network-slicing/smf2.yaml` | smf2 container |
| smf3.yaml | `configs/network-slicing/smf3.yaml` | smf3 container |
| upf1.yaml | `configs/network-slicing/upf1.yaml` | upf1 container |
| upf2.yaml | `configs/network-slicing/upf2.yaml` | upf2 container |
| upf3.yaml | `configs/network-slicing/upf3.yaml` | upf3 container |
| ausf.yaml | `configs/network-slicing/ausf.yaml` | ausf container |
| udm.yaml | `configs/network-slicing/udm.yaml` | udm container |
| udr.yaml | `configs/network-slicing/udr.yaml` | udr container |
| nssf.yaml | `configs/network-slicing/nssf.yaml` | nssf container |
| bsf.yaml | `configs/network-slicing/bsf.yaml` | bsf container |
| pcf.yaml | `configs/network-slicing/pcf.yaml` | pcf container |
| gnb.yaml | `configs/network-slicing/gnb.yaml` | gnb container |
| ue1.yaml | `configs/network-slicing/ue1.yaml` | ue1 container |
| ue2.yaml | `configs/network-slicing/ue2.yaml` | ue2 container |
| ue3.yaml | `configs/network-slicing/ue3.yaml` | ue3 container |
| packetrusher.yaml | `configs/network-slicing/packetrusher.yaml` | packetrusher container |
| mongo-init.js | `configs/network-slicing/mongo-init.js` | db-init container |

---

[← Back to Main README](../README.md) | [Previous: Architecture & Design](architecture-design.md) | [Next: Docker Compose Files →](compose-files.md)