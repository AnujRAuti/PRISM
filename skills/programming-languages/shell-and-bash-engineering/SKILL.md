---
name: shell-and-bash-engineering
description: Write shell scripts that fail loudly and safely—strict mode, quoting, trap cleanup, argument parsing, and shellcheck-clean portability.
metadata:
  domain: programming-languages
  version: 1.0.0
  risk: high
---

# Shell and Bash Engineering

## 1. Purpose

Write shell scripts that behave correctly under failure, spaces in filenames, and partial execution. Shell is the most dangerous glue language: `rm -rf $DIR/` with an empty variable, unquoted variables splitting on spaces, missing `set -e` letting a script continue after a failure, and traps that leave temp files and locks behind. This skill covers strict mode, quoting, cleanup, argument handling, and testing.

**Scope:** scripts you run on systems you administer. Shell scripts routinely run as root and delete data: default to read-only, require explicit confirmation for destructive operations, never interpolate untrusted input into a command, and never `curl | bash` an unverified script. Validate every path and variable before use.

## 2. Activation Conditions

- Automating deployment, backup, cleanup, or provisioning steps.
- A script failed silently, half-applied, or deleted the wrong thing.
- CI steps written inline in YAML growing beyond a few lines.
- Portability questions (bash vs. POSIX sh, macOS vs. Linux).
- Keywords: bash, shellcheck, set -euo pipefail, trap, quoting, shopt, getopts, POSIX, shebang, IFS, tempfile, trap EXIT, CachyOS, Arch Linux.

## 3. When Not to Use

- Logic beyond ~200 lines with data structures or tests (use Python or Go; shell has no types).
- Complex JSON/YAML processing (use `jq`/`yq` but keep orchestration minimal; prefer a real language).
- Cross-platform application installers with GUI flows.

## 4. Required Context

1. Target shells and platforms (bash version, busybox/ash on Alpine, POSIX sh).
2. Privilege level the script runs with.
3. Inputs: arguments, environment, config files.
4. Idempotency requirements (can it be re-run safely?).
5. Failure semantics required by the caller (exit codes, CI step behavior).

## 5. Operating Procedure

1. **Start every script with the strict-mode prelude** and a deliberate shebang: `#!/usr/bin/env bash` for bash features, `#!/bin/sh` for POSIX-only.
2. **Quote every expansion** (`"$var"`, `"${arr[@]}"`), and set `IFS=$'\n\t'` when word-splitting semantics matter.
3. **Use `[[ ]]` in bash** (not `[ ]`), `$(( ))` for arithmetic, and `printf '%s\n'` instead of `echo` for arbitrary data.
4. **Clean up with `trap`**: `trap cleanup EXIT INT TERM`, remove temp dirs created with `mktemp -d`, and release locks.
5. **Validate inputs and preconditions before acting**: required args, files exist, commands available (`command -v`), correct user/privileges.
6. **Parse arguments explicitly** with `getopts` (POSIX) or a `while` loop with a `usage()` function; reject unknown flags.
7. **Make destructive operations explicit**: print the target, require `--yes` or a typed confirmation, and never run `rm -rf` on a variable that could be empty (`rm -rf -- "${dir:?}"`).
8. **Prefer idempotent operations** (`mkdir -p`, `install -D`, checks before create) so re-runs are safe.
9. **Write progress and errors to stderr** (`>&2`), keep stdout for data; include the failing command and line number.
10. **Log with timestamps and exit codes**, and propagate failures as meaningful non-zero codes.
11. **Lint with shellcheck and format with shfmt** in CI, and test with `bats` or a small harness.
12. **Consider portability explicitly**: bash 4+ features (`mapfile`, associative arrays) fail on macOS bash 3.2 and Alpine ash — check or document.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Lint/format | shellcheck, `shfmt` |
| Testing | `bats-core`, `shunit2`, custom harness with fixtures |
| Parsing | `jq` (JSON), `yq` (YAML), `awk`/`sed` for text |
| Templating | `envsubst` (with care), `sed` with escaping, or a real language |
| Portability | POSIX sh, `checkbashisms`, containers with target shells |
| Debug | `bash -x`, `set +e` selectively, `PS4` with line numbers |
| Privilege | `sudo -n` checks, `command -v`, capability checks |

## 7. Practical Implementation

**Strict-mode prelude with cleanup and error reporting:**

```bash
#!/usr/bin/env bash
# Rotate API credentials for the orders service.
set -Eeuo pipefail
IFS=$'\n\t'

readonly SCRIPT_NAME="${0##*/}"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
TMP_DIR=""

usage() {
    cat >&2 <<EOF
Usage: $SCRIPT_NAME [-e environment] [-n] [-h]

  -e  target environment (dev|staging|prod), default: dev
  -n  dry run (print actions, change nothing)
  -h  show this help
EOF
}

log()  { printf '%s [%s] %s\n' "$(date -u +%FT%TZ)" "${SCRIPT_NAME}" "$*" >&2; }
die()  { log "ERROR: $*"; exit 1; }

cleanup() {
    local exit_code=$?
    if [[ -n "${TMP_DIR}" && -d "${TMP_DIR}" ]]; then
        rm -rf -- "${TMP_DIR}"
    fi
    if (( exit_code != 0 )); then
        log "failed with exit code ${exit_code}"
    fi
    exit "${exit_code}"
}

on_error() {
    local line=$1 cmd=$2
    log "ERROR: command '${cmd}' failed at line ${line}"
}
trap cleanup EXIT
trap 'on_error "${LINENO}" "${BASH_COMMAND}"' ERR
```

**Argument parsing with validation:**

```bash
environment="dev"
dry_run=false

while getopts ":e:nh" opt; do
    case "${opt}" in
        e) environment="${OPTARG}" ;;
        n) dry_run=true ;;
        h) usage; exit 0 ;;
        :) die "option -${OPTARG} requires an argument" ;;
        \?) die "unknown option -${OPTARG}" ;;
    esac
done
shift $((OPTIND - 1))
(( $# == 0 )) || die "unexpected positional arguments: $*"

case "${environment}" in
    dev|staging|prod) ;;
    *) die "invalid environment: ${environment}" ;;
esac

command -v curl >/dev/null 2>&1 || die "curl is required"
[[ -n "${API_TOKEN:-}" ]] || die "API_TOKEN must be set"
```

**Safe destructive operation with explicit confirmation and path validation:**

```bash
prune_cache() {
    local cache_dir="${1:-}"
    [[ -n "${cache_dir}" ]] || die "cache directory is required"
    [[ "${cache_dir}" == /var/cache/orders/* ]] || die "refusing to prune outside /var/cache/orders: ${cache_dir}"
    [[ -d "${cache_dir}" ]] || die "not a directory: ${cache_dir}"

    local bytes
    bytes=$(du -sb -- "${cache_dir}" | cut -f1)

    if [[ "${dry_run}" == true ]]; then
        log "DRY RUN: would remove ${bytes} bytes from ${cache_dir}"
        return 0
    fi
    if [[ "${environment}" == "prod" && "${CONFIRM_PROD:-}" != "yes" ]]; then
        die "set CONFIRM_PROD=yes to prune in production"
    fi

    log "pruning ${bytes} bytes from ${cache_dir}"
    find -- "${cache_dir}" -mindepth 1 -maxdepth 1 -mtime +30 -print0 \
        | xargs -0 --no-run-if-empty rm -rf --
    log "prune complete"
}
```

**Correct iteration over filenames (spaces, newlines, globs):**

```bash
# BAD: breaks on spaces and globs; also fails on zero matches
for f in $(ls /data/incoming); do
    process "$f"
done

# GOOD: null-delimited, safe with any filename, works when empty
while IFS= read -r -d '' file; do
    process -- "$file"
done < <(find /data/incoming -maxdepth 1 -type f -name '*.csv' -print0)

# GOOD: bash glob with nullglob and array
shopt -s nullglob
files=(/data/incoming/*.csv)
(( ${#files[@]} )) || { log "no input files"; exit 0; }
for file in "${files[@]}"; do
    process -- "${file}"
done
```

**Temp files and locks (trap guarantees cleanup):**

```bash
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/orders-rotate.XXXXXXXX")"
readonly LOCK_FILE="/var/lock/orders-rotate.lock"

exec 9>"${LOCK_FILE}"
flock -n 9 || die "another instance is running (${LOCK_FILE})"

printf 'token=%s\n' "${API_TOKEN}" > "${TMP_DIR}/payload"
chmod 600 "${TMP_DIR}/payload"
curl --fail --silent --show-error --max-time 10 \
    --request POST --data "@${TMP_DIR}/payload" \
    "https://api.${environment}.example.com/v1/keys/rotate"
```

**Pipeline failure detection (`pipefail` and explicit checks):**

```bash
# Without pipefail, a failing producer is invisible if the consumer succeeds
set -o pipefail
if ! curl --fail --silent --show-error --max-time 30 "${URL}" | jq -e '.items | length > 0' >/dev/null; then
    die "fetch or parse failed for ${URL}"
fi
```

**Idempotent, rerunnable install step:**

```bash
install_unit() {
    local src="$1" dest="/etc/systemd/system/orders-api.service"
    if [[ -f "${dest}" ]] && cmp -s -- "${src}" "${dest}"; then
        log "unit already current: ${dest}"
        return 0
    fi
    install -o root -g root -m 0644 -- "${src}" "${dest}"
    systemctl daemon-reload
    log "installed ${dest}"
}
```

**Lint and test in CI:**

```bash
shellcheck --severity=warning --format=gcc scripts/*.sh
shfmt --diff --indent 4 scripts/
bash -n scripts/*.sh                       # syntax check without executing
bats --print-output-on-failure tests/      # behavior tests for arg parsing and helpers
```

```bash
#!/usr/bin/env bats
# tests/rotate.bats
setup() { load '../scripts/rotate.sh'; }

@test "rejects unknown environment" {
    run bash scripts/rotate.sh -e production
    [ "$status" -ne 0 ]
    [[ "$output" == *"invalid environment"* ]]
}

@test "dry run changes nothing" {
    run bash scripts/rotate.sh -n -e dev
    [ "$status" -eq 0 ]
    [[ "$output" == *"DRY RUN"* ]]
}

@test "fails cleanly when API_TOKEN is unset" {
    unset API_TOKEN
    run bash scripts/rotate.sh -e dev
    [ "$status" -ne 0 ]
    [[ "$output" == *"API_TOKEN must be set"* ]]
}
```

**CachyOS/Arch Linux–flavoured examples (package operations):**

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

# Check for updates without touching the system; requires no privileges.
check_updates() {
    command -v checkupdates >/dev/null || die "install pacman-contrib for checkupdates"
    local pending
    pending=$(checkupdates 2>/dev/null | wc -l) || true
    log "pending updates: ${pending}"
}

# Refresh mirrors, then upgrade; explicit confirmation for a full system upgrade.
upgrade_system() {
    [[ "${EUID}" -eq 0 ]] || die "run as root (sudo)"
    pacman -Sy --noconfirm --needed archlinux-keyring
    if [[ "${dry_run}" == true ]]; then
        pacman -Su --print
        return 0
    fi
    pacman -Su --noconfirm
    # Rebuild AUR packages against updated libs only with explicit intent:
    command -v paru >/dev/null && log "remember: paru -Sua for AUR packages"
}
```

## 8. Quality Standards

- Every script starts with `set -Eeuo pipefail`, a shebang, and a cleanup trap.
- All expansions are quoted; arrays are iterated as `"${arr[@]}"`; filenames are handled null-delimited.
- Destructive commands validate non-empty, absolute, allowlisted paths and require explicit confirmation in production.
- Inputs are validated before any side effect; errors go to stderr with a non-zero exit code.
- Temp files use `mktemp`, are `chmod 600` when sensitive, and are always removed by the trap.
- Concurrent runs are prevented with `flock` where state is shared.
- `shellcheck` and `shfmt` pass with no warnings in CI; `bash -n` runs pre-commit.
- Portability claims are tested in the target shell (bash vs. POSIX vs. busybox); bash-4-only features are documented.
- Scripts are idempotent where operationally required.

## 9. Verification and Testing

- `shellcheck --severity=warning` clean; `shfmt --diff` clean.
- `bats` tests cover argument validation, dry-run behavior, and failure paths.
- Run the script with `bash -x` in a staging environment and review each command executed.
- Test with hostile inputs: paths with spaces, newlines, leading dashes, and empty variables.
- Verify traps fire on `INT`/`TERM` (send Ctrl-C in a sandbox) and that temp files/locks are released.
- Confirm exit codes propagate: a failing step makes the CI job fail.

## 10. Security Considerations

- Never `eval` untrusted input, never build commands by string concatenation with external data, and never pass user input as a format string.
- `curl | bash` executes remote code: download, verify a checksum/signature, inspect, then run — or use a package manager.
- Validate and allowlist paths before `rm`, `mv`, `chown`, or `find -delete`; use `--` to end option parsing.
- Secrets must not appear in argv (visible in `ps`), shell history, or logs; read from files/env or a secret manager, and use `--data @file`.
- Set `umask 077` for files containing credentials; avoid writing them to disk at all where possible.
- Run with the least privilege possible; avoid `sudo` inside scripts and elevate only for specific commands if unavoidable.
- `IFS` manipulation and globbing can silently change targets — quote and use explicit paths.
- Logs and error messages must not echo tokens; redact before printing.
- Consider `set -o noclobber` to prevent accidental file clobbering, and `shred`/secure deletion policies where required.

## 11. Failure Handling

- **Script exits immediately on an expected non-zero command:** use `command || true` only with a comment, or wrap in `if`/`set +e` scoped narrowly.
- **`set -u` breaks on optional variables:** use `${VAR:-}` with an explicit default, not by removing `-u`.
- **`pipefail` surfaces failures in `grep` returning 1:** handle the no-match case explicitly (`grep -q ... || true` with a reason).
- **Trap not running cleanup:** `kill -9` cannot be trapped—design for a stale lock (check owner PID) and a stale temp dir sweep.
- **Works in bash, fails in POSIX sh:** `[[ ]]`, arrays, and `local` — either declare `#!/usr/bin/env bash` or rewrite with `[ ]` and no arrays.
- **Script behaves differently via cron:** cron has a minimal environment; set `PATH` explicitly and use absolute paths.

## 12. Expected Deliverables

1. Scripts with strict mode, trap cleanup, and usage/help output.
2. Validated argument parsing and precondition checks.
3. Safe destructive-operation patterns with confirmation and path allowlists.
4. shellcheck/shfmt CI integration.
5. `bats` tests for failure paths and dry-run behavior.
6. Portability notes and target-shell assumptions.
7. Logging/exit-code conventions.

## 13. References

- GNU Bash manual — https://www.gnu.org/software/bash/manual/
- Bash Pitfalls — https://mywiki.wooledge.org/BashPitfalls
- Google Shell Style Guide — https://google.github.io/styleguide/shellguide.html
- ShellCheck — https://www.shellcheck.net/
- shfmt — https://github.com/mvdan/sh
- bats-core — https://bats-core.readthedocs.io/
- POSIX shell command language — https://pubs.opengroup.org/onlinepubs/9699919799/utilities/V3_chap02.html
- `flock(1)` — https://man7.org/linux/man-pages/man1/flock.1.html
- Arch Wiki (pacman tips) — https://wiki.archlinux.org/title/Pacman/Tips_and_tricks
