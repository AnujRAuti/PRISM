---
name: clean-code
description: Write and refactor code for readability, small units, explicit naming, and low cognitive load—while preserving observable behavior.
metadata:
  domain: software-engineering
  version: 1.0.0
  risk: low
---

# Clean Code

## 1. Purpose

Make code that another engineer (or agent) can change safely in six months. This skill governs naming, function size, structure, error handling, and comment discipline, and provides a behavior-preserving refactoring loop. It solves the common failure where working code is technically correct but unmaintainable: long functions, boolean parameters, primitive obsession, hidden side effects, and misleading names.

## 2. Activation Conditions

- Writing new functions, classes, or modules where readability matters.
- Reviewer feedback containing: "hard to read", "too long", "unclear", "duplicate logic".
- Before adding tests to untested code (clean first, then test).
- Keywords: clean code, readability, naming, refactor for clarity, duplication, magic numbers, god class, cognitive complexity.

## 3. When Not to Use

- Throwaway scripts and one-liners where clarity beyond the obvious is unnecessary.
- Minified/generated code, vendored third-party code.
- Performance-critical hot loops where readability must yield to measured optimization (document why).
- When a team style guide already covers the exact rule—follow it instead of imposing generic rules.

## 4. Required Context

1. Language, version, and formatter/linter configuration (`.editorconfig`, `ruff.toml`, `.eslintrc`, `golangci.yml`, `clippy.toml`).
2. Existing naming conventions in the repository—consistency beats preference.
3. Test suite presence and how to run it (`pytest`, `npm test`, `go test ./...`).
4. Whether the code is public API (changing names is a breaking change).
5. Domain glossary: what the business calls things (e.g. "policy" vs "contract").

## 5. Operating Procedure

1. **Establish a safety net.** Confirm tests pass before changing anything. If none exist, write characterization tests around the target behavior first.
2. **Read the whole unit before editing.** Note side effects, hidden state, and error paths.
3. **Name things.** Replace `data`, `tmp`, `res`, `handle` with domain-meaningful nouns. Functions get verb phrases (`calculate_tax`, not `tax`). Booleans read as assertions (`is_active`, `has_retries`).
4. **Flatten.** Replace nesting depth > 3 with guard clauses, early returns, and extracted helpers.
5. **Shrink functions** to one level of abstraction. Target ≤ 20 logical lines, ≤ 4 parameters; beyond that, pass a typed object.
6. **Remove duplication** only where the duplicated thing changes for the same reason. Premature deduplication of coincidentally similar code is worse than repetition.
7. **Replace primitives with types** when a value has units, bounds, or invariants (`Money`, `Email`, `UserId`, `Duration`).
8. **Make side effects explicit.** Functions that mutate state or perform I/O should say so in the name (`save`, `send`, `write`).
9. **Fix error handling.** Never swallow exceptions; include context in the message; use one error strategy per layer.
10. **Write comments only for "why",** not "what". Delete commented-out code (git remembers).
11. **Run formatter and linter**, then tests, after each small change.
12. **Commit in small, reviewable steps** with behavior-preserving intent stated.

## 6. Tools and Technologies

| Tool | Use |
|---|---|
| `ruff format` / `ruff check` | Python formatting + lint |
| `black`, `isort` | Legacy Python formatting |
| `mypy`, `pyright` | Type clarity |
| Prettier / ESLint / `tsc` | JS/TS |
| `gofmt`, `go vet`, `golangci-lint` | Go |
| `rustfmt`, `clippy` | Rust |
| SonarQube / CodeScene | Cognitive complexity and hotspots |
| `import-linter`, ArchUnit | Structural rules |

## 7. Practical Implementation

**Before:**

```python
def proc(d, t):
    r = []
    for x in d:
        if x['s'] == 1 and t is not None:
            if x['v'] > t:
                if x['a']:
                    r.append(x['id'])
                else:
                    r.append(x['id'])
        else:
            if x['s'] == 2:
                r.append(x['id'])
    return r
```

**After:**

```python
from dataclasses import dataclass
from typing import Iterable, Optional

@dataclass(frozen=True)
class Account:
    id: str
    status: int
    balance: int
    is_verified: bool

def is_chargeable(account: Account) -> bool:
    return account.status == 1 and account.is_verified

def select_chargeable_ids(accounts: Iterable[Account], minimum_balance: Optional[int]) -> list[str]:
    selected = []
    for account in accounts:
        if account.status == 2:
            selected.append(account.id)
        elif is_chargeable(account) and minimum_balance is not None and account.balance > minimum_balance:
            selected.append(account.id)
    return selected
```

**TypeScript — boolean parameter smell:**

```ts
// Before: process(user, true) — what does true mean?
function processUser(user: User, sendEmail: boolean) {}

// After
function processUser(user: User, options: { notify: boolean }) {}
```

**Rust — newtype for invariants:**

```rust
#[derive(Debug, Clone)]
pub struct Port(u16);

impl Port {
    pub fn new(value: u16) -> Option<Self> {
        if value == 0 { None } else { Some(Self(value)) }
    }
}
```

**Comment discipline:**

```python
# BAD: increments i
# GOOD: The provider bills in 30-day windows, so a month is not a calendar month.
```

## 8. Quality Standards

- Names are domain-meaningful and consistent with the codebase glossary.
- Functions do one thing; nesting ≤ 3; parameter count ≤ 4.
- No magic numbers or string literals repeated across the module—hoist to named constants.
- No dead code, no commented-out blocks, no `TODO` without an owner and issue link.
- Errors are never silently swallowed; every `catch`/`except` does something meaningful.
- Public API changes are additive or explicitly versioned.
- Linter and formatter pass with zero warnings on changed files.

## 9. Verification and Testing

```bash
# Python
ruff format --check . && ruff check . && mypy src && pytest -q

# TypeScript
npx tsc --noEmit && npx eslint . && npm test -- --run

# Go
gofmt -l . && go vet ./... && go test ./...

# Rust
cargo fmt --check && cargo clippy -- -D warnings && cargo test
```

Additional checks: a diff review that confirms only renames/structure changed; complexity report before/after (e.g. `radon cc -s src`); test count unchanged.

## 10. Security Considerations

- Renaming and refactoring must not change authorization checks or input validation—verify these line-by-line in the diff.
- Do not "clean up" logging so that audit events are removed.
- Never move secrets into constants; `const API_KEY` is still a secret. Keep secret access behind config/env loading.
- Extracting a function must not accidentally widen visibility (e.g. `private` → `public`).
- Avoid introducing reflection/dynamic dispatch for brevity—it hides control flow from security review.

## 11. Failure Handling

- **No tests:** write characterization tests that pin current behavior (including quirks) before refactoring.
- **Refactor breaks a test:** the test may encode incidental behavior; decide explicitly whether behavior or test is wrong.
- **Merge conflicts during cleanup:** keep refactors in separate commits from behavior changes so conflicts are mechanically resolvable.
- **Scope creep:** stop at the agreed file/unit; log further opportunities as issues.
- **Linter churn across the repo:** format only touched files; do not reformat the world in a feature PR.

## 12. Expected Deliverables

- Refactored or newly written code with unchanged public behavior.
- A short changelog of structural changes (what was renamed, what was extracted).
- Passing formatter, linter, and test evidence.
- List of deferred cleanups as tracked issues.

## 13. References

- Martin Fowler, *Refactoring: Improving the Design of Existing Code*, 2nd ed.
- Robert C. Martin, *Clean Code* (use critically; modern practice differs on some points).
- Google Engineering Practices — Code Review Developer Guide: https://google.github.io/eng-practices/review/
- Ruff documentation: https://docs.astral.sh/ruff/
- ESLint documentation: https://eslint.org/docs/latest/
- Clippy lint list: https://rust-lang.github.io/rust-clippy/master/
- Michael Feathers, *Working Effectively with Legacy Code* (characterization tests).
