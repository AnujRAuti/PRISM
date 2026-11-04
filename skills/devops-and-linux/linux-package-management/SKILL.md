---
name: linux-package-management
description: Manage packages safely across Arch/CachyOS, Debian/Ubuntu, RHEL/Fedora and containers—pinning, rollback, keyring trust, dependency repair, and upgrade strategy.
metadata:
  domain: devops-and-linux
  version: 1.0.0
  risk: high
---

# Linux Package Management

## 1. Purpose

Install, upgrade, pin, and roll back software without breaking the system or silently trusting unknown code. This skill covers the differences between rolling (Arch/CachyOS) and fixed-release (Debian, RHEL) models, keyring and signature trust, partial upgrades, dependency conflicts, and recovery when a package operation goes wrong. Package managers run as root and modify the base system—every destructive action needs a snapshot or a documented rollback.

**Scope:** systems you administer. Never add third-party repositories or keys without verifying ownership and purpose.

## 2. Activation Conditions

- Installing or upgrading packages, or resolving dependency conflicts.
- System upgrade planning (especially Arch rolling releases).
- Adding a third-party repository or PPA.
- A broken package database, held package, or failed update.
- Keywords: pacman, paru, yay, apt, dpkg, dnf, rpm, AUR, PPA, keyring, dependency hell, pin version, downgrade, orphans.

## 3. When Not to Use

- Language-level dependency management (pip/npm/cargo) — use the corresponding engineering skill.
- Container image contents (use container skills); though base-image packages follow these rules.
- Configuring the software after installation.

## 4. Required Context

1. Distribution and release (`/etc/os-release`), package manager version.
2. Whether the system is rolling (Arch/CachyOS) or fixed-release.
3. Current state: pending updates (`pacman -Qu`, `apt list --upgradable`, `dnf check-update`).
4. Repositories configured and their trust anchors.
5. Backup/snapshot capability (btrfs snapshots, timeshift, VM snapshot).
6. Services that will restart during upgrade.

## 5. Operating Procedure

1. **Read before you run**: check `/etc/os-release`, `pacman -Q --info`/`dpkg -l` state, and pending updates.
2. **Take a snapshot or verify backups** before a full upgrade, especially on rolling releases.
3. **Refresh metadata first**, then upgrade: Arch: `pacman -Syu` (never partial `-Sy` alone); Debian: `apt update && apt full-upgrade`; Fedora: `dnf upgrade --refresh`.
4. **Read the news** on rolling releases (Arch news) for manual interventions before upgrading.
5. **Install with intent**: exact package names, from official repos; avoid `--nodeps`, `--force`, `--overwrite`.
6. **Handle AUR carefully** (Arch/CachyOS): build from a reviewed PKGBUILD, never `curl | bash`, check the diff with the maintainer's version (`paru --diff`/`pikaur --review`).
7. **Pin or hold** when a version must not change: Arch `/etc/pacman.conf` `IgnorePkg`; Debian `apt-mark hold`; Fedora `dnf versionlock`.
8. **Third-party repos**: verify the vendor, import only their documented key, prefer signed-by keyrings over global `trusted=yes`.
9. **Resolve conflicts by understanding them** (which package owns the file, which dependency is unsatisfiable), not by forcing.
10. **Clean up** orphans (`pacman -Qtdq`), stale caches (`pacman -Sc`, `apt autoremove`), but review the list first.
11. **Verify**: services restart, kernel/bootloader entries intact, package signatures valid, no `.pacnew` files unmerged.
12. **Record** what changed with versions so a rollback is possible.

## 6. Tools and Technologies

| Distro family | Tools |
|---|---|
| Arch/CachyOS | `pacman`, `paru`/`yay`, `makepkg`, `paccache`, `pacman-contrib`, `reflector` |
| Debian/Ubuntu | `apt`, `dpkg`, `apt-mark`, `unattended-upgrades`, `debconf`, `add-apt-repository` |
| Fedora/RHEL | `dnf`, `rpm`, `dnf versionlock`, `rpmconf`, `subscription-manager` |
| Cross | `flatpak`, `snap` (sandboxed alternatives), `nix` |
| Audit | `pacman -Qkk`, `debsums`, `rpm -Va` |
| Rollback | btrfs snapshots, `pacman -U /var/cache/pacman/pkg/<older>.pkg.tar.zst`, `apt install pkg=version`, `dnf downgrade` |

## 7. Practical Implementation

**Arch/CachyOS — safe full upgrade:**

```bash
# 1) Snapshot (btrfs) before a big upgrade
sudo snapper -c root create -d "pre-upgrade $(date -u +%F)"

# 2) Read the news for required manual interventions
curl -fsS https://archlinux.org/feeds/news/ | head -40   # or a feed reader

# 3) Full sync + upgrade (never -Sy without -u)
sudo pacman -Syu

# 4) Merge config changes
sudo pacdiff -s            # package: pacman-contrib
# 5) Check for problems
pacman -Qkk 2>&1 | grep -v '0 altered files' | head
systemctl --failed
```

**Arch — install, query, pin, and remove:**

```bash
sudo pacman -S --needed --asdeps libfoo     # explicit dependency
pacman -Qi libfoo
pacman -Ql libfoo | head
pacman -Qo /usr/bin/foo                     # which package owns a file
sudo pacman -Rns libfoo                     # remove with config + unneeded deps
pacman -Qtdq                                # orphans (review before removing)
sudo pacman -Rns $(pacman -Qtdq)            # only if the list looks correct
```

**Arch — pin a package in `/etc/pacman.conf`:**

```ini
[options]
IgnorePkg = linux linux-headers
IgnoreGroup = 
```

**Arch/CachyOS — AUR review workflow:**

```bash
paru -G --print-comments pkgname > /dev/null 2>&1 || true
paru --review pkgname          # review PKGBUILD before building
# Manual, most explicit:
git clone https://aur.archlinux.org/pkgname.git /tmp/pkgname && cd /tmp/pkgname
less PKGBUILD                  # inspect sources, checksums, install scripts
makepkg -si --cleanbuild
```

**Arch — rollback a bad package:**

```bash
ls /var/cache/pacman/pkg/libfoo-*        # older versions are cached by default
sudo pacman -U /var/cache/pacman/pkg/libfoo-1.2.3-1-x86_64.pkg.tar.zst
# pin it until upstream fixes the issue:
echo "IgnorePkg = libfoo" | sudo tee -a /etc/pacman.conf
```

**Debian/Ubuntu:**

```bash
sudo apt update
apt list --upgradable
sudo apt full-upgrade -y
sudo apt-mark hold openssl
sudo apt-mark unhold openssl
apt-cache policy openssl
sudo apt install openssl=3.0.13-0ubuntu3.4     # pin a version
sudo apt install --reinstall openssl
sudo dpkg --configure -a                        # repair interrupted installs
sudo apt --fix-broken install
sudo apt autoremove --purge
```

**Third-party repo done safely (Debian):**

```bash
# Vendor key into a dedicated keyring, referenced with signed-by (no global trust)
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://vendor.example.com/key.asc | sudo gpg --dearmor -o /etc/apt/keyrings/vendor.gpg
echo "deb [signed-by=/etc/apt/keyrings/vendor.gpg] https://vendor.example.com/apt stable main" \
  | sudo tee /etc/apt/sources.list.d/vendor.list
sudo apt update
```

**Fedora/RHEL:**

```bash
sudo dnf upgrade --refresh
sudo dnf install pkg
sudo dnf versionlock add pkg
sudo dnf downgrade pkg-1.2.3-1.fc40
sudo dnf repoquery --duplicates
sudo rpm -V pkg            # verify file integrity
sudo rpm -qa --last | head
```

**Archive integrity check:**

```bash
sudo pacman -Qkk | grep -vE '0 altered files$' | head -20     # Arch
sudo debsums -c                                              # Debian (package: debsums)
sudo rpm -Va --nofiles --nodigest | head                     # Fedora/RHEL
```

**Cache cleanup with limits:**

```bash
sudo paccache -r -k 2          # keep 2 versions of each package
sudo paccache -ruk0            # remove all uninstalled package versions
sudo pacman -Sc                # clean sync db + uninstalled packages (asks)
sudo apt clean && sudo apt autoremove --purge
sudo dnf clean all
```

## 8. Quality Standards

- Full upgrades are never partial on rolling releases (`-Syu`, not `-Sy` then `-S`).
- Snapshots/backups exist before major upgrades, and the rollback path is known.
- Third-party repositories use dedicated keyrings and `signed-by`, never `trusted=yes`.
- AUR packages are reviewed, not blindly installed; `--noconfirm` is not used for AUR.
- No `--force`, `--nodeps`, or `--overwrite` without a documented reason.
- `.pacnew`/`.rpmsave`/`.dpkg-dist` files are merged, not ignored.
- Orphan removal and cache cleanup are reviewed before execution.
- Version pins are recorded with the reason and a review date.

## 9. Verification and Testing

```bash
# Arch
pacman -Qkk | grep -vE '0 altered files$'
systemctl --failed
journalctl -p err -b --no-pager | tail -20
uname -r && pacman -Q linux
# Debian
dpkg --audit
debsums -c
apt-mark showhold
# Fedora
sudo rpm -Va --nofiles --nodigest
sudo dnf check
```

Expected evidence: no failed units, no altered files outside expected config areas, bootloader entries valid, and services responding after restart. After a rollback: the package version is confirmed via `pacman -Q`/`dpkg -s`/`rpm -q`.

## 10. Security Considerations

- Every new repository is a trust decision: a compromised repo can replace any package. Verify the vendor and use signed repos.
- Do not disable signature verification (`SigLevel = Never` is never acceptable).
- `curl <url> | sudo bash` installers bypass the package manager's integrity model—download, verify checksum/signature, review.
- AUR PKGBUILDs execute code during build: read `build()`, `package()`, and any `.install` scriptlet; check source URLs and hashes.
- Keep the keyring updated (`archlinux-keyring`), and investigate signature errors rather than bypassing them.
- Package-manager caches may contain sensitive config backups; restrict access.
- Unattended upgrades on servers should be scoped to security updates and paired with monitoring; automatic reboots need policy.

## 11. Failure Handling

- **"failed to commit transaction (conflicting files)":** identify the owning package (`pacman -Qo <file>`); resolve by removing the conflicting package or using `--overwrite` only for a known-good case.
- **Broken dependencies after partial upgrade:** complete the full upgrade (`pacman -Syu`); never leave a rolling system half-upgraded.
- **Signature unknown/untrusted:** update `archlinux-keyring`, check system clock, and verify the mirror; do not set `SigLevel = Never`.
- **Boot broken after kernel update:** boot the fallback/previous kernel entry, reinstall the kernel and initramfs, check free space in `/boot`.
- **dpkg interrupted:** `sudo dpkg --configure -a` then `sudo apt --fix-broken install`.
- **Held package blocks an upgrade:** check why it was held (`apt-mark showhold`, `IgnorePkg`), upgrade the dependency chain first, then release the pin.

## 12. Expected Deliverables

1. Environment and repository inventory.
2. Pre-upgrade snapshot/backup evidence.
3. Executed command list with package versions before/after.
4. Pins/holds and their justification.
5. Verification output (integrity, failed units, services).
6. Rollback procedure specific to the change.

## 13. References

- Arch Wiki — pacman — https://wiki.archlinux.org/title/Pacman
- Arch Wiki — system maintenance — https://wiki.archlinux.org/title/System_maintenance
- Arch Wiki — Arch User Repository — https://wiki.archlinux.org/title/Arch_User_Repository
- CachyOS documentation — https://wiki.cachyos.org/
- Debian Administrator's Handbook — apt — https://debian-handbook.info/browse/stable/sect.apt-get.html
- `apt(8)` — https://manpages.debian.org/bookworm/apt/apt.8.en.html
- Fedora docs — DNF — https://docs.fedoraproject.org/en-US/quick-docs/dnf/
- `pacman.conf(5)` — https://man.archlinux.org/man/pacman.conf.5
