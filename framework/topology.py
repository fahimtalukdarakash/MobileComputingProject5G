# framework/topology.py
"""
5G Network Topology Module
===========================
Provides both live Docker container state AND logical 5G architecture
(NF relationships, slice mappings, IP subnets, interfaces).
"""

import json
import subprocess
from typing import Dict, Any, List

# =============================================================================
# 5G Architecture Definition
# =============================================================================

SLICE_DEFINITIONS = {
    "slice1": {
        "name": "Slice 1 – IoT",
        "sst": 1, "sd": "000001",
        "subnet": "10.45.0.0/16",
        "dnn": "internet",
        "description": "IoT devices (sensors, MQTT telemetry)",
        "internet_access": True,
    },
    "slice2": {
        "name": "Slice 2 – Vehicle",
        "sst": 1, "sd": "000002",
        "subnet": "10.46.0.0/16",
        "dnn": "internet",
        "description": "Connected cars (GPS, alerts, edge computing)",
        "internet_access": True,
    },
    "slice3": {
        "name": "Slice 3 – Restricted",
        "sst": 1, "sd": "000003",
        "subnet": "10.47.0.0/16",
        "dnn": "internet",
        "description": "Internal-only access (no internet, local services only)",
        "internet_access": False,
    },
}

NODE_DEFINITIONS = {
    # 5G Core Control Plane
    "nrf":  {"category": "core_cp", "label": "NRF",  "fullname": "Network Repository Function",     "role": "NF discovery & registration"},
    "ausf": {"category": "core_cp", "label": "AUSF", "fullname": "Authentication Server Function",   "role": "UE authentication"},
    "udm":  {"category": "core_cp", "label": "UDM",  "fullname": "Unified Data Management",          "role": "Subscriber data management"},
    "udr":  {"category": "core_cp", "label": "UDR",  "fullname": "Unified Data Repository",          "role": "Subscriber data storage"},
    "nssf": {"category": "core_cp", "label": "NSSF", "fullname": "Network Slice Selection Function",  "role": "Slice selection"},
    "bsf":  {"category": "core_cp", "label": "BSF",  "fullname": "Binding Support Function",          "role": "Session binding"},
    "pcf":  {"category": "core_cp", "label": "PCF",  "fullname": "Policy Control Function",           "role": "Policy decisions (QoS, charging)"},
    "amf":  {"category": "core_cp", "label": "AMF",  "fullname": "Access & Mobility Mgmt Function",   "role": "Registration, connection, mobility"},

    # 5G Core User Plane (per-slice)
    "smf1": {"category": "slice1", "label": "SMF1", "fullname": "Session Mgmt Function (Slice 1)", "role": "PDU session management"},
    "smf2": {"category": "slice2", "label": "SMF2", "fullname": "Session Mgmt Function (Slice 2)", "role": "PDU session management"},
    "smf3": {"category": "slice3", "label": "SMF3", "fullname": "Session Mgmt Function (Slice 3)", "role": "PDU session management"},
    "upf1": {"category": "slice1", "label": "UPF1", "fullname": "User Plane Function (Slice 1)",   "role": "Data forwarding, NAT (10.45.0.0/16)"},
    "upf2": {"category": "slice2", "label": "UPF2", "fullname": "User Plane Function (Slice 2)",   "role": "Data forwarding, NAT (10.46.0.0/16)"},
    "upf3": {"category": "slice3", "label": "UPF3", "fullname": "User Plane Function (Slice 3)",   "role": "Data forwarding, blackhole (10.47.0.0/16)"},

    # RAN
    "gnb":  {"category": "ran", "label": "gNB", "fullname": "gNodeB (Base Station)", "role": "5G NR radio access"},

    # UEs
    "ue1":  {"category": "slice1", "label": "UE1", "fullname": "UE 1 (IoT)",        "role": "IMSI: 001010000000004, Slice 1"},
    "ue2":  {"category": "slice2", "label": "UE2", "fullname": "UE 2 (Vehicle)",     "role": "IMSI: 001010000000002, Slice 2"},
    "ue3":  {"category": "slice3", "label": "UE3", "fullname": "UE 3 (Restricted)",  "role": "IMSI: 001010000000001, Slice 3"},

    # Applications
    "mqtt":    {"category": "apps", "label": "MQTT",    "fullname": "Mosquitto Broker",       "role": "IoT message broker (port 1883)"},
    "nodered": {"category": "apps", "label": "NodeRED", "fullname": "Node-RED Dashboard",     "role": "IoT/Vehicle dashboard (port 1880)"},
    "edge":    {"category": "apps", "label": "Edge",    "fullname": "Edge Computing Server",  "role": "Vehicle telemetry processor (port 5000)"},

    # Infrastructure
    "db":    {"category": "infra", "label": "MongoDB", "fullname": "MongoDB Database",    "role": "Subscriber database"},
    "webui": {"category": "infra", "label": "WebUI",   "fullname": "Open5GS Web Console", "role": "Subscriber management (port 9999)"},
}

EDGE_DEFINITIONS = [
    # Core NFs → NRF (SBI registration)
    ("ausf", "nrf",  "SBI",  "NF Registration"),
    ("udm",  "nrf",  "SBI",  "NF Registration"),
    ("udr",  "nrf",  "SBI",  "NF Registration"),
    ("nssf", "nrf",  "SBI",  "NF Registration"),
    ("bsf",  "nrf",  "SBI",  "NF Registration"),
    ("pcf",  "nrf",  "SBI",  "NF Registration"),
    ("amf",  "nrf",  "SBI",  "NF Registration"),
    ("smf1", "nrf",  "SBI",  "NF Registration"),
    ("smf2", "nrf",  "SBI",  "NF Registration"),
    ("smf3", "nrf",  "SBI",  "NF Registration"),

    # Database connections
    ("udr", "db", "MongoDB", "Subscriber Data"),
    ("pcf", "db", "MongoDB", "Policy Data"),
    ("webui", "db", "MongoDB", "Subscriber Management"),

    # N2: AMF ↔ gNB
    ("amf", "gnb", "NGAP (N2)", "Control Plane"),

    # NR-Uu: gNB ↔ UEs
    ("gnb", "ue1", "NR-Uu", "Radio (Slice 1)"),
    ("gnb", "ue2", "NR-Uu", "Radio (Slice 2)"),
    ("gnb", "ue3", "NR-Uu", "Radio (Slice 3)"),

    # N4: SMF ↔ UPF (PFCP)
    ("smf1", "upf1", "PFCP (N4)", "Session Mgmt"),
    ("smf2", "upf2", "PFCP (N4)", "Session Mgmt"),
    ("smf3", "upf3", "PFCP (N4)", "Session Mgmt"),

    # N3: gNB ↔ UPF (GTP-U user plane tunnel)
    ("gnb", "upf1", "GTP-U (N3)", "User Plane Tunnel"),
    ("gnb", "upf2", "GTP-U (N3)", "User Plane Tunnel"),
    ("gnb", "upf3", "GTP-U (N3)", "User Plane Tunnel"),

    # Authentication path
    ("amf", "ausf", "SBI", "Authentication"),
    ("ausf", "udm", "SBI", "Auth Vectors"),
    ("udm", "udr", "SBI", "Subscriber Lookup"),

    # Slice selection
    ("amf", "nssf", "SBI", "Slice Selection"),

    # Session creation AMF → SMFs
    ("amf", "smf1", "SBI", "Session Create (Slice 1)"),
    ("amf", "smf2", "SBI", "Session Create (Slice 2)"),
    ("amf", "smf3", "SBI", "Session Create (Slice 3)"),

    # Policy
    ("smf1", "pcf", "SBI", "Policy Fetch"),
    ("smf2", "pcf", "SBI", "Policy Fetch"),
    ("smf3", "pcf", "SBI", "Policy Fetch"),

    # App data flows
    ("upf1", "mqtt",    "IP", "IoT Data (MQTT)"),
    ("upf2", "edge",    "IP", "Vehicle Telemetry (HTTP)"),
    ("upf3", "mqtt",    "IP", "Restricted Data (MQTT)"),
    ("upf3", "nodered", "IP", "Restricted Data (Dashboard)"),
    ("edge", "mqtt",    "MQTT", "Telemetry Relay"),
]

CATEGORY_STYLES = {
    "core_cp": {"color": "#2563EB", "name": "5G Core (Control Plane)", "shape": "box"},
    "ran":     {"color": "#16A34A", "name": "RAN (Radio Access)",       "shape": "diamond"},
    "slice1":  {"color": "#EA580C", "name": "Slice 1 – IoT",           "shape": "box"},
    "slice2":  {"color": "#9333EA", "name": "Slice 2 – Vehicle",       "shape": "box"},
    "slice3":  {"color": "#DC2626", "name": "Slice 3 – Restricted",    "shape": "box"},
    "apps":    {"color": "#0891B2", "name": "Applications",             "shape": "box"},
    "infra":   {"color": "#6B7280", "name": "Infrastructure",           "shape": "database"},
}


# =============================================================================
# Docker State
# =============================================================================

def run(cmd: List[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{p.stderr.strip()}")
    return p.stdout


def get_docker_state() -> Dict[str, Dict[str, Any]]:
    """Get live container status, IPs, images from Docker."""
    try:
        names_raw = run(["docker", "ps", "-a", "--format", "{{.Names}}"]).strip()
    except RuntimeError:
        return {}

    if not names_raw:
        return {}

    state = {}
    for name in names_raw.splitlines():
        name = name.strip()
        if not name:
            continue
        try:
            raw = run(["docker", "inspect", name])
            info = json.loads(raw)[0]

            nets = info.get("NetworkSettings", {}).get("Networks", {}) or {}
            net_info = []
            for net_name, net_obj in nets.items():
                net_info.append({
                    "network": net_name,
                    "ip": net_obj.get("IPAddress", ""),
                    "gateway": net_obj.get("Gateway", ""),
                    "mac": net_obj.get("MacAddress", ""),
                })

            state[name] = {
                "status": info.get("State", {}).get("Status", "unknown"),
                "running": info.get("State", {}).get("Running", False),
                "image": info.get("Config", {}).get("Image", ""),
                "networks": net_info,
            }
        except (RuntimeError, json.JSONDecodeError, IndexError):
            state[name] = {"status": "error", "running": False, "image": "", "networks": []}

    return state


# =============================================================================
# Public API
# =============================================================================

def get_full_topology() -> Dict[str, Any]:
    """
    Returns the complete 5G topology:
      - nodes: all NFs/UEs/apps with category, IPs, status
      - edges: logical connections with protocols
      - slices: slice definitions
      - categories: styling info
    """
    docker_state = get_docker_state()

    nodes = []
    for container_name, definition in NODE_DEFINITIONS.items():
        docker_info = docker_state.get(container_name, {})
        nodes.append({
            "id": container_name,
            "label": definition["label"],
            "fullname": definition["fullname"],
            "role": definition["role"],
            "category": definition["category"],
            "status": docker_info.get("status", "not found"),
            "running": docker_info.get("running", False),
            "image": docker_info.get("image", ""),
            "networks": docker_info.get("networks", []),
        })

    edges = []
    for src, dst, protocol, desc in EDGE_DEFINITIONS:
        edges.append({"from": src, "to": dst, "protocol": protocol, "description": desc})

    return {
        "nodes": nodes,
        "edges": edges,
        "slices": SLICE_DEFINITIONS,
        "categories": CATEGORY_STYLES,
        "docker_network": {"name": "open5gs", "subnet": "10.33.33.0/24", "bridge": "br-ogs"},
    }