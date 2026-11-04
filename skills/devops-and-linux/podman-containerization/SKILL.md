---
name: podman-containerization
description: Build and run OCI containers rootless with Podman—daemonless architecture, Quadlet systemd units, pods, and Compose compatibility—especially on Arch/CachyOS.
metadata:
  domain: devops-and-linux
  version: 1.0.0
  risk: medium
---

# Podman Containerization

## 1. Purpose

Use Podman's daemonless, rootless model correctly. Podman runs containers as the invoking user without a root daemon, which improves security posture but changes operations: there is no `docker.sock`, user namespace mapping matters, ports below 1024 need extra configuration, and service management is done with systemd (Quadlet) rather than a restart policy. This skill covers those differences concretely.

**Scope:** your own machines. System-wide (`sudo podman`) changes affect all users; prefer rootless.

## 2. Activation Conditions

- Rootless container workflows, or environments where running a root daemon is prohibited.
- Distros that ship Podman by default (Fedora, RHEL, Arch) including CachyOS.
- Replacing Docker Compose stacks with `podman compose` or Quadlet units.
- Running containers as systemd services without Docker.
- Keywords: podman, rootless, Quadlet, podman-compose, user namespace, subuid, subgid, buildah, skopeo, daemonless.

## 3. When Not to Use

- Environments standardized on Docker Engine APIs and tooling that requires `docker.sock` (though `podman-docker` socket emulation exists, behavior differs).
- Kubernetes-deployed workloads where the orchestrator handles lifecycle.
- When rootless port binding or overlay storage is unavailable and cannot be configured.

## 4. Required Context

1. Podman version (`podman --version`) — Quadlet requires Podman ≥ 4.4; `podman compose` requires ≥ 4.7.
2. `/etc/subuid` and `/etc/subgid` entries for the user (required for rootless).
3. Storage driver and available space (`podman info --format '{{.Store.GraphDriverName}}'`).
4. Whether ports < 1024 must be bound (requires `net.ipv4.ip_unprivileged_port_start` tuning).
5. Whether the workload needs to run at boot without a login session (`loginctl enable-linger`).

## 5. Operating Procedure

1. **Verify rootless prerequisites**: `grep "$USER" /etc/subuid /etc/subgid`, then `podman info` to confirm rootless mode and storage.
2. **Choose the build tool**: `podman build` (Buildah under the hood) for OCI images; `buildah` for scripted, daemonless builds.
3. **Set up the runtime user**: non-root inside the container too; use `--userns=keep-id` for bind-mounted files to keep ownership consistent.
4. **Use podman-compatible Compose** for local multi-service stacks, or Quadlet for production-grade systemd integration.
5. **Enable lingering** for containers that must start at boot and survive logout: `loginctl enable-linger $USER`.
6. **Generate or write Quadlet units** in `~/.config/containers/systemd/` for services; reload and start via systemd.
7. **Handle port binding**: keep ports ≥ 1024, or lower `net.ipv4.ip_unprivileged_port_start` via sysctl, or front with a proxy.
8. **Configure volumes**: named volumes for data; `:Z`/`:z` SELinux labels for bind mounts on enforcing systems.
9. **Logging**: `podman logs`, journald driver for systemd integration (`--log-driver journald`).
10. **Update images** deliberately: `podman auto-update` with `io.containerd.image.name` labels or a scheduled pull/restart.
11. **Verify**: rootless UID mapping, health, restart on failure (via systemd), logs in journal.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Build | `podman build`, `buildah bud`, `buildah from/run/commit` |
| Run | `podman run`, `podman pod` |
| Compose | `podman compose` (wrapper for podman-compose/docker-compose), `podman-compose` |
| systemd | Quadlet (`~/.config/containers/systemd/*.container`), `podman generate systemd` (legacy) |
| Images | `skopeo copy/inspect`, `podman pull`, `podman auto-update` |
| Inspect | `podman inspect`, `podman top`, `podman stats` |
| Rootless | `/etc/subuid`, `/etc/subgid`, `newuidmap`/`newgidmap` |

## 7. Practical Implementation

**Rootless prerequisite check:**

```bash
grep "^${USER}:" /etc/subuid /etc/subgid
podman info --format '{{.Host.Security.Rootless}} {{.Store.GraphDriverName}}'
podman unshare cat /proc/self/uid_map     # shows the UID mapping in the user namespace
```

**Build with Podman (same Dockerfile works):**

```bash
podman build -t localhost/orders-api:1.4.2 -f Dockerfile .
skopeo inspect docker://registry.example.com/orders-api:1.4.2 | jq '.Digest, .Labels'
```

**Run rootless with bind-mount ownership preserved:**

```bash
podman run -d --name orders-api \
  --userns=keep-id \
  --memory 512m --cpus 1.5 --pids-limit 256 \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --cap-drop=ALL --security-opt no-new-privileges \
  -p 8080:8080 \
  -e NODE_ENV=production --env-file ~/.config/orders/api.env \
  -v ~/data/orders:/data:Z \
  localhost/orders-api:1.4.2
```

**Quadlet unit (the modern replacement for `podman generate systemd`):**

```ini
# ~/.config/containers/systemd/orders-api.container
[Unit]
Description=Orders API (rootless)
Wants=network-online.target
After=network-online.target

[Container]
Image=registry.example.com/orders-api:1.4.2
ContainerName=orders-api
PublishPort=8080:8080
Environment=NODE_ENV=production
EnvironmentFile=%h/.config/orders/api.env
Volume=%h/data/orders:/data:Z
UserNS=keep-id
ReadOnly=true
Tmpfs=/tmp:rw,noexec,nosuid,size=64m
DropCapability=ALL
NoNewPrivileges=true
Memory=512m
PidsLimit=256
HealthCmd=/nodejs/bin/node -e "fetch('http://127.0.0.1:8080/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
HealthInterval=30s
HealthRetries=3
AutoUpdate=registry

[Service]
Restart=on-failure
TimeoutStartSec=120

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user start orders-api.service
systemctl --user status orders-api.service
journalctl --user -u orders-api -n 50 --no-pager
loginctl enable-linger "$USER"     # start at boot without login
```

**Pods (group containers sharing a network namespace):**

```bash
podman pod create --name web --publish 8080:80 --publish 5432:5432
podman run -d --pod web --name nginx docker.io/library/nginx:alpine
podman run -d --pod web --name db -e POSTGRES_PASSWORD=dev-only docker.io/library/postgres:16-alpine
podman pod ps && podman pod stats
# Containers in the pod reach each other via 127.0.0.1
```

**Compose compatibility:**

```bash
podman compose up -d          # uses podman-compose or a docker-compose provider
podman compose ps
podman compose down
```

**Auto-update:**

```bash
podman auto-update --dry-run
systemctl --user enable --now podman-auto-update.timer
podman auto-update
```

**Ports below 1024 (rootless):**

```bash
# Option A: keep app on 8080 and reverse-proxy (preferred)
# Option B: allow unprivileged low ports for all users (system-wide change)
sudo sysctl -w net.ipv4.ip_unprivileged_port_start=80
echo 'net.ipv4.ip_unprivileged_port_start=80' | sudo tee /etc/sysctl.d/50-unprivileged-ports.conf
```

**Migrating from Docker CLI:**

```bash
alias docker=podman          # optional, in ~/.config/fish/functions or bashrc
podman system service --time=0 &   # docker.sock-compatible API (if a tool requires it)
```

## 8. Quality Standards

- Containers run rootless unless a documented requirement forces otherwise.
- `loginctl enable-linger` configured for any service that must survive logout/reboot.
- Services defined as Quadlet units, not bare `podman run` in a shell loop.
- Bind mounts carry `:Z` on SELinux-enforcing hosts.
- No privileged containers; capabilities dropped; read-only rootfs where possible.
- Image references use fully qualified names (`registry.example.com/...`) to avoid ambiguous short-name resolution.
- Health checks defined for services that systemd should restart on failure.

## 9. Verification and Testing

```bash
podman info --format '{{.Host.Security.Rootless}}'
podman inspect orders-api --format '{{.HostConfig.User}} {{.HostConfig.ReadonlyRootfs}}'
podman top orders-api user pid comm
systemctl --user is-active orders-api.service
journalctl --user -u orders-api --since "10 min ago" --no-pager | tail -20
podman healthcheck run orders-api; echo "health=$?"
podman auto-update --dry-run
```

Expected evidence: `Rootless=true`, non-root container user, service `active`, healthcheck exit 0, logs in journal, auto-update detecting the pinned digest.

## 10. Security Considerations

- Rootless Podman is a meaningful security improvement, but user namespaces still share the kernel—use separate VMs or gVisor for hostile workloads.
- Never run `podman --privileged`; it disables most isolation.
- Keep the subuid/subgid ranges disjoint from real system UIDs; validate `/etc/subuid` changes.
- Rootless mounts use user-namespace ownership: verify with `podman unshare ls -l` before debugging "permission denied".
- The Podman API socket (`podman system service`) grants container control; bind it to a Unix socket with restricted permissions, never TCP on a public interface.
- Registry credentials live in `~/.config/containers/auth.json`—mode 0600, never committed.
- Quadlet `EnvironmentFile` with secrets: use `%h/.config/...` with 0600 and consider `podman secret` for stronger handling.

## 11. Failure Handling

- **"cannot clone: Operation not permitted" (rootless):** missing subuid/subgid mapping or `/proc/sys/user/max_user_namespaces=0`; verify limits and `podman info`.
- **"permission denied" on bind mount:** ownership mapping—use `--userns=keep-id` or `podman unshare chown -R`.
- **Quadlet unit not found:** file must end in `.container` inside `~/.config/containers/systemd/`; run `systemctl --user daemon-reload` and check `systemctl --user list-unit-files | grep orders`.
- **Service stops at logout:** `loginctl enable-linger $USER` missing.
- **Short-name resolution ambiguity:** set `short-name-mode="enforcing"` in `~/.config/containers/registries.conf` and always use fully qualified names.
- **Compose behavior differences:** `podman compose` may use different providers; check `podman compose version` and prefer Quadlet for production.

## 12. Expected Deliverables

1. Rootless readiness verification output.
2. Build and run commands with security flags.
3. Quadlet unit files for persistent services.
4. Compose compatibility note if used.
5. Verification transcript (rootless, user, health, logs).
6. Migration notes from Docker where applicable.

## 13. References

- Podman documentation — https://docs.podman.io/
- Podman rootless tutorial — https://github.com/containers/podman/blob/main/docs/tutorials/rootless_tutorial.md
- Quadlet — https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html
- podman-compose — https://github.com/containers/podman-compose
- Buildah — https://github.com/containers/buildah
- Skopeo — https://github.com/containers/skopeo
- Arch Wiki — Podman — https://wiki.archlinux.org/title/Podman
