---
name: linux-security-hardening
description: Harden Linux hosts—SSH, accounts, sudo, kernel sysctls, filesystem permissions, firewalls, auditing, and MAC—measured against CIS benchmarks without locking yourself out.
metadata:
  domain: cybersecurity
  version: 1.0.0
  risk: high
---

# Linux Security Hardening

## 1. Purpose

Reduce the attack surface of a Linux host and make intrusion detectable. This skill covers account and authentication hardening, SSH configuration, privilege escalation controls, kernel hardening, filesystem mount options, firewalling, auditing, and patch management—applied in an order that never severs your own access. It is written for modern systemd distributions including Arch/CachyOS and Debian/Ubuntu.

**Scope:** systems you own or administer with written authorization. Never harden a production host without a tested recovery path (console/serial access or snapshot).

## 2. Activation Conditions

- Provisioning a new server or re-baselining an existing one.
- CIS benchmark or compliance requirement.
- Post-incident hardening after a compromise.
- Audit finding on SSH, sudo, or permissions.
- Keywords: hardening, CIS, SSH hardening, sysctl, AppArmor, SELinux, auditd, UFW, nftables, fail2ban, sudoers, rootkit.

## 3. When Not to Use

- Container images (use container-security; many kernel controls belong to the host).
- Managed appliances where the vendor controls the OS (apply vendor guidance).
- When you lack console access and cannot afford lockout risk—get access first.

## 4. Required Context

1. Distribution and version, init system, and kernel version (`uname -r`).
2. Access method: SSH only? Console available? Cloud serial console?
3. Role of the host: web server, database, bastion, workstation, CI runner.
4. Which services must remain reachable and from where.
5. Existing users, sudo rules, keys, and automation accounts.
6. Compliance profile in effect.

## 5. Operating Procedure

1. **Snapshot/backup and confirm console access** before changing SSH or firewall.
2. **Inventory**: open ports (`ss -tulpn`), services (`systemctl list-units --type=service --state=running`), users (`getent passwd`), sudoers (`sudo -l` per user), cron jobs, world-writable files.
3. **Patch first**: apply all security updates; enable unattended upgrades where appropriate.
4. **Accounts**: lock unused accounts, set password aging, remove UID 0 duplicates, restrict shells, disable root login.
5. **SSH**: key-only auth, no root password login, modern algorithms, `AllowUsers`/`AllowGroups`, rate limiting, optional port change (defense in depth, not a control), MFA where supported.
6. **Privilege escalation**: minimal sudoers (`NOPASSWD` only where automation requires it and scoped to specific commands), `requiretty` policy considerations, sudo logging.
7. **Kernel/sysctl hardening**: `kptr_restrict`, `dmesg_restrict`, `unprivileged_bpf_disabled`, IP forwarding off unless needed, SYN cookies, `rp_filter`, ASLR on.
8. **Filesystem**: mount `/tmp`, `/var/tmp`, `/dev/shm` with `nodev,nosuid,noexec`; set `umask 027`; fix world-writable files; restrict `/etc/shadow` to 640 root:shadow.
9. **Firewall**: default-deny inbound, allowlist ports and sources; egress policy per role.
10. **MAC**: enable AppArmor or SELinux in enforcing mode; verify profiles for exposed services.
11. **Audit**: `auditd` rules for identity, privilege, and configuration changes; centralize logs off-host.
12. **Integrity and malware detection**: AIDE or `rpm -Va`/`debsums`, rootkit scanners (`rkhunter`, `chkrootkit`) as secondary signals only.
13. **Reboot-check**: validate SSH, services, and console after changes; document rollback steps.

## 6. Tools and Technologies

| Area | Tools |
|---|---|
| Benchmark | `lynis audit system`, OpenSCAP, `oscap` |
| SSH | `sshd_config`, `ssh-audit` |
| Firewall | `nftables`, `ufw`, `firewalld` |
| MAC | AppArmor (`aa-status`), SELinux (`sestatus`) |
| Audit | `auditd`/`auditctl`/`ausearch` |
| Integrity | AIDE, `debsums`, `rpm -Va` |
| Updates | `unattended-upgrades` (Debian), `pacman -Syu` (Arch) |
| Access | `fail2ban`, PAM (`pam_faillock`) |
| Scanning | `lynis`, `nmap` (own hosts only) |

## 7. Practical Implementation

**SSH hardening (`/etc/ssh/sshd_config.d/10-hardening.conf`):**

```conf
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
AuthenticationMethods publickey
AllowGroups ssh-users
MaxAuthTries 3
MaxSessions 4
LoginGraceTime 20
ClientAliveInterval 300
ClientAliveCountMax 2
KexAlgorithms sntrup761x25519-sha512@openssh.com,curve25519-sha256
Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com
MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
PermitTunnel no
```

```bash
# ALWAYS validate before reload — prevents lockout
sudo sshd -t && sudo systemctl reload sshd
# Keep the current session open while testing a NEW session in parallel.
ssh-audit localhost
```

**Account hygiene:**

```bash
# find duplicate UID 0 accounts
awk -F: '($3==0){print}' /etc/passwd
# lock accounts with no login shell usage
sudo passwd -l olduser
sudo usermod -L -e 1 olduser            # lock + expire
sudo chage -l deploy                    # review aging
# restrict privileged groups
getent group sudo wheel docker
```

**Sysctl hardening (`/etc/sysctl.d/90-hardening.conf`):**

```conf
kernel.kptr_restrict = 2
kernel.dmesg_restrict = 1
kernel.yama.ptrace_scope = 1
kernel.unprivileged_bpf_disabled = 1
net.core.bpf_jit_harden = 2
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv6.conf.all.accept_ra = 0
fs.protected_hardlinks = 1
fs.protected_symlinks = 1
fs.suid_dumpable = 0
```

```bash
sudo sysctl --system
sysctl kernel.kptr_restrict
```

**Filesystem mounts (`/etc/fstab`):**

```conf
tmpfs   /tmp      tmpfs   defaults,noatime,nodev,nosuid,noexec,size=1G  0 0
tmpfs   /dev/shm  tmpfs   defaults,noatime,nodev,nosuid,noexec,size=512M 0 0
```

**nftables default-deny (own server):**

```nft
#!/usr/sbin/nft -f
flush ruleset
table inet filter {
  chain input {
    type filter hook input priority 0; policy drop;
    ct state established,related accept
    iif lo accept
    ip protocol icmp accept
    ip6 nexthdr ipv6-icmp accept
    tcp dport 22 accept           # restrict further: ip saddr @admin_nets
    tcp dport { 80, 443 } accept
    counter log prefix "nft-drop-in: " drop
  }
  chain forward { type filter hook forward priority 0; policy drop; }
  chain output  { type filter hook output  priority 0; policy accept; }
}
```

```bash
sudo nft -f /etc/nftables.conf && sudo systemctl enable --now nftables
```

**auditd rules (`/etc/audit/rules.d/10-hardening.rules`):**

```conf
-D
-b 8192
-w /etc/passwd -p wa -k identity
-w /etc/shadow -p wa -k identity
-w /etc/sudoers -p wa -k privilege
-w /etc/sudoers.d/ -p wa -k privilege
-w /etc/ssh/sshd_config -p wa -k sshd
-a always,exit -F arch=b64 -S execve -F euid=0 -C auid!=0 -k root_exec
-a always,exit -F arch=b64 -S setuid -S setgid -S setreuid -k privilege_change
```

```bash
sudo augenrules --load && sudo auditctl -l
sudo ausearch -k privilege -ts recent
```

**AppArmor status (Debian/Ubuntu/Arch optional):**

```bash
sudo aa-status
sudo aa-enforce /etc/apparmor.d/usr.bin.nginx
```

**Verification with lynis:**

```bash
sudo lynis audit system --quick
sudo grep -E 'Hardening index' /var/log/lynis.log
```

## 8. Quality Standards

- SSH is key-only; root login disabled; config validated with `sshd -t`.
- Default-deny firewall with documented allowlist.
- No duplicate UID 0; unused accounts locked; sudo scoped and logged.
- sysctl hardening applied and persisted across reboot.
- `/tmp`, `/var/tmp`, `/dev/shm` mounted `noexec,nosuid,nodev`.
- MAC framework enforcing for exposed services.
- Auditd rules loaded and logs shipped off-host.
- Patches current; unattended security updates configured where suitable.
- Recovery path (console/snapshot) documented and tested.

## 9. Verification and Testing

```bash
sudo ss -tulpn | sort -k5
sudo sshd -T | grep -E 'permitrootlogin|passwordauthentication|allowgroups'
sudo nft list ruleset
getenforce 2>/dev/null || sudo aa-status --enabled && echo apparmor-enabled
sudo find / -xdev -perm -0002 -type f 2>/dev/null | head
sudo lynis audit system --quick | tail -5
```

Expected evidence: reduced listening ports, hardened sshd settings, enforcing MAC, zero world-writable files outside `/tmp`, lynis hardening index improved with a before/after record.

## 10. Security Considerations

- Never lock yourself out: change SSH last, keep a session open, verify config syntax, and confirm console access.
- Do not disable SELinux/AppArmor to make an app work; write a policy or use labeled ports (`semanage port -a`).
- `NOPASSWD` sudo rules are root-equivalent if the allowed command is a shell, editor, or anything with `!`/`:!` escapes.
- Docker group membership is root-equivalent—treat it as such.
- Logs may contain secrets; restrict `/var/log` permissions and scrub before sharing.
- Time-sync must be enabled (chrony/systemd-timesyncd): logs and TLS validity depend on it.
- Harden only with change control; document each change and its rollback.

## 11. Failure Handling

- **Locked out after SSH change:** use console/serial, boot with `init=/bin/bash` if needed, revert the drop-in, then re-apply incrementally.
- **Service fails after `noexec` on `/tmp`:** move its temp directory to a dedicated volume with `exec` for that path only.
- **SELinux denials:** read `ausearch -m avc -ts recent`, use `audit2why`/`audit2allow` to craft a policy, never set permissive permanently.
- **Firewall blocks monitoring/backup:** add explicit source allowlists for those systems; document in the firewall file.
- **Audit log volume too high:** narrow rules to key paths and privileged execs; keep the buffer large (`-b`).

## 12. Expected Deliverables

1. Baseline inventory (ports, services, users, sudo).
2. Applied configuration files with comments.
3. Before/after lynis/CIS report.
4. Firewall ruleset in version control.
5. Auditd rules and log shipping configuration.
6. Recovery procedure and rollback notes.
7. Residual risks and exceptions with justification.

## 13. References

- CIS Benchmarks — https://www.cisecurity.org/cis-benchmarks
- OpenSSH `sshd_config(5)` — https://man.openbsd.org/sshd_config
- Arch Wiki — Security — https://wiki.archlinux.org/title/Security
- Debian Security Manual — https://www.debian.org/doc/manuals/securing-debian-manual/
- `nftables` wiki — https://wiki.nftables.org/wiki-nftables/index.php/Main_Page
- auditd documentation — https://github.com/linux-audit/audit-documentation
- Lynis — https://cisofy.com/lynis/
- NIST SP 800-123 (server security) — https://csrc.nist.gov/pubs/sp/800/123/final
