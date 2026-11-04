---
name: shell-scripting
description: Write robust POSIX/Bash scripts—strict mode, argument parsing, safe quoting, traps, temp files, and idempotent operations—that fail loudly instead of silently.
metadata:
  domain: devops-and-linux
  version: 1.0.0
  risk: medium
---

# Shell Scripting

## 1. Purpose

Produce shell scripts that behave predictably under failure, with no spaces, no special characters, and no interrupted processes. Most production shell bugs come from unquoted variables, unchecked exit codes, unsafe temp files, and parsing `ls`. This skill encodes the defensive patterns and provides a reusable template.

**Scope:** scripts you write for your own systems. Scripts that modify production run with privileges—require review and a dry-run mode.

## 2. Activation Conditions

- Automating a sequence of Linux commands for deployment, backup, or maintenance.
- Writing a CI helper, container entrypoint, or cron job.
- A shell script fails intermittently or breaks on filenames with spaces.
- Reviewing a script before it runs with sudo.
- Keywords: bash, shell script, POSIX sh, set -euo pipefail, quoting, trap, getopts, shebang, idempotent script.

## 3. When Not to Use

- Logic beyond ~150 lines or requiring data structures—use Python/Go.
- Performance-critical loops over large data—shell forks per iteration are slow.
- Interactive TUIs.
- Anything that must run identically on Windows without WSL.

## 4. Required Context

1. Target shell: POSIX `sh` (dash/busybox), Bash, or Zsh/Fish (different skills).
2. Platforms: GNU vs. BSD userland differences (macOS).
3. Required privileges and whether `sudo` is available.
4. Input sources: arguments, env vars, files, stdin.
5. Failure policy: continue on error, abort, or retry.

## 5. Operating Procedure

1. **Choose the interpreter** deliberately: `#!/usr/bin/env bash` for Bash-isms, `#!/bin/sh` for portable scripts. Never rely on the user's interactive shell.
2. **Enable strict mode**: `set -euo pipefail`, and `IFS=$'\n\t'` where appropriate.
3. **Parse arguments** with `getopts` (POSIX) or manual `while` loop for long options; validate before doing anything.
4. **Define a usage function** and exit code conventions (0 success, 1 general error, 2 usage error).
5. **Quote everything**: `"${var}"`, `"${arr[@]}"`, `--` before operands.
6. **Use `mktemp`** for temp files and a `trap` for cleanup.
7. **Check commands explicitly** when not relying on `set -e` (conditions, pipelines, subshells).
8. **Make destructive operations dry-runnable** and require `--yes`/`-f` confirmation.
9. **Log with timestamps to stderr**, keep data on stdout.
10. **Handle signals**: `trap 'cleanup' EXIT INT TERM`.
11. **Test with `shellcheck`** and against filenames with spaces, empty vars, and missing files.
12. **Document** required env vars, dependencies, and examples at the top of the file.

## 6. Tools and Technologies

| Tool | Use |
|---|---|
| `shellcheck` | Static analysis (run in CI) |
| `shfmt` | Formatting |
| `bats-core` | Shell test framework |
| `getopts` / `argparse` libs | Argument parsing |
| `mktemp`, `trap` | Safe temp files and cleanup |
| `envsubst` | Template expansion (careful with secrets) |
| `timeout` | Bound long operations |

## 7. Practical Implementation

**Robust template:**

```bash
#!/usr/bin/env bash
# deploy.sh — deploy a build artifact to a host.
# Usage: deploy.sh -e <env> -a <artifact> [-n] [-h]
# Requires: curl, jq, sha256sum
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"
readonly LOG_PREFIX="[$(date -u +%Y-%m-%dT%H:%M:%SZ)]"

log()  { printf '%s %s\n' "$LOG_PREFIX" "$*" >&2; }
die()  { log "ERROR: $*"; exit 1; }
usage() { sed -n '2,4p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

cleanup() {
  local rc=$?
  [[ -n "${tmpdir:-}" && -d "$tmpdir" ]] && rm -rf -- "$tmpdir"
  (( rc == 0 )) || log "failed with exit code $rc"
  return $rc
}
trap cleanup EXIT INT TERM

main() {
  local env="" artifact="" dry_run=0
  while getopts ":e:a:nh" opt; do
    case "$opt" in
      e) env="$OPTARG" ;;
      a) artifact="$OPTARG" ;;
      n) dry_run=1 ;;
      h) usage 0 ;;
      :) die "option -$OPTARG requires an argument" ;;
      *) usage 2 ;;
    esac
  done
  shift $((OPTIND - 1))

  [[ -n "$env" ]] || die "-e is required"
  [[ -n "$artifact" ]] || die "-a is required"
  [[ -f "$artifact" ]] || die "artifact not found: $artifact"
  case "$env" in prod|staging|dev) ;; *) die "invalid env: $env" ;; esac

  tmpdir="$(mktemp -d)"
  local digest
  digest="$(sha256sum -- "$artifact" | cut -d' ' -f1)"
  log "artifact sha256=$digest env=$env dry_run=$dry_run"

  if (( dry_run )); then
    log "dry run: would upload $artifact to $env"
    return 0
  fi

  timeout 60 curl -fsS --retry 3 --retry-connrefused \
    -H "X-Artifact-SHA256: $digest" \
    --data-binary "@$artifact" \
    "https://deploy.internal/api/v1/${env}/artifacts" \
    -o "$tmpdir/resp.json" || die "upload failed"

  jq -e '.status == "accepted"' "$tmpdir/resp.json" >/dev/null \
    || die "unexpected response: $(head -c 200 "$tmpdir/resp.json")"
  log "deploy accepted"
}

main "$@"
```

**Safe file iteration:**

```bash
# WRONG: breaks on spaces, newlines
for f in $(ls *.log); do rm "$f"; done

# RIGHT: glob handles spaces; -0/-- handles leading dashes
for f in *.log; do
  [[ -e "$f" ]] || continue
  rm -f -- "$f"
done

# Reading NUL-delimited lists safely
find . -type f -name '*.log' -print0 | while IFS= read -r -d '' f; do
  printf 'processing %s\n' "$f"
done
```

**Checking command availability and versions:**

```bash
command -v jq >/dev/null || die "jq is required"
curl_ver="$(curl --version | head -n1 | awk '{print $2}')"
```

**Conditional without `set -e` pitfalls:**

```bash
if ! grep -q '^root:' /etc/passwd; then
  die "unexpected passwd file"
fi

# Pipelines: pipefail makes this work as intended
set -o pipefail
if ! grep -q 'enabled' /etc/feature.conf | head -n1 >/dev/null; then
  log "feature disabled"
fi
```

**Confirmation for destructive steps:**

```bash
if [[ "${FORCE:-0}" != "1" ]]; then
  read -r -p "Delete $target? type 'yes': " answer
  [[ "$answer" == "yes" ]] || die "aborted"
fi
```

**bats test:**

```bash
#!/usr/bin/env bats
setup() { load '/usr/lib/bats-support/load.bash'; }

@test "fails without -e" {
  run ./deploy.sh -a /etc/hostname
  [ "$status" -eq 1 ]
  [[ "$output" == *"-e is required"* ]]
}

@test "rejects unknown env" {
  run ./deploy.sh -e prodx -a /etc/hostname
  [ "$status" -eq 1 ]
}
```

## 8. Quality Standards

- `set -Eeuo pipefail` present unless justified.
- Every variable expansion is quoted.
- `shellcheck` clean (or every disable annotated with a reason).
- `trap` cleans temp resources on all exit paths.
- Exit codes are meaningful and documented.
- Scripts are idempotent where possible (re-running does not corrupt state).
- No secrets in code, args, or `ps`-visible command lines.
- `--help` works and states dependencies.

## 9. Verification and Testing

```bash
shellcheck -x deploy.sh
shfmt -d -i 2 deploy.sh
bash -n deploy.sh                 # syntax check
bash -x deploy.sh -h 2>&1 | head  # trace during development
bats tests/                       # unit tests
# adversarial inputs
./deploy.sh -e prod -a "file with spaces.tar.gz"
env -i PATH=/usr/bin:/bin ./deploy.sh -e prod -a /etc/hostname   # empty environment
```

## 10. Security Considerations

- Never `eval` untrusted input, and never build commands from user-supplied strings—use arrays: `cmd=("$bin" "$arg")`.
- Quote `--` before operands to prevent option injection from filenames starting with `-`.
- Do not write secrets to temp files without `umask 077` and immediate cleanup; prefer passing via stdin or file descriptors.
- `curl ... | bash` is a supply-chain risk; download, verify checksum/signature, then run.
- Avoid `sudo` inside scripts; require the caller to grant privilege and validate `id -u`.
- Validate paths before `rm -rf`: refuse empty variables, `/`, and unset variables (`rm -rf -- "${dir:?}"`).
- Log redaction: never echo tokens; mask with `${token:0:4}****`.

## 11. Failure Handling

- **`set -e` does not trigger in `if` contexts:** check explicitly with `|| die`.
- **Masked exit code in a pipeline:** use `curl -f` so HTTP errors become exit codes, and `pipefail`.
- **Script works in Bash, fails in `sh`:** remove Bash-isms (`[[ ]]`, arrays, `<<<`), or change the shebang.
- **Unicode/space filename failures:** switch to `find -print0` + `read -d ''`, and quote.
- **Partial failure leaves state:** implement idempotent steps and a rollback trap; log what changed before changing it.

## 12. Expected Deliverables

- The script with header documentation, strict mode, and traps.
- `shellcheck` and `shfmt` output.
- Unit tests (bats) for argument validation and failure paths.
- Usage examples and required environment variables.
- Dry-run demonstration and a rollback note for destructive scripts.

## 13. References

- Bash Reference Manual — https://www.gnu.org/software/bash/manual/bash.html
- BashFAQ (Greg's Wiki) — https://mywiki.wooledge.org/BashFAQ
- ShellCheck — https://www.shellcheck.net/
- POSIX Shell Command Language — https://pubs.opengroup.org/onlinepubs/9699919799/utilities/V3_chap02.html
- bats-core — https://github.com/bats-core/bats-core
- `sh(1p)` — https://pubs.opengroup.org/onlinepubs/9699919799/utilities/sh.html
