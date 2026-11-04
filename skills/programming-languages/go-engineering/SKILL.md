---
name: go-engineering
description: Write idiomatic Go—error wrapping, context propagation, goroutine lifecycle, interface design, and race/benchmark discipline.
metadata:
  domain: programming-languages
  version: 1.0.0
  risk: medium
---

# Go Engineering

## 1. Purpose

Write Go that is simple, correct under concurrency, and observable. Go's traps are structural: goroutines that outlive their work, ignored `context` cancellation, errors swallowed or compared by string, interfaces defined before they are needed, and `go test -race` never run. This skill covers error handling, context propagation, concurrency patterns with bounded parallelism, interface design, module hygiene, and profiling.

**Scope:** your own code and modules. `go get` fetches and builds third-party code: pin versions in `go.sum`, review new dependencies, and never add a module from an unverified path.

## 2. Activation Conditions

- New Go service, CLI, or library.
- Race conditions, deadlocks, or goroutine leaks.
- Errors that lose context or are mishandled across layers.
- Module/build hygiene problems or slow builds.
- Keywords: Go, golang, context, errors.Is, errors.As, goroutine leak, errgroup, sync, interface, go.mod, go test -race, pprof, benchmark, generics, defer.

## 3. When Not to Use

- Heavy numerical/ML work better served by Python ecosystems.
- Scripting (use shell-scripting) or frontend code.
- Microservice architecture decisions (use backend-architecture).

## 4. Required Context

1. Go version and target platforms (GOOS/GOARCH matrix).
2. Service shape: HTTP/gRPC server, worker, CLI, library.
3. Concurrency requirements and shared state.
4. Dependency policy (module proxy, vendoring).
5. Observability stack for logs/metrics/traces.

## 5. Operating Procedure

1. **Return errors; do not panic** (except for truly unrecoverable programmer errors at startup). Wrap with `%w` and add context: `fmt.Errorf("load order %s: %w", id, err)`.
2. **Check errors with `errors.Is`/`errors.As`**, never string comparison; define sentinel errors or typed errors per package.
3. **Pass `context.Context` as the first parameter** through every call that can block; never store it in a struct; always `defer cancel()`.
4. **Bound goroutines**: use `errgroup` with `SetLimit`, a worker pool, or semaphores. Every goroutine must have a clear exit path and be waited on.
5. **Protect shared state explicitly** with `sync.Mutex` (documented invariants) or channels for ownership transfer; prefer immutability.
6. **Define interfaces at the consumer**, small (1–3 methods), only when a second implementation or a test fake exists.
7. **Handle `defer` correctly in loops**: extract the body into a function, or resources accumulate until the function returns.
8. **Run `go vet` and the race detector in CI**; treat data races as build failures.
9. **Benchmark before optimizing** and profile with `pprof`; know the allocation profile of hot paths.
10. **Keep modules tidy**: `go mod tidy`, pinned `go.sum`, minimal dependency surface, and vendoring only when builds require it.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Tooling | `go build`, `go vet`, `gofmt`/`goimports`, `staticcheck`, `golangci-lint` |
| Concurrency | `sync`, `errgroup`, `semaphore`, `context` |
| Errors | `fmt.Errorf("%w")`, `errors.Is/As`, custom typed errors |
| Testing | `testing`, `testify` (optional), `go test -race -count`, fuzz tests |
| Profiling | `net/http/pprof`, `go tool pprof`, `go test -bench -benchmem` |
| Modules | `go.mod`, `go.sum`, `GOPROXY`, `go work` |
| HTTP | `net/http`, chi, gin, echo; gRPC with protobuf |

## 7. Practical Implementation

**Error wrapping and typed errors:**

```go
package orders

import (
	"errors"
	"fmt"
)

var (
	ErrNotFound   = errors.New("order not found")
	ErrConflict   = errors.New("order state conflict")
)

type ValidationError struct {
	Field  string
	Reason string
}

func (e *ValidationError) Error() string {
	return fmt.Sprintf("invalid %s: %s", e.Field, e.Reason)
}

func (s *Service) Pay(ctx context.Context, id string) (*Order, error) {
	o, err := s.repo.Get(ctx, id)
	if err != nil {
		return nil, fmt.Errorf("get order %s: %w", id, err)
	}
	if o.Status != StatusPlaced {
		return nil, fmt.Errorf("%w: cannot pay order in status %s", ErrConflict, o.Status)
	}
	if o.TotalCents <= 0 {
		return nil, &ValidationError{Field: "total_cents", Reason: "must be positive"}
	}
	if _, err := s.payments.Charge(ctx, o.ID, o.TotalCents); err != nil {
		return nil, fmt.Errorf("charge order %s: %w", id, err)
	}
	return s.repo.MarkPaid(ctx, id)
}

// Callers distinguish causes without parsing strings.
func HandleError(w http.ResponseWriter, err error) {
	var verr *ValidationError
	switch {
	case errors.Is(err, ErrNotFound):
		http.Error(w, "not found", http.StatusNotFound)
	case errors.Is(err, ErrConflict):
		http.Error(w, "conflict", http.StatusConflict)
	case errors.As(err, &verr):
		http.Error(w, verr.Error(), http.StatusUnprocessableEntity)
	case errors.Is(err, context.DeadlineExceeded):
		http.Error(w, "timeout", http.StatusGatewayTimeout)
	default:
		http.Error(w, "internal error", http.StatusInternalServerError) // never leak internals
	}
}
```

**Context propagation with timeouts and cancellation:**

```go
func (h *Handler) CreateOrder(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()

	var req CreateOrderRequest
	dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)) // bound the body
	dec.DisallowUnknownFields()
	if err := dec.Decode(&req); err != nil {
		http.Error(w, "invalid request", http.StatusBadRequest)
		return
	}

	order, err := h.svc.Create(ctx, req)
	if err != nil {
		HandleError(w, err)
		return
	}
	w.Header().Set("Location", "/v1/orders/"+order.ID)
	w.WriteHeader(http.StatusCreated)
	_ = json.NewEncoder(w).Encode(order)
}
```

**Bounded parallel work with `errgroup` (no leaked goroutines):**

```go
import "golang.org/x/sync/errgroup"

func (s *Service) Enrich(ctx context.Context, ids []string) ([]Enriched, error) {
	g, ctx := errgroup.WithContext(ctx)
	g.SetLimit(8) // cap in-flight work; protects downstreams

	results := make([]Enriched, len(ids))
	for i, id := range ids {
		i, id := i, id // capture loop vars (pre-1.22 idiom; explicit for clarity)
		g.Go(func() error {
			e, err := s.fetch(ctx, id)
			if err != nil {
				return fmt.Errorf("enrich %s: %w", id, err)
			}
			results[i] = e // each goroutine writes its own index
			return nil
		})
	}
	if err := g.Wait(); err != nil {
		return nil, err // the first error cancels ctx for the rest
	}
	return results, nil
}
```

**Worker pool with graceful shutdown:**

```go
func Run(ctx context.Context, jobs <-chan Job, workers int) error {
	var wg sync.WaitGroup
	wg.Add(workers)
	errCh := make(chan error, workers)

	for i := 0; i < workers; i++ {
		go func(workerID int) {
			defer wg.Done()
			for {
				select {
				case <-ctx.Done():
					return
				case job, ok := <-jobs:
					if !ok {
						return
					}
					if err := process(ctx, job); err != nil {
						errCh <- fmt.Errorf("worker %d job %s: %w", workerID, job.ID, err)
						return
					}
				}
			}
		}(i)
	}

	wg.Wait()
	close(errCh)
	return errors.Join(collect(errCh)...) // Go 1.20+: multiple errors without losing any
}
```

**Small consumer-side interface (testability without ceremony):**

```go
// In the service package, not in the repository package.
type OrderStore interface {
	Get(ctx context.Context, id string) (*Order, error)
	MarkPaid(ctx context.Context, id string) (*Order, error)
}

type Service struct {
	repo     OrderStore
	payments PaymentGateway
	clock    func() time.Time
}

// Test fake lives beside the test, only implements what is used.
type fakeStore struct {
	orders map[string]*Order
	err    error
}

func (f *fakeStore) Get(_ context.Context, id string) (*Order, error) {
	if f.err != nil {
		return nil, f.err
	}
	o, ok := f.orders[id]
	if !ok {
		return nil, ErrNotFound
	}
	return o, nil
}
```

**Defer inside loops (the classic leak):**

```go
// BAD: every file stays open until the function returns
func loadAllBad(paths []string) error {
	for _, p := range paths {
		f, err := os.Open(p)
		if err != nil {
			return err
		}
		defer f.Close() // accumulates
		_ = f
	}
	return nil
}

// GOOD: scope the defer per iteration
func loadAll(paths []string) error {
	for _, p := range paths {
		if err := func() error {
			f, err := os.Open(p)
			if err != nil {
				return err
			}
			defer f.Close()
			return scan(f)
		}(); err != nil {
			return fmt.Errorf("load %s: %w", p, err)
		}
	}
	return nil
}
```

**CI checks including the race detector and fuzzing:**

```bash
gofmt -l . | tee /tmp/fmt.txt && [ ! -s /tmp/fmt.txt ]
go vet ./...
staticcheck ./... || golangci-lint run
go test -race -count=1 ./...
go test -run=^$ -bench=. -benchmem ./internal/pricing | tee bench.txt
go test -fuzz=FuzzParseCursor -fuzztime=30s ./internal/api
go mod tidy && git diff --exit-code go.mod go.sum
```

**Benchmark that proves a change:**

```go
func BenchmarkPriceOrder(b *testing.B) {
	o := newTestOrder(50)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if _, err := PriceOrder(o, nil); err != nil {
			b.Fatal(err)
		}
	}
}
// Before: 4200 ns/op, 1200 B/op, 22 allocs/op
// After:  3100 ns/op,  160 B/op,  3 allocs/op  (preallocated slice)
```

## 8. Quality Standards

- Errors are wrapped with context (`%w`) and inspected with `errors.Is`/`errors.As`.
- No ignored errors except with an explicit, commented justification.
- Every blocking call takes and honors `context.Context`; timeouts are set at the boundary.
- All goroutines are bounded, cancellable, and waited on; no fire-and-forget without lifecycle management.
- Shared state is protected by a mutex with documented invariants, or owned by a single goroutine.
- Interfaces are consumer-defined and small; no interface with more than three methods without cause.
- `gofmt`, `go vet`, `staticcheck`, and `-race` pass in CI.
- Benchmarks exist for hot paths and are cited when performance claims are made.
- `go mod tidy` leaves no diff; dependencies are minimal and pinned.

## 9. Verification and Testing

```bash
go test -race -count=5 ./...         # repetition catches flaky concurrency
go test -run TestLeak -v ./...       # goroutine-leak assertions where used
GODEBUG=gctrace=1 ./bin/service      # allocation/GC pressure during a load run
go tool pprof http://localhost:6060/debug/pprof/heap
```

- Goroutine leak check after request bursts: compare `runtime.NumGoroutine()` before/after in a test.
- Table-driven tests for error classification (`errors.Is`) across layers.
- Fuzz tests for parsers, cursor decoding, and header handling.
- `go test -cover -covermode=atomic` for coverage; branch behavior via table cases.

## 10. Security Considerations

- Never build SQL or shell commands with string concatenation; use parameterized queries and `exec.Command` with argument slices.
- `http.Server` must set `ReadHeaderTimeout`, `ReadTimeout`, `WriteTimeout`, and `MaxHeaderBytes` to avoid slowloris-style exhaustion.
- Bound request bodies with `http.MaxBytesReader`; bound JSON decoding depth/size for nested payloads.
- Do not log secrets; scrub headers (`Authorization`, `Cookie`) before logging requests.
- `crypto/rand` for tokens, never `math/rand`; use `crypto/subtle.ConstantTimeCompare` for secret comparison.
- Verify TLS (`InsecureSkipVerify: false`), set `MinVersion: tls.VersionTLS12`, and never disable verification to fix a test.
- Validate and canonicalize file paths; `filepath.Join` alone does not prevent traversal.
- Dependencies: `govulncheck ./...` in CI and a reviewed, pinned module graph.

## 11. Failure Handling

- **Data race reported in CI:** it is a real bug, not test noise. Reproduce with `-race -count`, then fix ownership or add locking.
- **Goroutine leak:** a goroutine is blocked on a channel or missing a cancel path; add `ctx` to the select and wait on the group.
- **Errors double-wrapped or lost:** use `%w` consistently and avoid `errors.New(err.Error())`, which destroys the chain.
- **`context canceled` in logs during deploys:** expected on shutdown; distinguish from `DeadlineExceeded` and handle both explicitly.
- **High allocations in a hot path:** preallocate slices, avoid interface boxing in loops, and reduce string concatenation.

## 12. Expected Deliverables

1. Module layout with `internal/` packages and consumer-defined interfaces.
2. Error taxonomy with sentinel and typed errors mapped to transport codes.
3. Context and timeout policy per boundary.
4. Concurrency patterns with bounded parallelism and shutdown.
5. CI pipeline including race, vet, staticcheck, and vulnerability scanning.
6. Benchmarks and profiles for performance-sensitive code.

## 13. References

- The Go Programming Language Specification — https://go.dev/ref/spec
- Effective Go — https://go.dev/doc/effective_go
- Go Code Review Comments — https://go.dev/wiki/CodeReviewComments
- `errors` package — https://pkg.go.dev/errors
- `golang.org/x/sync/errgroup` — https://pkg.go.dev/golang.org/x/sync/errgroup
- Go blog: Contexts and cancellation — https://go.dev/blog/context
- Profiling Go programs — https://go.dev/blog/pprof
- `govulncheck` — https://pkg.go.dev/golang.org/x/vuln/cmd/govulncheck
- staticcheck — https://staticcheck.dev/docs/
