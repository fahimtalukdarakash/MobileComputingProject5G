# framework/app.py
"""
5G Framework Backend
====================
FastAPI application serving HTML pages and REST API for
topology, control, configuration, and test automation.
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import subprocess
import time
from typing import Dict, List, Optional

# Background task storage for async operations
_bg_tasks: Dict[str, Dict] = {}
from pathlib import Path

# Local modules
from framework.topology import get_full_topology
from framework.basic_topology import get_basic_topology
from framework.control import (
    up_all, down_all, restart_service, stop_service, start_service,
    list_containers, get_container_logs,
    get_config_files, read_config, write_config, get_network_config_summary,
    stop_slice, start_slice, get_slice_status, SLICE_CONTAINERS,
    run_resilience_test, get_resilience_result,
)
from framework.tests import (
    test_suite, run_all_tests, run_throughput_test,
    ping_test, check_pdu_session, test_slice_isolation, test_service_health,
)
from framework.usecases import (
    list_usecases, start_usecase, stop_usecase,
    start_all_usecases, stop_all_usecases, get_usecase_logs,
)
from framework.monitoring import (
    get_stats_snapshot, get_stats_history, get_mqtt_snapshot,
    get_ue_metrics, get_dashboard_data,
)
from framework.transport import (
    apply_tc_rules, clear_tc_rules, clear_all_rules,
    get_tc_status, get_all_transport_status, apply_dscp_marking,
    auto_configure_qos, QOS_PROFILES, SLICE_MAP,
    apply_priority_rules, clear_priority_rules, get_priority_status,
    run_priority_test, PRIORITY_PRESETS,
)
from framework.loadtest import (
    get_pr_status, start_packetrusher, stop_packetrusher,
    provision_subscribers, run_multi_ue_test, run_gtp_throughput_test,
    get_loadtest_summary, get_task_result,
)
from framework.callsim import (
    initiate_call, terminate_call, get_call_status, get_call_profiles, CALL_PROFILES,
)

# =============================================================================
# App setup
# =============================================================================

app = FastAPI(title="5G Framework Backend", version="0.3.0")

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Pydantic models
# =============================================================================

class ConfigUpdate(BaseModel):
    filename: str
    content: str


# =============================================================================
# HTML Pages
# =============================================================================

@app.get("/", response_class=HTMLResponse)
def page_topology(request: Request):
    return templates.TemplateResponse("topology.html", {"request": request})

@app.get("/control", response_class=HTMLResponse)
def page_control(request: Request):
    return templates.TemplateResponse("control.html", {"request": request})

@app.get("/usecases", response_class=HTMLResponse)
def page_usecases(request: Request):
    return templates.TemplateResponse("usecases.html", {"request": request})

@app.get("/verify", response_class=HTMLResponse)
def page_verify(request: Request):
    return templates.TemplateResponse("verify.html", {"request": request})

@app.get("/monitoring", response_class=HTMLResponse)
def page_monitoring(request: Request):
    return templates.TemplateResponse("monitoring.html", {"request": request})

@app.get("/loadtest", response_class=HTMLResponse)
def page_loadtest(request: Request):
    return templates.TemplateResponse("loadtest.html", {"request": request})

@app.get("/basic", response_class=HTMLResponse)
def page_basic_topology(request: Request):
    return templates.TemplateResponse("basic-topology.html", {"request": request})

@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


# =============================================================================
# Topology API
# =============================================================================

@app.get("/api/topology")
def topology_simple():
    try:
        p = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True, text=True
        )
        containers = []
        for line in p.stdout.strip().splitlines():
            if not line.strip():
                continue
            name, status = line.split("\t", 1)
            containers.append({"name": name.strip(), "status": status.strip()})
        return {"containers": sorted(containers, key=lambda x: x["name"])}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/topology/full")
def topology_full():
    return get_full_topology()

@app.get("/api/topology/basic")
def topology_basic():
    return get_basic_topology()


# =============================================================================
# Control API — Container Lifecycle
# =============================================================================

@app.get("/api/control/containers")
def api_list_containers():
    """List all containers with status."""
    return {"containers": list_containers()}

@app.post("/api/control/up")
def api_control_up():
    """Bring up all services."""
    return up_all()

@app.post("/api/control/down")
def api_control_down():
    """Stop all services."""
    return down_all()

@app.post("/api/control/restart/{name}")
def api_control_restart(name: str):
    """Restart a single container."""
    return restart_service(name)

@app.post("/api/control/stop/{name}")
def api_control_stop(name: str):
    """Stop a single container."""
    return stop_service(name)

@app.post("/api/control/start/{name}")
def api_control_start(name: str):
    """Start a single container."""
    return start_service(name)

@app.get("/api/control/logs/{name}")
def api_control_logs(name: str, lines: int = 50):
    """Get container logs."""
    return get_container_logs(name, lines)

# Slice-level operations
@app.get("/api/slice/status")
def api_slice_status():
    """Get status of all slices."""
    return get_slice_status()

@app.post("/api/slice/stop/{slice_id}")
def api_slice_stop(slice_id: str):
    """Stop a slice (SMF + UPF)."""
    return stop_slice(slice_id)

@app.post("/api/slice/start/{slice_id}")
def api_slice_start(slice_id: str):
    """Start a slice (SMF + UPF)."""
    return start_slice(slice_id)

# Resilience testing
@app.post("/api/resilience/test")
def api_resilience_test(stop: str = "slice1,slice2", verify: str = "slice3"):
    """Run resilience test: stop slices, verify remaining works."""
    stop_list = [s.strip() for s in stop.split(",") if s.strip()]
    return run_resilience_test(stop_list, verify)

@app.get("/api/resilience/task/{task_id}")
def api_resilience_task(task_id: str):
    """Poll for resilience test result."""
    return get_resilience_result(task_id)


# =============================================================================
# Config API
# =============================================================================

@app.get("/api/config/files")
def api_config_files():
    """List available config files."""
    return {"files": get_config_files()}

@app.get("/api/config/read/{filename}")
def api_config_read(filename: str):
    """Read a config file."""
    return read_config(filename)

@app.post("/api/config/write")
def api_config_write(update: ConfigUpdate):
    """Write a config file."""
    return write_config(update.filename, update.content)

@app.get("/api/config/summary")
def api_config_summary():
    """Get network config summary (PLMN, slices, UEs)."""
    return get_network_config_summary()


# =============================================================================
# Monitoring API
# =============================================================================

@app.get("/api/monitoring/stats")
def api_monitoring_stats():
    """Get current container resource usage."""
    return get_stats_snapshot()

@app.get("/api/monitoring/history")
def api_monitoring_history():
    """Get stats history for charts."""
    return {"history": get_stats_history()}

@app.get("/api/monitoring/mqtt")
def api_monitoring_mqtt():
    """Get recent MQTT messages."""
    return get_mqtt_snapshot()

@app.get("/api/monitoring/ue")
def api_monitoring_ue():
    """Get UE tunnel metrics."""
    return {"ues": get_ue_metrics()}

@app.get("/api/monitoring/dashboard")
def api_monitoring_dashboard():
    """Get all monitoring data in one call."""
    return get_dashboard_data()


# =============================================================================
# Subscriber Auto-Provisioning
# =============================================================================

@app.post("/api/provision/ueransim")
def api_provision_ueransim():
    """Auto-provision the 3 UERANSIM subscribers in MongoDB."""
    import os
    init_js = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "configs", "network-slicing", "mongo-init.js"
    )
    if not os.path.exists(init_js):
        return {"success": False, "error": f"Init script not found: {init_js}"}

    with open(init_js, "r") as f:
        js_content = f.read()

    r = subprocess.run(
        ["docker", "exec", "-i", "db", "mongosh", "--quiet"],
        input=js_content, capture_output=True, text=True, timeout=15
    )
    output = (r.stdout or "") + (r.stderr or "")
    return {
        "success": r.returncode == 0 or "CREATED" in output or "EXISTS" in output,
        "output": output.strip(),
    }


# =============================================================================
# Load Test API (PacketRusher)
# =============================================================================

@app.get("/api/loadtest/status")
def api_loadtest_status():
    """Get PacketRusher status and dashboard data."""
    return get_loadtest_summary()

@app.post("/api/loadtest/provision")
def api_loadtest_provision(count: int = 10):
    """Register PacketRusher subscribers in MongoDB."""
    return provision_subscribers(count)

@app.post("/api/loadtest/start")
def api_loadtest_start():
    """Start PacketRusher with single UE."""
    return start_packetrusher()

@app.post("/api/loadtest/stop")
def api_loadtest_stop():
    """Stop PacketRusher."""
    return stop_packetrusher()

@app.post("/api/loadtest/multi-ue")
def api_loadtest_multi_ue(count: int = 5):
    """Run multi-UE load test."""
    return run_multi_ue_test(count)

@app.post("/api/loadtest/gtp-throughput")
def api_loadtest_gtp_throughput(duration: int = 5):
    """Run iperf3 through GTP tunnel (real 5G user plane)."""
    return run_gtp_throughput_test(duration)

@app.get("/api/loadtest/task/{task_id}")
def api_loadtest_task(task_id: str):
    """Poll for background task result."""
    return get_task_result(task_id)


# =============================================================================
# Call Simulation API
# =============================================================================

@app.get("/api/call/profiles")
def api_call_profiles():
    """Get available call type profiles."""
    return get_call_profiles()

@app.post("/api/call/initiate")
def api_call_initiate(caller: str, callee: str, call_type: str = "voice"):
    """Initiate a call between two UEs."""
    return initiate_call(caller, callee, call_type)

@app.post("/api/call/terminate")
def api_call_terminate(call_id: str = None):
    """Terminate the active call."""
    return terminate_call(call_id)

@app.get("/api/call/status")
def api_call_status(call_id: str = None):
    """Get current call status, logs, and packet stats."""
    return get_call_status(call_id)


# =============================================================================
# Transport Network Control API
# =============================================================================

@app.get("/api/transport/status")
def api_transport_status():
    """Get transport control status for all slices."""
    return get_all_transport_status()

@app.get("/api/transport/status/{slice_id}")
def api_transport_slice_status(slice_id: str):
    """Get transport control status for a specific slice."""
    return get_tc_status(slice_id)

@app.get("/api/transport/profiles")
def api_transport_profiles():
    """Get available QoS profiles."""
    return {"profiles": QOS_PROFILES}

@app.post("/api/transport/apply/{slice_id}")
def api_transport_apply(slice_id: str, profile: str = None,
                        bandwidth_down: str = None, bandwidth_up: str = None,
                        latency_ms: int = None, jitter_ms: int = None,
                        loss_pct: float = None):
    """Apply QoS rules to a slice."""
    return apply_tc_rules(slice_id, profile_id=profile,
                          bandwidth_down=bandwidth_down, bandwidth_up=bandwidth_up,
                          latency_ms=latency_ms, jitter_ms=jitter_ms, loss_pct=loss_pct)

@app.post("/api/transport/clear/{slice_id}")
def api_transport_clear(slice_id: str):
    """Clear all tc rules for a slice."""
    return clear_tc_rules(slice_id)

@app.post("/api/transport/clear-all")
def api_transport_clear_all():
    """Clear all transport rules."""
    return clear_all_rules()

@app.post("/api/transport/dscp/{slice_id}")
def api_transport_dscp(slice_id: str, dscp: int = 46):
    """Apply DSCP marking to a slice."""
    return apply_dscp_marking(slice_id, dscp)

@app.post("/api/transport/auto-configure")
def api_transport_auto_configure(use_cases: List[str] = None):
    """Auto-configure QoS based on active use cases."""
    if not use_cases:
        from framework.usecases import USE_CASES
        use_cases = list(USE_CASES.keys())
    return auto_configure_qos(use_cases)


# =============================================================================
# Priority-Based QoS API
# =============================================================================

@app.get("/api/priority/presets")
def api_priority_presets():
    """Get available priority presets."""
    return PRIORITY_PRESETS

@app.get("/api/priority/status")
def api_priority_status():
    """Get current priority rules status."""
    return get_priority_status()

@app.post("/api/priority/apply")
def api_priority_apply(preset: str = "iot-first"):
    """Apply priority rules on Edge server."""
    return apply_priority_rules(preset)

@app.post("/api/priority/clear")
def api_priority_clear():
    """Clear priority rules from Edge server."""
    return clear_priority_rules()

@app.post("/api/priority/test")
def api_priority_test(duration: int = 10, preset: str = "iot-first"):
    """Run simultaneous iperf3 test with priority rules (background)."""
    import threading as _thr
    task_id = f"priority_{int(time.time())}"
    _bg_tasks[task_id] = {"status": "running", "message": f"Running priority test ({preset})..."}

    def _run():
        try:
            result = run_priority_test(duration, preset)
            _bg_tasks[task_id] = {**result, "status": "complete"}
        except Exception as e:
            _bg_tasks[task_id] = {"status": "error", "error": str(e)}

    _thr.Thread(target=_run, daemon=True).start()
    return {"task_id": task_id, "status": "running"}

@app.get("/api/priority/task/{task_id}")
def api_priority_task(task_id: str):
    """Poll for priority test result."""
    return _bg_tasks.get(task_id, {"status": "not_found"})


# =============================================================================
# Use Cases API
# =============================================================================

@app.get("/api/usecases")
def api_list_usecases():
    """List all use cases with status."""
    return {"usecases": list_usecases()}

@app.post("/api/usecases/start/{uc_id}")
def api_start_usecase(uc_id: str):
    return start_usecase(uc_id)

@app.post("/api/usecases/stop/{uc_id}")
def api_stop_usecase(uc_id: str):
    return stop_usecase(uc_id)

@app.post("/api/usecases/start-all")
def api_start_all_usecases():
    return start_all_usecases()

@app.post("/api/usecases/stop-all")
def api_stop_all_usecases():
    return stop_all_usecases()

@app.get("/api/usecases/logs/{uc_id}")
def api_usecase_logs(uc_id: str, lines: int = 30):
    return get_usecase_logs(uc_id, lines)


# =============================================================================
# Test automation API
# =============================================================================

@app.post("/api/tests/run")
def api_run_tests():
    """Run basic connectivity tests (backward compatible)."""
    return test_suite()

@app.post("/api/tests/full")
def api_run_full_tests():
    """Run comprehensive test suite (PDU, connectivity, isolation, health)."""
    return run_all_tests()

@app.post("/api/tests/throughput")
def api_run_throughput(client: str = "ue1", server: str = "edge", duration: int = 5):
    """Run iperf3 throughput test."""
    return run_throughput_test(client, server, duration)

@app.post("/api/tests/ping")
def api_ping(container: str = "ue1", target: str = "8.8.8.8"):
    """Run a single ping test."""
    return ping_test(container, target)

@app.post("/api/tests/pdu/{container}")
def api_check_pdu(container: str):
    """Check PDU session for a UE."""
    return check_pdu_session(container)

@app.post("/api/tests/isolation")
def api_test_isolation():
    """Test Slice 3 internet isolation."""
    return test_slice_isolation()

@app.post("/api/tests/health")
def api_test_health():
    """Test service health (MQTT, Edge, NodeRED, WebUI)."""
    return test_service_health()