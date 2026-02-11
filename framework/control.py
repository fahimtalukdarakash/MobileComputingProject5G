import subprocess
from typing import List, Dict

NETWORK_SLICE_COMPOSE = "compose-files/network-slicing/docker-compose.yaml"
APPS_COMPOSE = "compose-files/apps/docker-compose.apps.yaml"
ENV_FILE = "build-files/open5gs.env"

def run(cmd: List[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stderr.strip()}")
    return p.stdout.strip()

def up_all() -> Dict[str, str]:
    out1 = run(["docker", "compose", "-f", NETWORK_SLICE_COMPOSE, "--env-file", ENV_FILE, "up", "-d"])
    out2 = run(["docker", "compose", "-f", APPS_COMPOSE, "--env-file", ENV_FILE, "up", "-d", "mqtt", "nodered", "edge"])
    return {"core": out1, "apps": out2}

def down_all() -> Dict[str, str]:
    out2 = run(["docker", "compose", "-f", APPS_COMPOSE, "--env-file", ENV_FILE, "down"])
    out1 = run(["docker", "compose", "-f", NETWORK_SLICE_COMPOSE, "--env-file", ENV_FILE, "down"])
    return {"apps": out2, "core": out1}

def restart_service(name: str) -> Dict[str, str]:
    out = run(["docker", "restart", name])
    return {"restarted": out}