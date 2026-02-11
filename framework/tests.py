import subprocess
from typing import Dict, List

def run(cmd: List[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        return f"ERR: {' '.join(cmd)}\n{p.stderr.strip()}"
    return p.stdout.strip()

def ping_from(container: str, target: str, count: int = 2) -> str:
    return run(["docker", "exec", "-t", container, "sh", "-lc", f"ping -c {count} {target}"])

def test_suite() -> Dict[str, Dict[str, str]]:
    results = {
        "ue1": {
            "ping_mqtt": ping_from("ue1", "mqtt"),
            "ping_internet": ping_from("ue1", "8.8.8.8"),
        },
        "ue2": {
            "ping_mqtt": ping_from("ue2", "mqtt"),
            "ping_internet": ping_from("ue2", "8.8.8.8"),
        },
        "ue3": {
            "ping_mqtt": ping_from("ue3", "mqtt"),
            "ping_nodered": ping_from("ue3", "nodered"),
            "ping_internet_should_fail": ping_from("ue3", "8.8.8.8"),
        }
    }
    return results