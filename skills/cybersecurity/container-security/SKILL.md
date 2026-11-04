---
name: container-security
description: Harden container images and runtimes—minimal base images, non-root users, dropped capabilities, read-only rootfs, image scanning, and supply-chain integrity.
metadata:
  domain: cybersecurity
  version: 1.0.0
  risk: medium
---

# Container Security

## 1. Purpose

Reduce the attack surface and blast radius of containerized workloads. This skill covers image construction (base image choice, multi-stage builds, no build tools in runtime), runtime hardening (non-root, seccomp, capabilities, read-only filesystems), image scanning and signing, and Kubernetes-level controls. It solves the common case of images running as root with full capabilities and a 1 GB attack surface.

**Scope:** images and runtimes you build and operate. Do not scan or probe images belonging to third parties for exploitation.

## 2. Activation Conditions

- Writing or reviewing a Dockerfile/Containerfile.
- Preparing an image for production or a regulated environment.
- Scanner reports critical CVEs in the base image.
- Kubernetes pod security admission warnings.
- Keywords: container hardening, Dockerfile security, non-root, capabilities, seccomp, distroless, image scanning, supply chain, rootless.

## 3. When Not to Use

- VM/bare-metal hardening (use linux-security-hardening).
- Application-layer vulnerabilities with no container dimension (use secure-code-review).
- Development-only throwaway containers with no data and no network exposure (still prefer safe defaults).

## 4. Required Context

1. Runtime: Docker Engine, Podman, containerd, Kubernetes (and version—rootless support varies).
2. Application language and build process.
3. Whether the workload needs privileged operations (raw sockets, device access, specific ports < 1024).
4. Registry and signing infrastructure.
5. Compliance constraints (CIS benchmark, PCI, FedRAMP).

## 5. Operating Procedure

1. **Inventory current image**: base image and digest, size, user, capabilities, entrypoint, exposed ports.
2. **Choose a minimal base**: distroless or slim/alpine variant; pin by digest.
3. **Multi-stage build**: build tools in the builder stage only; copy artifacts into a minimal runtime.
4. **Create an unprivileged user** and `USER` it; never run as UID 0.
5. **Remove secrets from layers** (no `ARG SECRET`, no `COPY .env`); use BuildKit secret mounts.
6. **Runtime hardening**: `--read-only` with explicit tmpfs, `--cap-drop=ALL --cap-add=<needed>`, `no-new-privileges`, seccomp profile, resource limits.
7. **Scan the image** for OS and language CVEs; fail the build on high/critical.
8. **Generate SBOM and sign** the image (cosign/sigstore); verify signatures at deploy.
9. **Kubernetes controls**: Pod Security Admission `restricted`, network policies, service account token automount off unless needed, seccomp `RuntimeDefault`.
10. **Verify** by running the container and inspecting effective user, capabilities, and mounts.
11. **Automate rebuilds** on base-image updates (Renovate/Dependabot or scheduled CI).

## 6. Tools and Technologies

| Tool | Use |
|---|---|
| Docker / Podman / Buildah | Build and run |
| `docker scout`, `trivy image`, `grype` | Image CVE scan |
| `syft` | SBOM generation |
| `cosign`, `sigstore` | Signing and verification |
| `hadolint` | Dockerfile linting |
| `dive` | Layer and wasted-space analysis |
| `docker-bench-security` / `kube-bench` | CIS benchmarks |
| Kubernetes PSA, OPA Gatekeeper, Kyverno | Admission policy |
| `seccomp`, AppArmor, SELinux | Host-level confinement |

## 7. Practical Implementation

**Hardened multi-stage Dockerfile (Python):**

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim@sha256:0000000000000000000000000000000000000000000000000000000000000000 AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM gcr.io/distroless/python3-debian12:nonroot
WORKDIR /app
COPY --from=builder /install /usr/local
COPY --chown=65532:65532 app/ ./app/
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 65532:65532
EXPOSE 8000
ENTRYPOINT ["python", "-m", "app"]
```

**BuildKit secret mount (never bake secrets):**

```dockerfile
# syntax=docker/dockerfile:1.7
RUN --mount=type=secret,id=pipconf,target=/etc/pip.conf \
    pip install --no-cache-dir -r requirements.txt
```

```bash
docker build --secret id=pipconf,src="${HOME}/.pip/pip.conf" -t app:1.0 .
```

**Hardened runtime flags:**

```bash
docker run --rm \
  --user 65532:65532 \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --cap-drop=ALL \
  --security-opt no-new-privileges \
  --security-opt seccomp=./seccomp.json \
  --memory 512m --cpus 1 --pids-limit 256 \
  -p 8000:8000 app:1.0
```

**Podman rootless run:**

```bash
podman run --rm --userns=keep-id --read-only \
  --cap-drop=ALL --security-opt no-new-privileges \
  -p 8000:8000 app:1.0
```

**Kubernetes secure pod spec:**

```yaml
apiVersion: v1
kind: Pod
metadata: {name: api}
spec:
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    runAsUser: 65532
    fsGroup: 65532
    seccompProfile: {type: RuntimeDefault}
  containers:
    - name: api
      image: registry.example.com/app@sha256:abc123...
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities: {drop: ["ALL"]}
      resources:
        limits: {memory: 512Mi, cpu: "1"}
        requests: {memory: 256Mi, cpu: "250m"}
      volumeMounts:
        - {name: tmp, mountPath: /tmp}
  volumes:
    - name: tmp
      emptyDir: {medium: Memory, sizeLimit: 64Mi}
```

**Scan, SBOM, sign, verify:**

```bash
trivy image --severity HIGH,CRITICAL --exit-code 1 app:1.0
syft app:1.0 -o cyclonedx-json=sbom.json
cosign sign --key cosign.key registry.example.com/app@sha256:abc123
cosign verify --key cosign.pub registry.example.com/app@sha256:abc123
```

**Hadolint:**

```bash
docker run --rm -i hadolint/hadolint < Dockerfile
```

## 8. Quality Standards

- Runtime image runs as non-root with a numeric UID (not just a name).
- Base image is pinned by digest and is distroless/slim.
- No build toolchain, package manager cache, or secrets in the final layer.
- `cap-drop=ALL` with an explicit, minimal allowlist.
- Read-only root filesystem; writable paths are explicit tmpfs/volumes.
- Scanner gate passes at HIGH/CRITICAL (or every exception is documented).
- Image is signed and verified at admission.
- Pod Security Admission level `restricted` satisfied.

## 9. Verification and Testing

```bash
docker run --rm --entrypoint id app:1.0                 # uid=65532 gid=65532
docker inspect app:1.0 --format '{{.Config.User}} {{.Config.Entrypoint}}'
docker run --rm --cap-add=NET_ADMIN --entrypoint capsh app:1.0 --print 2>/dev/null || true
kubectl get pod api -o jsonpath='{.spec.containers[*].securityContext}'
trivy image --ignore-unfixed app:1.0 | tail -20
cosign verify --key cosign.pub registry.example.com/app@sha256:abc123
```

Expected evidence: non-root UID, no added capabilities, scan clean or triaged, signature verified, pod admitted under restricted policy.

## 10. Security Considerations

- Treat the registry as a trust boundary: require signed images and immutable tags (digest pinning).
- Never mount the Docker socket into a container; it is equivalent to host root.
- Avoid `--privileged`; if a workload needs it, isolate on a dedicated node pool with taints.
- Do not run untrusted images on a host with credentials or sensitive mounts; use gVisor/Kata or a disposable VM.
- Scan the base image on a schedule—new CVEs appear without any change to your Dockerfile.
- Keep build args out of secrets: `ARG` values persist in image history.
- Restrict egress from containers to prevent data exfiltration and C2.

## 11. Failure Handling

- **App needs root to bind port 80:** bind to 8080 inside and map at the edge (or `--cap-add=NET_BIND_SERVICE` as a last resort).
- **Read-only filesystem breaks the app:** identify write paths with `strace -f -e trace=openat` and mount explicit writable volumes; do not fall back to writable root.
- **Base image CVE with no fix:** switch base (distroless/UBI) or apply `--ignore-unfixed` with documented risk and a review date.
- **Missing shared library in distroless:** copy the library in the builder stage or switch to a slim variant.
- **Signature verification blocks deploys:** fix the signing pipeline; never disable verification globally.

## 12. Expected Deliverables

1. Hardened Dockerfile with multi-stage build and pinned digest.
2. Runtime flags or Kubernetes manifests with securityContext.
3. Scan report and SBOM.
4. Signing/verification configuration.
5. Admission policy (PSA/Kyverno) applied.
6. Before/after evidence (user, capabilities, size, CVE count).

## 13. References

- Docker build best practices — https://docs.docker.com/build/building/best-practices/
- Distroless images — https://github.com/GoogleContainerTools/distroless
- Trivy — https://trivy.dev/
- Sigstore/cosign — https://docs.sigstore.dev/
- Kubernetes Pod Security Standards — https://kubernetes.io/docs/concepts/security/pod-security-standards/
- CIS Docker Benchmark — https://www.cisecurity.org/benchmark/docker
- OWASP Docker Security Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html
