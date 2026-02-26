# framework/monitoring.py
"""
5G Network Monitoring Module
==============================
Collects live metrics: container resource usage (CPU, memory, network I/O),
MQTT message stream, and UE session metrics.
"""

import subprocess
import json
import time
import re
from typing import Dict, Any, List
from pathlib import Path
from collections import deque
import threading

TIMEOUT = 10

# In-memory stores for time-series data (last N samples)
MAX_HISTORY = 60  # keep 60 samples (~5 min at 5s interval)
_stats_history: deque = deque(maxlen=MAX_HISTORY)
_mqtt_messages: deque = deque(maxlen=100)
_mqtt_listener_started = False


def run(cmd: List[str], timeout: int = TIMEOUT) -> Dict[str, Any]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"success": p.returncode == 0, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Timed out"}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e)}


def docker_exec(container: str, cmd: str, timeout: int = TIMEOUT) -> Dict[str, Any]:
    return run(["docker", "exec", container, "sh", "-lc", cmd], timeout)


# =============================================================================
# Docker Stats (CPU, Memory, Network I/O)
# =============================================================================

def parse_size(s: str) -> float:
    """Parse Docker size string like '42.3MiB' or '1.2GiB' to MB."""
    s = s.strip()
    match = re.match(r"([\d.]+)\s*(B|KiB|MiB|GiB|kB|MB|GB)", s, re.IGNORECASE)
    if not match:
        return 0.0
    val = float(match.group(1))
    unit = match.group(2).lower()
    multipliers = {"b": 1/1048576, "kib": 1/1024, "kb": 1/1024, "mib": 1, "mb": 1, "gib": 1024, "gb": 1024}
    return round(val * multipliers.get(unit, 1), 2)


def get_docker_stats() -> List[Dict[str, Any]]:
    """Get real-time resource usage for all containers."""
    res = run(["docker", "stats", "--no-stream", "--format",
               "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.PIDs}}"])

    if not res["success"] or not res["stdout"]:
        return []

    stats = []
    for line in res["stdout"].splitlines():
        parts = line.split("\t")
        if len(parts) < 6:
            continue

        name = parts[0].strip()
        cpu_str = parts[1].strip().rstrip("%")
        mem_usage = parts[2].strip()
        mem_pct_str = parts[3].strip().rstrip("%")
        net_io = parts[4].strip()
        pids = parts[5].strip()

        # Parse memory usage "42.3MiB / 7.5GiB"
        mem_parts = mem_usage.split("/")
        mem_used_mb = parse_size(mem_parts[0]) if len(mem_parts) >= 1 else 0
        mem_limit_mb = parse_size(mem_parts[1]) if len(mem_parts) >= 2 else 0

        # Parse network I/O "1.2MB / 3.4MB"
        net_parts = net_io.split("/")
        net_rx_mb = parse_size(net_parts[0]) if len(net_parts) >= 1 else 0
        net_tx_mb = parse_size(net_parts[1]) if len(net_parts) >= 2 else 0

        try:
            cpu_pct = float(cpu_str)
        except ValueError:
            cpu_pct = 0.0

        try:
            mem_pct = float(mem_pct_str)
        except ValueError:
            mem_pct = 0.0

        stats.append({
            "name": name,
            "cpu_pct": cpu_pct,
            "mem_used_mb": mem_used_mb,
            "mem_limit_mb": mem_limit_mb,
            "mem_pct": mem_pct,
            "net_rx_mb": net_rx_mb,
            "net_tx_mb": net_tx_mb,
            "pids": int(pids) if pids.isdigit() else 0,
        })

    return sorted(stats, key=lambda x: x["name"])


def get_stats_snapshot() -> Dict[str, Any]:
    """Get current stats + store in history."""
    stats = get_docker_stats()
    timestamp = time.strftime("%H:%M:%S")

    snapshot = {"timestamp": timestamp, "containers": stats}
    _stats_history.append(snapshot)

    # Aggregate totals
    total_cpu = sum(s["cpu_pct"] for s in stats)
    total_mem = sum(s["mem_used_mb"] for s in stats)
    container_count = len(stats)

    return {
        "current": snapshot,
        "totals": {
            "cpu_pct": round(total_cpu, 1),
            "mem_mb": round(total_mem, 1),
            "containers": container_count,
        },
    }


def get_stats_history() -> List[Dict[str, Any]]:
    """Get historical stats samples."""
    return list(_stats_history)


# =============================================================================
# MQTT Message Stream
# =============================================================================

def _start_mqtt_listener():
    """Start a background thread that subscribes to all MQTT topics."""
    global _mqtt_listener_started
    if _mqtt_listener_started:
        return

    def listener():
        while True:
            # Use docker exec to subscribe and capture messages
            try:
                p = subprocess.Popen(
                    ["docker", "exec", "mqtt", "mosquitto_sub", "-h", "localhost",
                     "-t", "#", "-v", "--retained-only"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                # Read for 2 seconds then kill
                time.sleep(2)
                p.terminate()
                out, _ = p.communicate(timeout=3)

                for line in out.splitlines():
                    if line.strip():
                        parts = line.split(" ", 1)
                        topic = parts[0] if parts else ""
                        payload = parts[1] if len(parts) > 1 else ""
                        _mqtt_messages.append({
                            "timestamp": time.strftime("%H:%M:%S"),
                            "topic": topic,
                            "payload": payload[:200],
                        })
            except Exception:
                pass
            time.sleep(3)

    _mqtt_listener_started = True
    t = threading.Thread(target=listener, daemon=True)
    t.start()


def get_mqtt_snapshot() -> Dict[str, Any]:
    """Get recent MQTT messages by subscribing briefly."""
    res = run(["docker", "exec", "mqtt", "timeout", "2",
               "mosquitto_sub", "-h", "localhost", "-t", "#", "-v", "-C", "20"], timeout=5)

    messages = []
    if res["success"] or res["stdout"]:
        for line in res["stdout"].splitlines():
            if line.strip():
                parts = line.split(" ", 1)
                topic = parts[0] if parts else ""
                payload = parts[1] if len(parts) > 1 else ""
                # Try to parse JSON payload
                try:
                    data = json.loads(payload)
                    messages.append({
                        "timestamp": time.strftime("%H:%M:%S"),
                        "topic": topic,
                        "payload": data,
                    })
                except (json.JSONDecodeError, ValueError):
                    messages.append({
                        "timestamp": time.strftime("%H:%M:%S"),
                        "topic": topic,
                        "payload": payload[:200],
                    })

    return {"messages": messages, "count": len(messages)}


# =============================================================================
# UE Session Metrics
# =============================================================================

def get_ue_metrics() -> List[Dict[str, Any]]:
    """Get UE tunnel interface stats (bytes rx/tx, packet counts)."""
    ues = []
    for ue in ["ue1", "ue2", "ue3"]:
        # Get interface stats
        res = docker_exec(ue, "cat /proc/net/dev")
        tun_stats = {}
        if res["success"]:
            for line in res["stdout"].splitlines():
                if "uesimtun0" in line:
                    # Format: iface: rx_bytes rx_packets ... tx_bytes tx_packets ...
                    parts = line.split(":")
                    if len(parts) == 2:
                        nums = parts[1].split()
                        if len(nums) >= 10:
                            tun_stats = {
                                "rx_bytes": int(nums[0]),
                                "rx_packets": int(nums[1]),
                                "tx_bytes": int(nums[8]),
                                "tx_packets": int(nums[9]),
                            }

        # Get IP
        ip_res = docker_exec(ue, "ip -4 addr show uesimtun0 | grep inet | awk '{print $2}'")
        ip_addr = ip_res["stdout"].strip() if ip_res["success"] else "N/A"

        ues.append({
            "name": ue,
            "ip": ip_addr,
            "tunnel": tun_stats,
            "has_tunnel": bool(tun_stats),
        })

    return ues


# =============================================================================
# Combined Dashboard Data
# =============================================================================

def get_dashboard_data() -> Dict[str, Any]:
    """Get all monitoring data in one call."""
    stats = get_stats_snapshot()
    ue_metrics = get_ue_metrics()

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stats": stats,
        "ue_metrics": ue_metrics,
    }