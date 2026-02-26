# framework/usecases.py
"""
5G Use Case Management
=======================
Defines, starts, stops, and monitors use-case simulators.
"""

import subprocess
import json
import time
from typing import Dict, Any, List
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
USECASES_COMPOSE = str(PROJECT_ROOT / "compose-files/network-slicing/docker-compose.usecases.yaml")

# Late import to avoid circular dependency
def _auto_configure_qos(uc_ids):
    from framework.transport import auto_configure_qos
    return auto_configure_qos(uc_ids)

# =============================================================================
# Use Case Definitions
# =============================================================================

USE_CASES = {
    "iot-environment": {
        "name": "IoT Environmental Monitoring",
        "description": "Temperature & humidity sensors publishing to MQTT broker via Slice 1.",
        "slice": "Slice 1 – IoT",
        "slice_id": "slice1",
        "ue": "ue1",
        "services": ["sim-iot-01"],
        "protocol": "MQTT",
        "data_topic": "iot/ue-iot-01",
        "data_fields": ["temperature_c", "humidity_percent"],
        "icon": "🌡",
        "dashboard_url": "/nodered-dashboard",
    },
    "smart-city": {
        "name": "Smart City Air Quality",
        "description": "CO₂ and PM2.5 air quality sensors publishing to MQTT via Slice 1.",
        "slice": "Slice 1 – IoT",
        "slice_id": "slice1",
        "ue": "ue1",
        "services": ["sim-iot-02"],
        "protocol": "MQTT",
        "data_topic": "iot/ue-iot-02",
        "data_fields": ["co2_ppm", "pm2_5_ugm3"],
        "icon": "🏙",
        "dashboard_url": "/nodered-dashboard",
    },
    "ehealth": {
        "name": "eHealth Sensor Station",
        "description": "Environmental health monitoring: temperature, pressure, battery via Slice 1.",
        "slice": "Slice 1 – IoT",
        "slice_id": "slice1",
        "ue": "ue1",
        "services": ["sim-iot-03"],
        "protocol": "MQTT",
        "data_topic": "iot/ue-iot-03",
        "data_fields": ["temperature_c", "pressure_hpa", "battery_percent"],
        "icon": "🏥",
        "dashboard_url": "/nodered-dashboard",
    },
    "vehicle-gps": {
        "name": "Vehicle GPS Tracking",
        "description": "Live GPS coordinates and speed sent to Edge server via Slice 2.",
        "slice": "Slice 2 – Vehicle",
        "slice_id": "slice2",
        "ue": "ue2",
        "services": ["sim-veh-01"],
        "protocol": "HTTP → Edge",
        "data_topic": "veh/telemetry",
        "data_fields": ["speed_kmh", "lat", "lon"],
        "icon": "🚗",
        "dashboard_url": "http://localhost:5000",
    },
    "vehicle-alerts": {
        "name": "Vehicle Emergency Alerts",
        "description": "Hard braking, overspeed, lane departure alerts to Edge server via Slice 2.",
        "slice": "Slice 2 – Vehicle",
        "slice_id": "slice2",
        "ue": "ue2",
        "services": ["sim-veh-02"],
        "protocol": "HTTP → Edge",
        "data_topic": "veh/telemetry",
        "data_fields": ["speed_kmh", "alert"],
        "icon": "🚨",
        "dashboard_url": "http://localhost:5000",
    },
    "restricted-iot": {
        "name": "Restricted Internal IoT",
        "description": "IoT sensor on Slice 3 — can reach MQTT internally but CANNOT access internet.",
        "slice": "Slice 3 – Restricted",
        "slice_id": "slice3",
        "ue": "ue3",
        "services": ["sim-restricted"],
        "protocol": "MQTT (internal only)",
        "data_topic": "iot/restricted",
        "data_fields": ["temperature_c", "humidity_percent", "restricted"],
        "icon": "🔒",
        "dashboard_url": "/nodered-dashboard",
    },
}


def run_cmd(cmd: List[str], timeout: int = 30) -> Dict[str, Any]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"success": p.returncode == 0, "output": p.stdout.strip(), "error": p.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": "Timed out"}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


def docker_compose_cmd(services: List[str], action: str) -> Dict[str, Any]:
    """Run docker compose command for use case services."""
    cmd = ["docker", "compose", "-f", USECASES_COMPOSE, action] + (["-d"] if action == "up" else []) + services
    return run_cmd(cmd, timeout=60)


# =============================================================================
# Public API
# =============================================================================

def list_usecases() -> List[Dict[str, Any]]:
    """List all use cases with current running status."""
    # Get running containers
    running = set()
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True
        ).stdout.strip()
        running = set(out.splitlines())
    except Exception:
        pass

    result = []
    for uc_id, uc in USE_CASES.items():
        svc_status = {}
        for svc in uc["services"]:
            svc_status[svc] = svc in running

        result.append({
            "id": uc_id,
            "name": uc["name"],
            "description": uc["description"],
            "slice": uc["slice"],
            "slice_id": uc["slice_id"],
            "ue": uc["ue"],
            "protocol": uc["protocol"],
            "data_topic": uc["data_topic"],
            "data_fields": uc["data_fields"],
            "icon": uc["icon"],
            "services": svc_status,
            "running": all(svc_status.values()),
            "dashboard_url": uc.get("dashboard_url", ""),
        })

    return result


def start_usecase(uc_id: str) -> Dict[str, Any]:
    """Start a use case's simulator services."""
    uc = USE_CASES.get(uc_id)
    if not uc:
        return {"success": False, "error": f"Unknown use case: {uc_id}"}

    result = docker_compose_cmd(uc["services"], "up")

    # Auto-configure QoS for the slice
    qos_result = None
    try:
        qos_result = _auto_configure_qos([uc_id])
    except Exception as e:
        qos_result = {"success": False, "error": str(e)}

    return {
        "usecase": uc_id,
        "name": uc["name"],
        "success": result["success"],
        "message": f"{uc['name']} started" if result["success"] else result["error"],
        "qos": qos_result,
    }


def stop_usecase(uc_id: str) -> Dict[str, Any]:
    """Stop a use case's simulator services."""
    uc = USE_CASES.get(uc_id)
    if not uc:
        return {"success": False, "error": f"Unknown use case: {uc_id}"}

    # Stop individual containers (compose down would remove all)
    results = []
    for svc in uc["services"]:
        r = run_cmd(["docker", "stop", svc])
        r2 = run_cmd(["docker", "rm", svc])
        results.append(r["success"])

    return {
        "usecase": uc_id,
        "name": uc["name"],
        "success": all(results),
        "message": f"{uc['name']} stopped" if all(results) else "Some services failed to stop",
    }


def start_all_usecases() -> Dict[str, Any]:
    """Start all use case simulators."""
    all_services = []
    for uc in USE_CASES.values():
        all_services.extend(uc["services"])
    result = docker_compose_cmd(all_services, "up")

    # Auto-configure QoS for all slices
    qos_result = None
    try:
        qos_result = _auto_configure_qos(list(USE_CASES.keys()))
    except Exception as e:
        qos_result = {"success": False, "error": str(e)}

    return {
        "success": result["success"],
        "message": "All use cases started" if result["success"] else result["error"],
        "qos": qos_result,
    }


def stop_all_usecases() -> Dict[str, Any]:
    """Stop all use case simulators."""
    results = []
    for uc in USE_CASES.values():
        for svc in uc["services"]:
            run_cmd(["docker", "stop", svc])
            run_cmd(["docker", "rm", svc])
            results.append(True)

    # Clear QoS rules
    try:
        from framework.transport import clear_all_rules
        clear_all_rules()
    except Exception:
        pass

    return {"success": True, "message": "All use cases stopped"}


def get_usecase_logs(uc_id: str, lines: int = 30) -> Dict[str, Any]:
    """Get logs from a use case's simulator containers."""
    uc = USE_CASES.get(uc_id)
    if not uc:
        return {"success": False, "error": f"Unknown use case: {uc_id}"}

    logs = {}
    for svc in uc["services"]:
        r = run_cmd(["docker", "logs", "--tail", str(lines), svc])
        logs[svc] = r["output"] if r["success"] else r["error"]

    return {"usecase": uc_id, "logs": logs, "success": True}