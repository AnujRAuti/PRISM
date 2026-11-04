---
name: infrastructure-automation
description: Automate server configuration and operations idempotently—Ansible, cloud-init, and declarative provisioning—with safe rollout, drift detection, and rollback.
metadata:
  domain: devops-and-linux
  version: 1.0.0
  risk: high
---

# Infrastructure Automation

## 1. Purpose

Make infrastructure changes repeatable, idempotent, and reviewable instead of applying them by hand over SSH. This skill covers configuration management with Ansible (and alternatives), cloud-init bootstrap, inventory and secrets handling, idempotence verification, drift detection, and safe rollout patterns. Terraform-style provisioning lives in the IaC skills; this skill targets *configuration* and *operational automation*.

**Scope:** infrastructure you own. Automation runs with elevated privileges across many hosts—test with `--check`, limit blast radius with batches, and require review before production runs.

## 2. Activation Conditions

- Managing more than a couple of servers with manual steps.
- Configuration drift between hosts causing "works on one box only".
- Rebuilding a host requires a documented runbook that must become code.
- Onboarding new environments (staging clone of prod).
- Keywords: Ansible, playbook, idempotent, cloud-init, configuration management, drift, inventory, roles, handlers, provision, bootstrap.

## 3. When Not to Use

- Cloud resource provisioning (use terraform-infrastructure-as-code / infrastructure-as-code).
- Container-based deployment where images are the unit of config (bake config into images).
- Kubernetes-managed workloads (use kubernetes-engineering).

## 4. Required Context

1. Host inventory, groups, and connection method (SSH keys, bastion, agentless vs. agent).
2. Existing configuration and the intended end state; which parts are managed vs. unmanaged.
3. Secrets source (Vault, Ansible Vault, SOPS, cloud secrets manager).
4. Change window and rollback plan; whether hosts are stateful (databases).
5. Current tooling and versions (`ansible --version`, Python version on targets).

## 5. Operating Procedure

1. **Define desired state per host role**, not per host. Roles: `common`, `web`, `db`, `bastion`.
2. **Structure the repo**: `inventories/`, `roles/`, `group_vars/`, `host_vars/`, `playbooks/`, `molecule/` for tests.
3. **Write idempotent tasks**: use modules (`ansible.builtin.template`, `package`, `service`, `user`, `lineinfile` with anchors) rather than `shell`/`command`; every `shell` needs `creates:`/`changed_when:` guards.
4. **Use handlers** for restarts, triggered only on change.
5. **Encrypt secrets** (Ansible Vault or external secret lookup); never plaintext in `group_vars`.
6. **Test first**: `ansible-playbook --check --diff` (dry run), then `--limit` one canary host, then the group in batches (`serial: 2` or `serial: 25%`).
7. **Add health gates** between batches (`wait_for`, `uri` on `/healthz`).
8. **Run from CI with the same playbook** used locally; no manual hotfixes.
9. **Verify idempotence**: a second run must report `changed=0`.
10. **Detect drift** on a schedule: run `--check` nightly and alert on unexpected diffs.
11. **Document rollback** per role (revert commit + re-run, or restore snapshot).
12. **Retire manual steps**: delete SSH runbooks and replace them with playbook tasks so they cannot diverge.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Config management | Ansible, SaltStack, Puppet, Chef |
| Bootstrap | cloud-init (`user-data`), `cloud-localds`, Packer |
| Secrets | Ansible Vault, HashiCorp Vault, SOPS+age, `community.sops` |
| Testing | `molecule` + Docker/Podman driver, `ansible-lint`, `yamllint` |
| Drift | `--check` runs, `ansible-cmdb`, config audit scripts |
| Inventory | static INI/YAML, dynamic plugins (AWS EC2, Proxmox) |
| Orchesration | AWX/Semaphore, CI runners |

## 7. Practical Implementation

**Repo layout:**

```
.
├── ansible.cfg
├── inventories/prod/hosts.yml
├── inventories/prod/group_vars/all/vault.yml
├── roles/
│   ├── common/{tasks,handlers,templates,defaults}/
│   └── web/tasks/main.yml
├── playbooks/site.yml
└── molecule/default/
```

**`ansible.cfg`:**

```ini
[defaults]
inventory = inventories/prod/hosts.yml
roles_path = roles
host_key_checking = True
interpreter_python = auto_silent
stdout_callback = yaml
forks = 20
retry_files_enabled = False

[ssh_connection]
pipelining = True
ssh_args = -o ControlMaster=auto -o ControlPersist=60s -o StrictHostKeyChecking=yes
```

**Inventory:**

```yaml
all:
  children:
    web:
      hosts:
        web1.example.com:
        web2.example.com:
    db:
      hosts:
        db1.example.com:
```

**Idempotent role tasks (`roles/web/tasks/main.yml`):**

```yaml
- name: Ensure nginx is installed
  ansible.builtin.package:
    name: nginx
    state: present

- name: Deploy nginx site config
  ansible.builtin.template:
    src: site.conf.j2
    dest: /etc/nginx/conf.d/site.conf
    owner: root
    group: root
    mode: "0644"
    validate: "nginx -t -c %s"
  notify: Reload nginx

- name: Ensure nginx is enabled and running
  ansible.builtin.service:
    name: nginx
    state: started
    enabled: true

- name: Allow HTTPS through the firewall
  ansible.posix.firewalld:
    service: https
    permanent: true
    immediate: true
    state: enabled

- name: Create app user (idempotent)
  ansible.builtin.user:
    name: appsvc
    system: true
    shell: /usr/sbin/nologin
    create_home: false
```

```yaml
# roles/web/handlers/main.yml
- name: Reload nginx
  ansible.builtin.service:
    name: nginx
    state: reloaded
```

**Guarded shell task (only when a module does not exist):**

```yaml
- name: Initialize application database schema
  ansible.builtin.command:
    cmd: /opt/app/bin/migrate --to-head
    creates: /var/lib/app/.schema-initialized
  changed_when: false
```

**Rolling deploy with health gates (`playbooks/deploy.yml`):**

```yaml
- name: Deploy API with rolling batches
  hosts: web
  serial: 1
  max_fail_percentage: 0
  pre_tasks:
    - name: Remove host from load balancer
      ansible.builtin.uri:
        url: "https://lb.example.com/api/backends/{{ inventory_hostname }}/drain"
        method: POST
        headers: {Authorization: "Bearer {{ lb_token }}"}
  roles:
    - api
  post_tasks:
    - name: Wait for health endpoint
      ansible.builtin.uri:
        url: "http://127.0.0.1:8080/healthz"
        status_code: 200
      retries: 12
      delay: 5
    - name: Return host to load balancer
      ansible.builtin.uri:
        url: "https://lb.example.com/api/backends/{{ inventory_hostname }}/ready"
        method: POST
        headers: {Authorization: "Bearer {{ lb_token }}"}
```

**Cloud-init bootstrap (`user-data`):**

```yaml
#cloud-config
users:
  - name: ops
    groups: [sudo]
    sudo: "ALL=(ALL) NOPASSWD:ALL"
    ssh_authorized_keys:
      - ssh-ed25519 AAAA... ops@example.com
package_update: true
packages: [qemu-guest-agent, chrony, unattended-upgrades]
runcmd:
  - systemctl enable --now chrony
  - systemctl enable --now qemu-guest-agent
write_files:
  - path: /etc/ssh/sshd_config.d/10-hardening.conf
    permissions: "0644"
    content: |
      PermitRootLogin no
      PasswordAuthentication no
```

**Secrets with Vault lookup:**

```yaml
- name: Fetch database password
  ansible.builtin.set_fact:
    db_password: "{{ lookup('community.hashi_vault.vault_kv2_get', 'secret/data/db', engine_mount_point='secret').secret.password }}"
  no_log: true
```

**Run sequence:**

```bash
ansible-lint
ansible-playbook playbooks/site.yml --check --diff
ansible-playbook playbooks/site.yml --limit web1.example.com
ansible-playbook playbooks/site.yml
ansible-playbook playbooks/site.yml | grep -E 'changed=[1-9]' && echo "NOT IDEMPOTENT"
```

## 8. Quality Standards

- Second run reports `changed=0` (idempotent).
- No plaintext secrets; `no_log: true` on secret-related tasks.
- `shell`/`command` usage justified and guarded with `creates`/`changed_when`.
- Roles are reusable, documented, and tested with molecule.
- Handlers used for service restarts; no restart on every run.
- Rolling deploys use `serial` and health gates.
- Drift detection runs on a schedule with alerting.
- `ansible-lint` and `yamllint` clean in CI.

## 9. Verification and Testing

```bash
molecule test                     # create -> converge -> idempotence -> verify -> destroy
ansible-playbook site.yml --check --diff
ansible-inventory --graph
ansible all -m ansible.builtin.ping
ansible web -m ansible.builtin.setup -a 'filter=ansible_distribution*'
ansible-playbook site.yml 2>&1 | tail -5     # expect changed=0
```

Expected evidence: molecule idempotence step passes, dry run shows no unexpected diffs, health checks pass during rollout, and a second production run shows zero changes.

## 10. Security Considerations

- Automation accounts hold broad SSH access: use a dedicated key, restricted sudo (`NOPASSWD` only for the specific modules' commands or use `become` with a scoped policy), and rotate.
- Never commit vault passwords; use `--ask-vault-pass`, `ANSIBLE_VAULT_PASSWORD_FILE` from a secret store, or an external lookup.
- `no_log: true` on tasks that handle secrets, but remember `--diff` can still reveal file contents—review output before sharing.
- Validate templates before writing (`validate:` with `nginx -t`, `sshd -t`) to avoid breaking access.
- Do not disable host key checking; verify new hosts out-of-band.
- Pin Ansible collections (`requirements.yml`) and review upstream changes; collections execute code on control and target nodes.
- `serial` limits blast radius; never target `all` for a risky change.
- The control node is a high-value target: it stores credentials—harden it and restrict who can run playbooks.

## 11. Failure Handling

- **Task not idempotent:** replace `shell` with the proper module or add `creates:`; check for commands that always report changed.
- **Vault password unavailable in CI:** provide it via a masked CI variable or an OIDC-exchanged secret; never store it in the repo.
- **Handler did not fire:** handlers run at the end of a play; use `meta: flush_handlers` if a later task depends on the reload.
- **SSH connection failures:** check `ssh -vvv`, control sockets, and `ansible_host`/bastion (`ProxyJump`) settings.
- **Partial rollout failure:** `max_fail_percentage: 0` stops the batch; roll back by reverting the commit and re-running, or restore the snapshot.
- **Python missing on target:** use `raw` for the bootstrap task to install Python, or use `gather_facts: false` for the first play.

## 12. Expected Deliverables

1. Repository structure with roles, inventories, and playbooks.
2. Idempotence evidence (second run `changed=0`).
3. Lint and molecule test output.
4. Secret-management integration.
5. Rolling deploy playbook with health gates.
6. Drift-detection schedule and rollback procedure.

## 13. References

- Ansible documentation — https://docs.ansible.com/
- Ansible best practices — https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_best_practices.html
- `ansible-lint` — https://ansible.readthedocs.io/projects/lint/
- Molecule — https://ansible.readthedocs.io/projects/molecule/
- cloud-init documentation — https://cloudinit.readthedocs.io/
- Ansible Vault — https://docs.ansible.com/ansible/latest/vault_guide/index.html
- SOPS — https://github.com/getsops/sops
