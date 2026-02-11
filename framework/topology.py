import json
import subprocess
from typing import Dict, Any, List

def run(cmd: List[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{p.stderr.strip()}")
    return p.stdout

def get_full_topology() -> Dict[str, Any]:
    # list running containers (names)
    names = run(["docker", "ps", "--format", "{{.Names}}"]).strip().splitlines()

    containers = []
    for name in names:
        raw = run(["docker", "inspect", name])
        info = json.loads(raw)[0]

        nets = info.get("NetworkSettings", {}).get("Networks", {}) or {}
        net_info = []
        for net_name, net_obj in nets.items():
            net_info.append({
                "network": net_name,
                "ip": net_obj.get("IPAddress"),
                "gateway": net_obj.get("Gateway"),
                "mac": net_obj.get("MacAddress"),
            })

        containers.append({
            "name": name,
            "state": info.get("State", {}).get("Status"),
            "image": info.get("Config", {}).get("Image"),
            "networks": net_info,
        })

    return {"containers": sorted(containers, key=lambda x: x["name"])}