---
name: kubernetes-administration
description: Operate Kubernetes clusters safely—resource requests and limits, probes, RBAC and network policy, disruption budgets, and upgrade discipline.
metadata:
  domain: cloud-and-infrastructure
  version: 1.0.0
  risk: high
---

# Kubernetes Administration

## 1. Purpose

Run workloads on Kubernetes so they stay available, bounded, and secure. Most cluster incidents trace to the same handful of omissions: no resource requests (scheduling chaos and OOM noise), missing or wrong probes (traffic to unready pods, or restart loops), no PodDisruptionBudget (drains take everything down), overprivileged service accounts, and no network policy (flat cluster, lateral movement). This skill covers those controls plus rollout and upgrade discipline.

**Scope:** clusters you administer. Kubernetes actions are destructive at scale: `delete`, `drain`, `evict`, and namespace removal can take down production. Require explicit authorization before touching production namespaces, never run `--force --grace-period=0` on stateful workloads, and never delete PersistentVolumeClaims without confirming backups.

## 2. Activation Conditions

- Deploying a new workload or namespace to a cluster.
- Pods restarting, pending, or OOM-killed.
- Deploys cause outages or drain takes services down.
- Preparing a cluster upgrade.
- Keywords: Kubernetes, kubectl, Deployment, requests and limits, liveness, readiness, startup probe, HPA, PDB, RBAC, NetworkPolicy, PodSecurity, drain, rollout, eviction, StatefulSet, kustomize, Helm.

## 3. When Not to Use

- Provisioning the cluster itself (use aws-engineering or infrastructure-automation).
- Application-level performance tuning (use performance-optimization).
- A single-container deployment where a managed container service is simpler.

## 4. Required Context

1. Cluster version, distribution, and managed vs. self-hosted.
2. Workload profiles: stateless web, batch, stateful, scheduled jobs.
3. Traffic patterns and SLOs.
4. Existing namespace and RBAC model.
5. Observability stack (metrics, logs, events).

## 5. Operating Procedure

1. **Set requests for every container** (they drive scheduling and QoS); set limits deliberately — CPU limits cause throttling, memory limits cause OOMKills. For latency-sensitive services, prefer requests-only CPU with cluster-level fairness, or generous limits.
2. **Define the three probes**: readiness (remove from Service endpoints), liveness (restart only for unrecoverable states), startup (protect slow boots). Never point liveness at a dependency that can fail independently, or a database blip restarts your whole fleet.
3. **Bound availability during disruption**: PodDisruptionBudget (`minAvailable` or `maxUnavailable`), multiple replicas across zones (`topologySpreadConstraints`), and `maxUnavailable`/`maxSurge` on rollouts.
4. **Apply least-privilege RBAC**: dedicated ServiceAccounts per workload, `automountServiceAccountToken: false` when the API is not needed, no `cluster-admin` bindings for applications.
5. **Enforce pod security**: Pod Security Admission (`restricted` where feasible), non-root, read-only root filesystem, dropped capabilities, seccomp `RuntimeDefault`.
6. **Default-deny network** with NetworkPolicies: allow DNS, explicit ingress from the ingress controller, and explicit egress to required services.
7. **Pin images by digest**, set `imagePullPolicy` appropriately, and use immutable tags (never `:latest` in production).
8. **Separate configuration from images**: ConfigMaps/Secrets (with an external secret operator), and checksums or reloader annotations so config changes actually roll out.
9. **Control resource growth**: HPA on meaningful signals (RPS/queue depth, not just CPU), ResourceQuota and LimitRange per namespace.
10. **Upgrade deliberately**: read the deprecation guide, upgrade one minor version at a time, drain nodes with PDBs, and verify API removals with `pluto`/`kubent`.
11. **Monitor what predicts failure**: pod restart rate, pending pods, evictions, PDB-blocked drains, and API server latency.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Clients | `kubectl`, `kubectx`/`kubens`, `k9s`, `stern` |
| Packaging | Helm, Kustomize, plain manifests + CI |
| Policy | Pod Security Admission, Kyverno, OPA Gatekeeper |
| Network | Calico, Cilium (with Hubble), cloud CNIs |
| Scaling | HPA, VPA, KEDA, Cluster Autoscaler/Karpenter |
| Secrets | External Secrets Operator, Sealed Secrets, SOPS |
| Upgrade tooling | `pluto`, `kubent`, `kube-no-trouble`, `kubectl drain --dry-run` |
| Debug | `kubectl describe/events/logs`, `kubectl debug` ephemeral containers |

## 7. Practical Implementation

**Deployment with requests, limits, three probes, and spread:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: payments
spec:
  replicas: 6
  strategy:
    rollingUpdate: {maxUnavailable: 1, maxSurge: 2}
  selector:
    matchLabels: {app: orders-api}
  template:
    metadata:
      labels: {app: orders-api}
    spec:
      serviceAccountName: orders-api
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        fsGroup: 10001
        seccompProfile: {type: RuntimeDefault}
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels: {app: orders-api}
      containers:
        - name: api
          image: registry.example.com/orders-api@sha256:4f1c2a9e...   # digest, not tag
          ports: [{name: http, containerPort: 8080}]
          resources:
            requests: {cpu: "500m", memory: "512Mi"}
            limits:   {memory: "1Gi"}          # CPU limit omitted on purpose (avoid throttling)
          startupProbe:
            httpGet: {path: /healthz/startup, port: http}
            failureThreshold: 30
            periodSeconds: 2                   # up to 60 s to boot
          readinessProbe:
            httpGet: {path: /healthz/ready, port: http}
            periodSeconds: 5
            failureThreshold: 2
          livenessProbe:
            httpGet: {path: /healthz/live, port: http}
            periodSeconds: 10
            failureThreshold: 3                # local check only, no DB dependency
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: {drop: ["ALL"]}
          volumeMounts:
            - {name: tmp, mountPath: /tmp}
      volumes:
        - name: tmp
          emptyDir: {sizeLimit: 256Mi}
```

**Probe endpoints that reflect the right thing:**

```python
# Readiness: can this pod serve traffic now (dependencies that matter per request)?
@app.get("/healthz/ready")
async def ready(pool=Depends(get_pool)):
    try:
        async with pool.acquire(timeout=0.5) as conn:
            await conn.execute("SELECT 1")
        return {"ready": True}
    except Exception:
        raise HTTPException(503, "database not ready")

# Liveness: is this process broken beyond recovery (never checks dependencies)?
@app.get("/healthz/live")
async def live():
    return {"alive": True}
```

**PodDisruptionBudget and zone spread for drains:**

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata: {name: orders-api, namespace: payments}
spec:
  minAvailable: 4          # with 6 replicas, a node drain evicts at most 2
  selector: {matchLabels: {app: orders-api}}
```

**Default-deny NetworkPolicy plus explicit allows:**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: default-deny, namespace: payments}
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: orders-api, namespace: payments}
spec:
  podSelector: {matchLabels: {app: orders-api}}
  policyTypes: [Ingress, Egress]
  ingress:
    - from:
        - namespaceSelector: {matchLabels: {kubernetes.io/metadata.name: ingress-nginx}}
      ports: [{protocol: TCP, port: 8080}]
  egress:
    - to: [{namespaceSelector: {matchLabels: {kubernetes.io/metadata.name: kube-system}}}]
      ports: [{protocol: UDP, port: 53}, {protocol: TCP, port: 53}]     # DNS
    - to: [{podSelector: {matchLabels: {app: postgres}}}]
      ports: [{protocol: TCP, port: 5432}]
```

**Least-privilege RBAC for a workload and for humans:**

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata: {name: config-reader, namespace: payments}
rules:
  - apiGroups: [""]
    resources: ["configmaps", "secrets"]
    resourceNames: ["orders-api-config"]     # named resources only
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: {name: orders-api-config-reader, namespace: payments}
subjects:
  - {kind: ServiceAccount, name: orders-api, namespace: payments}
roleRef: {kind: Role, name: config-reader, apiGroup: rbac.authorization.k8s.io}
```

**Namespace guardrails: Pod Security, quotas, and default limits:**

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: payments
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
---
apiVersion: v1
kind: ResourceQuota
metadata: {name: payments-quota, namespace: payments}
spec:
  hard:
    requests.cpu: "40"
    requests.memory: 80Gi
    limits.memory: 120Gi
    count/pods: "200"
---
apiVersion: v1
kind: LimitRange
metadata: {name: payments-defaults, namespace: payments}
spec:
  limits:
    - type: Container
      default: {memory: 512Mi}
      defaultRequest: {cpu: 100m, memory: 128Mi}
```

**Safe drain and rollout checks:**

```bash
# Is anything going to block the drain?
kubectl -n payments get pdb
kubectl drain node-3 --ignore-daemonsets --delete-emptydir-data --dry-run=server

# Real drain with the PDB protecting availability
kubectl drain node-3 --ignore-daemonsets --delete-emptydir-data --timeout=300s
kubectl rollout status deploy/orders-api -n payments --timeout=300s
kubectl rollout undo deploy/orders-api -n payments        # if it goes wrong
```

**Upgrade readiness before bumping the control plane:**

```bash
kubent                                   # deprecated APIs in use
pluto detect-all-in-cluster              # apiVersion removals for the target version
kubectl api-resources --verbs=list --namespaced -o name | xargs -n1 kubectl get --show-kind --ignore-not-found -A >/dev/null
# Verify every addon (CNI, ingress, autoscaler, CSI) supports the target version first.
```

**Symptom triage commands:**

```bash
kubectl -n payments get pods -o wide
kubectl -n payments describe pod orders-api-xxxx     # Events section is the answer 80% of the time
kubectl -n payments logs orders-api-xxxx --previous # the crashed container's last words
kubectl -n payments top pods
kubectl get events -A --sort-by=.lastTimestamp | tail -30
kubectl -n payments get pods -o json | jq -r '.items[] | select(.status.phase!="Running") | "\(.metadata.name) \(.status.phase) \(.status.reason)"'
```

## 8. Quality Standards

- Every container has CPU/memory requests; memory limits set; CPU limits justified either way.
- Readiness and liveness probes are distinct and correct; liveness never depends on external services.
- Every production workload has a PDB and multi-AZ spread.
- ServiceAccounts are per-workload, token automount disabled unless required; no application uses `cluster-admin`.
- Namespaces enforce Pod Security `restricted` (or documented baseline with justification).
- Default-deny NetworkPolicy exists in every namespace, with explicit allows.
- Images are pinned by digest; production never uses `:latest`.
- Namespaces have ResourceQuota and LimitRange; HPA scales on a meaningful metric.
- Upgrades are preceded by deprecated-API detection and addon compatibility checks.

## 9. Verification and Testing

- `kubectl rollout status` after every deploy; verify old pods terminate and new ones become ready.
- Deliberate failure test: kill a pod, confirm Service endpoints remove it and no user-facing errors occur.
- Drain a node in staging and confirm PDB blocks over-eviction and workloads reschedule.
- `kubectl auth can-i --list --as=system:serviceaccount:payments:orders-api` to review effective permissions.
- Network policy test: from a debug pod, confirm denied egress fails and allowed DNS/SQL succeeds.
- `kube-score`/`kubeconform`/`polaris` in CI on rendered manifests.
- Load a namespace above quota in staging and confirm rejection with a clear message.

## 10. Security Considerations

- Never mount tokens into pods that do not need the API; a stolen token is cluster access.
- Secrets in etcd are base64, not encrypted by default — enable encryption at rest and use an external secret store.
- `hostPath`, `hostNetwork`, `privileged: true`, and `hostPID` are cluster-compromise primitives; block them with Pod Security or admission policy.
- Restrict `kubectl exec` and `port-forward` via RBAC and audit logs; production shell access should be intentional and recorded.
- Default-deny network policy is the primary control against lateral movement inside a cluster.
- Image provenance matters: enforce signed images (cosign/Sigstore) and pull only from your registry mirror.
- Audit log enabled on the API server for all human actions; alert on RBAC changes and Secret reads.

## 11. Failure Handling

- **Pods pending:** insufficient resources or unsatisfiable node selectors/tolerations — check `describe pod` Events and node capacity.
- **CrashLoopBackOff:** read `--previous` logs; distinguish application crash from a failing liveness probe (the probe kills a healthy app that boots slowly — add/adjust a startupProbe).
- **OOMKilled:** the memory limit is too tight or there is a leak; raise requests/limits after measuring, and investigate the leak.
- **Rollout stuck:** `rollout status` reports the reason (image pull, quota, PDB, readiness); fix and `rollout undo` if needed.
- **Drain hangs:** a pod without a controller is not evicted; PDB may be blocking; check `kubectl get pdb` and the pod's owner.
- **Service has no endpoints:** readiness failing or the selector does not match — verify labels and probe results.

## 12. Expected Deliverables

1. Workload manifests with resources, probes, security context, and spread.
2. PDBs per production workload.
3. RBAC roles/bindings and ServiceAccount inventory.
4. NetworkPolicy set with default deny.
5. Namespace guardrails (Pod Security, quotas, limits).
6. Rollout, drain, and upgrade runbooks.
7. Monitoring and alert list for cluster and workload health.

## 13. References

- Kubernetes documentation — https://kubernetes.io/docs/home/
- Resource management for pods and containers — https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
- Configure liveness, readiness and startup probes — https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
- PodDisruptionBudget — https://kubernetes.io/docs/concepts/workloads/pods/disruptions/
- Network Policies — https://kubernetes.io/docs/concepts/services-networking/network-policies/
- Pod Security Standards — https://kubernetes.io/docs/concepts/security/pod-security-standards/
- RBAC good practices — https://kubernetes.io/docs/concepts/security/rbac-good-practices/
- Cluster upgrade — https://kubernetes.io/docs/tasks/administer-cluster/kubeadm/kubeadm-upgrade/
- pluto (deprecated APIs) — https://pluto.docs.fairwinds.com/
