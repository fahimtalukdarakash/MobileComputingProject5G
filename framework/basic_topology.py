# framework/basic_topology.py
"""
Basic 5G Network Topology (No Slicing)
=======================================
Single-slice Open5GS + UERANSIM architecture with 5 UEs and application layer.
"""

import json
import subprocess
from typing import Dict, Any, List


# =============================================================================
# Node definitions — Basic Setup (single slice, no SMF1/2/3 split)
# =============================================================================

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

    # 5G Core User Plane (single)
    "smf": {"category": "core_up", "label": "SMF", "fullname": "Session Mgmt Function",  "role": "PDU session management"},
    "upf": {"category": "core_up", "label": "UPF", "fullname": "User Plane Function",    "role": "Data forwarding, NAT"},

    # RAN
    "gnb": {"category": "ran", "label": "gNB", "fullname": "gNodeB (Base Station)", "role": "5G NR radio access"},

    # IoT UEs
    "ue-iot-01": {"category": "iot", "label": "UE-IoT-01", "fullname": "IoT UE 1 (Temp/Humidity)",      "role": "Temperature & Humidity sensor"},
    "ue-iot-02": {"category": "iot", "label": "UE-IoT-02", "fullname": "IoT UE 2 (Air Quality)",        "role": "CO₂ & PM2.5 sensor"},
    "ue-iot-03": {"category": "iot", "label": "UE-IoT-03", "fullname": "IoT UE 3 (Temp/Pressure/Batt)", "role": "Temperature, Pressure & Battery"},

    # Vehicle UEs
    "ue-veh-01": {"category": "vehicle", "label": "UE-Veh-01", "fullname": "Vehicle UE 1", "role": "GPS, Speed, Alerts → Edge"},
    "ue-veh-02": {"category": "vehicle", "label": "UE-Veh-02", "fullname": "Vehicle UE 2", "role": "GPS, Speed, Alerts → Edge"},

    # Simulators
    "sim-iot-01": {"category": "simulator", "label": "sim-iot-01", "fullname": "IoT Simulator 1", "role": "Publishes to MQTT iot/ue-iot-01"},
    "sim-iot-02": {"category": "simulator", "label": "sim-iot-02", "fullname": "IoT Simulator 2", "role": "Publishes to MQTT iot/ue-iot-02"},
    "sim-iot-03": {"category": "simulator", "label": "sim-iot-03", "fullname": "IoT Simulator 3", "role": "Publishes to MQTT iot/ue-iot-03"},
    "sim-veh-01": {"category": "simulator", "label": "sim-veh-01", "fullname": "Vehicle Simulator 1", "role": "HTTP POST → Edge server"},
    "sim-veh-02": {"category": "simulator", "label": "sim-veh-02", "fullname": "Vehicle Simulator 2", "role": "HTTP POST → Edge server"},

    # Application Layer
    "mqtt":    {"category": "apps", "label": "MQTT",    "fullname": "Mosquitto Broker",       "role": "IoT message broker (port 1883)"},
    "nodered": {"category": "apps", "label": "Node-RED", "fullname": "Node-RED Dashboard",     "role": "Visualization dashboard (port 1880)"},
    "edge":    {"category": "apps", "label": "Edge",    "fullname": "Edge Computing Server",  "role": "Vehicle telemetry aggregator (port 5000)"},

    # Infrastructure
    "db":    {"category": "infra", "label": "MongoDB", "fullname": "MongoDB Database",    "role": "Subscriber database (port 27017)"},
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
    ("smf",  "nrf",  "SBI",  "NF Registration"),

    # Database connections
    ("udr",   "db", "MongoDB", "Subscriber Data"),
    ("pcf",   "db", "MongoDB", "Policy Data"),
    ("webui", "db", "MongoDB", "Subscriber Mgmt"),

    # N2: AMF ↔ gNB
    ("amf", "gnb", "NGAP (N2)", "Control Plane"),

    # N4: SMF ↔ UPF
    ("smf", "upf", "PFCP (N4)", "Session Mgmt"),

    # N3: gNB ↔ UPF (GTP-U user plane tunnel)
    ("gnb", "upf", "GTP-U (N3)", "User Plane Tunnel"),

    # N11: AMF → SMF
    ("amf", "smf", "SBI", "Session Create"),

    # Authentication path
    ("amf",  "ausf", "SBI", "Authentication"),
    ("ausf", "udm",  "SBI", "Auth Vectors"),
    ("udm",  "udr",  "SBI", "Subscriber Lookup"),

    # Slice selection
    ("amf", "nssf", "SBI", "Slice Selection"),

    # Policy
    ("smf", "pcf", "SBI", "Policy Fetch"),

    # NR-Uu: gNB ↔ UEs (radio interface)
    ("gnb", "ue-iot-01", "NR-Uu", "Radio"),
    ("gnb", "ue-iot-02", "NR-Uu", "Radio"),
    ("gnb", "ue-iot-03", "NR-Uu", "Radio"),
    ("gnb", "ue-veh-01", "NR-Uu", "Radio"),
    ("gnb", "ue-veh-02", "NR-Uu", "Radio"),

    # Simulators → UEs (network_mode: container)
    ("sim-iot-01", "ue-iot-01", "container", "net:container"),
    ("sim-iot-02", "ue-iot-02", "container", "net:container"),
    ("sim-iot-03", "ue-iot-03", "container", "net:container"),
    ("sim-veh-01", "ue-veh-01", "container", "net:container"),
    ("sim-veh-02", "ue-veh-02", "container", "net:container"),

    # App data flows
    ("upf", "mqtt", "IP", "IoT Data (MQTT)"),
    ("upf", "edge", "IP", "Vehicle Telemetry (HTTP)"),
    ("edge", "mqtt", "MQTT", "Telemetry Relay"),
    ("mqtt", "nodered", "MQTT", "Dashboard Subscribe"),
]

CATEGORY_STYLES = {
    "core_cp":   {"color": "#2563EB", "name": "5G Core (Control Plane)", "shape": "box"},
    "core_up":   {"color": "#7C3AED", "name": "5G Core (User Plane)",    "shape": "box"},
    "ran":       {"color": "#16A34A", "name": "RAN (Radio Access)",       "shape": "diamond"},
    "iot":       {"color": "#0891B2", "name": "IoT UEs",                  "shape": "box"},
    "vehicle":   {"color": "#EA580C", "name": "Vehicle UEs",              "shape": "box"},
    "simulator": {"color": "#6B7280", "name": "Simulators",               "shape": "box"},
    "apps":      {"color": "#DB2777", "name": "Applications",             "shape": "box"},
    "infra":     {"color": "#92400E", "name": "Infrastructure",           "shape": "database"},
}


# =============================================================================
# Docker State
# =============================================================================

def _run(cmd: List[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{p.stderr.strip()}")
    return p.stdout


def _get_docker_state() -> Dict[str, Dict[str, Any]]:
    """Get live container status, IPs, images from Docker."""
    try:
        names_raw = _run(["docker", "ps", "-a", "--format", "{{.Names}}"]).strip()
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
            raw = _run(["docker", "inspect", name])
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

def get_basic_topology() -> Dict[str, Any]:
    """Returns the complete basic 5G topology with live Docker state."""
    docker_state = _get_docker_state()

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
        "categories": CATEGORY_STYLES,
        "docker_network": {"name": "open5gs", "subnet": "10.33.33.0/24", "bridge": "br-ogs"},
    }