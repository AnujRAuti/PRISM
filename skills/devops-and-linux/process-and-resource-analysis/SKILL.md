---
name: process-and-resource-analysis
description: Analyze processes, cgroups, and host resources—who is consuming CPU, memory, I/O, and file descriptors—and decide whether to tune, limit, or kill.
metadata:
  domain: devops-and-linux
  version: 1.0.0
  risk: medium
---

# Process and Resource Analysis

## 1. Purpose

Answer "what is using the machine?" with evidence. This skill covers process enumeration and attribution, per-process I/O, memory accounting, file descriptor and thread limits, cgroup accounting (containers, systemd slices), and the correct decision procedure for limiting or terminating work. It is the diagnostic layer beneath performance tuning: you cannot optimize a resource you cannot attribute.

**Scope:** hosts you administer. Killing processes on production requires owner approval and an understanding of the supervisor's restart policy.

## 2. Activation Conditions

- High load average with no obvious cause.
- "Too many open files", "cannot allocate memory", "Resource temporarily unavailable".
- A container or service is being OOM-killed or throttled.
- Need to attribute CPU/IO to a specific unit, container, or user.
- Keywords: top, htop, ps, cgroup, lsof, file descriptors, threads, OOM, throttling, CPU steal, load average, resource limits.

## 3. When Not to Use

- Latency analysis of one application (use performance-optimization).
- Memory leak hunting inside a runtime (use memory-optimization).
- Kernel-level profiling of a single hot function (use linux-performance-analysis).

## 4. Required Context

1. Host specs: CPU count, memory, swap, disk type (`lscpu`, `free -h`, `lsblk`).
2. Whether workloads run bare-metal, in VMs (steal time matters), or in containers.
3. The service–process mapping: which units/containers correspond to business services.
4. Current limits: `ulimit -n`, `systemd` `TasksMax`/`MemoryMax`, cgroup v2 files.
5. Change history and known expected baselines (busy hours).

## 5. Operating Procedure

1. **Establish the baseline**: `uptime`, `vmstat 1 5`, `mpstat -P ALL 1 3` — is it CPU, memory, I/O, or blocked processes?
2. **Interpret load average correctly**: it counts runnable + uninterruptible (I/O wait) tasks; on an 8-core box, load 8 is saturated for CPU-bound work but can also mean 8 processes stuck in D-state.
3. **Attribute CPU**: `top -b -n1 -o %CPU | head`, `pidstat -u 1 3`, `ps -eo pid,ppid,user,pcpu,pmem,stat,comm --sort=-pcpu | head -15`.
4. **Attribute memory**: `ps -eo pid,rss,pmem,comm --sort=-rss | head`, `smem -tk`, and per-cgroup `memory.current`. Sum RSS cautiously: shared pages are counted multiple times.
5. **Attribute I/O**: `iotop -oPa`, `pidstat -d 1 3`, `cat /proc/<pid>/io`.
6. **Check descriptor and thread limits**: `ls /proc/<pid>/fd | wc -l`, `cat /proc/<pid>/limits`, `ps -eLf | wc -l`, `cat /proc/sys/kernel/threads-max`.
7. **Check cgroup pressure**: `cat /sys/fs/cgroup/<path>/cpu.stat` (`nr_throttled`, `throttled_usec`), `memory.events` (`oom`, `oom_kill`), `memory.pressure`.
8. **Identify blocked processes**: `ps -eo stat,pid,wchan:30,comm | awk '$1 ~ /D/'`, then inspect `/proc/<pid>/stack`.
9. **Decide**: tune config, apply limits, add capacity, or restart/kill. Prefer limits and supervision over manual kills.
10. **Document and monitor**: add alerting on the metric that failed.

## 6. Tools and Technologies

| Area | Tools |
|---|---|
| Overview | `top`, `htop`, `btop`, `vmstat`, `mpstat`, `uptime` |
| Per-process | `pidstat`, `ps`, `pstree`, `pgrep`, `/proc/<pid>/*` |
| Memory | `smem`, `free`, `/proc/meminfo`, `systemd-cgtop` |
| I/O | `iotop`, `pidstat -d`, `/proc/<pid>/io`, `blktrace` |
| Files/descriptors | `lsof`, `/proc/<pid>/fd`, `fuser` |
| cgroups | `systemd-cgls`, `systemd-cgtop`, `/sys/fs/cgroup/` |
| Containers | `docker stats`, `podman stats`, `crictl stats` |
| Pressure | `/proc/pressure/{cpu,memory,io}` |

## 7. Practical Implementation

**Full triage snapshot:**

```bash
date -u; uptime
lscpu | grep -E '^CPU\(s\)|Model name'
free -h; echo; vmstat 1 3
echo '--- top CPU'; ps -eo pid,ppid,user,pcpu,pmem,stat,etimes,comm --sort=-pcpu | head -12
echo '--- top RSS'; ps -eo pid,rss,pmem,comm --sort=-rss | head -12
echo '--- top IO'; sudo iotop -b -o -n 2 -q | head -20
echo '--- D-state'; ps -eo stat,pid,wchan:28,comm | awk '$1 ~ /^D/'
```

**Load average interpretation:**

```bash
nproc                                    # usable cores (respects cgroup? no — use nproc --all vs cgroup quota)
cat /sys/fs/cgroup/cpu.max               # "200000 100000" => 2 CPUs of quota
uptime
# load 12 on cpu.max=2 CPUs => heavily oversubscribed
```

**Find the file-descriptor hog:**

```bash
sudo lsof -nP -u '*' 2>/dev/null | awk '{print $1}' | sort | uniq -c | sort -rn | head
for p in $(pgrep -u appsvc); do printf '%s %s\n' "$(ls /proc/$p/fd 2>/dev/null | wc -l)" "$p"; done | sort -rn | head
cat /proc/sys/fs/file-nr                  # allocated / free / max
```

**Thread and task limits:**

```bash
cat /proc/$(pgrep -f orders-api | head -1)/limits | grep -Ei 'open files|processes|stack'
systemctl show orders-api -p TasksMax -p LimitNOFILE
cat /sys/fs/cgroup/system.slice/orders-api.service/pids.current
```

**CPU throttling in a container (cgroup v2):**

```bash
cat /sys/fs/cgroup/system.slice/orders-api.service/cpu.stat
# nr_periods / nr_throttled / throttled_usec -> ratio tells you if quota is too tight
awk '/nr_throttled/{t=$2} /nr_periods/{p=$2} END{printf "throttled %.1f%%\n", 100*t/p}' \
  /sys/fs/cgroup/system.slice/orders-api.service/cpu.stat
```

**Memory pressure and OOM evidence:**

```bash
cat /proc/pressure/memory
cat /sys/fs/cgroup/system.slice/orders-api.service/memory.events
sudo journalctl -k --since -2h | grep -iE 'oom|killed process'
systemd-cgtop --order=memory -b -n1 | head -12
```

**Per-process I/O attribution:**

```bash
for p in $(pgrep -d' ' -f 'python|node|postgres'); do
  printf '%6s %-24s rchar=%s wchar=%s\n' "$p" "$(cat /proc/$p/comm 2>/dev/null)" \
    "$(awk '/^rchar/{print $2}' /proc/$p/io 2>/dev/null)" \
    "$(awk '/^wchar/{print $2}' /proc/$p/io 2>/dev/null)"
done
```

**Graceful termination procedure:**

```bash
# 1) Identify precisely
ps -o pid,ppid,stat,etime,cmd -p "$PID"
# 2) Prefer the supervisor
systemctl restart orders-api
# 3) If manual: SIGTERM, wait, then SIGKILL as last resort
kill -TERM "$PID"; for i in $(seq 1 20); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
kill -KILL "$PID" 2>/dev/null || true
```

**Limit examples:**

```bash
# Per-service (systemd)
systemctl set-property orders-api.service MemoryMax=1G CPUQuota=150% TasksMax=512

# Shell/session
ulimit -n 65536
```

## 8. Quality Standards

- Every claim about resource usage is attributed to a PID, unit, or cgroup.
- Load average is interpreted against actual CPU quota, not core count alone.
- RSS vs. PSS/USS distinction is respected when summing memory.
- No process is killed before identifying its supervisor and restart policy.
- Limits are applied at the supervisor level (systemd/cgroup/Kubernetes), not by ad-hoc renice.
- Baselines are recorded so future anomalies are detectable.

## 9. Verification and Testing

```bash
systemd-cgtop -b -n1 --order=cpu | head
cat /sys/fs/cgroup/system.slice/orders-api.service/memory.current
cat /sys/fs/cgroup/system.slice/orders-api.service/memory.max
systemctl show orders-api -p MemoryMax -p CPUQuotaPerSecUSec -p TasksMax
# after tuning:
vmstat 1 5 && uptime
```

Expected evidence: reduced throttling ratio, no OOM events after limit change (or clean OOM at a predictable threshold), load average within quota, and logs showing normal operation.

## 10. Security Considerations

- `/proc/<pid>/environ` and `fd` can expose secrets; restrict access and never print them into tickets.
- `lsof` and `iotop` reveal file paths and network peers; treat output as sensitive in multi-tenant environments.
- Running monitoring tools as root weakens least privilege; grant `CAP_SYS_PTRACE`/`CAP_DAC_READ_SEARCH` narrowly or use an agent with a restricted account.
- Killing a security agent or audit daemon disables detection—never do it as a quick fix.
- `nice`/`renice` on security-critical processes can mask attacks; investigate first.
- Beware of resource-exhaustion DoS: unbounded per-user process limits are an attack vector; enforce `TasksMax` per user/service.

## 11. Failure Handling

- **High load, near-zero CPU:** blocked I/O or D-state processes. Inspect `/proc/<pid>/stack` and storage health (`smartctl`, `dmesg`).
- **Memory numbers do not add up:** check for page cache (normal), shared memory, and huge pages; use `smem -tk` for PSS.
- **OOM kills despite free memory:** cgroup limit, not host limit—check `memory.max` for the unit.
- **FD leak:** confirm growth over time (`watch -n5 'ls /proc/PID/fd | wc -l'`), find the leaked type via `lsof -p PID | awk '{print $5}' | sort | uniq -c`, then fix in code.
- **Cannot kill process (D-state):** it is waiting on I/O; rebooting may be the only option—investigate the storage subsystem first.
- **Container throttled but host idle:** raise `cpu.max` or reduce worker count; check `nr_throttled` trend.

## 12. Expected Deliverables

1. Resource snapshot with timestamps.
2. Attribution table (PID/unit → CPU, RSS, I/O, FDs).
3. Root-cause statement for the anomaly.
4. Applied limits or configuration changes.
5. Verification output after the change.
6. Monitoring recommendation (which metric, threshold, alert).

## 13. References

- `proc(5)` — https://man7.org/linux/man-pages/man5/proc.5.html
- `ps(1)` — https://man7.org/linux/man-pages/man1/ps.1.html
- cgroup v2 documentation — https://docs.kernel.org/admin-guide/cgroup-v2.html
- PSI (pressure stall information) — https://docs.kernel.org/accounting/psi.html
- `systemd.resource-control(5)` — https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html
- Brendan Gregg, *Systems Performance* — https://www.brendangregg.com/systems-performance-2nd-edition-book.html
