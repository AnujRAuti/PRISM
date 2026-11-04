---
name: rust-engineering
description: Write production Rust—ownership and borrow discipline, error handling with thiserror/anyhow, async with Tokio, unsafe justification, and clippy-clean builds.
metadata:
  domain: programming-languages
  version: 1.0.0
  risk: medium
---

# Rust Engineering

## 1. Purpose

Build Rust systems that are safe, correct, and maintainable. Rust removes whole classes of bugs at compile time, but it introduces its own: fighting the borrow checker with `clone()` everywhere, `unwrap()` in request paths, `unsafe` blocks nobody can justify, async code holding a `MutexGuard` across an `await`, and dependency trees that balloon build times. This skill covers ownership modeling, error design, concurrency, unsafe policy, and tooling.

**Scope:** your own crates and dependencies. `cargo` fetches and compiles third-party code (including build scripts that execute): review dependencies, pin with `Cargo.lock`, and run `cargo audit`/`cargo deny` in CI.

## 2. Activation Conditions

- New Rust service, CLI, or library.
- Borrow-checker battles leading to excessive cloning or `Rc<RefCell<>>`.
- Panics in production paths from `unwrap`/`expect`.
- Async runtime issues, deadlocks, or slow builds.
- Keywords: Rust, cargo, ownership, borrow checker, lifetimes, thiserror, anyhow, Result, Tokio, async, Send, Sync, clippy, miri, cargo deny, unsafe.

## 3. When Not to Use

- Rapid prototyping where a scripting language is faster to iterate.
- Frontend/UI work better served by TypeScript (unless WASM).
- Team with no Rust experience on a deadline-critical service (train first).

## 4. Required Context

1. Toolchain/edition (stable vs. nightly) and target platforms.
2. Application type: CLI, network service, embedded, library.
3. Concurrency model: threads, async runtime, or both.
4. Performance and binary-size constraints.
5. Dependency and licensing policy.

## 5. Operating Procedure

1. **Model ownership first**: decide what owns data and what borrows it; pass `&str`/`&[T]` in APIs and own (`String`/`Vec<T>`) at storage boundaries.
2. **Return `Result<T, E>` everywhere fallible**; use `thiserror` for library errors and `anyhow` (or a typed error) at the application boundary. Reserve `panic!` for invariant violations and never in request handling.
3. **Avoid `unwrap()`/`expect()` outside tests and startup**: use `?`, `ok_or_else`, and `expect("<invariant>")` only where a panic is genuinely impossible and documented.
4. **Design errors for the caller**: a library error enum must let callers match on causes (`NotFound`, `Conflict`, `Invalid`) rather than parse strings.
5. **Use `Cow`, `&str`, and iterators** instead of cloning into temporary `String`s; measure before reaching for `clone()`.
6. **In async code, never hold a `std::sync::Mutex` guard across `.await`** — use `tokio::sync::Mutex` or restructure to shorten the critical section.
7. **Bound concurrency** with `tokio::sync::Semaphore` and set timeouts on every network operation.
8. **Isolate and justify `unsafe`**: a `// SAFETY:` comment explaining the invariant, a safe wrapper, and Miri tests where applicable.
9. **Run the tooling in CI**: `cargo fmt --check`, `cargo clippy -- -D warnings`, `cargo test`, `cargo audit`, `cargo deny check`.
10. **Keep build times sane**: minimize features, avoid unnecessary proc macros in hot crates, use workspace dependency inheritance, and check `cargo tree -d` for duplicates.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Toolchain | `rustup`, stable/nightly, editions 2021/2024 |
| Errors | `thiserror` (libraries), `anyhow` (applications), custom enums |
| Async | Tokio, async-std, `tokio::time::timeout`, `futures` |
| Serialization | `serde`, `serde_json`, `bincode` |
| Web | `axum`, `actix-web`, `tonic` (gRPC) |
| Testing | built-in `#[test]`, `proptest`, `rstest`, `insta` snapshots |
| Lint/security | clippy, `cargo audit`, `cargo deny`, `cargo miri` |
| Profiling | `perf`, `flamegraph`, `tokio-console` |
| Docs | `cargo doc`, `#![deny(missing_docs)]` on libraries |

## 7. Practical Implementation

**Library errors with `thiserror` (matchable by callers):**

```rust
use thiserror::Error;

#[derive(Debug, Error)]
pub enum OrderError {
    #[error("order {0} not found")]
    NotFound(String),

    #[error("order {id} is in status {status}, cannot pay")]
    InvalidState { id: String, status: String },

    #[error("invalid field {field}: {reason}")]
    Validation { field: &'static str, reason: String },

    #[error("payment provider failed: {0}")]
    Payment(#[from] PaymentError),

    #[error("database error")]
    Db(#[from] sqlx::Error),
}

#[derive(Debug, Error)]
pub enum PaymentError {
    #[error("provider declined: {code}")]
    Declined { code: String },
    #[error("provider timeout after {0:?}")]
    Timeout(std::time::Duration),
}
```

**Application boundary with `anyhow` context (and no panics):**

```rust
use anyhow::{Context, Result};

pub async fn run(config_path: &Path) -> Result<()> {
    let raw = std::fs::read_to_string(config_path)
        .with_context(|| format!("reading config {}", config_path.display()))?;
    let cfg: Config = toml::from_str(&raw).context("parsing config")?;

    let pool = sqlx::postgres::PgPoolOptions::new()
        .max_connections(cfg.db_pool_size)
        .acquire_timeout(std::time::Duration::from_secs(3))
        .connect(&cfg.database_url)
        .await
        .context("connecting to database")?;

    serve(cfg, pool).await.context("server exited with error")
}
```

**Axum handler mapping typed errors to HTTP (no unwrap in the path):**

```rust
use axum::{http::StatusCode, response::{IntoResponse, Response}, Json};
use serde_json::json;

impl IntoResponse for OrderError {
    fn into_response(self) -> Response {
        let (status, code) = match &self {
            OrderError::NotFound(_) => (StatusCode::NOT_FOUND, "not_found"),
            OrderError::InvalidState { .. } => (StatusCode::CONFLICT, "invalid_state"),
            OrderError::Validation { .. } => (StatusCode::UNPROCESSABLE_ENTITY, "validation"),
            OrderError::Payment(_) => (StatusCode::BAD_GATEWAY, "payment_failed"),
            OrderError::Db(_) => (StatusCode::INTERNAL_SERVER_ERROR, "internal"),
        };
        // Log full detail server-side; return a safe problem body to the client.
        if status == StatusCode::INTERNAL_SERVER_ERROR {
            tracing::error!(error = ?self, "request failed");
        }
        (
            status,
            Json(json!({"type": format!("/problems/{code}"), "status": status.as_u16()})),
        )
            .into_response()
    }
}
```

**Async with timeouts and bounded concurrency:**

```rust
use std::sync::Arc;
use tokio::{sync::Semaphore, time::{timeout, Duration}};

pub struct Enricher {
    client: reqwest::Client,
    permits: Arc<Semaphore>,
}

impl Enricher {
    pub async fn fetch(&self, sku: &str) -> Result<Quote, EnrichError> {
        let _permit = self.permits.acquire().await.map_err(|_| EnrichError::Closed)?;
        let resp = timeout(Duration::from_secs(2), self.client.get(format!("/quotes/{sku}")).send())
            .await
            .map_err(|_| EnrichError::Timeout)?
            .map_err(EnrichError::Http)?;
        resp.error_for_status_ref().map_err(EnrichError::Http)?;
        resp.json::<Quote>().await.map_err(EnrichError::Decode)
    }
}

pub async fn enrich_all(enr: &Enricher, skus: &[String]) -> Vec<Result<Quote, EnrichError>> {
    let futs = skus.iter().map(|s| enr.fetch(s));
    futures::future::join_all(futs).await   // errors are per-item, not all-or-nothing
}
```

**Correct shared state in async (`tokio::sync::Mutex`, short critical section):**

```rust
use std::collections::HashMap;
use tokio::sync::Mutex;

pub struct IdempotencyCache {
    inner: Mutex<HashMap<String, Vec<u8>>>,   // tokio mutex: safe across await
}

impl IdempotencyCache {
    pub async fn get_or_insert<F, Fut>(&self, key: &str, produce: F) -> Vec<u8>
    where
        F: FnOnce() -> Fut,
        Fut: std::future::Future<Output = Vec<u8>>,
    {
        // Do not hold the guard across the producing future.
        if let Some(hit) = self.inner.lock().await.get(key).cloned() {
            return hit;
        }
        let value = produce().await;
        self.inner.lock().await.insert(key.to_string(), value.clone());
        value
    }
}
```

**Justified `unsafe` with a safe wrapper and tests:**

```rust
/// Parses a fixed-size header known to be 4 bytes by the caller's buffer check.
///
/// # Safety
/// `bytes.len()` must be at least 4. The caller guarantees this via `parse_header`.
pub unsafe fn read_u32_unchecked(bytes: &[u8]) -> u32 {
    u32::from_be_bytes([bytes[0], bytes[1], bytes[2], bytes[3]])
}

pub fn parse_header(bytes: &[u8]) -> Option<u32> {
    if bytes.len() < 4 {
        return None;
    }
    // SAFETY: length checked immediately above.
    Some(unsafe { read_u32_unchecked(bytes) })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn short_header_is_none() {
        assert_eq!(parse_header(&[0, 1]), None);
    }

    #[test]
    fn parses_big_endian() {
        assert_eq!(parse_header(&[0, 0, 0, 7]), Some(7));
    }
}
```

**Iterator-based processing instead of clone-heavy loops:**

```rust
pub fn total_cents(orders: &[Order]) -> i64 {
    orders
        .iter()
        .flat_map(|o| o.lines.iter())
        .map(|l| l.unit_cents * i64::from(l.quantity))
        .sum()
}

pub fn describe(order: &Order) -> String {
    // Cow avoids allocating when no transformation is needed
    let name: std::borrow::Cow<'_, str> = if order.customer_name.is_empty() {
        std::borrow::Cow::Borrowed("unknown customer")
    } else {
        std::borrow::Cow::Borrowed(&order.customer_name)
    };
    format!("order {} for {}", order.id, name)
}
```

**CI toolchain:**

```bash
cargo fmt --all --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test --all-features
cargo audit
cargo deny check licenses advisories bans sources
cargo tree -d | head -20          # duplicate crate versions slow builds
cargo build --release --locked
```

```toml
# deny.toml
[advisories]
vulnerability = "deny"
unmaintained = "warn"

[licenses]
allow = ["MIT", "Apache-2.0", "BSD-3-Clause", "ISC", "Unicode-3.0"]

[bans]
multiple-versions = "warn"
deny = [{ name = "openssl-sys", reason = "use rustls for consistent TLS behaviour" }]
```

## 8. Quality Standards

- No `unwrap()`/`expect()` in request or job paths; `expect` only for proven invariants with a message.
- Library crates expose a typed error enum; application binaries add context with `anyhow`.
- No `std::sync` guards held across `.await`.
- All network operations have timeouts; concurrency is bounded by semaphores or pools.
- Every `unsafe` block has a `// SAFETY:` justification and a safe wrapper; Miri runs on unsafe-heavy crates.
- `cargo fmt --check` and `cargo clippy -D warnings` pass in CI.
- `cargo audit`/`cargo deny` pass with documented exceptions.
- Public library items are documented; `#![deny(missing_docs)]` where appropriate.
- `Cargo.lock` is committed for binaries; dependencies are minimized and feature-gated.

## 9. Verification and Testing

```bash
cargo test --all-features -- --nocapture
cargo test --release                        # catches overflow/optimization differences
RUSTFLAGS="-Z sanitizer=thread" cargo +nightly test --target x86_64-unknown-linux-gnu
cargo miri test                             # undefined behaviour in unsafe code
cargo insta test --review                   # snapshot tests for serialization/output
```

- Property tests with `proptest` for parsers and arithmetic (round-trips, invariants).
- Load test the service and inspect `tokio-console` for task starvation and blocked tasks.
- `cargo llvm-cov` for coverage; `cargo bench`/criterion for performance claims.
- Verify builds with `--locked` to confirm the lockfile is authoritative.

## 10. Security Considerations

- `unsafe` is the boundary of Rust's guarantees: require review, keep blocks minimal, and prefer safe alternatives.
- Deserialization of untrusted input (serde) must use bounded sizes; avoid `bincode` on hostile data without limits.
- Constant-time comparison for secrets (`subtle` crate); `rand` vs. `rand_core` — use `OsRng` for cryptographic randomness.
- Never `include!` or `env!` secrets into binaries; they are extractable.
- TLS: prefer `rustls` with verified roots; never disable certificate validation to fix a test.
- Build scripts (`build.rs`) from dependencies execute at build time: allowlist crates and review surprises.
- `cargo deny` blocks unmaintained/vulnerable crates and disallowed licenses — keep it enforced.
- Path handling: canonicalize and check prefixes; do not trust `Path::join` alone for containment.

## 11. Failure Handling

- **Borrow-checker gridlock:** restructure ownership (own the data, pass references down) or split functions; `clone()` is a last resort with a comment explaining why.
- **Panic in production:** locate the `unwrap`/slice index/arithmetic overflow; convert to `Result`, use `get()` instead of indexing, and enable overflow checks in release if arithmetic is untrusted.
- **Async deadlock:** a lock held across `await`, or a task awaiting itself; shrink critical sections and prefer message passing.
- **Build times growing:** feature unification across the workspace; disable default features, split crates, and inspect `cargo tree -e features`.
- **Dependency advisories:** update or patch; if unavoidable, add a documented `deny.toml` exception with an expiry and an owner.

## 12. Expected Deliverables

1. Workspace layout with library/binary separation.
2. Error enums per crate and an application-level context strategy.
3. Async architecture with timeouts, bounded concurrency, and shutdown.
4. `unsafe` inventory with SAFETY justifications.
5. CI pipeline: fmt, clippy, test, audit, deny, locked builds.
6. Benchmarks and profiles for critical paths.

## 13. References

- The Rust Programming Language (book) — https://doc.rust-lang.org/book/
- Rust API guidelines — https://rust-lang.github.io/api-guidelines/
- `thiserror` — https://docs.rs/thiserror/
- `anyhow` — https://docs.rs/anyhow/
- Tokio tutorial — https://tokio.rs/tokio/tutorial
- Clippy lints — https://rust-lang.github.io/rust-clippy/master/
- `cargo audit` — https://rustsec.org/
- `cargo deny` — https://embarkstudios.github.io/cargo-deny/
- The Rustonomicon (unsafe) — https://doc.rust-lang.org/nomicon/
- Miri — https://github.com/rust-lang/miri
