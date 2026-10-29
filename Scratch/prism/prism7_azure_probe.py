"""PRISM-7: measure every real path to the Azure VM and record which one is open.

Four questions, answered by observation rather than assumption: is the machine
addressable at all, can this laptop reach the internet (so a timeout means the
target, not the route), does any credential-free control path exist that could
start it, and once SSH is accepted - what is actually deployed there (commit,
image, containers, database revision, whether OIDC is configured at all).
Writes a JSON record; prints nothing secret. Configuration keys are listed by
name only, never by value.
"""

import json
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

VM_IP = "172.198.77.149"
KEY = Path("D:/CODING/Projects/poa-submission-vm_key.pem")
OUT = Path(__file__).with_name("prism7_azure_probe.json")


def port_open(host: str, port: int, timeout: float = 6.0) -> tuple[str, float]:
    started = time.time()
    with socket.socket() as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
            return "OPEN", round(time.time() - started, 2)
        except Exception as error:
            return type(error).__name__, round(time.time() - started, 2)


def powershell(command: str) -> tuple[int, str]:
    proc = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                          capture_output=True, text=True)
    return proc.returncode, (proc.stdout or proc.stderr).strip()


def ssh_readonly(command: str, timeout: int = 60) -> tuple[int, str]:
    """One BatchMode ssh call. Every command issued here is read-only."""
    proc = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                           "-o", "StrictHostKeyChecking=no", "-i", str(KEY),
                           f"azureuser@{VM_IP}", command],
                          capture_output=True, text=True, timeout=timeout)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def live_inventory() -> dict:
    """What is actually deployed on the VM, as one measured record.

    Environment secrets are never read: the OIDC check lists key *names* and a
    boolean, because the release question is 'is this configured', not 'what
    is configured to'.
    """
    code, banner = ssh_readonly("hostname; who -b | head -1; uname -r")
    if code != 0:
        return {"reachable": False, "first_line": banner.splitlines()[:1]}
    lines = banner.splitlines()
    git = ssh_readonly(
        "cd ~/proof-of-action && "
        "git rev-parse --short HEAD && git rev-parse --abbrev-ref HEAD && "
        "git status --porcelain | wc -l")[1]
    images = ssh_readonly(
        "docker images --format '{{.Repository}}:{{.Tag}}' | grep -i poa | head -10")[1]
    containers = ssh_readonly(
        "docker ps --format '{{.Names}} | {{.Status}} | ports={{.Ports}}'")[1]
    revision = ssh_readonly(
        "docker exec pofa_db psql -U poa_owner -d poa_prod -tAc "
        "'select version_num from alembic_version'")[1]
    ledger = ssh_readonly(
        "docker exec pofa_db psql -U poa_owner -d poa_prod -tAc "
        "'select count(*) from audit_ledger_events'")[1]
    users = ssh_readonly(
        "docker exec pofa_db psql -U poa_owner -d poa_prod -tAc "
        "'select count(*) from users'")[1]
    oidc_names = ssh_readonly(
        "cd ~/proof-of-action && test -f .env && echo '.env present, keys='$(grep -cE '^[A-Z_]+=' .env); "
        "cd ~/proof-of-action && echo 'AUTH_OIDC keys='$(grep -cE '^AUTH_OIDC' .env); "
        "cd ~/proof-of-action && grep -oE '^AUTH_OIDC[A-Z_]*' .env")[1]
    http = ssh_readonly(
        "for p in /health /ready /metrics; do "
        "printf '%s %s\\n' \"$p\" "
        "\"$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000$p)\"; done")[1]
    # Bind address is the whole point: a port list that drops it cannot show
    # whether anything is exposed beyond loopback.
    listening = ssh_readonly("ss -ltn | awk 'NR>1{print $4}' | sort -u")[1]
    buildx = ssh_readonly("docker buildx version 2>&1 | head -1")[1]
    # Run from the VM: the release depends on the VM reaching the provider, and
    # the published key set is what settles which algorithm can verify a token.
    provider = ssh_readonly(
        "ref=tuaeujvuuanadqvykugw; "
        "curl -fsS \"https://$ref.supabase.co/auth/v1/.well-known/openid-configuration\""
        " | python3 -c 'import json,sys; d=json.load(sys.stdin);"
        "print(\"issuer=\"+d[\"issuer\"]);"
        "print(\"algos=\"+\",\".join(d[\"id_token_signing_alg_values_supported\"]));"
        "print(\"jwks_uri=\"+d[\"jwks_uri\"])'; "
        "curl -fsS \"https://$ref.supabase.co/auth/v1/.well-known/jwks.json\""
        " | python3 -c 'import json,sys; k=json.load(sys.stdin)[\"keys\"];"
        "print(\"keys=\"+str(len(k))); [print(\" \"+x[\"kty\"]+\" \"+x.get(\"crv\",\"\")+\" \""
        "+x.get(\"alg\",\"none\")+\" kid=\"+x[\"kid\"]+\" use=\"+x.get(\"use\",\"-\")) for x in k]'")[1]
    return {
        "reachable": True,
        "hostname": lines[0] if lines else "",
        "booted": lines[1] if len(lines) > 1 else "",
        "kernel": lines[2] if len(lines) > 2 else "",
        "git_head_and_dirty_count": git.splitlines(),
        "poa_images": images.splitlines(),
        "containers": containers.splitlines(),
        "poa_prod_revision": revision,
        "poa_prod_ledger_rows": ledger,
        "poa_prod_user_rows": users,
        "oidc_key_names": oidc_names.splitlines(),
        "anonymous_http": http.splitlines(),
        "socket_binds": listening.splitlines(),
        "buildx": buildx,
        "oidc_provider": provider.splitlines(),
    }


def main() -> int:
    record: dict = {"vm_ip": VM_IP, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    record["vm_ports"] = {str(port): port_open(VM_IP, port) for port in (22, 80, 443)}
    # A timeout on the target means nothing unless this machine's own egress works.
    record["egress_control"] = {"github.com:443": port_open("github.com", 443, 5.0)}
    record["ssh_key_present"] = KEY.is_file()

    record["control_paths"] = {
        "az_cli": shutil.which("az"),
        "azure_powershell_module": powershell(
            "if (Get-Module -ListAvailable Az.Compute) { 'present' } else { 'absent' }")[1],
        # Any management call (power state, NSG, start) needs the Az cmdlets;
        # recording their absence is part of the measurement.
        "get_azcontext_cmdlet": powershell(
            "if (Get-Command Get-AzContext -ErrorAction SilentlyContinue) { 'present' } else { 'absent' }")[1],
    }

    ssh = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                          "-o", "StrictHostKeyChecking=no", "-i", str(KEY),
                          f"azureuser@{VM_IP}", "true"],
                         capture_output=True, text=True)
    errors = (ssh.stderr or ssh.stdout).strip().splitlines()
    record["ssh_attempt"] = {"exit_code": ssh.returncode,
                             "first_error_line": errors[0] if errors else ""}
    record["live_inventory"] = (live_inventory() if ssh.returncode == 0
                                else {"skipped": "ssh not accepted yet"})

    OUT.write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
