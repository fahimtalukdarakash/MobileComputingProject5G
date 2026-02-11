# framework/app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Local modules we created
from framework.topology import get_full_topology
from framework.control import up_all, down_all, restart_service
from framework.tests import test_suite

import subprocess
from typing import Dict, List


app = FastAPI(title="5G Framework Backend", version="0.1.0")

# CORS (React dev server usually runs on 3000 or 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run(cmd: List[str]) -> str:
    """Run command and return stdout, raise on failure."""
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stderr.strip()}")
    return p.stdout.strip()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


# -------------------------
# Topology endpoints
# -------------------------

@app.get("/api/topology")
def topology_simple() -> Dict[str, List[Dict[str, str]]]:
    """
    Lightweight topology: container name + docker status.
    """
    out = _run(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"])
    containers = []
    for line in out.splitlines():
        if not line.strip():
            continue
        name, status = line.split("\t", 1)
        containers.append({"name": name.strip(), "status": status.strip()})
    containers.sort(key=lambda x: x["name"])
    return {"containers": containers}


@app.get("/api/topology/full")
def topology_full() -> Dict:
    """
    Full topology: container + image + state + network IPs.
    """
    return get_full_topology()


# -------------------------
# Control endpoints
# -------------------------

@app.post("/api/control/up")
def control_up() -> Dict[str, str]:
    """
    Bring up network slicing core + apps (mqtt/nodered/edge).
    """
    return up_all()


@app.post("/api/control/down")
def control_down() -> Dict[str, str]:
    """
    Stop apps + core.
    """
    return down_all()


@app.post("/api/control/restart/{name}")
def control_restart(name: str) -> Dict[str, str]:
    """
    Restart a single container (e.g., mqtt, ue1, smf1, upf3).
    """
    return restart_service(name)


# -------------------------
# Test automation endpoint
# -------------------------

@app.post("/api/tests/run")
def run_tests() -> Dict:
    """
    Run verification tests (pings from ue1/ue2/ue3).
    """
    return test_suite()
