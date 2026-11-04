---
name: linux-system-troubleshooting
description: Diagnose a misbehaving Linux host systematically—boot failures, resource exhaustion, service failures, filesystem errors—using evidence before intervention.
metadata:
  domain: devops-and-linux
  version: 1.0.0
  risk: medium
---

# Linux System Troubleshooting

## 1. Purpose

Find the cause of a broken or degraded Linux host without guessing or rebooting away the evidence. This skill provides an ordered diagnostic procedure covering boot problems, unresponsive systems, disk exhaustion, memory pressure, service failures, and filesystem errors, with the exact commands and what each output means.

**Scope:** hosts you administer. Destructive recovery steps (fsck with repair, reboot, killing processes) require confirmation from the owner, and this skill prefers read-only diagnosis first.

## 2. Activation Conditions

- Host is unresponsive, slow, or rebooting unexpectedly.
- Service fails to start or keeps restarting.
- "No space left on device", "read-only file system", "out of memory".
- Boot stops at a prompt or emergency mode.
- Keywords: troubleshooting, server down, kernel panic, OOM, disk full, inode full, fsck, boot failure, unresponsive, hung.

## 3. When Not to Use

- Application-level bugs (use systematic-debugging).
- Container-specific issues where the host is healthy (use docker/podman skills).
- Performance tuning with no fault (use linux-performance-analysis).
- Security incident triage (use incident-response; preserve evidence first).

## 4. Required Context

1. What changed recently: kernel update, package upgrade, config change, deploy.
2. Symptoms: start time, frequency, reproduction, error messages seen.
3. Access: SSH, console, cloud serial console, IPMI.
4. Distribution and kernel version, bootloader (GRUB/systemd-boot), filesystem types (ext4, btrfs, xfs, zfs).
5. Whether the host is production and whether a reboot is permitted.

## 5. Operating Procedure

1. **Establish access and state.** Can you log in? If not, use console/serial. Check uptime and last boot reason (`last reboot`, `journalctl --list-boots`).
2. **Read the logs before doing anything**: `journalctl -b -1 -p err`, `journalctl -b -p warning`, `dmesg -T | tail -100`.
3. **Check the big four resources**: disk (`df -h`, `df -i`), memory (`free -m`, `/proc/meminfo`, OOM killer messages), CPU/load (`uptime`, `top`, `mpstat`), and process count (`ps -eLf | wc -l`, PIDs limit).
4. **Identify the failing unit**: `systemctl --failed`, `systemctl status <unit> -l --no-pager`, unit logs with `journalctl -u <unit> -n 100`.
5. **Filesystem health**: read-only remount usually follows an I/O error—find it in `dmesg` (`I/O error`, `EXT4-fs error`, `BTRFS error`, `XFS`). Check `mount | grep ' ro,'`.
6. **Boot failures**: boot to rescue/emergency target with `systemd.unit=rescue.target` or `emergency.target`; check `fstab` errors, missing LUKS unlock, broken initramfs.
7. **Network/services dependency order**: `systemctl list-dependencies --failed`, check time sync, DNS, and mount ordering.
8. **Form a hypothesis and test it non-destructively** (e.g. restart a single unit, raise a limit, free space) before full remediation.
9. **Remediate with a change record**; verify with the same commands used to diagnose.
10. **Post-incident**: capture a summary, add monitoring/alerting for the symptom class.

## 6. Tools and Technologies

| Area | Commands |
|---|---|
| Logs | `journalctl`, `dmesg`, `/var/log/syslog`, `last`, `who` |
| Boot | GRUB/systemd-boot entries, `systemd.unit=rescue.target`, `rd.break` (RHEL) |
| Disk | `df -h`, `df -i`, `du -xhd1`, `ncdu`, `lsof +L1`, `find / -xdev -size +1G` |
| Memory | `free`, `vmstat`, `smem`, `/proc/pressure/memory` |
| CPU/load | `uptime`, `top`, `mpstat`, `pidstat`, `vmstat` |
| Processes | `ps`, `pgrep`, `pstree`, `lsof`, `strace`, `gdb` |
| Services | `systemctl`, `journalctl -u`, `systemd-analyze` |
| Filesystem | `fsck`, `smartctl`, `btrfs scrub`, `xfs_repair`, `dmesg` |
| Kernel | `modprobe`, `lsmod`, `sysctl`, `ulimit` |

## 7. Practical Implementation

**Triage one-liners:**

```bash
uptime; echo ---; free -m; echo ---; df -h -x tmpfs -x devtmpfs; echo ---; systemctl --failed
```

**Find what filled the disk (deleted-but-open files are the classic gotcha):**

```bash
df -h /
sudo du -xhd1 / 2>/dev/null | sort -rh | head -15
sudo lsof +L1 | awk '{print $1, $2, $7, $9}' | sort -k3 -rn | head
# If a deleted file is still held open by a process, restart that process to reclaim space.
```

**Inode exhaustion (disk shows free space but writes fail):**

```bash
df -i /
sudo find /var -xdev -type d -printf '%p\n' -exec sh -c 'echo "$(ls -A "$1" | wc -l) $1"' _ {} \; 2>/dev/null | sort -rn | head
```

**OOM investigation:**

```bash
sudo journalctl -k | grep -i -E 'out of memory|oom-kill|killed process'
cat /proc/pressure/memory
sudo systemd-cgtop --order=memory -b -n 1 | head -15
```

**Service keeps restarting:**

```bash
systemctl status myapp --no-pager -l
journalctl -u myapp -n 200 --no-pager
systemctl show myapp -p Restart -p RestartUSec -p ExecMainStatus -p NRestarts
systemd-analyze verify /etc/systemd/system/myapp.service
```

**Filesystem errors and read-only remount:**

```bash
dmesg -T | grep -i -E 'I/O error|EXT4-fs error|BTRFS|XFS|read-only'
mount | grep ' ro,'
# Diagnose before repairing. Repair only with the FS unmounted and a backup taken:
sudo smartctl -a /dev/nvme0n1 | head -30      # is the disk failing?
sudo umount /data && sudo fsck -f /dev/nvme0n1p3   # ext4; xfs_repair or btrfs check differ
```

**Boot to rescue (GRUB):** at the GRUB menu press `e`, append to the `linux` line:

```
systemd.unit=rescue.target
```

then `Ctrl-X` to boot. For emergency (no services): `systemd.unit=emergency.target`.

**Hung process diagnosis:**

```bash
ps -eo pid,ppid,stat,wchan:32,cmd --sort=-%cpu | head -20
sudo cat /proc/<pid>/stack        # kernel stack (if permitted)
sudo strace -p <pid> -f -tt -T    # what syscall is it stuck in
sudo gdb -p <pid> -batch -ex 'thread apply all bt'   # userspace stacks
```

**Boot time analysis:**

```bash
systemd-analyze
systemd-analyze blame | head -20
systemd-analyze critical-chain
```

## 8. Quality Standards

- Diagnosis precedes remediation; no "try rebooting" without capturing evidence.
- Every finding is backed by a command output or log line.
- Root cause is distinguished from symptom (disk full is a symptom; log rotation misconfiguration is a cause).
- Remediation is minimal and reversible; changes are recorded.
- Monitoring is added for the symptom class to prevent silent recurrence.
- Production changes get approval and a rollback note.

## 9. Verification and Testing

- Re-run the diagnostic commands and confirm the abnormal condition is gone.
- For a service, verify `systemctl is-active`, a real request, and clean logs for 10+ minutes.
- For disk, confirm `df` and `df -i` are below 80% and that writes succeed (`fallocate -l 100M /var/tmp/probe`).
- For boot, perform a controlled reboot in a window and verify all units reach `active`.
- Evidence: before/after command output captured in the ticket.

## 10. Security Considerations

- Logs may contain secrets and PII; redact before attaching to tickets.
- Do not disable SELinux/AppArmor or firewalls to "fix" a symptom; find the denial (`ausearch -m avc`).
- Root shell sessions should be logged; never use `chmod 777` as a fix—use correct ownership/groups.
- Recovery boot (`init=/bin/bash`) bypasses authentication: use console access only, and reboot afterwards.
- Preserve evidence if a compromise is suspected—do not wipe logs.
- Validate any command copied from the internet or a model output before running it, especially with `rm`, `dd`, or `mkfs`.

## 11. Failure Handling

- **No console access and network down:** use the provider's serial console or rescue VM; if unavailable, escalate to physical/hosting support.
- **fsck cannot repair:** restore from backup; check SMART data and replace the disk before re-imaging.
- **OOM persists after adding memory:** find the leak (memory-optimization) or add a container memory limit and restart policy; do not just increase swap.
- **Service fails only under load:** check `ulimit -n` (file descriptors), connection backlog (`ss -lnt` Send-Q), and dependency latency.
- **Boot loop after upgrade:** boot the previous kernel from GRUB, then bisect the change; pin the working kernel until fixed.

## 12. Expected Deliverables

1. Symptom statement with timeline.
2. Evidence set (command outputs, log excerpts).
3. Root-cause hypothesis and confirmation.
4. Applied remediation with change record.
5. Verification output.
6. Monitoring/prevention recommendation.

## 13. References

- `journalctl(1)` — https://www.freedesktop.org/software/systemd/man/latest/journalctl.html
- `systemd.special(7)` rescue/emergency targets — https://www.freedesktop.org/software/systemd/man/latest/systemd.special.html
- Arch Wiki — General troubleshooting — https://wiki.archlinux.org/title/General_troubleshooting
- Ubuntu Server Guide — https://documentation.ubuntu.com/server/
- `proc(5)` — https://man7.org/linux/man-pages/man5/proc.5.html
- kernel.org documentation — https://docs.kernel.org/
