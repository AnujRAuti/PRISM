---
name: linux-performance-analysis
description: System-level performance analysis with the USE method—CPU, memory, disk, network, and scheduler—using perf, bpftrace, and cgroup evidence to locate bottlenecks.
metadata:
  domain: devops-and-linux
  version: 1.0.0
  risk: medium
---

# Linux Performance Analysis

## 1. Purpose

Locate the kernel/hardware-level cause of poor performance using a disciplined method instead of a grab bag of commands. This skill applies the USE method (Utilization, Saturation, Errors) to each resource, uses `perf` and eBPF tooling for deep analysis, and interprets counters correctly (steal time, iowait, runqueue, PSI). It complements application profiling (performance-optimization) by covering the platform beneath the app.

**Scope:** hosts you administer. `perf` and eBPF require privileges; tracing production has overhead—measure and bound it, and get approval.

## 2. Activation Conditions

- CPU, disk, network, or memory is suspected as the bottleneck but not proven.
- Latency spikes with no application-level explanation.
- Container CPU throttling or I/O contention.
- Kernel tuning decisions (I/O scheduler, network stack) must be justified.
- Keywords: perf, bpftrace, iowait, steal time, runqueue, USE method, flame graph, off-CPU, disk latency, PSI, kernel tuning.

## 3. When Not to Use

- Pure application CPU profiling (use performance-optimization with `py-spy`, `pprof`, etc.).
- Capacity planning without measurements.
- Systems where tracing overhead is unacceptable and no maintenance window exists.

## 4. Required Context

1. Hardware: CPU model/cores, memory, storage type (NVMe vs. network-attached), NIC speed.
2. Virtualization: bare metal, VM (steal time), container (cgroup limits).
3. The workload and expected performance envelope.
4. Whether `perf_event_paranoid` allows profiling (`cat /proc/sys/kernel/perf_event_paranoid`).
5. Baseline metrics from normal operation.

## 5. Operating Procedure

1. **Start with the USE checklist per resource**, using cheap counters first.
2. **CPU**: utilization (`mpstat -P ALL 1`), saturation (runqueue `vmstat r`, PSI `cat /proc/pressure/cpu`), errors (MCE, throttling `dmesg | grep -i thermal`).
3. **Memory**: utilization (`free -h`, `vmstat`), saturation (swap in/out `si/so`, PSI memory), errors (ECC via `edac-util`).
4. **Disk**: utilization (`iostat -xz 1` `%util`), saturation (`aqu-sz`, `await`), errors (`dmesg`, `smartctl -a`).
5. **Network**: utilization (`sar -n DEV 1` or `ip -s link`), saturation (drops/overruns, `tc -s qdisc` backlog), errors (`rx/tx errors`, retransmits `nstat -az | grep -i retrans`).
6. **Interpret `iowait` carefully**: it counts idle-with-outstanding-I/O; high iowait with low application I/O can indicate a slow storage path, not CPU starvation.
7. **Check virtualization steal**: `mpstat` `%steal` > 0 means the hypervisor is oversubscribed—no kernel tuning will fix it.
8. **Profile CPU** with `perf stat` (IPC, cache misses) and `perf record -g` → flame graph when utilization is high.
9. **Profile off-CPU time** with `offcputime` (bcc) when threads are blocked.
10. **Test hypotheses with bounded experiments**: drop caches? change scheduler? add a cgroup limit? Measure after each change, one at a time.
11. **Document** the bottleneck, evidence, change, and result; revert experiments that do not help.

## 6. Tools and Technologies

| Area | Tools |
|---|---|
| Overview | `vmstat`, `mpstat`, `iostat`, `sar`, `pidstat`, `atop` |
| Pressure | `/proc/pressure/*` (PSI), `systemd-cgtop` |
| CPU profiling | `perf stat`, `perf record`, `perf report`, `perf top`, FlameGraph |
| eBPF | `bcc` tools (`biolatency`, `offcputime`, `execsnoop`, `tcplife`), `bpftrace` |
| Disk | `iostat -xz`, `blktrace`, `biolatency`, `fio` (benchmark) |
| Network | `sar -n`, `nstat`, `ss -i`, `iperf3`, `tc -s` |
| Memory | `vmstat`, `slabtop`, `numastat` |
| Tunables | `sysctl`, `tuned`, `cgroup v2` files |

## 7. Practical Implementation

**60-second triage (adapted from Brendan Gregg's methodology):**

```bash
uptime
dmesg -T | tail -20
vmstat 1 5
mpstat -P ALL 1 3
pidstat -u -r -d 1 3
iostat -xz 1 2
free -m
sar -n DEV 1 3
sar -n TCP,ETCP 1 3
top -b -n1 | head -20
```

**CPU saturation and steal:**

```bash
cat /proc/pressure/cpu
mpstat -P ALL 1 2 | awk '/Average/ && $NF+0 >= 0'
# %steal > 1% sustained => hypervisor contention: resize the VM, do not tune the guest.
# %system unusually high with low throughput => syscall/scheduler overhead: perf stat.
```

**perf CPU analysis:**

```bash
perf stat -a sleep 5                 # IPC, cycles, cache misses, context switches
perf stat -p "$(pgrep -f orders-api | head -1)" -e cycles,instructions,cache-misses -I 1000 sleep 5

perf record -F 99 -g --call-graph dwarf -p "$(pgrep -f orders-api | head -1)" -- sleep 30
perf report --stdio --percent-limit 1 | head -40
# Flame graph
perf script | stackcollapse-perf.pl | flamegraph.pl > perf.svg
```

**Off-CPU analysis (where threads block):**

```bash
# bcc
sudo offcputime-bpfcc -p "$(pgrep -f orders-api | head -1)" 10 > offcpu.txt
# bpftrace one-liner: blocked time by kernel stack
sudo bpftrace -e '
  tracepoint:sched:sched_switch /args->prev_state == 2/ {
    @[kstack] = sum(nsecs - @start[tid]);
  }
  tracepoint:sched:sched_switch { @start[args->next_pid] = nsecs; }
' 
```

**Disk latency distribution (not just averages):**

```bash
sudo biolatency-bpfcc 10 1
iostat -xz 1 3          # r_await/w_await, aqu-sz, %util per device
```

**Network drops and retransmits:**

```bash
ip -s link show dev eth0 | sed -n '4,6p'
nstat -az | grep -Ei 'retrans|drops|listenoverflows'
ss -tin state established | head -20        # per-socket retransmits and rtt
```

**cgroup throttling check (container):**

```bash
CG=/sys/fs/cgroup/system.slice/orders-api.service
awk '{print FILENAME": "$0}' "$CG/cpu.stat" "$CG/memory.events" "$CG/io.stat" 2>/dev/null | head -20
```

**Bounded benchmark with fio (do not run on production disks without approval):**

```bash
fio --name=randread --rw=randread --bs=4k --iodepth=32 --numjobs=4 \
    --size=1G --runtime=30 --time_based --group_reporting --filename=/tmp/fio.test
```

**Tuning example (verify the default first):**

```bash
cat /sys/block/nvme0n1/queue/scheduler        # e.g. [none] mq-deadline kyber bfq
systemctl cat tuned 2>/dev/null || true
sysctl net.core.somaxconn vm.swappiness
```

## 8. Quality Standards

- Bottleneck identified with a resource, a metric, and a value (e.g. "NVMe `w_await` 42 ms at 100% util").
- USE method applied to all five resources before concluding.
- Virtualization effects (steal, noisy neighbors) checked before kernel tuning.
- One change at a time; each measured with the same workload.
- Tracing overhead estimated and bounded (duration, filters).
- Every tuning change is persisted and documented with a rollback.
- Averages never used alone; distributions (p95/p99, histograms) support conclusions.

## 9. Verification and Testing

- Re-run the same triage commands after tuning and compare the specific metric.
- Assert application-level improvement (p95 latency, throughput) with the same workload.
- Confirm no new errors appeared (`dmesg`, `nstat`, `systemctl --failed`).
- Repeat measurement at least 3 times and report variance.
- Evidence: `perf stat` before/after, flame graphs, iostat deltas, PSI readings.

## 10. Security Considerations

- `perf` and BPF expose kernel memory potentially containing secrets: restrict to root, delete artifacts after analysis.
- `perf_event_paranoid` lowered for observability increases the attack surface—prefer targeted use over a permanent global change.
- `strace`/`gdb` on production processes can stall them; use short, filtered sessions.
- Do not run benchmarks (fio, stress-ng) on production without approval and without free-space checks.
- Tracing tools themselves can be abused for data exfiltration—restrict installation and use.
- Some tuning (`vm.swappiness=0`, disabling THP) has security/stability implications; justify and document.

## 11. Failure Handling

- **High load but low CPU and no I/O:** look for D-state processes and lock contention; check off-CPU time.
- **`perf` reports `<not counted>` or permission errors:** `perf_event_paranoid` too high; change temporarily with a documented revert, or use `--no-inherit` with narrower scope.
- **iostat shows low %util but high latency:** queue depth too low to saturate, or a network-attached device whose latency is on the path—check `aqu-sz` and the storage network.
- **Flame graph dominated by unknown frames:** missing debug symbols—install debuginfo packages for the kernel/app.
- **Benchmark results not reproducible:** pin CPU (`taskset`), disable turbo/frequency scaling for the test window, and control the page cache (`O_DIRECT`).
- **Tuning did not help:** revert it; the bottleneck is elsewhere. Keep a log of ruled-out hypotheses.

## 12. Expected Deliverables

1. Triage transcript with timestamps.
2. USE table per resource with values and verdicts.
3. Profiling artifacts (perf report, flame graphs, latency histograms).
4. Bottleneck statement with evidence.
5. Applied tunings with before/after measurements.
6. Revert instructions and monitoring recommendations.

## 13. References

- Brendan Gregg, *Systems Performance*, 2nd ed. — https://www.brendangregg.com/systems-performance-2nd-edition-book.html
- Brendan Gregg, "Linux Performance" tool map — https://www.brendangregg.com/linuxperf.html
- PSI documentation — https://docs.kernel.org/accounting/psi.html
- `perf` wiki — https://perf.wiki.kernel.org/
- bcc tools — https://github.com/iovisor/bcc
- bpftrace — https://bpftrace.org/
- `iostat(1)` / sysstat — https://github.com/sysstat/sysstat
- Cgroup v2 — https://docs.kernel.org/admin-guide/cgroup-v2.html
