---
name: fish-shell-automation
description: Automate Fish shell environments—config organization, functions, abbrs, event handlers, universal variables, and completions—while keeping scripts portable by using POSIX sh for automation logic.
metadata:
  domain: devops-and-linux
  version: 1.0.0
  risk: low
---

# Fish Shell Automation

## 1. Purpose

Use Fish effectively as an interactive shell and configuration layer without making automation non-portable. Fish has sane defaults (autosuggestions, syntax highlighting, no word splitting), but its syntax is not POSIX: automation written in Fish does not run under `sh`, `bash`, cron, or container `RUN` steps. This skill provides the correct division of labor: Fish for interactive ergonomics and environment setup, POSIX/Bash for scripts, plus the Fish-specific mechanics agents need (`set`, `string`, `argparse`, events, universal variables).

**Scope:** your own user environment and hosts you administer. Editing system-wide `/etc/fish` affects all users.

## 2. Activation Conditions

- Configuring a Fish environment (`config.fish`, functions, abbreviations).
- Writing Fish functions for interactive workflows.
- Setting up per-machine or per-project environment variables.
- Adding completions for a CLI tool.
- Debugging why a Fish function behaves differently than expected.
- Keywords: fish shell, config.fish, fisher, abbr, fish function, universal variables, `string` builtin, completions, prompt.

## 3. When Not to Use

- Portable automation scripts, CI steps, cron jobs, Dockerfile `RUN`, or anything invoked by `sh -c`—use POSIX sh/Bash (shell-scripting).
- Systems where Fish is not installed and cannot be installed.
- Complex programs—use Python/Go.

## 4. Required Context

1. Fish version (`fish --version`); 3.6+ recommended for `path` variables and modern `string`.
2. Config layout: `~/.config/fish/config.fish`, `conf.d/`, `functions/`, `completions/`.
3. Whether configuration must work across machines (dotfiles repo) or per machine.
4. Which secrets/environment variables are needed and how they are injected (keychain, 1Password CLI, direnv).
5. Plugin manager usage (fisher) and plugin inventory.

## 5. Operating Procedure

1. **Verify Fish version** and note incompatibilities (`path` variable support, `string pad`).
2. **Organize `conf.d/`** by concern — one file per topic, loaded in lexical order: `00-env.fish`, `10-aliases.fish`, `20-integrations.fish`. Keep `config.fish` nearly empty.
3. **Use universal variables** (`set -U`) for values that should persist across sessions but not be shared between machines; keep them out of dotfiles.
4. **Use `set -gx`** for exported environment variables. Since Fish 3.2, prefer the `fish_add_path` helper for `PATH`.
5. **Define functions** in `~/.config/fish/functions/<name>.fish` — one function per file so they autoload lazily.
6. **Use abbreviations** (`abbr`) for interactive expansion; use functions for logic. Abbrs are not aliases and must not be used inside scripts.
7. **Handle events** with `--on-event`, `--on-variable`, and `--on-process-exit` for reactive configuration.
8. **Write completions** with `complete -c` and dynamic candidates via command substitution.
9. **Guard interactive-only code** with `status is-interactive` so non-interactive `fish -c` calls stay fast and side-effect-free.
10. **Guard secrets** so they are never persisted to universal variables or dotfiles.
11. **Test** in `fish -i -c '...'` and in a clean environment (`fish --no-config`), plus a smoke test in `fish -c`.
12. **Keep shell scripts in `sh`/`bash`** and call them from Fish with arguments array-style.

## 6. Tools and Technologies

| Tool | Use |
|---|---|
| `fish_add_path` | Managed `PATH` updates (3.2+) |
| `set`, `string`, `argparse` | Core builtins for Fish logic |
| `abbr` | Interactive abbreviations |
| `complete` | Completion definitions |
| `fisher` | Plugin manager |
| `direnv` + `direnv hook fish` | Per-directory env |
| `starship`/`tide` | Prompts |
| `fish --no-config`, `fish_trace` | Debugging |

## 7. Practical Implementation

**Config layout:**

```
~/.config/fish/
├── config.fish
├── conf.d/
│   ├── 00-path.fish
│   ├── 10-editor.fish
│   └── 20-integrations.fish
├── functions/
│   └── gswb.fish
└── completions/
    └── deploy.fish
```

**`config.fish` (minimal):**

```fish
# Loaded once per interactive session. Keep this file near-empty.
if status is-interactive
    set -g fish_greeting ""
end
```

**`conf.d/00-path.fish`:**

```fish
# Idempotent: fish_add_path avoids duplicates automatically.
fish_add_path --global --prepend "$HOME/.local/bin"
fish_add_path --global --append "/opt/homebrew/bin"
```

**`conf.d/10-editor.fish`:**

```fish
if status is-interactive
    set -gx EDITOR nvim
    set -gx VISUAL nvim
    set -gx PAGER less
    set -gx LESS "-FRX"
end
```

**`conf.d/20-integrations.fish` (secrets via external CLI, never persisted):**

```fish
if status is-interactive
    if type -q direnv
        direnv hook fish | source
    end
    if type -q starship
        starship init fish | source
    end
end
```

**Function (`functions/gswb.fish`) — git switch with branch picker:**

```fish
function gswb --description "Switch to a local or remote git branch via fuzzy picker"
    if not git rev-parse --is-inside-work-tree >/dev/null 2>&1
        echo "not a git repository" >&2
        return 1
    end

    set -l branch (git branch --all --format='%(refname:short)' \
        | string replace --regex '^origin/' '' \
        | sort -u \
        | fzf --height=40% --prompt='branch> ')

    if test -z "$branch"
        return 1
    end

    git switch "$branch"; or git switch --track "origin/$branch"
end
```

**`argparse` in a Fish function:**

```fish
function deploy --description "Deploy build to an environment"
    argparse 'e/env=' 'n/dry-run' 'h/help' -- $argv
    or return 2

    if set -q _flag_help
        echo "usage: deploy -e <env> [-n]"
        return 0
    end
    if not set -q _flag_env
        echo "error: -e/--env is required" >&2
        return 2
    end

    switch $_flag_env
        case prod staging dev
        case '*'
            echo "error: invalid environment: $_flag_env" >&2
            return 2
    end

    if set -q _flag_n
        echo "dry run: would deploy to $_flag_env"
        return 0
    end

    echo "deploying to $_flag_env"
end
```

**Abbreviations (`conf.d/30-abbr.fish`):**

```fish
if status is-interactive
    abbr --add gs --position command 'git status --short --branch'
    abbr --add gd --position command 'git diff'
    abbr --add k --position command 'kubectl'
    abbr --add tf --position command 'terraform'
end
```

Note: abbrs expand in the interactive command line only. Do not depend on them inside functions or scripts.

**Event handler (react to directory changes):**

```fish
function __on_pwd --on-variable PWD --description "Reload env when entering a project"
    if test -f .envrc.local
        set -gx PROJECT_SCOPE (basename (pwd))
    end
end
```

**Dynamic completions (`completions/deploy.fish`):**

```fish
complete -c deploy -s e -l env -d "Target environment" \
    -x -a "dev staging prod"
complete -c deploy -s n -l dry-run -d "Preview only"
complete -c deploy -f    # no file completion by default

# Dynamic from an internal API
complete -c deploy -l service -x -a "(curl -fsS https://deploy.internal/api/services 2>/dev/null | string split \n)"
```

**Calling a POSIX script correctly from Fish (no word splitting surprises):**

```fish
set -l args --env=prod --artifact=/tmp/app.tar.gz
bash ./scripts/deploy.sh $args
```

**Universal vs global vs local variables:**

```fish
set -U fish_color_command cyan        # persists across sessions, per machine
set -gx DATABASE_URL postgres://localhost/dev   # exported, session-only
set -l tmp (mktemp)                    # function-local
set -e OLD_VAR                         # erase
set --show DATABASE_URL                # inspect scope and value
```

## 8. Quality Standards

- `config.fish` stays minimal; logic lives in `conf.d/` and `functions/`.
- Every function has `--description` and returns meaningful status codes.
- Interactive-only code is guarded by `status is-interactive` for startup speed.
- No secrets stored with `set -U` or committed in dotfiles.
- `PATH` managed only via `fish_add_path`, never by appending strings directly.
- Completions disable file completion where a fixed list is expected.
- Scripts intended for automation are not written in Fish.

## 9. Verification and Testing

```bash
fish --version
fish -n ~/.config/fish/config.fish          # syntax check
fish --no-config -c 'echo clean-start-ok'   # ensure no dependency on config
fish -c 'source ~/.config/fish/functions/gswb.fish; functions gswb | head'
fish -i -c 'abbr --show | head'             # interactive-only features
time fish -i -c exit                        # startup time (target < 150 ms)
fish_trace=1 fish -c 'source ~/.config/fish/conf.d/00-path.fish' 2>&1 | head -20
```

Expected evidence: syntax clean, startup time acceptable, functions autoload, completions appear on <kbd>Tab</kbd>, no duplicate `PATH` entries (`string split : $PATH | sort | uniq -d`).

## 10. Security Considerations

- Never store tokens in universal variables (`~/.config/fish/fish_variables` is plaintext).
- Prefer credential helpers or `op read`/`pass show` at the moment of use; keep values in `set -l` locals where possible.
- Dotfiles may be public: audit before pushing; check for hostnames, internal URLs, and env values.
- Sourcing external files (`source (curl ...)`) is remote code execution—download, review, then source.
- Plugins from `fisher` run arbitrary code at install: review before installing, pin versions in your dotfiles.
- Completions that call internal APIs should use timeouts and fail silently to avoid leaking internal hostnames in shared terminals.

## 11. Failure Handling

- **Function not found:** file must be named exactly `<name>.fish` in `~/.config/fish/functions/`; run `functions -q name` to test.
- **`set` behaves differently than `export`:** use `set -gx` for export; `set -Ux` persists.
- **`PATH` corrupted/duplicated:** inspect with `string split : $PATH | sort | uniq -c | sort -rn | head`; remove manual appends and rely on `fish_add_path`.
- **Script works in bash but not fish:** convert syntax (`$var` → `$var` is fine, but `$(...)` → `(...)`, `export X=y` → `set -gx X y`, `if [ ... ]` → `test ... ; and ...`), or move the script to bash.
- **Slow startup:** bisect `conf.d/` files by moving them aside; look for command substitutions at load time.
- **Plugin conflict:** `fisher list` then remove the offending plugin; prefer built-in features when equivalent.

## 12. Expected Deliverables

1. Organized config layout with per-concern `conf.d` files.
2. Function files with descriptions and error handling.
3. Abbreviations and completions.
4. Secret-loading strategy that avoids persistence.
5. Startup-time measurement and syntax-check output.
6. Note on which tasks were deliberately delegated to POSIX scripts.

## 13. References

- Fish documentation — https://fishshell.com/docs/current/index.html
- Fish tutorial — https://fishshell.com/docs/current/tutorial.html
- `fish_for_bash_users` — https://fishshell.com/docs/current/fish_for_bash_users.html
- `fish_add_path` — https://fishshell.com/docs/current/cmds/fish_add_path.html
- `complete` builtin — https://fishshell.com/docs/current/cmds/complete.html
- `abbr` builtin — https://fishshell.com/docs/current/cmds/abbr.html
- fisher plugin manager — https://github.com/jorgebucaran/fisher
- direnv — https://direnv.net/
