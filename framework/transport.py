# framework/transport.py
"""
5G Transport Network Control
==============================
Manages QoS, bandwidth limits, latency simulation, and prioritization
per network slice using Linux Traffic Control (tc) and iptables.

Architecture:
  Each UPF has an 'ogstun' interface carrying slice traffic.
  - UPF1 (ogstun) → Slice 1 IoT      (10.45.0.0/16)
  - UPF2 (ogstun) → Slice 2 Vehicle   (10.46.0.0/16)
  - UPF3 (ogstun) → Slice 3 Restricted(10.47.0.0/16)

  tc rules are applied on ogstun inside each UPF container to shape traffic.
"""

import subprocess
import json
import time
from typing import Dict, Any, List, Optional
from copy import deepcopy

TIMEOUT = 10

# =============================================================================
# Slice QoS Profiles
# =============================================================================

# Default QoS profiles per use case type
QOS_PROFILES = {
    "iot-default": {
        "name": "IoT Default",
        "description": "Low bandwidth, tolerant latency — typical sensor data",
        "bandwidth_down": "5mbit",
        "bandwidth_up": "2mbit",
        "latency_ms": 50,
        "jitter_ms": 10,
        "loss_pct": 0,
        "priority": 3,
    },
    "vehicle-default": {
        "name": "Vehicle / URLLC",
        "description": "High bandwidth, ultra-low latency — safety-critical",
        "bandwidth_down": "50mbit",
        "bandwidth_up": "25mbit",
        "latency_ms": 5,
        "jitter_ms": 2,
        "loss_pct": 0,
        "priority": 1,
    },
    "restricted-default": {
        "name": "Restricted Internal",
        "description": "Limited bandwidth, internal only — no internet access",
        "bandwidth_down": "2mbit",
        "bandwidth_up": "1mbit",
        "latency_ms": 20,
        "jitter_ms": 5,
        "loss_pct": 0,
        "priority": 4,
    },
    "embb": {
        "name": "Enhanced Mobile Broadband",
        "description": "Maximum bandwidth for data-heavy applications",
        "bandwidth_down": "100mbit",
        "bandwidth_up": "50mbit",
        "latency_ms": 10,
        "jitter_ms": 3,
        "loss_pct": 0,
        "priority": 2,
    },
    "emergency": {
        "name": "Emergency / Mission-Critical",
        "description": "Highest priority, guaranteed bandwidth, minimal latency",
        "bandwidth_down": "30mbit",
        "bandwidth_up": "15mbit",
        "latency_ms": 2,
        "jitter_ms": 1,
        "loss_pct": 0,
        "priority": 0,
    },
    "degraded": {
        "name": "Degraded Network Simulation",
        "description": "Simulate poor network conditions for testing",
        "bandwidth_down": "1mbit",
        "bandwidth_up": "512kbit",
        "latency_ms": 200,
        "jitter_ms": 50,
        "loss_pct": 5,
        "priority": 5,
    },
}

# Map slices to UPF containers and interfaces
# Traffic between UE↔Edge goes through Docker network (eth0), not GTP tunnel.
# We apply tc on BOTH eth0 (catches Docker network traffic) AND tunnel interfaces.
SLICE_MAP = {
    "slice1": {"upf": "upf1", "upf_iface": "ogstun", "subnet": "10.45.0.0/16", "ue": "ue1", "ue_iface": "eth0", "ue_tun": "uesimtun0"},
    "slice2": {"upf": "upf2", "upf_iface": "ogstun", "subnet": "10.46.0.0/16", "ue": "ue2", "ue_iface": "eth0", "ue_tun": "uesimtun0"},
    "slice3": {"upf": "upf3", "upf_iface": "ogstun", "subnet": "10.47.0.0/16", "ue": "ue3", "ue_iface": "eth0", "ue_tun": "uesimtun0"},
}

# Currently applied rules per slice
_active_rules: Dict[str, Dict[str, Any]] = {}


def run(cmd: List[str], timeout: int = TIMEOUT) -> Dict[str, Any]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"success": p.returncode == 0, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Timed out"}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e)}


def docker_exec(container: str, cmd: str) -> Dict[str, Any]:
    return run(["docker", "exec", container, "sh", "-c", cmd])


# =============================================================================
# Traffic Control (tc) Operations
# =============================================================================

def clear_tc_rules(slice_id: str) -> Dict[str, Any]:
    """Remove all tc rules from a slice's UPF and UE interfaces."""
    smap = SLICE_MAP.get(slice_id)
    if not smap:
        return {"success": False, "error": f"Unknown slice: {slice_id}"}

    upf = smap["upf"]
    ue = smap["ue"]

    # Clear on UPF (ogstun)
    docker_exec(upf, f"tc qdisc del dev {smap['upf_iface']} root 2>/dev/null || true")

    # Clear on UE (eth0 egress + ingress + uesimtun0)
    docker_exec(ue, f"tc qdisc del dev {smap['ue_iface']} root 2>/dev/null || true")
    docker_exec(ue, f"tc qdisc del dev {smap['ue_iface']} ingress 2>/dev/null || true")
    docker_exec(ue, f"tc qdisc del dev {smap['ue_tun']} root 2>/dev/null || true")

    if slice_id in _active_rules:
        del _active_rules[slice_id]

    return {"success": True, "message": f"Cleared tc rules on {upf} and {ue}"}


def apply_tc_rules(slice_id: str, profile_id: str = None,
                   bandwidth_down: str = None, bandwidth_up: str = None,
                   latency_ms: int = None, jitter_ms: int = None,
                   loss_pct: float = None) -> Dict[str, Any]:
    """
    Apply traffic control rules to a slice's UPF interface.

    Can use a preset profile or custom values. Custom values override profile.
    """
    smap = SLICE_MAP.get(slice_id)
    if not smap:
        return {"success": False, "error": f"Unknown slice: {slice_id}"}

    # Start with profile defaults or empty
    params = {}
    if profile_id and profile_id in QOS_PROFILES:
        params = deepcopy(QOS_PROFILES[profile_id])
    else:
        params = {
            "bandwidth_down": "100mbit", "bandwidth_up": "50mbit",
            "latency_ms": 0, "jitter_ms": 0, "loss_pct": 0, "priority": 2,
        }

    # Override with custom values
    if bandwidth_down: params["bandwidth_down"] = bandwidth_down
    if bandwidth_up: params["bandwidth_up"] = bandwidth_up
    if latency_ms is not None: params["latency_ms"] = latency_ms
    if jitter_ms is not None: params["jitter_ms"] = jitter_ms
    if loss_pct is not None: params["loss_pct"] = loss_pct

    upf = smap["upf"]
    ue = smap["ue"]
    ue_iface = smap["ue_iface"]      # eth0 — where Docker network traffic flows
    ue_tun = smap["ue_tun"]          # uesimtun0 — GTP tunnel traffic
    upf_iface = smap["upf_iface"]    # ogstun — UPF tunnel interface

    results = []

    # 1. Clear existing rules
    clear_tc_rules(slice_id)

    # 2. Apply download shaping on UE eth0 (incoming traffic from Docker network)
    #    This is the KEY fix — iperf3 traffic between UE↔Edge goes through eth0
    #    HTB for bandwidth + netem for latency/loss
    netem_params = []
    if params.get("latency_ms", 0) > 0:
        netem_params.append(f"delay {params['latency_ms']}ms")
        if params.get("jitter_ms", 0) > 0:
            netem_params.append(f"{params['jitter_ms']}ms")
    if params.get("loss_pct", 0) > 0:
        netem_params.append(f"loss {params['loss_pct']}%")

    # 2. Apply DOWNLOAD shaping on UE eth0 using INGRESS POLICING
    #    tc only shapes egress — for ingress we use a police filter
    #    This limits incoming traffic (download) on UE's eth0
    cmds_ue_dl = [
        f"tc qdisc add dev {ue_iface} handle ffff: ingress",
        f"tc filter add dev {ue_iface} parent ffff: protocol ip u32 match u32 0 0 police rate {params['bandwidth_down']} burst 256k drop flowid :1",
    ]

    for cmd in cmds_ue_dl:
        r = docker_exec(ue, cmd)
        results.append({"cmd": f"[{ue}] {cmd}", "success": r["success"], "error": r["stderr"] if not r["success"] else ""})

    # 3. Apply UPLOAD shaping on UE eth0 using HTB (egress) + netem for latency
    cmds_ue_ul = [
        f"tc qdisc add dev {ue_iface} root handle 1: htb default 10",
        f"tc class add dev {ue_iface} parent 1: classid 1:10 htb rate {params['bandwidth_up']} ceil {params['bandwidth_up']}",
    ]
    if netem_params:
        cmds_ue_ul.append(f"tc qdisc add dev {ue_iface} parent 1:10 handle 10: netem {' '.join(netem_params)}")

    for cmd in cmds_ue_ul:
        r = docker_exec(ue, cmd)
        results.append({"cmd": f"[{ue}] {cmd}", "success": r["success"], "error": r["stderr"] if not r["success"] else ""})

    # 4. Also apply on UE uesimtun0 for real GTP tunnel traffic
    cmds_ue_tun = [
        f"tc qdisc add dev {ue_tun} root handle 1: htb default 10",
        f"tc class add dev {ue_tun} parent 1: classid 1:10 htb rate {params['bandwidth_up']} ceil {params['bandwidth_up']}",
    ]

    for cmd in cmds_ue_tun:
        r = docker_exec(ue, cmd)
        results.append({"cmd": f"[{ue}] {cmd}", "success": r["success"], "error": r["stderr"] if not r["success"] else ""})

    # 4. Also apply on UPF ogstun for real GTP tunnel traffic
    cmds_upf = [
        f"tc qdisc add dev {upf_iface} root handle 1: htb default 10",
        f"tc class add dev {upf_iface} parent 1: classid 1:10 htb rate {params['bandwidth_down']} ceil {params['bandwidth_down']}",
    ]
    if netem_params:
        cmds_upf.append(f"tc qdisc add dev {upf_iface} parent 1:10 handle 10: netem {' '.join(netem_params)}")

    for cmd in cmds_upf:
        r = docker_exec(upf, cmd)
        results.append({"cmd": f"[{upf}] {cmd}", "success": r["success"], "error": r["stderr"] if not r["success"] else ""})

    # Store active rules
    _active_rules[slice_id] = {
        "slice_id": slice_id,
        "profile_id": profile_id,
        "upf": upf,
        "ue": ue,
        "params": params,
        "applied_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    all_ok = all(r["success"] for r in results)
    return {
        "success": all_ok,
        "slice_id": slice_id,
        "profile": profile_id,
        "params": params,
        "details": results,
        "message": f"QoS applied to {slice_id}: ↓{params['bandwidth_down']} ↑{params['bandwidth_up']} latency={params['latency_ms']}ms"
                   if all_ok else "Some rules failed to apply",
    }


# =============================================================================
# iptables Operations (packet marking for prioritization)
# =============================================================================

def apply_dscp_marking(slice_id: str, dscp_value: int = 46) -> Dict[str, Any]:
    """
    Apply DSCP marking to slice traffic for QoS prioritization.
    DSCP values: EF=46 (voice/emergency), AF41=34 (video), AF21=18 (data), BE=0 (best effort)
    """
    smap = SLICE_MAP.get(slice_id)
    if not smap:
        return {"success": False, "error": f"Unknown slice: {slice_id}"}

    upf = smap["upf"]
    iface = smap["upf_iface"]

    # Mark outgoing packets with DSCP
    r = docker_exec(upf, f"iptables -t mangle -A POSTROUTING -o {iface} -j DSCP --set-dscp {dscp_value}")

    return {
        "success": r["success"],
        "message": f"DSCP {dscp_value} marking applied on {upf}/{iface}" if r["success"] else r["stderr"],
    }


def clear_iptables_rules(slice_id: str) -> Dict[str, Any]:
    """Clear iptables mangle rules on a slice's UPF."""
    smap = SLICE_MAP.get(slice_id)
    if not smap:
        return {"success": False, "error": f"Unknown slice: {slice_id}"}

    upf = smap["upf"]
    r = docker_exec(upf, "iptables -t mangle -F POSTROUTING 2>/dev/null || true")
    return {"success": True, "message": f"Cleared iptables mangle rules on {upf}"}


# =============================================================================
# Query Current State
# =============================================================================

def get_tc_status(slice_id: str) -> Dict[str, Any]:
    """Get current tc rules applied on a slice."""
    smap = SLICE_MAP.get(slice_id)
    if not smap:
        return {"success": False, "error": f"Unknown slice: {slice_id}"}

    upf = smap["upf"]
    ue = smap["ue"]

    # Get tc qdisc from UPF ogstun
    qdisc_upf = docker_exec(upf, f"tc qdisc show dev {smap['upf_iface']}")
    classes_upf = docker_exec(upf, f"tc class show dev {smap['upf_iface']}")

    # Get tc qdisc from UE eth0
    qdisc_ue = docker_exec(ue, f"tc qdisc show dev {smap['ue_iface']}")
    # Get tc qdisc from UE uesimtun0
    qdisc_ue_tun = docker_exec(ue, f"tc qdisc show dev {smap['ue_tun']}")

    return {
        "slice_id": slice_id,
        "upf": upf,
        "ue": ue,
        "active_profile": _active_rules.get(slice_id, {}).get("profile_id"),
        "active_params": _active_rules.get(slice_id, {}).get("params"),
        "applied_at": _active_rules.get(slice_id, {}).get("applied_at"),
        "upf_qdisc": qdisc_upf["stdout"] if qdisc_upf["success"] else qdisc_upf["stderr"],
        "upf_classes": classes_upf["stdout"] if classes_upf["success"] else classes_upf["stderr"],
        "ue_qdisc": qdisc_ue["stdout"] if qdisc_ue["success"] else qdisc_ue["stderr"],
        "ue_tun_qdisc": qdisc_ue_tun["stdout"] if qdisc_ue_tun["success"] else qdisc_ue_tun["stderr"],
    }


def get_all_transport_status() -> Dict[str, Any]:
    """Get transport control status for all slices."""
    slices = {}
    for slice_id in SLICE_MAP:
        slices[slice_id] = get_tc_status(slice_id)

    return {
        "slices": slices,
        "profiles": QOS_PROFILES,
        "active_rules": _active_rules,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def clear_all_rules() -> Dict[str, Any]:
    """Clear all tc and iptables rules across all slices."""
    results = {}
    for slice_id in SLICE_MAP:
        results[slice_id] = {
            "tc": clear_tc_rules(slice_id),
            "iptables": clear_iptables_rules(slice_id),
        }
    return {"success": True, "results": results, "message": "All transport rules cleared"}


# =============================================================================
# Use Case → QoS Mapping (for auto-configuration)
# =============================================================================

USE_CASE_QOS_MAP = {
    "iot-environment":  {"slice": "slice1", "profile": "iot-default"},
    "smart-city":       {"slice": "slice1", "profile": "iot-default"},
    "ehealth":          {"slice": "slice1", "profile": "iot-default"},
    "vehicle-gps":      {"slice": "slice2", "profile": "vehicle-default"},
    "vehicle-alerts":   {"slice": "slice2", "profile": "emergency"},
    "restricted-iot":   {"slice": "slice3", "profile": "restricted-default"},
}

def auto_configure_qos(use_case_ids: List[str]) -> Dict[str, Any]:
    """
    Automatically configure QoS based on active use cases.
    Handles priority conflicts when multiple use cases share a slice
    by selecting the highest priority (lowest number) profile.
    """
    # Determine which profile each slice should use
    slice_profiles: Dict[str, str] = {}

    for uc_id in use_case_ids:
        mapping = USE_CASE_QOS_MAP.get(uc_id)
        if not mapping:
            continue

        slice_id = mapping["slice"]
        profile_id = mapping["profile"]
        profile = QOS_PROFILES.get(profile_id, {})

        # If multiple use cases on same slice, pick highest priority (lowest number)
        if slice_id in slice_profiles:
            existing = QOS_PROFILES.get(slice_profiles[slice_id], {})
            if profile.get("priority", 5) < existing.get("priority", 5):
                slice_profiles[slice_id] = profile_id
        else:
            slice_profiles[slice_id] = profile_id

    # Apply profiles
    results = {}
    for slice_id, profile_id in slice_profiles.items():
        results[slice_id] = apply_tc_rules(slice_id, profile_id=profile_id)

    return {
        "success": all(r["success"] for r in results.values()),
        "configured": results,
        "message": f"Auto-configured QoS for {len(results)} slice(s)",
    }


# =============================================================================
# Priority-Based QoS (Shared Bottleneck Demo)
# =============================================================================
# Creates a bandwidth bottleneck on the Edge server where Slice 1 (IoT) and
# Slice 2 (Vehicle) compete. HTB priority classes ensure IoT gets guaranteed
# bandwidth first, with Vehicle getting the remainder.

import threading

_priority_active = False

# Priority presets (total_bw shared between slices)
PRIORITY_PRESETS = {
    "iot-first": {
        "name": "IoT Priority (Default)",
        "description": "IoT gets guaranteed bandwidth; Vehicle gets remainder",
        "total_bw": "20mbit",
        "iot_rate": "14mbit",    # Guaranteed for IoT
        "iot_ceil": "18mbit",    # Can burst up to
        "iot_prio": 1,
        "vehicle_rate": "4mbit", # Guaranteed for Vehicle
        "vehicle_ceil": "15mbit",# Can burst up to (only if IoT is idle)
        "vehicle_prio": 2,
    },
    "equal": {
        "name": "Equal Share",
        "description": "Both slices get equal bandwidth (baseline comparison)",
        "total_bw": "20mbit",
        "iot_rate": "10mbit",
        "iot_ceil": "15mbit",
        "iot_prio": 1,
        "vehicle_rate": "10mbit",
        "vehicle_ceil": "15mbit",
        "vehicle_prio": 1,
    },
    "vehicle-first": {
        "name": "Vehicle Priority",
        "description": "Vehicle gets priority (for comparison)",
        "total_bw": "20mbit",
        "iot_rate": "4mbit",
        "iot_ceil": "15mbit",
        "iot_prio": 2,
        "vehicle_rate": "14mbit",
        "vehicle_ceil": "18mbit",
        "vehicle_prio": 1,
    },
    "emergency": {
        "name": "Emergency Override",
        "description": "IoT gets near-total bandwidth (emergency scenario)",
        "total_bw": "20mbit",
        "iot_rate": "17mbit",
        "iot_ceil": "19mbit",
        "iot_prio": 0,
        "vehicle_rate": "1mbit",
        "vehicle_ceil": "5mbit",
        "vehicle_prio": 3,
    },
}


def _get_ue_docker_ip(container: str) -> str:
    """Get a UE container's Docker network IP (eth0)."""
    r = docker_exec(container, "hostname -i")
    if r["success"] and r["stdout"]:
        # May return multiple IPs, pick first
        return r["stdout"].strip().split()[0]
    return ""


def _edge_tc(cmd: str) -> Dict[str, Any]:
    """Run tc command in Edge container's network namespace using a helper container with NET_ADMIN."""
    return run([
        "docker", "run", "--rm",
        "--net=container:edge",
        "--cap-add=NET_ADMIN",
        "alpine", "sh", "-c",
        f"apk add --no-cache -q iproute2 >/dev/null 2>&1; tc {cmd}"
    ], timeout=15)


def _edge_tc_batch(cmds: list) -> list:
    """Run multiple tc commands in one container (faster than individual runs)."""
    script = "apk add --no-cache -q iproute2 >/dev/null 2>&1\n"
    for i, cmd in enumerate(cmds):
        script += f'tc {cmd} 2>&1 && echo "RESULT:{i}:OK" || echo "RESULT:{i}:FAIL:$(tc {cmd} 2>&1)"\n'

    r = run([
        "docker", "run", "--rm",
        "--net=container:edge",
        "--cap-add=NET_ADMIN",
        "alpine", "sh", "-c", script
    ], timeout=20)

    # Parse results
    results = []
    output = r["stdout"] + "\n" + r["stderr"]
    for i, cmd in enumerate(cmds):
        ok = f"RESULT:{i}:OK" in output
        err = ""
        if not ok:
            import re as _re
            m = _re.search(f"RESULT:{i}:FAIL:(.*)", output)
            err = m.group(1).strip() if m else "Unknown error"
        results.append({"cmd": f"tc {cmd}", "success": ok, "error": err})

    return results


def apply_priority_rules(preset_id: str = "iot-first") -> Dict[str, Any]:
    """
    Apply priority-based HTB rules on Edge server's eth0.
    Creates a shared bottleneck where IoT and Vehicle slices compete.

    Uses nsenter to run tc in Edge's network namespace (no NET_ADMIN needed).
    HTB classes with different rates/priorities control bandwidth allocation.
    """
    global _priority_active

    preset = PRIORITY_PRESETS.get(preset_id)
    if not preset:
        return {"success": False, "error": f"Unknown preset: {preset_id}"}

    # 1. Get UE Docker IPs
    ue1_ip = _get_ue_docker_ip("ue1")
    ue2_ip = _get_ue_docker_ip("ue2")
    if not ue1_ip or not ue2_ip:
        return {"success": False, "error": f"Could not discover UE IPs: ue1={ue1_ip}, ue2={ue2_ip}"}

    # 2. Clear any existing rules on edge
    clear_priority_rules()

    # 3. Apply HTB hierarchy on edge eth0 (egress = download for UEs)
    cmds = [
        # Root qdisc
        f"qdisc add dev eth0 root handle 1: htb default 30",
        # Parent class (total bandwidth cap)
        f"class add dev eth0 parent 1: classid 1:1 htb rate {preset['total_bw']} ceil {preset['total_bw']}",
        # IoT class (UE1) — higher priority
        f"class add dev eth0 parent 1:1 classid 1:10 htb rate {preset['iot_rate']} ceil {preset['iot_ceil']} prio {preset['iot_prio']}",
        # Vehicle class (UE2) — lower priority
        f"class add dev eth0 parent 1:1 classid 1:20 htb rate {preset['vehicle_rate']} ceil {preset['vehicle_ceil']} prio {preset['vehicle_prio']}",
        # Default class (everything else)
        f"class add dev eth0 parent 1:1 classid 1:30 htb rate 2mbit ceil 5mbit prio 3",
        # Filters — classify by destination IP
        f"filter add dev eth0 parent 1: protocol ip u32 match ip dst {ue1_ip}/32 flowid 1:10",
        f"filter add dev eth0 parent 1: protocol ip u32 match ip dst {ue2_ip}/32 flowid 1:20",
    ]

    results = _edge_tc_batch(cmds)

    _priority_active = True

    return {
        "success": all(r["success"] for r in results),
        "preset": preset_id,
        "preset_name": preset["name"],
        "ue1_ip": ue1_ip,
        "ue2_ip": ue2_ip,
        "config": {
            "total_bw": preset["total_bw"],
            "iot": f"{preset['iot_rate']} (ceil {preset['iot_ceil']}, prio {preset['iot_prio']})",
            "vehicle": f"{preset['vehicle_rate']} (ceil {preset['vehicle_ceil']}, prio {preset['vehicle_prio']})",
        },
        "results": results,
    }


def clear_priority_rules() -> Dict[str, Any]:
    """Remove priority HTB rules from Edge server."""
    global _priority_active
    _edge_tc("qdisc del dev eth0 root")
    _priority_active = False
    return {"success": True, "message": "Priority rules cleared from Edge"}


def get_priority_status() -> Dict[str, Any]:
    """Get current priority rules status."""
    tc_out = _edge_tc("qdisc show dev eth0")
    tc_class = _edge_tc("class show dev eth0")
    return {
        "active": _priority_active,
        "tc_qdisc": tc_out["stdout"] if tc_out["success"] else "",
        "tc_classes": tc_class["stdout"] if tc_class["success"] else "",
    }


def run_priority_test(duration: int = 10, preset_id: str = "iot-first") -> Dict[str, Any]:
    """
    Run simultaneous iperf3 tests from UE1 (IoT) and UE2 (Vehicle) to Edge.
    Both compete for the shared bandwidth on Edge's eth0.
    Returns bandwidth each slice actually received.
    """
    # 1. Ensure iperf3 is installed/available
    for ctr in ["ue1", "ue2", "edge"]:
        check = run(["docker", "exec", ctr, "which", "iperf3"])
        if not check["success"]:
            docker_exec(ctr, "apt-get update -qq && apt-get install -y -qq iperf3 2>/dev/null || "
                            "apk add --no-cache iperf3 2>/dev/null || true")

    # 2. Kill any existing iperf3 on edge
    docker_exec("edge", "kill -9 $(pidof iperf3) 2>/dev/null; true")
    time.sleep(1)

    # 3. Start two iperf3 servers on edge (different ports)
    run(["docker", "exec", "-d", "edge", "iperf3", "-s", "-B", "0.0.0.0", "-p", "5201"])
    run(["docker", "exec", "-d", "edge", "iperf3", "-s", "-B", "0.0.0.0", "-p", "5202"])
    time.sleep(2)

    # 4. Apply priority rules
    apply_result = apply_priority_rules(preset_id)
    if not apply_result["success"]:
        return {"success": False, "error": "Failed to apply priority rules", "details": apply_result}

    time.sleep(1)

    # 5. Run both iperf3 clients SIMULTANEOUSLY (download: -R flag)
    results = {}
    threads = []

    def run_iperf(ue, port, label):
        # Download test (edge → UE)
        r = run(
            ["docker", "exec", ue, "iperf3", "-c", "edge", "-p", str(port), "-t", str(duration), "-R", "-J"],
            timeout=duration + 15
        )
        parsed = {"label": label, "ue": ue, "success": r["success"]}
        if r["success"]:
            try:
                data = json.loads(r["stdout"])
                end = data.get("end", {})
                summary = end.get("sum_received", end.get("sum_sent", {}))
                parsed["mbps"] = round(summary.get("bits_per_second", 0) / 1_000_000, 2)
                parsed["bytes"] = summary.get("bytes", 0)
            except Exception as e:
                parsed["error"] = str(e)
                parsed["raw"] = (r["stdout"] or "")[:300]
        else:
            parsed["error"] = r["stderr"] or r["stdout"] or "Failed"
        results[label] = parsed

    t1 = threading.Thread(target=run_iperf, args=("ue1", 5201, "iot"))
    t2 = threading.Thread(target=run_iperf, args=("ue2", 5202, "vehicle"))

    t1.start()
    t2.start()
    t1.join(timeout=duration + 20)
    t2.join(timeout=duration + 20)

    # 6. Cleanup iperf3 servers
    docker_exec("edge", "kill -9 $(pidof iperf3) 2>/dev/null; true")

    iot_mbps = results.get("iot", {}).get("mbps", 0)
    veh_mbps = results.get("vehicle", {}).get("mbps", 0)
    total = iot_mbps + veh_mbps

    return {
        "success": True,
        "preset": preset_id,
        "preset_name": PRIORITY_PRESETS[preset_id]["name"],
        "duration": duration,
        "iot": results.get("iot", {}),
        "vehicle": results.get("vehicle", {}),
        "summary": {
            "iot_mbps": iot_mbps,
            "vehicle_mbps": veh_mbps,
            "total_mbps": round(total, 2),
            "iot_share_pct": round(iot_mbps / total * 100, 1) if total > 0 else 0,
            "vehicle_share_pct": round(veh_mbps / total * 100, 1) if total > 0 else 0,
        },
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }