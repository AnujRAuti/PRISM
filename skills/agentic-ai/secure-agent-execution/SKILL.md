---
name: secure-agent-execution
description: Run untrusted or model-driven code and actions safely—sandboxing, egress control, resource limits, output validation, and defense against prompt-injected tool use.
metadata:
  domain: agentic-ai
  version: 1.0.0
  risk: high
---

# Secure Agent Execution

## 1. Purpose

Contain the blast radius of an agent that executes code or takes actions. When an agent writes or runs code, browses, installs packages, or calls APIs, the model's output becomes an execution vector. This skill defines the isolation model (what runs where), the egress policy, secret handling, output validation, and the monitoring that detects anomalous behavior.

**Scope:** your own execution environments. Never execute model-generated code on a host with production credentials or unrestricted network access. Do not test containment by attacking infrastructure you do not own.

## 2. Activation Conditions

- An agent executes generated code (Python, shell, SQL) or arbitrary commands.
- Agents browse the web, install packages, or call third-party APIs.
- Agents run in a multi-tenant service with shared infrastructure.
- A security review requires evidence of containment.
- Keywords: sandbox, code execution, egress control, container isolation, seccomp, gVisor, Firecracker, prompt injection, tool abuse, resource limits, allowlist.

## 3. When Not to Use

- The agent only produces text with no execution or external action.
- Standard application security review without an agent dimension (use secure-code-review).

## 4. Required Context

1. What the agent must execute and why (code interpreter, shell, SQL).
2. Data the execution environment can see (mounts, env vars, network).
3. Tenancy model: one sandbox per user/session, or shared?
4. Required network access (package installs, API calls) and destinations.
5. Resource budget and timeout requirements.

## 5. Operating Procedure

1. **Assume the code is hostile.** It may be produced by a model influenced by injected content, or by a user directly.
2. **Choose isolation level**:
   - Container with dropped capabilities + seccomp + read-only rootfs (baseline).
   - gVisor or Kata for stronger kernel isolation.
   - Firecracker microVM per session for untrusted, multi-tenant execution.
3. **Deny egress by default**; allowlist destinations (package mirrors, specific APIs) and block link-local/metadata endpoints (169.254.169.254) and private ranges.
4. **Mount nothing sensitive**: no host home, no docker socket, no cloud credentials, no service tokens. Provide a scratch volume only.
5. **Run as a non-root, unprivileged user** with `no-new-privileges`, `cap_drop=ALL`, pids/memory/CPU/disk limits, and a wall-clock timeout.
6. **Validate and constrain outputs** before use: file sizes, MIME types, JSON schema, and no execution of output as code in the host.
7. **Sanitize the input pipeline**: strip injected instructions from retrieved content, delimit untrusted data, and restrict what tools the agent may call in this session.
8. **Rate-limit and budget** executions per user; kill long-running or runaway processes.
9. **Log every execution** with code hash, exit code, resource usage, and network destinations contacted; alert on anomalies.
10. **Destroy the sandbox after use** (ephemeral, no reuse across users/sessions).
11. **Test the containment**: try to read host files, reach the internet, read metadata, spawn threads, fill disk, and fork-bomb—inside the sandbox.

## 6. Tools and Technologies

| Layer | Options |
|---|---|
| Isolation | Docker/Podman (baseline), gVisor (`runsc`), Firecracker, Kata Containers |
| Kernel controls | seccomp profiles, AppArmor/SELinux, `cap_drop`, `no-new-privileges` |
| Network | nftables/iptables egress rules, DNS allowlist, HTTP proxy with domain allowlist |
| Resource limits | cgroups v2 (`memory.max`, `pids.max`, `cpu.max`, `io.max`) |
| Code execution services | E2B-style sandboxes, Jupyter kernels in containers, `nsjail` |
| Secrets | short-lived scoped tokens injected per call, never mounted persistently |
| Monitoring | eBPF (`execsnoop`, `tcpconnect`), Falco, audit logs |

## 7. Practical Implementation

**Hardened container invocation:**

```bash
podman run --rm \
  --network=none \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m \
  --user 1000:1000 \
  --cap-drop=ALL \
  --security-opt no-new-privileges \
  --security-opt seccomp=./seccomp-exec.json \
  --memory 512m --memory-swap 512m --pids-limit 128 --cpus 1 \
  --ulimit nofile=256 \
  --timeout 30 \
  -v "$SCRATCH:/work:rw,Z" \
  python:3.12-slim python /work/run.py
```

**seccomp profile (deny-list the dangerous syscalls):**

```json
{
  "defaultAction": "SCMP_ACT_ALLOW",
  "architectures": ["SCMP_ARCH_X86_64"],
  "syscalls": [
    {"names": ["clone3"], "action": "SCMP_ACT_ERRNO"},
    {"names": ["mount", "umount2", "pivot_root", "chroot"], "action": "SCMP_ACT_ERRNO"},
    {"names": ["ptrace", "process_vm_readv", "process_vm_writev"], "action": "SCMP_ACT_ERRNO"},
    {"names": ["reboot", "kexec_load", "init_module", "delete_module"], "action": "SCMP_ACT_ERRNO"},
    {"names": ["setns", "unshare"], "action": "SCMP_ACT_ERRNO"},
    {"names": ["bpf"], "action": "SCMP_ACT_ERRNO"}
  ]
}
```

**gVisor runtime for stronger isolation:**

```bash
# install runsc, then run with the gVisor runtime
sudo podman run --rm --runtime=runsc --network=none --read-only \
  --user 1000:1000 --cap-drop=ALL python:3.12-slim python -c "import os; print(os.uname())"
```

**Egress allowlist with nftables (default drop):**

```nft
table inet egress {
  set allowed_v4 { type ipv4_addr; flags interval; elements = { 151.101.0.0/16 } }
  chain output {
    type filter hook output priority 0; policy drop;
    oif lo accept
    ct state established,related accept
    ip daddr @allowed_v4 tcp dport 443 accept
    ip daddr 169.254.169.254 drop
    ip daddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 } drop
    counter log prefix "egress-deny: " drop
  }
}
```

**Per-execution resource wrapper (Python control plane):**

```python
import subprocess, uuid, shutil, pathlib, json

def run_untrusted(code: str, timeout_s: int = 30) -> dict:
    job = uuid.uuid4().hex
    workdir = pathlib.Path(f"/srv/sandbox/{job}")
    workdir.mkdir(parents=True, mode=0o700)
    (workdir / "run.py").write_text(code, encoding="utf-8")

    cmd = [
        "podman", "run", "--rm", "--network=none", "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "--user", "1000:1000", "--cap-drop=ALL",
        "--security-opt", "no-new-privileges",
        "--security-opt", "seccomp=/etc/seccomp/seccomp-exec.json",
        "--memory", "512m", "--pids-limit", "128", "--cpus", "1",
        "--ulimit", "nofile=256", "--ulimit", "fsize=10485760",
        "-v", f"{workdir}:/work:rw,Z",
        "python:3.12-slim", "python", "-I", "-B", "/work/run.py",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        return {"ok": proc.returncode == 0, "exit_code": proc.returncode,
                "stdout": proc.stdout[-8000:], "stderr": proc.stderr[-4000:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    finally:
        subprocess.run(["podman", "rm", "-f", f"sandbox-{job}"], check=False)
        shutil.rmtree(workdir, ignore_errors=True)
```

**Output validation before host use:**

```python
import json, pathlib
from pydantic import BaseModel, ValidationError

class PlotSpec(BaseModel):
    kind: str
    series: list[float]

def consume_artifact(path: str) -> dict:
    p = pathlib.Path(path).resolve()
    assert p.is_file() and p.stat().st_size < 5_000_000, "artifact too large"
    data = json.loads(p.read_text(encoding="utf-8"))
    return PlotSpec.model_validate(data).model_dump()
```

**Anomaly detection on execution (Falco-style rule intent):**

```text
Alert when, inside a sandbox:
  - a process other than the allowlisted interpreter is executed
  - an outbound connection is attempted to a non-allowlisted address
  - /proc/self/environ is read for credentials
  - the scratch volume write rate exceeds N MB/s
  - >50 processes are spawned within 5 s
```

## 8. Quality Standards

- Default-deny egress; allowlist is explicit and reviewed.
- No credentials, host mounts, or docker socket in the sandbox.
- Non-root, dropped capabilities, seccomp, and resource limits on every execution.
- Sandboxes are ephemeral and never reused across users.
- Timeouts and output size caps are enforced by the control plane, not the sandboxed code.
- All executions are logged with enough detail to attribute and replay.
- Containment is verified by an adversarial test suite, not assumed.

## 9. Verification and Testing

```bash
# Inside the sandbox, these must all fail
podman run --rm --network=none --read-only --user 1000:1000 python:3.12-slim \
  python -c "import socket; socket.create_connection(('1.1.1.1',443), timeout=3)"   # expect failure
podman run --rm --network=none python:3.12-slim \
  python -c "open('/etc/shadow').read()"                                            # expect permission denied
# Resource limits
podman run --rm --memory 128m --pids-limit 32 python:3.12-slim \
  python -c "x = bytearray(512*1024*1024)"                                          # expect MemoryError
```

Test suite: file read escape, network egress, metadata endpoint access, fork bomb, disk fill, long-running CPU loop, and an attempt to read env vars for secrets. All must be blocked or contained, with evidence in logs.

## 10. Security Considerations

- **Prompt injection → code execution** is the headline risk. Treat all generated code as untrusted regardless of the model's confidence.
- Metadata endpoints (169.254.169.254, fd00:ec2::254) are a common credential-theft path; block them explicitly.
- DNS exfiltration is possible even with TCP blocked; constrain resolvers and log queries.
- Containers share the kernel: for hostile code, use a microVM or gVisor.
- Never run the sandbox with the host's package manager privileges or on a host with broad IAM roles.
- Secrets, if truly required, should be injected per call with shortest TTL and scoped to the specific operation.
- Persistent sandboxes accumulate attack surface (installed tools, caches); destroy on session end.
- Log and alert on repeated escape attempts: they indicate either a bug or an active attacker.

## 11. Failure Handling

- **Sandbox won't start:** check runtime availability and cgroup limits; fail closed rather than falling back to an unsandboxed run.
- **Legitimate workload blocked:** widen the allowlist narrowly (specific host/port), never disable egress controls.
- **Resource exhaustion on the host:** enforce per-sandbox cgroups and a global concurrency cap.
- **Package installs required:** use a mirrored registry with pinned packages and no arbitrary index URLs; snapshot the environment instead of installing at runtime.
- **Suspicious activity detected:** kill the sandbox, preserve logs, rotate any credentials reachable from the control plane, and open an incident.

## 12. Expected Deliverables

1. Isolation model and runtime selection rationale.
2. Sandbox launch configuration (all security flags).
3. Egress policy with allowlist.
4. Resource limits and timeouts.
5. Output validation code.
6. Execution audit log schema.
7. Adversarial containment test results.
8. Incident procedure for a suspected escape.

## 13. References

- gVisor documentation — https://gvisor.dev/docs/
- Firecracker — https://firecracker-microvm.github.io/
- OCI runtime `seccomp` — https://github.com/opencontainers/runtime-spec/blob/main/config-linux.md
- NIST SP 800-190 (container security) — https://csrc.nist.gov/pubs/sp/800/190/final
- OWASP LLM Top 10 — https://owasp.org/www-project-top-10-for-large-language-model-applications/
- Falco — https://falco.org/docs/
- Kubernetes Pod Security Standards — https://kubernetes.io/docs/concepts/security/pod-security-standards/
- CISA/NIST, "Zero Trust Architecture" SP 800-207 — https://csrc.nist.gov/pubs/sp/800/207/final
