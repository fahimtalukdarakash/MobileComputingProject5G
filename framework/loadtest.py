# framework/loadtest.py
"""
PacketRusher Load Testing Module
==================================
Integrates PacketRusher for 5G core performance/load testing.
Complements UERANSIM (functional) with stress testing (multi-UE).

UERANSIM = "Does slicing work correctly?"
PacketRusher = "How many UEs can the network handle? How fast?"
"""

import subprocess
import json
import time
import re
import threading
from typing import Dict, Any, List
from pathlib import Path

TIMEOUT = 30
PROJECT_ROOT = Path(__file__).parent.parent
PR_COMPOSE = str(PROJECT_ROOT / "compose-files/network-slicing/docker-compose.packetrusher.yaml")
ENV_FILE = str(PROJECT_ROOT / "build-files/open5gs.env")

BASE_IMSI_NUM = 100  # Starting MSIN: 0000000100
PR_KEY = "00000000000000000000000000000000"
PR_OPC = "00000000000000000000000000000000"

# Background task storage
_task_results: Dict[str, Dict[str, Any]] = {}
_task_lock = threading.Lock()


def run(cmd: List[str], timeout: int = TIMEOUT, input_text: str = None) -> Dict[str, Any]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input_text)
        return {"success": p.returncode == 0, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Timed out"}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e)}


def docker_exec(container: str, cmd: str, timeout: int = TIMEOUT) -> Dict[str, Any]:
    return run(["docker", "exec", container, "sh", "-c", cmd], timeout)


# =============================================================================
# Subscriber Provisioning (MongoDB)
# =============================================================================

def provision_subscribers(count: int = 1) -> Dict[str, Any]:
    """
    Register PacketRusher UE subscribers in Open5GS MongoDB.
    Uses IMSI range starting from 001010000000100.
    """
    results = []

    for i in range(count):
        imsi = f"001010000000{BASE_IMSI_NUM + i:03d}"

        # Build JS script as a heredoc to avoid quoting issues
        mongo_js = (
            f'db = db.getSiblingDB("open5gs");\n'
            f'var result = db.subscribers.updateOne(\n'
            f'  {{ imsi: "{imsi}" }},\n'
            f'  {{ $set: {{\n'
            f'    imsi: "{imsi}",\n'
            f'    schema_version: 1,\n'
            f'    security: {{ k: "{PR_KEY}", amf: "8000", op: null, opc: "{PR_OPC}" }},\n'
            f'    ambr: {{ downlink: {{ value: 1, unit: 3 }}, uplink: {{ value: 1, unit: 3 }} }},\n'
            f'    slice: [{{ sst: 1, sd: "000001", default_indicator: true,\n'
            f'      session: [{{ name: "internet", type: 3,\n'
            f'        qos: {{ index: 9, arp: {{ priority_level: 8, pre_emption_capability: 1, pre_emption_vulnerability: 1 }} }},\n'
            f'        ambr: {{ downlink: {{ value: 1, unit: 3 }}, uplink: {{ value: 1, unit: 3 }} }}\n'
            f'      }}]\n'
            f'    }}]\n'
            f'  }} }},\n'
            f'  {{ upsert: true }}\n'
            f');\n'
            f'print("OK:" + result.acknowledged);\n'
        )

        # Write script to container via stdin using docker exec
        r = run(
            ["docker", "exec", "-i", "db", "mongosh", "--quiet"],
            timeout=10,
            input_text=mongo_js,
        )

        success = r["success"] or "OK:true" in (r["stdout"] or "") or "acknowledged" in (r["stdout"] or "").lower()
        results.append({
            "imsi": imsi,
            "success": success,
            "output": (r["stdout"] or r["stderr"] or "")[:100],
        })

    return {
        "success": all(r["success"] for r in results),
        "count": count,
        "subscribers": results,
        "imsi_range": f"001010000000{BASE_IMSI_NUM:03d} - 001010000000{BASE_IMSI_NUM + count - 1:03d}",
    }


def get_subscriber_count() -> int:
    """Count PacketRusher subscribers in DB (IMSI range 001010000000100+)."""
    js = 'db = db.getSiblingDB("open5gs"); print(db.subscribers.countDocuments({imsi: /^0010100000001/}));'
    r = run(["docker", "exec", "-i", "db", "mongosh", "--quiet"], timeout=10, input_text=js)
    try:
        return int(r["stdout"].strip().split("\n")[-1])
    except (ValueError, AttributeError, IndexError):
        return 0


# =============================================================================
# PacketRusher Lifecycle
# =============================================================================

def get_pr_status() -> Dict[str, Any]:
    """Check if PacketRusher container is running."""
    r = run(["docker", "inspect", "--format", "{{.State.Status}}", "packetrusher"])
    running = r["success"] and "running" in r["stdout"]

    iperf_r = run(["docker", "inspect", "--format", "{{.State.Status}}", "iperf-server"])
    iperf_running = iperf_r["success"] and "running" in iperf_r["stdout"]

    # Get PR logs (last few lines)
    logs = ""
    if running:
        log_r = run(["docker", "logs", "--tail", "20", "packetrusher"])
        logs = log_r["stdout"] or log_r["stderr"]

    return {
        "packetrusher_running": running,
        "iperf_server_running": iperf_running,
        "logs": logs,
        "subscriber_count": get_subscriber_count(),
    }


def start_packetrusher(mode: str = "single") -> Dict[str, Any]:
    """
    Start PacketRusher container.
    mode: 'single' = 1 UE, 'multi' uses the compose default
    """
    # Make sure subscribers exist
    provision_subscribers(1)

    # Stop if already running
    stop_packetrusher()
    time.sleep(1)

    # Start via compose
    r = run([
        "docker", "compose",
        "-f", PR_COMPOSE,
        "--env-file", ENV_FILE,
        "up", "-d"
    ], timeout=30)

    time.sleep(3)

    # Get status + logs
    status = get_pr_status()

    return {
        "success": r["success"],
        "mode": mode,
        "message": "PacketRusher started" if r["success"] else r["stderr"],
        "status": status,
    }


def stop_packetrusher() -> Dict[str, Any]:
    """Stop PacketRusher containers."""
    run(["docker", "stop", "packetrusher"], timeout=10)
    run(["docker", "rm", "packetrusher"], timeout=10)
    # Keep iperf-server running if needed
    return {"success": True, "message": "PacketRusher stopped"}


# =============================================================================
# Load Tests
# =============================================================================

def run_multi_ue_test(num_ues: int = 5) -> Dict[str, Any]:
    """Start multi-UE load test in background. Returns task_id for polling."""
    task_id = f"multi_ue_{int(time.time())}"

    with _task_lock:
        _task_results[task_id] = {"status": "running", "message": f"Starting {num_ues} UE load test..."}

    def _run():
        try:
            # 1. Provision subscribers
            prov = provision_subscribers(num_ues)
            if not prov["success"]:
                with _task_lock:
                    _task_results[task_id] = {"status": "error", "error": "Failed to provision subscribers", "details": prov}
                return

            # 2. Stop existing PR
            stop_packetrusher()
            time.sleep(1)

            # 3. Run PacketRusher in background (it never exits on its own)
            start_time = time.time()
            run(["docker", "rm", "-f", "packetrusher"], timeout=5)
            time.sleep(1)

            r = run([
                "docker", "run", "-d",
                "--name", "packetrusher",
                "--network", "open5gs",
                "--network-alias", "gnb.packetrusher.org",
                "--privileged",
                "-v", f"{PROJECT_ROOT}/configs/network-slicing/packetrusher.yaml:/PacketRusher/config/packetrusher.yaml",
                f"fgftk/packetrusher:main",
                "--config", "/PacketRusher/config/packetrusher.yaml",
                "multi-ue",
                "-n", str(num_ues),
                "--timeBetweenRegistration", "100",
            ], timeout=30)

            if not r["success"]:
                with _task_lock:
                    _task_results[task_id] = {"status": "error", "error": f"Failed to start container: {r['stderr']}"}
                return

            # 4. Wait for registrations (100ms between each + processing time)
            wait_time = max(10, num_ues * 0.5 + 5)
            time.sleep(wait_time)
            elapsed = round(time.time() - start_time, 2)

            # 5. Collect logs
            log_r = run(["docker", "logs", "packetrusher"], timeout=10)
            output = (log_r["stdout"] or "") + "\n" + (log_r["stderr"] or "")

            # 6. Parse results
            registrations = len(re.findall(r"Registration Accept", output, re.IGNORECASE))
            pdu_sessions = len(re.findall(r"PDU Session Establishment Accept|PDU Session was created", output, re.IGNORECASE))
            pdu_addresses = re.findall(r"PDU address received: ([\d.]+)", output)
            errors = len(re.findall(r"Registration reject|error.*fail", output, re.IGNORECASE))

            # 7. Stop container
            run(["docker", "rm", "-f", "packetrusher"], timeout=10)

            with _task_lock:
                _task_results[task_id] = {
                    "status": "complete",
                    "success": registrations > 0,
                    "num_ues": num_ues,
                    "elapsed_seconds": elapsed,
                    "registrations_detected": registrations,
                    "pdu_sessions_established": pdu_sessions,
                    "pdu_addresses": pdu_addresses,
                    "errors_detected": errors,
                    "avg_registration_time_ms": round((elapsed * 1000) / max(num_ues, 1), 1),
                    "output": output[-3000:],
                }
        except Exception as e:
            with _task_lock:
                _task_results[task_id] = {"status": "error", "error": str(e)}

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return {"task_id": task_id, "status": "running", "message": f"Multi-UE test started with {num_ues} UEs"}


def run_gtp_throughput_test(duration: int = 5) -> Dict[str, Any]:
    """Start GTP throughput test in background. Returns task_id for polling."""
    task_id = f"gtp_{int(time.time())}"

    # Quick check — is PacketRusher running?
    pr_check = run(["docker", "inspect", "--format", "{{.State.Status}}", "packetrusher"])
    pr_running = pr_check["success"] and "running" in pr_check["stdout"]
    if not pr_running:
        return {"task_id": None, "status": "error", "error": "PacketRusher is not running. Start it first with a single UE."}

    with _task_lock:
        _task_results[task_id] = {"status": "running", "message": "Running GTP throughput test..."}

    def _run():
        try:
            # Make sure iperf-server is running
            iperf_check = run(["docker", "inspect", "--format", "{{.State.Status}}", "iperf-server"])
            if not (iperf_check["success"] and "running" in iperf_check["stdout"]):
                run(["docker", "compose", "-f", PR_COMPOSE, "--env-file", ENV_FILE,
                     "up", "-d", "iperf-server"], timeout=20)
                time.sleep(2)

            # Upload test
            upload = run([
                "docker", "exec", "packetrusher",
                "iperf3", "-c", "test.iperf.org", "-t", str(duration), "-J"
            ], timeout=duration + 15)

            # Download test
            download = run([
                "docker", "exec", "packetrusher",
                "iperf3", "-c", "test.iperf.org", "-t", str(duration), "-J", "-R"
            ], timeout=duration + 15)

            def parse_iperf(res):
                if not res["success"]:
                    return {"success": False, "error": res["stderr"] or "Failed"}
                try:
                    data = json.loads(res["stdout"])
                    end = data.get("end", {})
                    summary = end.get("sum_sent", end.get("sum_received", {}))
                    return {
                        "success": True,
                        "mbps": round(summary.get("bits_per_second", 0) / 1_000_000, 2),
                        "bytes": summary.get("bytes", 0),
                        "retransmits": summary.get("retransmits", 0),
                    }
                except Exception as e:
                    return {"success": False, "error": str(e), "raw": res["stdout"][:300]}

            with _task_lock:
                _task_results[task_id] = {
                    "status": "complete",
                    "success": True,
                    "upload": parse_iperf(upload),
                    "download": parse_iperf(download),
                    "note": "Traffic flows through GTP-U tunnel via UPF (real 5G user plane)",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
        except Exception as e:
            with _task_lock:
                _task_results[task_id] = {"status": "error", "error": str(e)}

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return {"task_id": task_id, "status": "running", "message": "GTP throughput test started"}


def get_task_result(task_id: str) -> Dict[str, Any]:
    """Poll for background task result."""
    with _task_lock:
        return _task_results.get(task_id, {"status": "not_found", "error": f"Unknown task: {task_id}"})


# =============================================================================
# Full Comparison Report
# =============================================================================

def get_loadtest_summary() -> Dict[str, Any]:
    """Get complete load test dashboard data."""
    return {
        "status": get_pr_status(),
        "profiles": {
            "ueransim": "Functional testing — 3 UEs, network slicing, PDU sessions, use cases",
            "packetrusher": "Performance testing — multi-UE load, GTP throughput, registration stress",
        },
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }