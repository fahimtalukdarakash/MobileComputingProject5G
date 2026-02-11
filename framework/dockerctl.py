import subprocess
from typing import List, Dict

def run(cmd: List[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n"
            f"exit={p.returncode}\n"
            f"stdout={p.stdout.strip()}\n"
            f"stderr={p.stderr.strip()}"
        )
    return p.stdout

def list_containers() -> List[Dict[str, str]]:
    out = run(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"])
    items = []
    for line in out.strip().splitlines():
        if not line.strip():
            continue
        name, status = line.split("\t", 1)
        items.append({"name": name.strip(), "status": status.strip()})
    return sorted(items, key=lambda x: x["name"])