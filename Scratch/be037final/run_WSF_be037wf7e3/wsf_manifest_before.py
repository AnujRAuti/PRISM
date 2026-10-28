"""BE-037 WS-F step 0: the ownership manifest, captured BEFORE anything is created.

The acceptance run has to be able to prove which resources it created, so this
records three things before a single container exists:

1. the exact names the run intends to own (containers, volumes, network, database,
   buckets, queue keys, roles), all carrying this run's id;
2. the measured fact that **none of them exists yet** on the Docker host, and that
   the host ports it will bind are free — so a later name match cannot be an
   accident of someone else's leftover;
3. the protected resources' identity at this moment (`pofa_db`, `pofa_redis`,
   `pofa_minio`: full id, created timestamp, state, restart count, image). The
   same fields are re-read at teardown; if they differ, this run disturbed
   something it must not have, and that is reported rather than glossed.

After `compose up`, `wsf_manifest_after.py` records the full container IDs, labels
and creation times that the daemon actually assigned, and cross-checks them
against this list.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
RUN_ID = "be037wf7e3"

PROTECTED_CONTAINERS = ["pofa_db", "pofa_redis", "pofa_minio"]

# Ports this run intends to bind. 1xxxx/18xxxx so a collision with a protected
# service is impossible by construction, but "free" still has to be measured.
HOST_PORTS = [15442, 16389, 19010, 19011, 18080]

INTENDED = {
    "compose_project": RUN_ID,
    "containers": [f"{RUN_ID}_db", f"{RUN_ID}_redis", f"{RUN_ID}_minio"],
    "app_containers": [f"{RUN_ID}_api", f"{RUN_ID}_worker", f"{RUN_ID}_wsig_probe"],
    "volumes": [f"{RUN_ID}_db_data", f"{RUN_ID}_redis_data", f"{RUN_ID}_minio_data"],
    "networks": [f"{RUN_ID}_net"],
    "databases": [f"{RUN_ID}_app"],
    "roles": [f"{RUN_ID}_runtime", f"{RUN_ID}_migrator"],
    "buckets": [f"{RUN_ID}-quarantine", f"{RUN_ID}-evidence"],
    "queue_keys": [f"{RUN_ID}:analysis:jobs", f"{RUN_ID}:analysis:jobs:processing"],
    "host_ports": HOST_PORTS,
}


def docker(*args: str, timeout: int = 90) -> tuple[int, str]:
    proc = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) != 0


def container_facts(name: str) -> dict:
    rc, out = docker(
        "inspect", "-f",
        "{{.Id}}|{{.Created}}|{{.State.Status}}|{{.RestartCount}}|{{.Config.Image}}|"
        "{{index .Config.Labels \"com.docker.compose.project\"}}",
        name,
    )
    if rc != 0:
        return {"exists": False, "inspect": out}
    cid, created, state, restarts, image, project = out.split("|")
    return {
        "exists": True, "id": cid, "id_short": cid[:12], "created": created,
        "state": state, "restart_count": restarts, "image": image,
        "compose_project": project,
    }


def exists(kind: str, name: str) -> bool:
    rc, out = docker(kind, "ls", "-q", "-f", f"name=^{name}$")
    return rc == 0 and bool(out.strip())


def main() -> int:
    EVIDENCE.mkdir(exist_ok=True)
    out: dict = {"captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "intended": INTENDED}

    out["pre_existence"] = {
        "containers": {n: exists("container", n) for n in INTENDED["containers"] + INTENDED["app_containers"]},
        "volumes": {n: exists("volume", n) for n in INTENDED["volumes"]},
        "networks": {n: exists("network", n) for n in INTENDED["networks"]},
    }
    out["all_names_free"] = not any(
        free_flag for kind in ("containers", "volumes", "networks")
        for free_flag in out["pre_existence"][kind].values()
    )
    out["host_ports_free"] = {p: port_free(p) for p in HOST_PORTS}
    out["all_ports_free"] = all(out["host_ports_free"].values())

    out["protected_baseline"] = {n: container_facts(n) for n in PROTECTED_CONTAINERS}

    # The run's own engineering stack (7c1f1) is still up; record that it is a
    # *different* project so nothing here can be confused with it.
    out["sibling_run_stack"] = {
        n: container_facts(n) for n in ("be037fin7c1f1_db", "be037fin7c1f1_redis", "be037fin7c1f1_minio")
    }

    (EVIDENCE / "wsf-00-manifest-before.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8")

    print(f"all_names_free={out['all_names_free']} all_ports_free={out['all_ports_free']}")
    print(f"protected: " + ", ".join(
        f"{n}={v.get('id_short')} state={v.get('state')} restarts={v.get('restart_count')}"
        for n, v in out["protected_baseline"].items()))
    print("wrote evidence/wsf-00-manifest-before.json")
    return 0 if (out["all_names_free"] and out["all_ports_free"]) else 1


if __name__ == "__main__":
    sys.exit(main())
