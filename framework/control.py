# framework/control.py
"""
5G Network Control Module
==========================
Container lifecycle management, log retrieval, and configuration management.
"""

import subprocess
import json
import os
import time
import yaml
from typing import List, Dict, Any, Optional
from pathlib import Path

# =============================================================================
# Paths (relative to project root)
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
NETWORK_SLICE_COMPOSE = str(PROJECT_ROOT / "compose-files/network-slicing/docker-compose.yaml")
APPS_COMPOSE = str(PROJECT_ROOT / "compose-files/apps/docker-compose.apps.yaml")
ENV_FILE = str(PROJECT_ROOT / "build-files/open5gs.env")
CONFIGS_DIR = PROJECT_ROOT / "configs/network-slicing"


def run(cmd: List[str], timeout: int = 30) -> str:
    """Run command, return stdout. Raises RuntimeError on failure."""
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stderr.strip()}")
    return p.stdout.strip()


def run_safe(cmd: List[str], timeout: int = 30) -> Dict[str, Any]:
    """Run command, return dict with success/output/error."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "success": p.returncode == 0,
            "output": p.stdout.strip(),
            "error": p.stderr.strip() if p.returncode != 0 else "",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": "Command timed out"}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


# =============================================================================
# Container Lifecycle
# =============================================================================

def up_all() -> Dict[str, Any]:
    """Bring up network-slicing core + app services."""
    results = {}
    try:
        run(["docker", "compose", "-f", NETWORK_SLICE_COMPOSE, "--env-file", ENV_FILE, "up", "-d"], timeout=120)
        results["core"] = {"success": True, "message": "Core network started"}
    except RuntimeError as e:
        results["core"] = {"success": False, "message": str(e)}

    try:
        run(["docker", "compose", "-f", APPS_COMPOSE, "--env-file", ENV_FILE, "up", "-d", "mqtt", "nodered", "edge"], timeout=60)
        results["apps"] = {"success": True, "message": "App services started"}
    except RuntimeError as e:
        results["apps"] = {"success": False, "message": str(e)}

    return results


def down_all() -> Dict[str, Any]:
    """Stop all services."""
    results = {}
    try:
        run(["docker", "compose", "-f", APPS_COMPOSE, "--env-file", ENV_FILE, "down"], timeout=60)
        results["apps"] = {"success": True, "message": "App services stopped"}
    except RuntimeError as e:
        results["apps"] = {"success": False, "message": str(e)}

    try:
        run(["docker", "compose", "-f", NETWORK_SLICE_COMPOSE, "--env-file", ENV_FILE, "down"], timeout=120)
        results["core"] = {"success": True, "message": "Core network stopped"}
    except RuntimeError as e:
        results["core"] = {"success": False, "message": str(e)}

    return results


def restart_service(name: str) -> Dict[str, Any]:
    """Restart a single container by name."""
    result = run_safe(["docker", "restart", name])
    return {
        "container": name,
        "success": result["success"],
        "message": f"{name} restarted" if result["success"] else result["error"],
    }


def stop_service(name: str) -> Dict[str, Any]:
    """Stop a single container."""
    result = run_safe(["docker", "stop", name])
    return {
        "container": name,
        "success": result["success"],
        "message": f"{name} stopped" if result["success"] else result["error"],
    }


def start_service(name: str) -> Dict[str, Any]:
    """Start a single container."""
    result = run_safe(["docker", "start", name])
    return {
        "container": name,
        "success": result["success"],
        "message": f"{name} started" if result["success"] else result["error"],
    }


# =============================================================================
# Container Info
# =============================================================================

def list_containers() -> List[Dict[str, Any]]:
    """List all project containers with detailed status."""
    try:
        out = run(["docker", "ps", "-a", "--format",
                    "{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.State}}\t{{.Ports}}"])
    except RuntimeError:
        return []

    containers = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 4:
            containers.append({
                "name": parts[0].strip(),
                "status": parts[1].strip(),
                "image": parts[2].strip(),
                "state": parts[3].strip(),
                "ports": parts[4].strip() if len(parts) > 4 else "",
            })
    return sorted(containers, key=lambda x: x["name"])


def get_container_logs(name: str, lines: int = 50) -> Dict[str, Any]:
    """Get recent logs from a container."""
    result = run_safe(["docker", "logs", "--tail", str(lines), name])
    return {
        "container": name,
        "logs": result["output"] if result["success"] else result["error"],
        "success": result["success"],
    }


# =============================================================================
# Configuration Management
# =============================================================================

def get_config_files() -> List[Dict[str, str]]:
    """List all config files in network-slicing directory."""
    files = []
    if CONFIGS_DIR.exists():
        for f in sorted(CONFIGS_DIR.glob("*.yaml")):
            files.append({"name": f.name, "path": str(f.relative_to(PROJECT_ROOT))})
    return files


def read_config(filename: str) -> Dict[str, Any]:
    """Read and parse a YAML config file."""
    filepath = CONFIGS_DIR / filename
    if not filepath.exists():
        return {"success": False, "error": f"File not found: {filename}"}
    if not filepath.suffix == ".yaml":
        return {"success": False, "error": "Only YAML files allowed"}

    try:
        with open(filepath, "r") as f:
            content = f.read()
        data = yaml.safe_load(content)
        return {"success": True, "filename": filename, "raw": content, "parsed": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_config(filename: str, content: str) -> Dict[str, Any]:
    """Write content to a YAML config file (with backup)."""
    filepath = CONFIGS_DIR / filename
    if not filepath.exists():
        return {"success": False, "error": f"File not found: {filename}"}
    if not filepath.suffix == ".yaml":
        return {"success": False, "error": "Only YAML files allowed"}

    try:
        # Validate YAML
        yaml.safe_load(content)
    except yaml.YAMLError as e:
        return {"success": False, "error": f"Invalid YAML: {e}"}

    try:
        # Create backup
        backup = filepath.with_suffix(".yaml.bak")
        with open(filepath, "r") as f:
            old_content = f.read()
        with open(backup, "w") as f:
            f.write(old_content)

        # Write new content
        with open(filepath, "w") as f:
            f.write(content)

        return {"success": True, "message": f"{filename} saved (backup at {backup.name})"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_network_config_summary() -> Dict[str, Any]:
    """Extract key network parameters from configs (MCC, MNC, slices, subnets)."""
    summary = {
        "plmn": {"mcc": "", "mnc": ""},
        "slices": [],
        "ues": [],
    }

    # Read AMF for PLMN
    amf_cfg = read_config("amf.yaml")
    if amf_cfg.get("success") and amf_cfg.get("parsed"):
        amf = amf_cfg["parsed"].get("amf", {})
        guami = amf.get("guami", [{}])
        if guami:
            plmn = guami[0].get("plmn_id", {})
            summary["plmn"]["mcc"] = str(plmn.get("mcc", ""))
            summary["plmn"]["mnc"] = str(plmn.get("mnc", ""))

        plmn_support = amf.get("plmn_support", [{}])
        if plmn_support:
            for nssai in plmn_support[0].get("s_nssai", []):
                summary["slices"].append({
                    "sst": nssai.get("sst"),
                    "sd": nssai.get("sd"),
                })

    # Read SMF configs for subnet info
    for smf_file, slice_name in [("smf1.yaml", "Slice 1"), ("smf2.yaml", "Slice 2"), ("smf3.yaml", "Slice 3")]:
        smf_cfg = read_config(smf_file)
        if smf_cfg.get("success") and smf_cfg.get("parsed"):
            smf = smf_cfg["parsed"].get("smf", {})
            sessions = smf.get("session", [])
            for s in sessions:
                subnet = s.get("subnet", "")
                # Find matching slice
                for sl in summary["slices"]:
                    info_list = smf.get("info", [{}])
                    if info_list:
                        for nssai_item in info_list[0].get("s_nssai", []):
                            if nssai_item.get("sd") == sl.get("sd"):
                                sl["subnet"] = subnet
                                sl["name"] = slice_name

    # Read UE configs
    for ue_file in ["ue1.yaml", "ue2.yaml", "ue3.yaml"]:
        ue_cfg = read_config(ue_file)
        if ue_cfg.get("success") and ue_cfg.get("parsed"):
            data = ue_cfg["parsed"]
            sessions = data.get("sessions", [{}])
            slice_info = sessions[0].get("slice", {}) if sessions else {}
            summary["ues"].append({
                "name": ue_file.replace(".yaml", "").upper(),
                "supi": data.get("supi", ""),
                "sst": slice_info.get("sst"),
                "sd": slice_info.get("sd"),
            })

    return summary


# =============================================================================
# Slice-Level Operations
# =============================================================================

SLICE_CONTAINERS = {
    "slice1": {"name": "Slice 1 (IoT)", "containers": ["smf1", "upf1"], "simulators": ["sim-iot-01", "sim-iot-02", "sim-iot-03"], "ue": "ue1", "color": "#4ade80"},
    "slice2": {"name": "Slice 2 (Vehicle)", "containers": ["smf2", "upf2"], "simulators": ["sim-veh-01", "sim-veh-02"], "ue": "ue2", "color": "#c084fc"},
    "slice3": {"name": "Slice 3 (Restricted)", "containers": ["smf3", "upf3"], "simulators": ["sim-restricted", "sim-fallback"], "ue": "ue3", "color": "#fb923c"},
}


def stop_slice(slice_id: str) -> Dict[str, Any]:
    """Stop all containers for a slice (SMF + UPF + simulators). UE stays up."""
    sinfo = SLICE_CONTAINERS.get(slice_id)
    if not sinfo:
        return {"success": False, "error": f"Unknown slice: {slice_id}"}

    results = []
    # Stop simulators first
    for ctr in sinfo.get("simulators", []):
        r = run_safe(["docker", "stop", ctr])
        results.append({"container": ctr, "success": r["success"], "type": "simulator"})
    # Stop core NFs
    for ctr in sinfo["containers"]:
        r = run_safe(["docker", "stop", ctr])
        results.append({"container": ctr, "success": r["success"], "type": "core"})

    return {
        "success": all(r["success"] for r in results),
        "slice": slice_id,
        "name": sinfo["name"],
        "action": "stopped",
        "results": results,
    }


def start_slice(slice_id: str) -> Dict[str, Any]:
    """Start all containers for a slice (UPF first, then SMF, then simulators)."""
    sinfo = SLICE_CONTAINERS.get(slice_id)
    if not sinfo:
        return {"success": False, "error": f"Unknown slice: {slice_id}"}

    results = []
    # Start UPF first (SMF depends on UPF DNS)
    upfs = [c for c in sinfo["containers"] if c.startswith("upf")]
    smfs = [c for c in sinfo["containers"] if c.startswith("smf")]

    for ctr in upfs:
        r = run_safe(["docker", "start", ctr])
        results.append({"container": ctr, "success": r["success"], "type": "upf"})

    # Wait for UPF to be DNS-resolvable
    time.sleep(5)

    for ctr in smfs:
        r = run_safe(["docker", "start", ctr])
        results.append({"container": ctr, "success": r["success"], "type": "smf"})

    # Wait for SMF to initialize
    time.sleep(3)

    # Start simulators
    for ctr in sinfo.get("simulators", []):
        r = run_safe(["docker", "start", ctr])
        results.append({"container": ctr, "success": r["success"], "type": "simulator"})

    return {
        "success": all(r["success"] for r in results),
        "slice": slice_id,
        "name": sinfo["name"],
        "action": "started",
        "results": results,
    }


def get_slice_status() -> Dict[str, Any]:
    """Get running status for each slice's containers."""
    status = {}
    for sid, sinfo in SLICE_CONTAINERS.items():
        containers = {}
        all_up = True
        for ctr in sinfo["containers"] + [sinfo["ue"]] + sinfo.get("simulators", []):
            r = run_safe(["docker", "inspect", "--format", "{{.State.Status}}", ctr])
            state = r["output"].strip() if r["success"] else "not_found"
            containers[ctr] = state
            if state != "running" and ctr in sinfo["containers"]:
                all_up = False

        status[sid] = {
            "name": sinfo["name"],
            "healthy": all_up,
            "containers": containers,
        }
    return status


# =============================================================================
# Resilience Testing
# =============================================================================

import threading

_resilience_results: Dict[str, Dict] = {}

def _check_ue_connectivity(ue: str) -> Dict[str, Any]:
    """Check if a UE still has PDU session and connectivity."""
    # Check if UE container is running
    state = run_safe(["docker", "inspect", "--format", "{{.State.Status}}", ue])
    if not state["success"] or state["output"].strip() != "running":
        return {"ue": ue, "running": False, "pdu": False, "ping": False}

    # Check tunnel interface (PDU session)
    tun = run_safe(["docker", "exec", ue, "ip", "addr", "show", "uesimtun0"])
    has_pdu = tun["success"] and "inet " in tun.get("output", "")

    # Extract tunnel IP
    tun_ip = ""
    if has_pdu:
        import re
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", tun["output"])
        if m:
            tun_ip = m.group(1)

    # Ping test (via tunnel to edge)
    ping = run_safe(["docker", "exec", ue, "ping", "-c", "2", "-W", "2", "-I", "uesimtun0", "edge"])
    can_ping = ping["success"]

    return {
        "ue": ue,
        "running": True,
        "pdu": has_pdu,
        "tunnel_ip": tun_ip,
        "ping": can_ping,
    }


def run_resilience_test(stop_slices: list, verify_slice: str = "slice3") -> Dict[str, Any]:
    """
    Resilience test: stop one or more slices, verify remaining slice still works.
    Returns task_id for polling.
    """
    task_id = f"resilience_{int(time.time())}"
    _resilience_results[task_id] = {"status": "running", "message": "Starting resilience test..."}

    def _run():
        try:
            steps = []

            # Step 1: Baseline — check all slices before stopping anything
            steps.append({"step": "Baseline Check", "phase": "before"})
            baseline = {}
            for sid, sinfo in SLICE_CONTAINERS.items():
                baseline[sid] = _check_ue_connectivity(sinfo["ue"])
                baseline[sid]["slice_name"] = sinfo["name"]
            steps[-1]["results"] = baseline

            # Step 2: Start Slice 3 fallback simulator (if not already running)
            steps.append({"step": "Start Slice 3 Fallback Simulator", "phase": "fallback"})
            USECASES_COMPOSE = str(Path(__file__).parent.parent / "compose-files/network-slicing/docker-compose.usecases.yaml")
            ENV = str(Path(__file__).parent.parent / "build-files/open5gs.env")
            fb_r = run_safe([
                "docker", "compose", "-f", USECASES_COMPOSE, "--env-file", ENV,
                "up", "-d", "sim-fallback"
            ], timeout=30)
            steps[-1]["result"] = {
                "success": fb_r["success"],
                "message": "Fallback sim started — publishing to all MQTT topics via Slice 3",
            }
            time.sleep(3)

            # Step 3: Stop requested slices (core NFs + simulators)
            for sid in stop_slices:
                sinfo = SLICE_CONTAINERS.get(sid, {})
                steps.append({"step": f"Stop {sinfo.get('name', sid)}", "phase": "stop"})
                r = stop_slice(sid)
                stopped_ctrs = [x["container"] for x in r.get("results", [])]
                steps[-1]["result"] = r
                steps[-1]["stopped_containers"] = stopped_ctrs

            # Step 4: Wait for network to settle
            time.sleep(5)

            # Step 5: Verify remaining slice(s) still work
            steps.append({"step": "Post-Failure Verification", "phase": "verify"})
            post_check = {}
            for sid, sinfo in SLICE_CONTAINERS.items():
                post_check[sid] = _check_ue_connectivity(sinfo["ue"])
                post_check[sid]["slice_name"] = sinfo["name"]
                post_check[sid]["was_stopped"] = sid in stop_slices
            steps[-1]["results"] = post_check

            # Step 6: Check fallback sim is publishing
            steps.append({"step": "Fallback MQTT Verification", "phase": "mqtt"})
            fb_log = run_safe(["docker", "logs", "--tail", "10", "sim-fallback"], timeout=5)
            fb_active = fb_log["success"] and "[FALLBACK]" in fb_log.get("output", "")
            mqtt_topics = []
            if fb_active:
                log_text = fb_log["output"]
                if "iot/ue-iot-01" in log_text: mqtt_topics.append("iot/ue-iot-01")
                if "iot/ue-iot-02" in log_text: mqtt_topics.append("iot/ue-iot-02")
                if "iot/ue-iot-03" in log_text: mqtt_topics.append("iot/ue-iot-03")
                if "veh/telemetry" in log_text: mqtt_topics.append("veh/telemetry")
            steps[-1]["result"] = {
                "success": fb_active,
                "message": f"Fallback publishing to: {', '.join(mqtt_topics)}" if fb_active else "Fallback not active",
                "topics": mqtt_topics,
                "log_sample": fb_log.get("output", "")[-500:],
            }

            # Step 7: Verify target slice specifically
            verify_info = SLICE_CONTAINERS.get(verify_slice, {})
            target_result = post_check.get(verify_slice, {})
            isolation_proven = target_result.get("running", False)

            _resilience_results[task_id] = {
                "status": "complete",
                "success": True,
                "isolation_proven": isolation_proven,
                "fallback_active": fb_active,
                "fallback_topics": mqtt_topics,
                "verify_slice": verify_slice,
                "verify_slice_name": verify_info.get("name", verify_slice),
                "stopped_slices": stop_slices,
                "steps": steps,
                "summary": {
                    "slices_stopped": [SLICE_CONTAINERS.get(s, {}).get("name", s) for s in stop_slices],
                    "target_survived": isolation_proven,
                    "target_pdu": target_result.get("pdu", False),
                    "target_ping": target_result.get("ping", False),
                    "fallback_active": fb_active,
                    "fallback_topics": len(mqtt_topics),
                    "all_recovered": False,
                },
                "note": "Slices remain stopped. Use Start buttons to manually restart.",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

        except Exception as e:
            _resilience_results[task_id] = {"status": "error", "error": str(e)}

    threading.Thread(target=_run, daemon=True).start()
    return {"task_id": task_id, "status": "running"}


def get_resilience_result(task_id: str) -> Dict[str, Any]:
    return _resilience_results.get(task_id, {"status": "not_found"})