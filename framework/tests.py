# framework/tests.py
"""
5G Network Verification & Test Automation
==========================================
Test categories:
  1. Connectivity  — ping between UEs, internal services, internet
  2. PDU Sessions  — verify tunnel interfaces and IP assignments
  3. Throughput    — iperf3 bandwidth tests between containers
  4. Slice Isolation — verify UE3 cannot reach internet
  5. Service Health — check app services respond correctly
"""

import subprocess
import re
import time
import json
from typing import Dict, List, Any, Optional

TIMEOUT = 15  # seconds per command


def run(cmd: List[str], timeout: int = TIMEOUT) -> Dict[str, Any]:
    """Run command, return structured result."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "success": p.returncode == 0,
            "stdout": p.stdout.strip(),
            "stderr": p.stderr.strip(),
            "exit_code": p.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Command timed out", "exit_code": -1}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "exit_code": -1}


def docker_exec(container: str, command: str, timeout: int = TIMEOUT) -> Dict[str, Any]:
    """Execute command inside a Docker container."""
    return run(["docker", "exec", container, "sh", "-lc", command], timeout)


# =============================================================================
# Ping Tests
# =============================================================================

def parse_ping(output: str) -> Dict[str, Any]:
    """Parse ping output to extract statistics."""
    result = {"raw": output}

    # packets: "3 packets transmitted, 3 received, 0% packet loss"
    pkt_match = re.search(r"(\d+) packets transmitted, (\d+) received.*?(\d+(?:\.\d+)?)% packet loss", output)
    if pkt_match:
        result["transmitted"] = int(pkt_match.group(1))
        result["received"] = int(pkt_match.group(2))
        result["loss_pct"] = float(pkt_match.group(3))

    # rtt: "rtt min/avg/max/mdev = 0.091/0.165/0.309/0.101 ms"
    rtt_match = re.search(r"rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)", output)
    if rtt_match:
        result["rtt_min"] = float(rtt_match.group(1))
        result["rtt_avg"] = float(rtt_match.group(2))
        result["rtt_max"] = float(rtt_match.group(3))
        result["rtt_mdev"] = float(rtt_match.group(4))

    return result


def ping_test(container: str, target: str, count: int = 3) -> Dict[str, Any]:
    """Ping from container to target, return parsed results."""
    res = docker_exec(container, f"ping -c {count} -W 2 {target}")
    parsed = parse_ping(res["stdout"]) if res["success"] else {"raw": res["stderr"] or res["stdout"]}

    return {
        "container": container,
        "target": target,
        "reachable": res["success"] and parsed.get("loss_pct", 100) == 0,
        "loss_pct": parsed.get("loss_pct", 100 if not res["success"] else None),
        "rtt_avg": parsed.get("rtt_avg"),
        "details": parsed,
    }


# =============================================================================
# PDU Session Tests
# =============================================================================

def check_pdu_session(container: str) -> Dict[str, Any]:
    """Check if UE has an active PDU session (uesimtun0 interface with IP)."""
    res = docker_exec(container, "ip addr show uesimtun0")

    if not res["success"]:
        return {
            "container": container,
            "active": False,
            "interface": "uesimtun0",
            "error": "Interface not found — no PDU session",
        }

    # Extract IP from output
    ip_match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/(\d+)", res["stdout"])
    ip_addr = ip_match.group(1) if ip_match else None
    subnet_mask = ip_match.group(2) if ip_match else None

    # Check interface state
    state_match = re.search(r"state (\w+)", res["stdout"])
    state = state_match.group(1) if state_match else "UNKNOWN"

    return {
        "container": container,
        "active": ip_addr is not None,
        "interface": "uesimtun0",
        "ip": ip_addr,
        "subnet_mask": subnet_mask,
        "state": state,
    }


def check_routing(container: str) -> Dict[str, Any]:
    """Check routing table of a container."""
    res = docker_exec(container, "ip route show")
    routes = []
    if res["success"]:
        for line in res["stdout"].splitlines():
            routes.append(line.strip())

    return {
        "container": container,
        "routes": routes,
        "has_default": any("default" in r for r in routes),
        "has_tunnel": any("uesimtun" in r for r in routes),
    }


# =============================================================================
# Throughput Tests (iperf3)
# =============================================================================

def iperf3_test(client_container: str, server_container: str,
                duration: int = 5, reverse: bool = False) -> Dict[str, Any]:
    """
    Run iperf3 between two containers.
    Starts server on server_container, runs client on client_container.
    Auto-installs iperf3 if not present.
    """
    # Ensure iperf3 is installed on both containers
    for ctr in [client_container, server_container]:
        check = docker_exec(ctr, "which iperf3")
        if not check["success"]:
            # Try installing — works on debian/ubuntu-based images
            docker_exec(ctr, "apt-get update -qq && apt-get install -y -qq iperf3 2>/dev/null || "
                            "apk add --no-cache iperf3 2>/dev/null || "
                            "pip install -q iperf3 2>/dev/null || true", timeout=30)

    # Use container name as address (Docker DNS) — more reliable than hostname -i
    server_addr = server_container

    # Kill any existing iperf3
    docker_exec(server_container, "kill -9 $(pidof iperf3) 2>/dev/null; true")
    time.sleep(0.5)
    run(["docker", "exec", "-d", server_container, "iperf3", "-s", "-1", "-B", "0.0.0.0"])
    time.sleep(2)

    # Verify server started (use pidof — works on slim containers)
    check_server = docker_exec(server_container, "pidof iperf3")
    if not check_server["success"]:
        return {"success": False, "error": f"iperf3 server failed to start on {server_container}. iperf3 may not be available."}

    # Run client using container name — direct exec, no sh wrapper
    cmd_list = ["docker", "exec", client_container, "iperf3", "-c", server_addr, "-t", str(duration), "-J"]
    if reverse:
        cmd_list.append("-R")
    res = run(cmd_list, timeout=duration + 10)

    result = {
        "client": client_container,
        "server": server_container,
        "server_ip": server_addr,
        "duration": duration,
        "direction": "download" if reverse else "upload",
        "success": res["success"],
    }

    if res["success"]:
        try:
            data = json.loads(res["stdout"])
            end = data.get("end", {})
            # sum_sent or sum_received
            summary = end.get("sum_sent", end.get("sum_received", {}))
            result["bits_per_second"] = summary.get("bits_per_second", 0)
            result["mbps"] = round(summary.get("bits_per_second", 0) / 1_000_000, 2)
            result["bytes"] = summary.get("bytes", 0)
            result["retransmits"] = summary.get("retransmits", 0)
        except Exception as e:
            result["parse_error"] = str(e)
            result["raw"] = res["stdout"][:500]
    else:
        result["error"] = res["stderr"] or res["stdout"]

    # Cleanup
    docker_exec(server_container, "kill -9 $(pidof iperf3) 2>/dev/null; true")

    return result


# =============================================================================
# Slice Isolation Test
# =============================================================================

def test_slice_isolation() -> Dict[str, Any]:
    """Verify UE3 cannot reach internet but can reach internal services."""
    results = {
        "description": "Slice 3 Isolation: UE3 should reach internal services but NOT the internet",
        "tests": [],
    }

    # UE3 → internet (should FAIL)
    internet_test = ping_test("ue3", "8.8.8.8", count=2)
    results["tests"].append({
        "name": "UE3 → Internet (8.8.8.8)",
        "expected": "BLOCKED",
        "actual": "BLOCKED" if not internet_test["reachable"] else "REACHABLE",
        "pass": not internet_test["reachable"],
    })

    # UE3 → mqtt (should SUCCEED)
    mqtt_test = ping_test("ue3", "mqtt", count=2)
    results["tests"].append({
        "name": "UE3 → MQTT (internal)",
        "expected": "REACHABLE",
        "actual": "REACHABLE" if mqtt_test["reachable"] else "BLOCKED",
        "pass": mqtt_test["reachable"],
        "rtt_avg": mqtt_test.get("rtt_avg"),
    })

    # UE3 → nodered (should SUCCEED)
    nodered_test = ping_test("ue3", "nodered", count=2)
    results["tests"].append({
        "name": "UE3 → NodeRED (internal)",
        "expected": "REACHABLE",
        "actual": "REACHABLE" if nodered_test["reachable"] else "BLOCKED",
        "pass": nodered_test["reachable"],
        "rtt_avg": nodered_test.get("rtt_avg"),
    })

    # UE3 → edge (should SUCCEED)
    edge_test = ping_test("ue3", "edge", count=2)
    results["tests"].append({
        "name": "UE3 → Edge (internal)",
        "expected": "REACHABLE",
        "actual": "REACHABLE" if edge_test["reachable"] else "BLOCKED",
        "pass": edge_test["reachable"],
        "rtt_avg": edge_test.get("rtt_avg"),
    })

    # UE1 → internet (should SUCCEED — proves only UE3 is blocked)
    ue1_test = ping_test("ue1", "8.8.8.8", count=2)
    results["tests"].append({
        "name": "UE1 → Internet (control test)",
        "expected": "REACHABLE",
        "actual": "REACHABLE" if ue1_test["reachable"] else "BLOCKED",
        "pass": ue1_test["reachable"],
        "rtt_avg": ue1_test.get("rtt_avg"),
    })

    all_pass = all(t["pass"] for t in results["tests"])
    results["overall"] = "PASS" if all_pass else "FAIL"
    results["passed"] = sum(1 for t in results["tests"] if t["pass"])
    results["total"] = len(results["tests"])

    return results


# =============================================================================
# Service Health Tests
# =============================================================================

def http_check(container: str, port: int, path: str = "/") -> Dict[str, Any]:
    """Check HTTP service using whatever tool is available in the container."""
    # Try curl first
    res = docker_exec(container, f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{port}{path}")
    if res["success"] and "not found" not in res["stderr"]:
        code = res["stdout"].strip().strip("'")
        return {"success": code.startswith("2") or code.startswith("3"), "detail": f"HTTP {code}"}

    # Try wget
    res = docker_exec(container, f"wget -q --spider http://localhost:{port}{path}")
    if "not found" not in res["stderr"]:
        return {"success": res["success"], "detail": "wget OK" if res["success"] else f"wget failed: {res['stderr'][:60]}"}

    # Try python3 urllib
    py_cmd = f"python3 -c \"import urllib.request; r=urllib.request.urlopen('http://localhost:{port}{path}'); print(r.status)\""
    res = docker_exec(container, py_cmd)
    if res["success"]:
        return {"success": "200" in res["stdout"] or "30" in res["stdout"], "detail": f"HTTP {res['stdout'].strip()}"}

    # Try node (for Node.js containers like WebUI)
    node_cmd = f"node -e \"const h=require('http');h.get('http://localhost:{port}{path}',r=>{{console.log(r.statusCode);r.resume()}})\""
    res = docker_exec(container, node_cmd)
    if res["success"]:
        return {"success": "200" in res["stdout"] or "30" in res["stdout"], "detail": f"HTTP {res['stdout'].strip()}"}

    return {"success": False, "detail": "No HTTP client found"}


def test_service_health() -> Dict[str, Any]:
    """Check that app services are responding."""
    results = {"tests": []}

    # MQTT: publish test
    mqtt_res = docker_exec("mqtt", "mosquitto_pub -h localhost -t test/health -m ok -q 0")
    results["tests"].append({
        "name": "MQTT Broker",
        "service": "mqtt",
        "port": 1883,
        "pass": mqtt_res["success"],
        "detail": "Publish OK" if mqtt_res["success"] else mqtt_res["stderr"],
    })

    # Edge server: HTTP check (python:3.11-slim → uses python3)
    edge_check = http_check("edge", 5000)
    results["tests"].append({
        "name": "Edge Server",
        "service": "edge",
        "port": 5000,
        "pass": edge_check["success"],
        "detail": edge_check["detail"],
    })

    # NodeRED: HTTP check
    nodered_check = http_check("nodered", 1880)
    results["tests"].append({
        "name": "Node-RED Dashboard",
        "service": "nodered",
        "port": 1880,
        "pass": nodered_check["success"],
        "detail": nodered_check["detail"],
    })

    # WebUI: HTTP check (Node.js container → uses node)
    webui_check = http_check("webui", 9999)
    results["tests"].append({
        "name": "Open5GS WebUI",
        "service": "webui",
        "port": 9999,
        "pass": webui_check["success"],
        "detail": webui_check["detail"],
    })

    results["passed"] = sum(1 for t in results["tests"] if t["pass"])
    results["total"] = len(results["tests"])
    results["overall"] = "PASS" if results["passed"] == results["total"] else "FAIL"

    return results


# =============================================================================
# Full Test Suite
# =============================================================================

def test_suite() -> Dict[str, Any]:
    """Run basic connectivity tests (backward compatible)."""
    return {
        "ue1": {
            "ping_mqtt": ping_test("ue1", "mqtt"),
            "ping_internet": ping_test("ue1", "8.8.8.8"),
        },
        "ue2": {
            "ping_mqtt": ping_test("ue2", "mqtt"),
            "ping_internet": ping_test("ue2", "8.8.8.8"),
        },
        "ue3": {
            "ping_mqtt": ping_test("ue3", "mqtt"),
            "ping_nodered": ping_test("ue3", "nodered"),
            "ping_internet_should_fail": ping_test("ue3", "8.8.8.8"),
        },
    }


def run_all_tests() -> Dict[str, Any]:
    """Run comprehensive test suite with all categories."""
    started = time.time()

    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "categories": {},
    }

    # 1. PDU Sessions
    pdu_tests = []
    for ue in ["ue1", "ue2", "ue3"]:
        pdu = check_pdu_session(ue)
        pdu_tests.append({
            "name": f"{ue.upper()} PDU Session",
            "pass": pdu["active"],
            "ip": pdu.get("ip"),
            "state": pdu.get("state"),
            "detail": f"IP: {pdu.get('ip', 'N/A')} | State: {pdu.get('state', 'N/A')}",
        })
    results["categories"]["pdu_sessions"] = {
        "name": "PDU Session Establishment",
        "tests": pdu_tests,
        "passed": sum(1 for t in pdu_tests if t["pass"]),
        "total": len(pdu_tests),
    }

    # 2. Connectivity (ping)
    conn_tests = []
    ping_cases = [
        ("ue1", "mqtt",    True,  "UE1 → MQTT"),
        ("ue1", "8.8.8.8", True,  "UE1 → Internet"),
        ("ue2", "mqtt",    True,  "UE2 → MQTT"),
        ("ue2", "edge",    True,  "UE2 → Edge"),
        ("ue2", "8.8.8.8", True,  "UE2 → Internet"),
        ("ue3", "mqtt",    True,  "UE3 → MQTT"),
        ("ue3", "nodered", True,  "UE3 → NodeRED"),
        ("ue3", "edge",    True,  "UE3 → Edge"),
    ]
    for container, target, expect_pass, name in ping_cases:
        p = ping_test(container, target, count=2)
        conn_tests.append({
            "name": name,
            "pass": p["reachable"] == expect_pass,
            "reachable": p["reachable"],
            "rtt_avg": p.get("rtt_avg"),
            "loss_pct": p.get("loss_pct"),
            "detail": f"RTT: {p.get('rtt_avg', 'N/A')}ms | Loss: {p.get('loss_pct', 'N/A')}%",
        })
    results["categories"]["connectivity"] = {
        "name": "Network Connectivity",
        "tests": conn_tests,
        "passed": sum(1 for t in conn_tests if t["pass"]),
        "total": len(conn_tests),
    }

    # 3. Slice Isolation
    isolation = test_slice_isolation()
    results["categories"]["slice_isolation"] = {
        "name": "Slice 3 Isolation",
        "tests": isolation["tests"],
        "passed": isolation["passed"],
        "total": isolation["total"],
    }

    # 4. Service Health
    health = test_service_health()
    results["categories"]["service_health"] = {
        "name": "Service Health",
        "tests": health["tests"],
        "passed": health["passed"],
        "total": health["total"],
    }

    # Summary
    total_tests = sum(c["total"] for c in results["categories"].values())
    total_passed = sum(c["passed"] for c in results["categories"].values())
    results["summary"] = {
        "total": total_tests,
        "passed": total_passed,
        "failed": total_tests - total_passed,
        "overall": "PASS" if total_passed == total_tests else "FAIL",
        "duration_s": round(time.time() - started, 1),
    }

    return results


def run_throughput_test(client: str = "ue1", server: str = "edge",
                        duration: int = 5) -> Dict[str, Any]:
    """Run iperf3 throughput test between two containers (upload + download)."""

    def kill_iperf3(container: str):
        """Kill iperf3 using methods available on minimal containers."""
        docker_exec(container, "kill -9 $(pidof iperf3) 2>/dev/null; true")

    # Ensure iperf3 is installed on both
    for ctr in [client, server]:
        check = run(["docker", "exec", ctr, "which", "iperf3"])
        if not check["success"]:
            docker_exec(ctr, "apt-get update -qq && apt-get install -y -qq iperf3 2>/dev/null || "
                            "apk add --no-cache iperf3 2>/dev/null || true", timeout=30)

    # Kill any leftover iperf3 processes on server
    kill_iperf3(server)
    time.sleep(1)

    # Start persistent iperf3 server (direct exec, no shell wrapper)
    run(["docker", "exec", "-d", server, "iperf3", "-s", "-B", "0.0.0.0"])
    time.sleep(2)

    # Verify server is running (pidof works on slim containers)
    check_srv = docker_exec(server, "pidof iperf3")
    if not check_srv["success"]:
        return {
            "client": client, "server": server,
            "upload": {"success": False, "error": "iperf3 server failed to start"},
            "download": {"success": False, "error": "iperf3 server failed to start"},
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def run_single(reverse: bool) -> Dict[str, Any]:
        # Direct docker exec — no sh -lc wrapper
        cmd = ["docker", "exec", client, "iperf3", "-c", server, "-t", str(duration), "-J"]
        if reverse:
            cmd.append("-R")
        res = run(cmd, timeout=duration + 15)

        result = {
            "direction": "download" if reverse else "upload",
            "success": res["success"],
        }

        if res["success"] and res["stdout"]:
            try:
                data = json.loads(res["stdout"])
                end = data.get("end", {})
                summary = end.get("sum_sent", end.get("sum_received", {}))
                result["bits_per_second"] = summary.get("bits_per_second", 0)
                result["mbps"] = round(summary.get("bits_per_second", 0) / 1_000_000, 2)
                result["bytes"] = summary.get("bytes", 0)
                result["retransmits"] = summary.get("retransmits", 0)
            except Exception as e:
                result["parse_error"] = str(e)
                result["raw"] = res["stdout"][:500]
        else:
            result["error"] = res["stderr"] or res["stdout"] or "No output"
        return result

    # Run upload test
    upload = run_single(reverse=False)
    time.sleep(1)

    # Run download test
    download = run_single(reverse=True)

    # Cleanup: kill server
    kill_iperf3(server)

    return {
        "client": client,
        "server": server,
        "upload": upload,
        "download": download,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }