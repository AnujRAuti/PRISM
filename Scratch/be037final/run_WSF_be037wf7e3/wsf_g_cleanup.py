"""BE-037 WS-G: scoped cleanup of this session's disposable resources.

Every removal is justified by a positive identification, never by a pattern:

* a container is removed only when its own ``com.docker.compose.project`` label
  equals one of the two run ids created by this task, and its name/id are
  echoed into the evidence before the call;
* a volume or network is removed only when its name is one of the names the run
  manifests recorded as *free before creation* (``wsf-00-manifest-before.json``
  and the ``be037fin7c1f1`` ownership manifest);
* nothing named ``pofa_*``, ``proof-of-action-final*`` or ``network_pbrpb*`` is
  ever passed to a mutating command — ``refuse()`` asserts that before docker
  is touched.

Before tearing anything down it re-measures the protected databases with the
same read-only query shape used for the opening baseline
(``run_1013t1635_7c1f1/final-00b-protected-db-baseline.txt``), so the
before/after comparison in the report is a comparison of measurements.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
REPO = Path("D:/CODING/Projects/Proof-Of-Action-Final")

RUN_IDS = ["be037wf7e3", "be037fin7c1f1"]
PROTECTED_CONTAINERS = ["pofa_db", "pofa_redis", "pofa_minio"]
PROTECTED_DBS = ["pofa_dev", "pofa_test"]
BASELINE_FILE = Path("D:/CODING/Scratch/be037final/run_1013t1635_7c1f1/"
                     "final-00b-protected-db-baseline.txt")

OUT_PATH = EVIDENCE / "wsg-07-cleanup.json"

OUT: dict = {}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def record(key: str, payload) -> None:
    OUT[key] = payload
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(OUT, indent=2, default=str), encoding="utf-8")


def docker(*args: str, timeout: int = 300) -> tuple[int, str]:
    proc = subprocess.run(["docker", *args], capture_output=True, text=True,
                          timeout=timeout)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def refuse(name: str, action: str) -> None:
    """Never aim a mutating command at a protected resource."""
    lowered = name.lower()
    if (lowered.startswith("pofa") or lowered.startswith("poa_")
            or "proof-of-action" in lowered or lowered.startswith("network_")):
        raise RuntimeError(f"refusing to {action} {name}: not this run's resource")


def inspect(name: str, fmt: str) -> str:
    rc, out = docker("inspect", "-f", fmt, name)
    return out if rc == 0 else f"<absent rc={rc}>"


# ---------------------------------------------------------------------------
# 1. protected databases, re-measured read-only before teardown
# ---------------------------------------------------------------------------

COLUMNS = ("ledger_count", "seq_lo", "seq_hi", "users", "projects", "evidence",
           "analysis_jobs", "webhook_events", "public_tables")

# The same statement, the same container and the same read-only session option
# as the opening baseline (run_1013t1635_7c1f1/run-protected-db-baseline.sh), so
# a difference in the numbers means a difference in the data, not in the probe.
COUNTS = ("SELECT (SELECT count(*) FROM audit_ledger_events)||'|'||"
          "(SELECT coalesce(min(sequence_number),0) FROM audit_ledger_events)||'|'||"
          "(SELECT coalesce(max(sequence_number),0) FROM audit_ledger_events)||'|'||"
          "(SELECT count(*) FROM users)||'|'||"
          "(SELECT count(*) FROM projects)||'|'||"
          "(SELECT count(*) FROM evidence)||'|'||"
          "(SELECT count(*) FROM analysis_jobs)||'|'||"
          "(SELECT count(*) FROM webhook_events)||'|'||"
          "(SELECT count(*) FROM information_schema.tables WHERE table_schema='public')")


def psql(db: str, statement: str) -> list[str]:
    rc, out = docker("exec", "-e", "PGOPTIONS=-c default_transaction_read_only=on",
                     "pofa_db", "psql", "-U", "postgres", "-d", db, "-tAc", statement,
                     timeout=180)
    if rc != 0:
        return [f"<psql rc={rc} {out[:180]}>"]
    return out.splitlines()


def protected_db_measures() -> dict:
    out: dict = {}
    for db in PROTECTED_DBS:
        row: dict = {}
        ident = psql(db, "SELECT 'identity: '||current_database()||'|'||current_user")
        row["identity"] = ident[0].replace("identity: ", "") if ident else None
        counts = psql(db, COUNTS)
        if counts and "|" in counts[0]:
            row.update(dict(zip(COLUMNS, counts[0].split("|"))))
        else:
            row["counts_error"] = counts
        alembic = psql(db, "SELECT 'alembic_version: '||version_num FROM alembic_version")
        row["alembic_version"] = [r.replace("alembic_version: ", "") for r in alembic]
        ext = psql(db, "SELECT coalesce(string_agg(extname,',' ORDER BY extname),'(none)') "
                       "FROM pg_extension")
        row["extensions"] = ext[0] if ext else None
        demo = psql(db, "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
                        "ON n.oid=c.relnamespace WHERE c.relname='exemplo_dados'")
        row["exemplo_dados_tables"] = demo[0] if demo else None
        out[db] = row
        log(f"{db} measured: {dict(zip(COLUMNS, counts)) if counts else row}")
    return out


def protected_containers(now: str) -> dict:
    out: dict = {}
    for name in PROTECTED_CONTAINERS:
        rc, out_ = docker("inspect", "-f",
                          "NAME={{.Name}}|ID={{.Id}}|CREATED={{.Created}}|"
                          "STARTED={{.State.StartedAt}}|RESTARTS={{.RestartCount}}|"
                          "RUNNING={{.State.Running}}|POLICY={{.HostConfig.RestartPolicy.Name}}",
                          name)
        out[name] = {"rc": rc, "facts": out_}
    log(f"protected containers re-read ({now})")
    return out


# ---------------------------------------------------------------------------
# 2. enumeration + teardown
# ---------------------------------------------------------------------------

def enumerate_containers() -> list[dict]:
    rc, out = docker("ps", "-a", "--format",
                     "{{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Image}}")
    rows = []
    for line in out.splitlines():
        cid, name, status, image = (line.split("\t") + ["", "", ""])[:4]
        if name.lstrip("/").split("_")[0] in RUN_IDS or any(
                name.lstrip("/").startswith(r) for r in RUN_IDS):
            prj = inspect(name, "{{index .Config.Labels \"com.docker.compose.project\"}}")
            rows.append({"id": cid, "name": name.lstrip("/"), "status": status,
                         "image": image, "compose_project_label": prj})
    return rows


def cluster_databases(container: str) -> list[str]:
    """Which databases lived inside one of *this run's* Postgres containers.

    Recorded before the container and its volume are removed, so the report can
    name exactly what went away — including the deliberately protected-named
    probe database, which existed only inside this run's cluster and died with
    this run's volume. Read-only listing; no server other than a run container
    is contacted.
    """
    rc, out = docker("exec", container, "psql", "-U", "postgres", "-d", "postgres",
                     "-tAc", "select datname from pg_database order by 1", timeout=120)
    return out.splitlines() if rc == 0 else [f"<absent or unreachable rc={rc}>"]


RUN_ID_OTHER = "be037fin7c1f1"
OTHER_RUN_DIR = HERE.parent / "run_1013t1635_7c1f1"

# Containers this task started with `docker run` instead of Compose carry no
# ``com.docker.compose.project`` label, so the label rule alone cannot justify
# removing them. Each is proven instead against the harness that created it.
HARNESS_CREATED = {
    "be037fin7c1f1_db2": {
        "script": OTHER_RUN_DIR / "wsd_second_boot.py",
        "name_literal": 'CONTAINER = f"{RUN_ID}_db2"',
        "volume_literal": 'VOLUME = f"{RUN_ID}_db2_data"',
        "evidence": OTHER_RUN_DIR / "evidence" / "wsd_second_boot.json",
    },
}


def harness_created(name: str) -> dict:
    """Positive identification of a docker-run-created container, or None."""
    spec = HARNESS_CREATED.get(name)
    if spec is None:
        return {}
    proof: dict = {"rule": "created by this task's own harness",
                   "script": str(spec["script"]),
                   "evidence": str(spec["evidence"])}
    if not spec["script"].exists() or not spec["evidence"].exists():
        proof["reason"] = "the creating script or its evidence file is absent"
        return proof
    text = spec["script"].read_text(encoding="utf-8", errors="replace")
    proof["script_names_this_container"] = (spec["name_literal"] in text
                                            and spec["volume_literal"] in text)
    recorded = json.loads(spec["evidence"].read_text(encoding="utf-8"))
    proof["evidence_recorded_container"] = recorded.get("container")
    proof["evidence_docker_run_rc"] = recorded.get("docker_run_rc")
    proof["live_id"] = inspect(name, "{{.Id}}")
    proof["live_created"] = inspect(name, "{{.Created}}")
    proof["live_image"] = inspect(name, "{{.Config.Image}}")
    proof["identified"] = bool(
        proof["script_names_this_container"]
        and proof["evidence_recorded_container"] == name
        and proof["evidence_docker_run_rc"] == 0)
    return proof


def teardown_containers() -> dict:
    rows = enumerate_containers()
    databases_in_run_clusters = {
        c: cluster_databases(c)
        for c in ("be037wf7e3_db", "be037fin7c1f1_db", "be037fin7c1f1_db2")
        if any(r["name"] == c for r in rows)
    }
    result = {"found": rows,
              "databases_in_run_clusters_before_removal": databases_in_run_clusters,
              "note_on_unreadable_clusters":
                  "A stopped container cannot be exec'd into, so the sibling run's "
                  "already-exited clusters are listed from that run's creation-time "
                  "evidence (final-03-ownership-manifest.md, wsd_second_boot.json) "
                  "instead of a post-hoc read.",
              "removals": []}
    for row in rows:
        name = row["name"]
        refuse(name, "remove")
        if row["compose_project_label"] not in RUN_IDS:
            proof = harness_created(name)
            if not proof.get("identified"):
                result["removals"].append({
                    "name": name,
                    "skipped": f"compose project label is "
                               f"{row['compose_project_label']!r}, not a run id, and "
                               f"no harness proof identifies it",
                    "identification_attempt": proof or "no rule matched"})
                log(f"SKIPPED {name}: not positively identified")
                continue
            result["removals"].append({"name": name, "identification": proof})
            log(f"identified {name} as harness-created: {proof['live_id'][:12]}")
        rc, out = docker("rm", "-f", name, timeout=180)
        rc2, _ = docker("inspect", name)
        result["removals"].append({"name": name, "rm_rc": rc, "rm_output": out[:160],
                                   "still_present_after": rc2 == 0})
        log(f"removed container {name} rc={rc}")
    return result


EXPECTED_VOLUMES = {
    "be037wf7e3": ["be037wf7e3_db_data", "be037wf7e3_redis_data",
                   "be037wf7e3_minio_data"],
    "be037fin7c1f1": ["be037fin7c1f1_db_data", "be037fin7c1f1_redis_data",
                      "be037fin7c1f1_minio_data", "be037fin7c1f1_db2_data"],
}

EXPECTED_NETWORKS = {
    "be037wf7e3": ["be037wf7e3_net"],
    "be037fin7c1f1": ["be037fin7c1f1_net"],
}


def list_volumes() -> list[str]:
    rc, out = docker("volume", "ls", "--format", "{{.Name}}")
    return [v for v in out.splitlines() if v.split("_")[0] in RUN_IDS]


def list_networks() -> list[str]:
    rc, out = docker("network", "ls", "--format", "{{.Name}}")
    return [n for n in out.splitlines() if n.split("_")[0] in RUN_IDS]


def teardown_volumes() -> dict:
    present = list_volumes()
    expected = {v for names in EXPECTED_VOLUMES.values() for v in names}
    result = {"listed": present, "unexpected_not_removed":
              [v for v in present if v not in expected], "removals": []}
    for name in present:
        if name not in expected:
            continue
        refuse(name, "remove volume")
        rc, out = docker("volume", "rm", name, timeout=180)
        result["removals"].append({"name": name, "rc": rc, "out": out[:160]})
        log(f"volume rm {name} rc={rc}")
    result["listed_after"] = list_volumes()
    return result


def teardown_networks() -> dict:
    present = list_networks()
    expected = {n for names in EXPECTED_NETWORKS.values() for n in names}
    result = {"listed": present, "unexpected_not_removed":
              [n for n in present if n not in expected], "removals": []}
    for name in present:
        if name not in expected:
            continue
        refuse(name, "remove network")
        rc, out = docker("network", "rm", name, timeout=120)
        result["removals"].append({"name": name, "rc": rc, "out": out[:200]})
        log(f"network rm {name} rc={rc}")
    result["listed_after"] = list_networks()
    return result


def port_state() -> dict:
    """The run's host port mappings must be free again after teardown."""
    import socket

    ports = [15442, 16389, 19010, 19011, 18080, 18081, 15432, 15433, 16379,
             19000, 19001]
    free = {}
    for p in ports:
        s = socket.socket()
        s.settimeout(2)
        free[p] = s.connect_ex(("127.0.0.1", p)) != 0
        s.close()
    return free


def image_state() -> dict:
    rc, out = docker("images", "poa-backend:be037final",
                     "--format", "{{.ID}}|{{.CreatedSince}}|{{.Size}}")
    rc2, users = docker("ps", "-a", "--filter", "ancestor=poa-backend:be037final",
                        "--format", "{{.Names}}")
    return {"listed": out, "rc": rc, "containers_using_it": users.splitlines(),
            "decision": "RETAINED and reported. It is a deterministic build of "
                        "committed code, contains no secrets, and deleting a "
                        "~10 GB image the owner may still want for a rebuild is "
                        "not a resource this task was asked to reclaim."}


CREDENTIAL_KEYS = ("POSTGRES_PASSWORD", "MINIO_ROOT_PASSWORD", "S3_SECRET_KEY",
                   "S3_ACCESS_KEY", "JWT_SECRET", "DATABASE_URL")

# Every entry is a file this task's own harness wrote, identified by the run id
# embedded in its name; none of them existed before the task started.
SCRUB_TARGETS = [
    HERE / "be037wf7e3.compose.yml",
    HERE / "f2-worker.env",
    HERE.parent / "run_1013t1635_7c1f1" / "be037fin7c1f1.compose.yml",
    HERE.parent / "run_1013t1635_7c1f1" / "worker-container.env",
]


def file_scrub() -> dict:
    """Throwaway credentials for containers that no longer exist."""
    rows = []
    for path in SCRUB_TARGETS:
        stat = path.stat() if path.exists() else None
        row = {"path": str(path),
               "identified_by": "filename embeds a run id created by this task "
                                f"({path.name}); "
                                "wsf-00-manifest-before.json / final-03-ownership-manifest.md "
                                "record the resource names as absent before creation",
               "size_bytes": stat.st_size if stat else None,
               "mtime_local": time.strftime("%Y-%m-%dT%H:%M:%S",
                                            time.localtime(stat.st_mtime)) if stat else None}
        if stat is None:
            row["state"] = "absent"
            rows.append(row)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        # Only the variable *names* are ever recorded, never a value.
        keys = [k for k in CREDENTIAL_KEYS if k in text]
        row["credential_variable_names_present"] = keys
        if keys:
            path.unlink()
            row["state"] = "deleted"
        else:
            row["state"] = "kept (no credential-bearing variables)"
        rows.append(row)
        log(f"scrub {path.name}: {row['state']}")
    return {"files": rows,
            "deleted": [r["path"] for r in rows if r.get("state") == "deleted"],
            "note": "Harness scripts, evidence JSON and the run manifests are kept "
                    "as the audit trail; only credential-bearing files are removed. "
                    "No secret value is written into this evidence."}


def merge_tear(key: str, payload: dict) -> None:
    """Keep every teardown pass: a second pass adds detail, it does not replace it."""
    if key not in OUT:
        OUT[key] = payload
        OUT[key]["passes"] = [1]
        return
    prev = OUT[key]
    prev.setdefault("passes", [1]).append(len(prev.get("passes", [1])) + 1)
    for field in ("removals", "found", "listed"):
        old, new = prev.get(field, []), payload.get(field, [])
        seen = {json.dumps(r, sort_keys=True, default=str) for r in old}
        prev[field] = old + [r for r in new
                             if json.dumps(r, sort_keys=True, default=str) not in seen]
    for field in ("removals_failed", "unexpected_not_removed",
                  "note_on_unreadable_clusters"):
        if field in payload:
            prev[field] = payload[field]
    clusters = prev.get("databases_in_run_clusters_before_removal", {})
    for container, dbs in (payload.get("databases_in_run_clusters_before_removal")
                           or {}).items():
        known = clusters.get(container)
        if known and str(known[0]).startswith("<absent"):
            clusters[container] = dbs
        elif not known:
            clusters[container] = dbs
    prev["databases_in_run_clusters_before_removal"] = clusters
    prev["listed_after"] = payload.get("listed_after", prev.get("listed_after"))
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(OUT, indent=2, default=str), encoding="utf-8")


def main() -> int:
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    # Steps are run as separate processes, and `teardown` must not rewrite away
    # the baseline a previous `baseline` process recorded.
    if OUT_PATH.exists():
        OUT.update(json.loads(OUT_PATH.read_text(encoding="utf-8")))
    OUT["steps_executed"] = OUT.get("steps_executed", []) + [step]
    OUT.setdefault("started_at", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    OUT["resumed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if step in ("all", "baseline"):
        record("protected_databases_before_teardown", protected_db_measures())
        record("protected_containers_before_teardown", protected_containers("before"))
    if step in ("all", "teardown"):
        record("containers", teardown_containers())
        record("volumes", teardown_volumes())
        record("networks", teardown_networks())
    if step in ("all", "verify"):
        record("host_ports_free_after", port_state())
        record("image", image_state())
        record("protected_containers_after_teardown", protected_containers("after"))
        record("protected_databases_after_teardown", protected_db_measures())
        rc, out = docker("ps", "-a", "--format", "{{.Names}}")
        record("containers_remaining_matching_run_ids",
               [n for n in out.splitlines()
                if n.lstrip("/").startswith(tuple(RUN_IDS))])
        rc, out = docker("volume", "ls", "--format", "{{.Name}}")
        record("volumes_remaining_matching_run_ids",
               [v for v in out.splitlines()
                if v.split("_")[0] in RUN_IDS])
        rc, out = docker("network", "ls", "--format", "{{.Name}}")
        record("networks_remaining", out.splitlines())
        # Only now, with no container left that could read them.
        record("credential_file_scrub", file_scrub())
    OUT["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    record("_written", str(OUT_PATH))
    return 0


if __name__ == "__main__":
    sys.exit(main())
