---
name: solid-principles
description: Apply SRP, OCP, LSP, ISP, and DIP pragmatically—detect violations with concrete smells and fix them without ceremony.
metadata:
  domain: software-engineering
  version: 1.0.0
  risk: low
---

# SOLID Principles

## 1. Purpose

Diagnose and fix design rigidity caused by class and module design errors. SOLID is a set of heuristics for managing dependencies: who depends on whom, what changes together, and what must remain substitutable. This skill converts the abstract principles into observable code smells, language-specific fixes, and refactoring moves—without turning every class into an interface.

## 2. Activation Conditions

- Adding a new variant (payment provider, export format, notification channel) and the change touches many files.
- Tests require heavy mocking of unrelated methods.
- Subclasses throw `NotImplementedError` or override methods to no-ops.
- Circular or layer-violating imports.
- Review comments: "tight coupling", "god class", "needs an interface".
- Keywords: SOLID, SRP, OCP, LSP, ISP, DIP, dependency injection, coupling, cohesion, substitutability.

## 3. When Not to Use

- Small scripts, DTOs, and data classes that legitimately have no behavior.
- When the cost of indirection (an extra interface) exceeds the cost of the expected change. YAGNI applies.
- Performance-critical code where virtual dispatch or allocation is measured as the bottleneck.
- As dogma: applying all five blindly produces "interface explosion" and abstract-factory ceremony.

## 4. Required Context

1. Language and idiom (Go's implicit interfaces, Rust's traits, Python's duck typing change how DIP/ISP look).
2. The set of known current and near-term variants of the concept being abstracted.
3. Dependency-injection mechanism in use (manual wiring, Spring, FastAPI `Depends`, `wire`, `tsyringe`).
4. Test setup—how easily can the unit be isolated today?
5. Module/layer boundaries and any enforced dependency rules.

## 5. Operating Procedure

1. **Map consumers.** For each class/module, list who calls it and which methods they use. Unused methods indicate ISP violation.
2. **Find change drivers.** List plausible future changes. If two unrelated reasons to change exist in one class, SRP is violated—split along the change axis, not per method.
3. **Check substitutability.** For each subtype/implementation: can it be used wherever the base type is expected without surprises? Watch for strengthened preconditions, weakened postconditions, and thrown `NotSupported`.
4. **Identify concrete dependencies.** Instantiation of collaborators inside the class, direct instantiation of clocks, HTTP clients, or DBs—these block testing and violate DIP.
5. **Introduce the narrowest possible abstraction.** Define interfaces on the *consumer* side with only the methods the consumer uses.
6. **Invert at the boundary.** Constructor/parameter injection, not service locators. Compose in a single composition root.
7. **Keep interfaces segregated** by consumer; do not create one `Repository` with 30 methods for 5 consumers.
8. **Preserve LSP by contract**, and add contract tests run against every implementation.
9. **Re-run tests**; add a test per new implementation, not per interface.
10. **Stop when the smell is gone.** Do not pre-abstract variants you cannot name.

## 6. Tools and Technologies

| Tool | Use |
|---|---|
| `import-linter` | Enforce layer/DIP rules in Python |
| ArchUnit (Java) | Enforce package dependency rules |
| `dependency-cruiser` (JS/TS) | Detect cycles and forbidden imports |
| Spring / Guice | DI containers (Java) |
| FastAPI `Depends` | Lightweight DI in Python |
| `wire` / `fx` (Go) | Compile-time / runtime DI |
| `unittest.mock` / `mockito` | Isolate collaborators in tests |
| Pact | Contract testing for substitutable implementations |

## 7. Practical Implementation

**SRP — split by change driver (Python):**

```python
# Violates SRP: pricing rules and persistence change for different reasons.
class Invoice:
    def total(self) -> int: ...
    def save(self) -> None: ...
    def render_pdf(self) -> bytes: ...

# Fixed: three collaborators, each with one reason to change.
class Invoice:            # domain calculation only
    def __init__(self, lines: list["Line"], tax: "TaxPolicy") -> None: ...
    def total(self) -> int: ...

class InvoiceRepository:   # persistence
    def save(self, invoice: Invoice) -> None: ...

class InvoicePdfRenderer:  # presentation
    def render(self, invoice: Invoice) -> bytes: ...
```

**OCP — extend without editing (TypeScript):**

```ts
interface Exporter { export(rows: Row[]): Promise<Buffer>; }

const exporters: Record<string, Exporter> = {
  csv: new CsvExporter(),
  xlsx: new XlsxExporter(),
};

function resolveExporter(kind: string): Exporter {
  const exporter = exporters[kind];
  if (!exporter) throw new Error(`unsupported export format: ${kind}`);
  return exporter;
}
```

**LSP — contract test across implementations (Python + pytest):**

```python
import pytest

class StoreContract:
    @pytest.fixture
    def store(self): raise NotImplementedError

    def test_get_missing_returns_none(self, store):
        assert store.get("absent") is None

    def test_put_then_get(self, store):
        store.put("k", "v")
        assert store.get("k") == "v"

class TestMemoryStore(StoreContract):
    @pytest.fixture
    def store(self): return MemoryStore()

class TestRedisStore(StoreContract):
    @pytest.fixture
    def store(self): return RedisStore(url="redis://localhost:6379/15")
```

**ISP + DIP — consumer-owned interface (Go):**

```go
// Consumer defines exactly what it needs.
type UserGetter interface {
    GetUser(ctx context.Context, id string) (User, error)
}

type WelcomeMailer struct{ users UserGetter }

func (m *WelcomeMailer) Send(ctx context.Context, id string) error {
    u, err := m.users.GetUser(ctx, id)
    if err != nil { return fmt.Errorf("get user %s: %w", id, err) }
    _ = u
    return nil
}
```

**DIP — inject the clock, do not call `time.Now()` inline (Go):**

```go
type Clock interface{ Now() time.Time }

type Service struct {
    clock Clock
    repo  Repository
}

func NewService(repo Repository, clock Clock) *Service {
    return &Service{repo: repo, clock: clock}
}
```

## 8. Quality Standards

- Interfaces exist only where there is ≥ 2 implementations or a genuine test/architecture boundary; each has a stated purpose.
- No consumer imports a concrete infrastructure type it does not need.
- Every implementation of an interface passes the same contract test suite.
- Composition root is a single, obvious place (`main.go`, `app/container.py`, `AppModule`).
- Dependency graph has no cycles (verified by tool).
- Depth of indirection: a reader can trace a call from entry point to side effect in ≤ 3 hops.

## 9. Verification and Testing

```bash
# Python

lint-imports          # import-linter contracts
pytest -q             # contract + unit tests
pydeps src --show-deps --noshow

# TypeScript
npx depcruise --config .dependency-cruiser.js src

# Java
./gradlew test        # ArchUnit rules run as tests
```

Evidence: contract tests green for all implementations; dependency-cycle check clean; a diff showing new variants added without modifying existing classes.

## 10. Security Considerations

- Inverting a dependency must not bypass authentication: keep authz checks in a single decorator/middleware, not duplicated per implementation.
- Do not inject permissive fakes into production paths for testing convenience.
- Interfaces that expose `execute(sql)`, `readFile(path)`, or `run(cmd)` widen attack surface—narrow them.
- Composition root is the correct place for secrets loading; never let a domain class read env vars directly.
- LSP violations in auth code can cause privilege escalation (a subtype that skips a check). Treat substitutability as security-relevant where permissions are involved.

## 11. Failure Handling

- **Interface explosion:** merge single-use interfaces back into concrete types until a second implementation appears.
- **DI container as magic:** if wiring is unreadable, prefer explicit manual construction in the composition root.
- **LSP breach by design:** if a variant cannot honor the contract, it is not a subtype—model with composition or a separate interface.
- **Tests still need mocks everywhere:** likely the unit boundary is wrong; move the boundary outward.
- **Over-abstraction warning sign:** every change now requires touching an interface, an impl, a factory, and a DI binding. Collapse layers.

## 12. Expected Deliverables

- Violation report listing each smell, the principle it violates, and the impacted files.
- Refactored code with narrow interfaces and a single composition root.
- Contract tests for shared abstractions.
- A note on what was deliberately *not* abstracted (and the trigger that would change that).

## 13. References

- Robert C. Martin, *Agile Software Development: Principles, Patterns, and Practices*.
- Barbara Liskov, "Data Abstraction and Hierarchy" (LSP origin).
- Martin Fowler, "Inversion of Control": https://martinfowler.com/bliki/InversionOfControl.html
- import-linter: https://import-linter.readthedocs.io/
- ArchUnit: https://www.archunit.org/
- dependency-cruiser: https://github.com/sverweij/dependency-cruiser
