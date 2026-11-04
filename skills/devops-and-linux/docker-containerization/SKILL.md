---
name: docker-containerization
description: Build, run, and operate production Docker images and Compose stacks—multi-stage builds, layer caching, healthchecks, logging, resource limits, and safe defaults.
metadata:
  domain: devops-and-linux
  version: 1.0.0
  risk: medium
---

# Docker Containerization

## 1. Purpose

Package an application into a reproducible, small, secure Docker image and run it with correct lifecycle behavior. This skill covers the BuildKit build model, layer cache strategy, multi-stage separation, `.dockerignore`, healthchecks, logging drivers, volume/network management, and Compose orchestration for local and small production deployments. Security hardening specifics live in container-security; here the focus is correct, efficient, operable builds.

**Scope:** images and hosts you own. Publishing images is externally visible—confirm registries and tags before pushing.

## 2. Activation Conditions

- Containerizing an application for the first time.
- Builds are slow, images are 2 GB, or rebuilds invalidate cache constantly.
- Container exits, restarts, or leaks storage.
- Migrating ad-hoc `docker run` commands into Compose.
- Keywords: Dockerfile, docker build, BuildKit, docker compose, multi-stage, layer cache, healthcheck, volumes, docker logs, image size.

## 3. When Not to Use

- Rootless/daemonless or Kubernetes-only constrained environments (use podman-containerization).
- Hardening review of an existing image (use container-security).
- Windows containers (different base images and semantics).

## 4. Required Context

1. Application language, dependency files, and build steps.
2. Runtime requirements: ports, env vars, writable paths, user.
3. Target platform(s): `linux/amd64`, `linux/arm64` — buildx for multi-arch.
4. Registry and tagging convention (semver + git SHA; avoid `latest` in production).
5. Docker/Compose versions (`docker version`, `docker compose version`).

## 5. Operating Procedure

1. **Write `.dockerignore` first** — exclude `.git`, `node_modules`, build output, secrets, test data.
2. **Choose the base image**: official, pinned by digest or minor version, slim/alpine where viable.
3. **Order layers by change frequency**: copy manifests and install dependencies before copying source.
4. **Use multi-stage**: builder compiles/installs, runtime gets only artifacts.
5. **Create and use a non-root user**; set `USER` with a numeric UID.
6. **Declare `EXPOSE`, `ENV`, and `ENTRYPOINT` in exec form** (`["node", "server.js"]`) so signals reach PID 1.
7. **Add `HEALTHCHECK`** or rely on orchestration probes; ensure the app has a cheap liveness endpoint.
8. **Pin dependency installs** (`npm ci`, `pip install -r` with hashes or lockfile, `go mod download` with `go.sum`).
9. **Build with BuildKit** (`DOCKER_BUILDKIT=1` or `docker buildx build`) for cache mounts, secrets, multi-arch.
10. **Tag immutably**: `app:1.4.2`, `app:1.4.2-<git sha>`, and a digest for deploy.
11. **Run with limits**: `--memory`, `--cpus`, `--pids-limit`, restart policy, log driver with size caps.
12. **Compose for multi-service**: healthcheck-based `depends_on`, named volumes, explicit networks.
13. **Verify**: image size, `docker history`, non-root user, health status, log output, restart behavior.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Build | `docker buildx`, BuildKit, `docker build --cache-from` |
| Multi-arch | `buildx create --use`, `--platform linux/amd64,linux/arm64` |
| Lint | `hadolint`, `dockerfilelint` |
| Inspect | `docker history`, `dive`, `docker inspect` |
| Orchestrate (local) | `docker compose` |
| Registry | Docker Hub, GHCR, ECR, GAR, Harbor |
| Debug | `docker exec`, `docker logs`, `docker events`, `docker system df` |

## 7. Practical Implementation

**Node/TypeScript multi-stage Dockerfile:**

```dockerfile
# syntax=docker/dockerfile:1.7
FROM node:22-bookworm-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

FROM deps AS build
COPY tsconfig.json ./
COPY src ./src
RUN npm run build && npm prune --omit=dev

FROM gcr.io/distroless/nodejs22-debian12:nonroot AS runtime
WORKDIR /app
COPY --from=build --chown=65532:65532 /app/node_modules ./node_modules
COPY --from=build --chown=65532:65532 /app/dist ./dist
COPY --chown=65532:65532 package.json ./
ENV NODE_ENV=production PORT=8080
USER 65532:65532
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["/nodejs/bin/node", "-e", "fetch('http://127.0.0.1:8080/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
ENTRYPOINT ["/nodejs/bin/node", "dist/server.js"]
```

**Go multi-stage (static binary, tiny image):**

```dockerfile
# syntax=docker/dockerfile:1.7
FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download
COPY . .
RUN --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/api ./cmd/api

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build --chown=65532:65532 /out/api /api
USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["/api"]
```

**`.dockerignore`:**

```
.git
.gitignore
node_modules
dist
build
coverage
*.log
.env
.env.*
secrets/
tests/
docs/
```

**BuildKit secret mount (never bake credentials):**

```dockerfile
RUN --mount=type=secret,id=npmrc,target=/root/.npmrc npm ci --ignore-scripts
```

```bash
docker buildx build --secret id=npmrc,src="$HOME/.npmrc" -t app:1.4.2 .
```

**Production `docker run`:**

```bash
docker run -d --name orders-api \
  --restart unless-stopped \
  --memory 512m --memory-swap 512m --cpus 1.5 --pids-limit 256 \
  --user 65532:65532 --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --cap-drop=ALL --security-opt no-new-privileges \
  --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 \
  -p 127.0.0.1:8080:8080 \
  -e NODE_ENV=production --env-file /etc/orders/api.env \
  registry.example.com/orders-api:1.4.2
```

**Compose stack (`compose.yaml`):**

```yaml
name: orders
services:
  api:
    image: registry.example.com/orders-api:1.4.2
    build:
      context: .
      target: runtime
    ports: ["127.0.0.1:8080:8080"]
    env_file: [./.env]
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_started
    healthcheck:
      test: ["CMD", "/nodejs/bin/node", "-e", "fetch('http://127.0.0.1:8080/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
      interval: 30s
      timeout: 3s
      retries: 3
      start_period: 15s
    restart: unless-stopped
    read_only: true
    tmpfs: ["/tmp:size=64m"]
    security_opt: ["no-new-privileges:true"]
    cap_drop: ["ALL"]
    deploy:
      resources:
        limits: {memory: 512M, cpus: "1.5"}
    logging:
      driver: json-file
      options: {max-size: "10m", max-file: "3"}

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: orders
      POSTGRES_PASSWORD: ${DB_PASSWORD:?set DB_PASSWORD}
    volumes: ["pgdata:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d orders"]
      interval: 10s
      timeout: 5s
      retries: 5

  cache:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes", "--maxmemory", "256mb", "--maxmemory-policy", "allkeys-lru"]
    volumes: ["redisdata:/data"]

volumes:
  pgdata: {}
  redisdata: {}
```

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=50 api
docker compose exec api /nodejs/bin/node -v
```

**Debugging an exited container:**

```bash
docker ps -a --filter name=orders-api
docker inspect orders-api --format '{{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} err={{.State.Error}}'
docker logs --tail 100 orders-api
docker run -it --rm --entrypoint /bin/sh app:1.4.2   # distroless: no shell, use a debug variant
```

**Disk cleanup (never `prune -a` on a shared host without review):**

```bash
docker system df -v
docker image prune -f --filter "until=168h"
docker builder prune -f --filter "until=168h"
```

## 8. Quality Standards

- Image size within a stated budget; runtime image has no compilers or package caches.
- `USER` is non-root with a numeric UID.
- Exec-form `ENTRYPOINT`/`CMD`; signals handled correctly (graceful shutdown verified).
- Dependency installs are deterministic (`npm ci`, lockfiles, checksums).
- Tags are immutable and traceable to a commit.
- Resource limits and log rotation configured for any long-running container.
- Healthcheck present and meaningful (not `CMD true`).
- No secrets in layers, build args, or `ENV`.

## 9. Verification and Testing

```bash
docker buildx build --progress=plain -t app:test .
hadolint Dockerfile
docker run --rm app:test id                        # uid=65532
docker history --no-trunc app:test | head -15
dive app:test --ci --highestWastePercent 10
docker run -d --name t --memory 128m app:test && docker stats --no-stream t
docker stop -t 20 t && docker inspect t --format '{{.State.ExitCode}}'   # 0 or 143, graceful
docker compose config                              # validates compose file
```

Expected evidence: build reproducible on a clean cache, non-root UID, small image, health status `healthy`, graceful shutdown before SIGKILL, logs visible with rotation configured.

## 10. Security Considerations

- Never `COPY .env`, private keys, or `.npmrc` with tokens; use BuildKit secret mounts.
- Build args are visible in image history—do not pass secrets as `ARG`.
- Pin base images by digest for reproducible, tamper-evident builds; rebuild regularly for CVEs.
- Never mount `/var/run/docker.sock` into containers (equivalent to host root).
- Set `--no-new-privileges`, drop capabilities, and use a read-only root filesystem.
- Registry auth: use short-lived tokens (ECR/GHCR OIDC) rather than long-lived passwords.
- A container is not a security boundary for untrusted code; use separate hosts/VMs or gVisor for that.
- `docker compose` reads `.env` automatically—ensure it is gitignored and 0600.

## 11. Failure Handling

- **Build cache misses on every change:** copy lockfiles before source; check `.dockerignore` is not excluding the lockfile.
- **Container exits immediately with code 127/1:** entrypoint path wrong or missing shared library; run with `--entrypoint /bin/sh` (or a debug image) and inspect.
- **App does not receive SIGTERM:** shell-form entrypoint swallows signals; switch to exec form.
- **Cannot write to filesystem with `--read-only`:** add explicit `tmpfs` or a named volume for the app's writable paths.
- **Image too large:** `dive` finds the offending layer; usually package manager caches or dev dependencies in the runtime stage.
- **`docker compose up` fails on variable:** `:?` guard in compose tells you which variable is missing—set it in `.env` (not committed) or the shell.

## 12. Expected Deliverables

1. Dockerfile with multi-stage build and comments.
2. `.dockerignore`.
3. Compose file for multi-service stacks.
4. Build and run commands with resource limits.
5. Verification transcript (size, user, health, shutdown).
6. Registry/tagging convention and CI build command.

## 13. References

- Docker Build best practices — https://docs.docker.com/build/building/best-practices/
- Dockerfile reference — https://docs.docker.com/reference/dockerfile/
- BuildKit — https://docs.docker.com/build/buildkit/
- Docker Compose specification — https://docs.docker.com/compose/compose-file/
- Distroless — https://github.com/GoogleContainerTools/distroless
- hadolint — https://github.com/hadolint/hadolint
- `dive` — https://github.com/wagoodman/dive
