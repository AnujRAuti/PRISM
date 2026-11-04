---
name: design-patterns
description: Select and implement GoF and enterprise patterns (strategy, adapter, factory, observer, repository, outbox, circuit breaker) with justified trade-offs.
metadata:
  domain: software-engineering
  version: 1.0.0
  risk: low
---

# Design Patterns

## 1. Purpose

Choose the right reusable design solution for a recurring structural problem, implement it idiomatically in the target language, and avoid pattern cargo-culting. This skill maps a stated problem (varying algorithms, third-party integration, object creation complexity, cross-cutting behavior, decoupling producers from consumers) to a named pattern, explains alternatives including "no pattern", and shows the implementation.

## 2. Activation Conditions

- A behavior varies by type, config, or tenant and is currently handled by `if/elif` or `switch` chains.
- Integrating a third-party SDK that must not leak into the domain.
- Object construction has many optional parameters or multi-step validation.
- Many objects must react to a state change without tight coupling.
- Need for cross-cutting behavior (retry, caching, logging, metrics) without editing every call site.
- Keywords: strategy, adapter, factory, builder, observer, decorator, repository, unit of work, circuit breaker, saga, outbox, pattern.

## 3. When Not to Use

- When a plain function, a dictionary, or a `switch` is clearer. Modern languages have first-class functions—`Strategy` is often just a function parameter.
- When only one implementation exists and no second is planned (YAGNI).
- Singleton for convenience—it is usually global state and harms testability. Prefer DI.
- Pattern names as status symbols in code review; judge by readability and change cost.

## 4. Required Context

1. The concrete problem, with two or three real examples of variation.
2. Language idioms: Go interfaces, Rust traits/enums, Python protocols, TS discriminated unions.
3. Whether concurrency is involved (patterns like Observer and Circuit Breaker change under concurrency).
4. Integration boundary and its failure modes (timeouts, partial failure, rate limits).
5. Team familiarity—an unfamiliar pattern costs maintenance.

## 5. Operating Procedure

1. **State the problem without naming a pattern.** "Three payment providers with different request shapes" or "audit logging needed on 12 handlers".
2. **List at least two candidate solutions**, including the naive one.
3. **Score on**: change cost when adding a variant, readability, testability, runtime overhead.
4. **Select** and name the pattern explicitly; record why in a comment or ADR.
5. **Define the seam**: interface/trait/protocol with the smallest surface.
6. **Implement one concrete variant first** and its tests.
7. **Add a second variant** to prove the seam is right; if the second forces interface changes, revisit the seam.
8. **Add the composite/decorator layer** for cross-cutting concerns if needed (retry, metrics).
9. **Wire selection logic in one place** (registry/factory) with explicit error for unknown keys.
10. **Document lifecycle**: who creates, who disposes, concurrency guarantees.

## 6. Tools and Technologies

| Pattern area | Tools / idioms |
|---|---|
| Strategy / Factory | Language function types, registries |
| Adapter | Domain port + infrastructure implementation |
| Repository / Unit of Work | ORM (`SQLAlchemy`, `Prisma`, `Hibernate`) |
| Observer | Event bus (`asyncio`, Node `EventEmitter`, NATS, Kafka) |
| Decorator | Middleware (FastAPI, Express, gRPC interceptors) |
| Circuit breaker | `resilience4j`, `pybreaker`, `opossum` |
| Retry with backoff | `tenacity` (Python), `p-retry` (Node), `backoff` crates |
| Distributed transactions | Transactional outbox + idempotent consumers, saga orchestration |
| Diagramming patterns | Mermaid class/sequence diagrams |

## 7. Practical Implementation

**Strategy with a registry (Python):**

```python
from typing import Protocol

class ShippingStrategy(Protocol):
    def quote(self, weight_g: int, distance_km: int) -> int: ...

class FlatRate:
    def quote(self, weight_g: int, distance_km: int) -> int:
        return 499

class DistanceBased:
    def quote(self, weight_g: int, distance_km: int) -> int:
        return max(499, distance_km * 12 + weight_g // 100)

_REGISTRY: dict[str, ShippingStrategy] = {
    "flat": FlatRate(),
    "distance": DistanceBased(),
}

def get_strategy(name: str) -> ShippingStrategy:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise ValueError(f"unknown shipping strategy: {name}") from None
```

**Adapter around a third-party SDK (TypeScript):**

```ts
export interface PaymentGateway {
  charge(amountMinor: number, currency: string, token: string): Promise<{ id: string; status: 'ok' | 'declined' }>;
}

export class StripeAdapter implements PaymentGateway {
  constructor(private readonly stripe: Stripe) {}
  async charge(amountMinor: number, currency: string, token: string) {
    const intent = await this.stripe.paymentIntents.create({
      amount: amountMinor, currency, payment_method: token, confirm: true,
    });
    return { id: intent.id, status: intent.status === 'succeeded' ? 'ok' : 'declined' };
  }
}
```

**Builder for multi-step config (Go):**

```go
type ServerConfig struct {
    Addr         string
    ReadTimeout  time.Duration
    MaxConns     int
}

type ServerOption func(*ServerConfig)

func WithAddr(a string) ServerOption { return func(c *ServerConfig) { c.Addr = a } }
func WithMaxConns(n int) ServerOption { return func(c *ServerConfig) { c.MaxConns = n } }

func NewServer(opts ...ServerOption) (*ServerConfig, error) {
    cfg := &ServerConfig{Addr: ":8080", ReadTimeout: 5 * time.Second, MaxConns: 100}
    for _, o := range opts { o(cfg) }
    if cfg.MaxConns <= 0 { return nil, errors.New("max conns must be positive") }
    return cfg, nil
}
```

**Transactional outbox (SQL):**

```sql
BEGIN;
INSERT INTO orders (id, status, total_cents) VALUES ($1, 'created', $2);
INSERT INTO outbox (id, topic, payload, created_at)
VALUES (gen_random_uuid(), 'order.created', $3::jsonb, now());
COMMIT;
-- A relay worker polls outbox, publishes, marks published_at — at-least-once delivery.
```

**Circuit breaker usage (Python):**

```python
import pybreaker

breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=30)

@breaker
def fetch_rate(source: str) -> Decimal: ...
```

## 8. Quality Standards

- The pattern solves a stated problem; the problem statement is written down.
- Interfaces are minimal and named in domain language, not `IAbstractFactoryImpl`.
- Unknown-key paths fail loudly with actionable errors.
- Cross-cutting decorators are composable and order-independent where possible.
- No global mutable singletons; dependencies are explicit.
- Concurrency semantics of every shared pattern instance are documented.
- Patterns are covered by at least one test per variant plus a selection test.

## 9. Verification and Testing

```bash
pytest -q tests/patterns            # Python
npm test -- --run tests/patterns    # Jest/Vitest
go test ./internal/... -race        # Go with race detector
cargo test && cargo clippy -- -D warnings
```

Checks: add a third variant in a test-only file and confirm zero production edits; run with `-race` for Observer/registry access; verify breaker opens after N failures in an integration test.

## 10. Security Considerations

- Adapters are trust boundaries: validate and normalize third-party responses; never pass through raw provider errors to users.
- Selection by string key must reject unknown values—untrusted input must not choose an unintended implementation.
- Decorators must not reorder security middleware (auth must run before business logic).
- Registries must not be mutable at runtime from external input (no plugin loading from user input or remote URLs).
- Watch deserialization in Observer payloads: prefer explicit schemas over `pickle`/`eval`-style loading.
- Circuit breakers can mask attacks (fail fast on mass requests); pair with rate limiting and alerting.

## 11. Failure Handling

- **Second variant needs interface change:** the seam was wrong; redesign before adding a third.
- **Registry grows unbounded:** enforce an allowlist and validate at startup.
- **Decorator ordering bugs:** test the composed chain, assert call order with spies.
- **Observer storm / feedback loops:** add deduplication keys and a max-depth or TTL on events.
- **Pattern not understood by the team:** simplify to the naive approach and document the intended refactor.

## 12. Expected Deliverables

- Problem statement and candidate comparison.
- Chosen pattern with rationale and alternatives rejected.
- Interface/port definitions and implementations.
- Selection/factory code with explicit error handling.
- Tests per variant, selection tests, and concurrency tests where relevant.

## 13. References

- *Design Patterns: Elements of Reusable Object-Oriented Software* (Gamma, Helm, Johnson, Vlissides).
- Martin Fowler, *Patterns of Enterprise Application Architecture* — https://martinfowler.com/books/eaa.html
- Refactoring.Guru pattern catalogue — https://refactoring.guru/design-patterns
- microservices.io (saga, outbox, CQRS) — https://microservices.io/patterns/
- tenacity — https://tenacity.readthedocs.io/
- resilience4j — https://resilience4j.readme.io/
