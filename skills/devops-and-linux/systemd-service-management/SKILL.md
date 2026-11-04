---
name: systemd-service-management
description: Author, harden, debug, and operate systemd units—services, timers, sockets, sandboxing directives, dependency ordering, and journal integration.
metadata:
  domain: devops-and-linux
  version: 1.0.0
  risk: medium
---

# systemd Service Management

## 1. Purpose

Run long-lived processes and scheduled jobs correctly under systemd. This skill covers unit authoring (service, timer, socket, path units), restart and dependency semantics, resource controls, sandboxing, logging, and debugging failed units. Most poorly written units fail in predictable ways—wrong `Type`, missing `ExecStart` path resolution, no restart policy, or running as root unnecessarily—and this skill encodes the correct patterns.

**Scope:** hosts you administer. Installing system units requires root; prefer user units (`--user`) for unprivileged services.

## 2. Activation Conditions

- Deploying a daemon or app server on a Linux host.
- Replacing cron jobs with systemd timers.
- A unit fails, restarts in a loop, or does not start at boot.
- Hardening an existing service (sandboxing, resource limits).
- Keywords: systemd, unit file, service, timer, socket activation, journalctl, ExecStart, hardening, Restart=, drop-in.

## 3. When Not to Use

- Container-orchestrated workloads (Kubernetes manages lifecycle; use the container skills).
- Hosts using OpenRC/runit/s6 instead of systemd.
- Application-level supervision inside a container's PID 1 (use `tini`/`dumb-init` or the app's own supervisor).

## 4. Required Context

1. Distribution and systemd version (`systemctl --version`) — directive availability varies.
2. The command to run, working directory, environment variables, and user to run as.
3. Whether the process forks, stays in foreground, or is socket-activated.
4. Dependencies: network, mounts, other services, database readiness.
5. Log destination expectations (journal, file, syslog).

## 5. Operating Procedure

1. **Choose the unit type**: `Type=simple` (foreground, default and preferred), `notify` (sd_notify support), `oneshot` (jobs), `forking` (legacy daemons only).
2. **Create a dedicated system user** for the service when possible: `useradd --system --no-create-home --shell /usr/sbin/nologin appsvc`.
3. **Write the unit** in `/etc/systemd/system/<name>.service`; use drop-ins in `*.service.d/*.conf` for overrides rather than editing vendor units.
4. **Set `ExecStart` with an absolute path** and explicit arguments; no shell pipelines (use `ExecStart=/bin/sh -c '...'` only when unavoidable and documented).
5. **Declare ordering and requirements** correctly: `After=` for ordering, `Requires=`/`Wants=` for dependency strength. `network.target` is not "network is up" — use `network-online.target` with the appropriate wait-online service.
6. **Add supervision**: `Restart=on-failure`, `RestartSec=`, `StartLimitIntervalSec`/`StartLimitBurst` to prevent crash loops.
7. **Apply resource limits**: `MemoryMax`, `CPUQuota`, `TasksMax`, `LimitNOFILE`.
8. **Harden**: `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`, `PrivateDevices`, `ReadWritePaths`, `RestrictAddressFamilies`, `SystemCallFilter=@system-service`, `CapabilityBoundingSet`.
9. **Configure logging**: journal by default; add `StandardOutput=journal` and structured fields if needed; set rotation via `journald.conf`.
10. **For scheduled jobs, write a `.timer`** with `OnCalendar=` and `Persistent=true`; enable the timer, not the service.
11. **Reload and validate**: `systemctl daemon-reload`, `systemd-analyze verify`, `systemctl enable --now`.
12. **Check the result**: `systemctl status`, `journalctl -u`, and `systemd-analyze security` score.

## 6. Tools and Technologies

| Purpose | Commands |
|---|---|
| Lifecycle | `systemctl start/stop/restart/reload/enable/disable/mask` |
| Inspection | `systemctl status`, `systemctl cat`, `systemctl show -p`, `systemctl list-units --failed` |
| Logs | `journalctl -u`, `-f`, `--since`, `-o json-pretty` |
| Validation | `systemd-analyze verify`, `systemd-analyze security`, `systemd-analyze blame` |
| Timers | `systemctl list-timers`, `OnCalendar` expressions |
| Sandboxing | `systemd.exec(5)` directives, `systemd-analyze security --offline` |
| User units | `systemctl --user`, `loginctl enable-linger` |

## 7. Practical Implementation

**Production-grade service unit (`/etc/systemd/system/orders-api.service`):**

```ini
[Unit]
Description=Orders API
Documentation=https://github.com/example/orders
After=network-online.target postgresql.service
Wants=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=notify
User=appsvc
Group=appsvc
WorkingDirectory=/opt/orders
EnvironmentFile=/etc/orders/env
Environment=RUST_LOG=info
ExecStart=/opt/orders/bin/orders-api --config /etc/orders/config.toml
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=3
TimeoutStopSec=20
KillSignal=SIGTERM

# Resource controls
MemoryMax=1G
CPUQuota=150%
TasksMax=512
LimitNOFILE=65536

# Sandboxing
NoNewPrivileges=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
RestrictRealtime=yes
LockPersonality=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
SystemCallFilter=@system-service
SystemCallErrorNumber=EPERM
CapabilityBoundingSet=
AmbientCapabilities=
ReadWritePaths=/var/lib/orders /var/log/orders

[Install]
WantedBy=multi-user.target
```

**Environment file (root-owned, 0600):**

```bash
sudo install -d -m 0750 -o root -g appsvc /etc/orders
sudo install -m 0640 -o root -g appsvc /dev/null /etc/orders/env
# /etc/orders/env
# DATABASE_URL=postgresql://orders:${DB_PASS}@127.0.0.1:5432/orders
# NEVER commit this file; do not use quotes for systemd EnvironmentFile values.
```

**Timer replacing a cron job (`backup.timer` + `backup.service`):**

```ini
# /etc/systemd/system/backup.service
[Unit]
Description=Nightly database backup

[Service]
Type=oneshot
User=postgres
ExecStart=/usr/local/bin/pg-backup.sh
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
```

```ini
# /etc/systemd/system/backup.timer
[Unit]
Description=Run backup nightly at 02:15 with jitter

[Timer]
OnCalendar=*-*-* 02:15:00
RandomizedDelaySec=300
Persistent=true
AccuracySec=1min

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now backup.timer
systemctl list-timers --all | grep backup
```

**Socket activation (on-demand service):**

```ini
# app.socket
[Socket]
ListenStream=/run/app/app.sock
SocketMode=0660
SocketUser=appsvc
SocketGroup=appsvc

[Install]
WantedBy=sockets.target
```

**Drop-in override (do not edit vendor units):**

```bash
sudo systemctl edit nginx.service
# creates /etc/systemd/system/nginx.service.d/override.conf
```

```ini
[Service]
LimitNOFILE=65536
```

**Debugging a failing unit:**

```bash
systemctl status orders-api --no-pager -l
journalctl -u orders-api -n 100 --no-pager -o short-precise
systemd-analyze verify /etc/systemd/system/orders-api.service
systemctl show orders-api -p ExecMainStatus -p Result -p NRestarts -p ActiveState
sudo systemd-analyze security orders-api
```

**Running ad-hoc with the exact unit environment:**

```bash
sudo systemd-run --unit=orders-debug --uid=appsvc --working-directory=/opt/orders \
  --property=EnvironmentFile=/etc/orders/env /opt/orders/bin/orders-api --check-config
```

## 8. Quality Standards

- `Type=simple` or `notify` used; `forking` only for legacy software.
- Absolute paths in `ExecStart`; no shell unless required.
- `Restart=on-failure` with sane `RestartSec` and start limits.
- Services run as a dedicated unprivileged user; `CapabilityBoundingSet=` empty unless needed.
- `systemd-analyze security` exposure score ≤ 3.0 for internet-facing services.
- `ProtectSystem=strict` with explicit `ReadWritePaths`.
- Environment files are root-owned, mode 0640, never in git.
- Timers use `Persistent=true` for jobs that must not be skipped.
- Every unit has a `Description` and, where relevant, `Documentation`.

## 9. Verification and Testing

```bash
systemctl start orders-api && systemctl is-active orders-api
systemd-analyze verify /etc/systemd/system/orders-api.service
systemd-analyze security orders-api --no-pager | tail -5
systemctl restart orders-api && journalctl -u orders-api -n 20 --no-pager
systemctl list-timers backup.timer
# reboot test in a window:
sudo systemctl reboot    # verify the unit is active after boot
```

Expected evidence: `active (running)`, no error lines in the first 30 s, security score in range, timer listed with a next-run timestamp, survives reboot.

## 10. Security Considerations

- Never run services as root without necessity; use `User=`, `Group=`, and drop capabilities.
- `EnvironmentFile` values are visible to root and via `systemctl show`; do not store long-lived cloud credentials there—use a credential manager and `LoadCredential=`.
- `ProtectSystem=strict` turns the filesystem read-only except explicit paths—this is the single highest-value hardening directive.
- `PrivateTmp=yes` prevents symlink attacks through shared `/tmp`.
- Do not use `ExecStartPre=/bin/bash -c "curl ... | sh"`; fetched code execution at start is a supply-chain hole.
- Mask units you do not want (`systemctl mask`), do not merely disable.
- Logs in the journal may contain sensitive data; set `SystemMaxUse=` and redact at the application level.

## 11. Failure Handling

- **Unit starts then exits 0 immediately:** `Type=simple` with a daemonizing process; use `forking` or run in foreground.
- **"Unit not found":** run `systemctl daemon-reload`; verify the filename and path.
- **Crash loop hits start limit:** inspect logs, fix the cause, then `systemctl reset-failed <unit>`.
- **`ExecStart` fails with ENOENT:** absolute path wrong or missing dynamic linker; test the binary manually as the service user (`sudo -u appsvc /path/bin`).
- **Sandbox blocks legitimate access:** read the denial in the journal, then add the narrowest `ReadWritePaths=`/`SystemCallFilter` allowance—not `ProtectSystem=no`.
- **Timer never fires:** check `systemctl list-timers --all`, ensure the timer (not the service) is enabled, and validate the `OnCalendar` expression with `systemd-analyze calendar`.

## 12. Expected Deliverables

1. Unit files (service, timer, socket) with comments.
2. Dedicated user creation commands.
3. Environment/credential handling plan.
4. Hardening summary with `systemd-analyze security` score.
5. Verification transcript (status, logs, reboot test).
6. Rollback instructions.

## 13. References

- `systemd.service(5)` — https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html
- `systemd.timer(5)` — https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html
- `systemd.exec(5)` sandboxing — https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html
- `systemd-analyze` man page — https://www.freedesktop.org/software/systemd/man/latest/systemd-analyze.html
- Arch Wiki — systemd — https://wiki.archlinux.org/title/Systemd
- Fedora Docs — systemd hardening — https://docs.fedoraproject.org/en-US/quick-docs/systemd-hardening/
