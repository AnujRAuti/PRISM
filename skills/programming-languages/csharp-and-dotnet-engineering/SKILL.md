---
name: csharp-and-dotnet-engineering
description: Build modern .NET services—nullable reference types, async/await correctness, DI lifetimes, EF Core query discipline, and trimming/AOT awareness.
metadata:
  domain: programming-languages
  version: 1.0.0
  risk: medium
---

# C# and .NET Engineering

## 1. Purpose

Write C#/.NET that is null-safe, asynchronous by default, and predictable under load. The recurring .NET problems are specific: `.Result`/`.Wait()` deadlocks, `async void`, DI lifetime mismatches (captive dependencies, scoped services in singletons), EF Core N+1 and client-side evaluation, and nullable warnings suppressed wholesale. This skill covers language and project configuration, async discipline, DI lifetimes, data access, and production diagnostics.

**Scope:** your own code and NuGet dependencies. Restore executes build tasks and analyzers: pin package versions, use a lockfile where available, and review new packages before adding them.

## 2. Activation Conditions

- New .NET service, API, worker, or library.
- Deadlocks, thread-pool starvation, or timeouts under load.
- Entity Framework Core performance issues.
- Nullable warnings turned off or suppressed.
- Keywords: C#, .NET 8, nullable reference types, async await, ConfigureAwait, DI lifetimes, scoped, singleton, EF Core, AsNoTracking, IAsyncEnumerable, minimal API, Serilog, OpenTelemetry, trimming, AOT.

## 3. When Not to Use

- Unity/game development (different runtime constraints).
- Cross-language platform decisions (use technical-research-reports).
- Legacy .NET Framework migration planning without an assessment (scope it first).

## 4. Required Context

1. Target framework (`net8.0`, `net9.0`) and hosting model (container, App Service, Lambda).
2. Framework stack: ASP.NET Core, EF Core, Dapper, MediatR, etc.
3. Data stores and query patterns.
4. Deployment model and whether trimming/AOT is required.
5. Observability stack.

## 5. Operating Procedure

1. **Enable nullable reference types** (`<Nullable>enable</Nullable>`) and treat warnings as errors; do not blanket-suppress with `!` — fix the flow or use explicit validation.
2. **Make async the default for I/O**; use `async`/`await` all the way up, never `.Result`, `.Wait()`, or `GetAwaiter().GetResult()` in request paths.
3. **Never use `async void`** except in event handlers, and then catch everything inside.
4. **Pass `CancellationToken` through every async call**, from the request context down to the data access layer.
5. **Get DI lifetimes right**: singleton services must not depend on scoped services; use `IServiceScopeFactory` for background work, and register with the narrowest lifetime that satisfies the requirement.
6. **Configure EF Core for performance**: `AsNoTracking()` for reads, projection (`Select`) instead of loading full graphs, `Include` only when needed, compiled queries for hot paths, and `AsAsyncEnumerable()` for streaming.
7. **Avoid client-side evaluation**; keep predicates translatable and check the generated SQL.
8. **Bound outbound calls** with `HttpClient` timeouts, `IHttpClientFactory`, and resilience handlers (`Microsoft.Extensions.Http.Resilience`).
9. **Validate inputs at the boundary** (FluentValidation, DataAnnotations, or minimal API filters) and return problem details.
10. **Instrument with OpenTelemetry/Serilog** from the start; use structured logs and correlation.
11. **Treat trimming/AOT as a design constraint** if publishing trimmed: avoid reflection-heavy patterns or annotate them (`[DynamicallyAccessedMembers]`).

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Runtime | .NET 8/9 LTS, ASP.NET Core, Worker Service |
| Data | EF Core 8/9, Dapper, `Npgsql`, `Microsoft.Data.SqlClient` |
| DI | `Microsoft.Extensions.DependencyInjection` |
| Validation | FluentValidation, minimal API validation filters |
| Resilience | `Microsoft.Extensions.Http.Resilience` (Polly-based) |
| Testing | xUnit, NUnit, FluentAssertions, Testcontainers |
| Diagnostics | `dotnet-counters`, `dotnet-trace`, `dotnet-dump`, `dotnet-gcdump` |
| Quality | Roslyn analyzers, `dotnet format`, `dotnet list package --vulnerable` |
| Observability | OpenTelemetry .NET, Serilog, Application Insights |

## 7. Practical Implementation

**Project configuration with nullable, warnings-as-errors, and analyzers:**

```xml
<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net9.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
    <WarningsNotAsErrors>CS1591</WarningsNotAsErrors>
    <EnforceCodeStyleInBuild>true</EnableCodeStyleInBuild>
    <AnalysisLevel>latest-recommended</AnalysisLevel>
    <InvariantGlobalization>false</InvariantGlobalization>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="9.0.0" />
    <PackageReference Include="Microsoft.Extensions.Http.Resilience" Version="9.0.0" />
    <PackageReference Include="OpenTelemetry.Extensions.Hosting" Version="1.9.0" />
  </ItemGroup>
</Project>
```

**Domain model with records, required members, and explicit validation:**

```csharp
namespace Acme.Orders.Domain;

public sealed record OrderLine
{
    public required int ProductId { get; init; }
    public required int Quantity { get; init; }
    public required decimal UnitPrice { get; init; }

    public decimal Subtotal => UnitPrice * Quantity;

    public static OrderLine Create(int productId, int quantity, decimal unitPrice)
    {
        if (quantity <= 0) throw new ArgumentOutOfRangeException(nameof(quantity), "must be positive");
        if (unitPrice < 0) throw new ArgumentOutOfRangeException(nameof(unitPrice), "must be >= 0");
        return new OrderLine { ProductId = productId, Quantity = quantity, UnitPrice = unitPrice };
    }
}

public sealed record Order
{
    public required string Id { get; init; }
    public required OrderStatus Status { get; init; }
    public required IReadOnlyList<OrderLine> Lines { get; init; }

    public decimal Total() => Lines.Count == 0
        ? throw new InvalidOperationException($"order {Id} has no lines")
        : Lines.Sum(l => l.Subtotal);
}

public enum OrderStatus { Draft, Placed, Paid, Cancelled }
```

**Async all the way, with cancellation and no `.Result`:**

```csharp
public sealed class OrderService(
    IOrderRepository repository,
    IPaymentGateway payments,
    TimeProvider clock,
    ILogger<OrderService> logger)
{
    public async Task<Order> PayAsync(string orderId, CancellationToken ct)
    {
        var order = await repository.FindAsync(orderId, ct)
            ?? throw new OrderNotFoundException(orderId);

        if (order.Status != OrderStatus.Placed)
            throw new InvalidOrderStateException(orderId, order.Status);

        var result = await payments.ChargeAsync(order.Id, order.Total(), ct);
        if (result is PaymentDeclined declined)
        {
            logger.LogWarning("Payment declined {Code} for order {OrderId}", declined.Code, order.Id);
            throw new PaymentDeclinedException(declined.Code);
        }

        var paid = order with { Status = OrderStatus.Paid };
        await repository.SaveAsync(paid, ct);
        return paid;
    }
}
```

```csharp
// BAD: deadlock/k starvation risk in sync-over-async and no cancellation
// var order = repository.FindAsync(id).Result;

// GOOD: async propagation, cancellation honored, timeout at the boundary
using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
cts.CancelAfter(TimeSpan.FromSeconds(3));
var order = await repository.FindAsync(id, cts.Token);
```

**DI lifetimes configured correctly (and a background worker that scopes properly):**

```csharp
builder.Services.AddSingleton<IClock>(TimeProvider.System);              // stateless
builder.Services.AddScoped<IOrderRepository, EfOrderRepository>();       // per request
builder.Services.AddScoped<OrderService>();
builder.Services.AddHttpClient<IPaymentGateway, PaymentGatewayClient>(c =>
{
    c.BaseAddress = new Uri("https://api.payments.example.com");
    c.Timeout = TimeSpan.FromSeconds(2);
}).AddStandardResilienceHandler();                                        // retries + circuit breaker

// Hosted service must create a scope per unit of work
public sealed class OutboxPublisher(IServiceScopeFactory scopes, ILogger<OutboxPublisher> log)
    : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            await using var scope = scopes.CreateAsyncScope();          // never inject scoped into singleton
            var repo = scope.ServiceProvider.GetRequiredService<IOutboxRepository>();
            var batch = await repo.ClaimBatchAsync(100, stoppingToken);
            if (batch.Count == 0)
            {
                await Task.Delay(TimeSpan.FromSeconds(2), stoppingToken);
                continue;
            }
            await repo.PublishBatchAsync(batch, stoppingToken);
            log.LogInformation("Published {Count} outbox messages", batch.Count);
        }
    }
}
```

**EF Core queries that stay server-side and avoid N+1:**

```csharp
public sealed class EfOrderRepository(AppDbContext db) : IOrderRepository
{
    public async Task<Order?> FindAsync(string id, CancellationToken ct) =>
        await db.Orders
            .AsNoTracking()                                 // read path: no change tracking
            .Include(o => o.Lines)
            .SingleOrDefaultAsync(o => o.Id == id, ct);

    // Projection: only the columns the API needs
    public async Task<IReadOnlyList<OrderSummary>> ListAsync(string tenantId, CancellationToken ct) =>
        await db.Orders
            .AsNoTracking()
            .Where(o => o.TenantId == tenantId && o.Status == OrderStatus.Paid)
            .OrderByDescending(o => o.CreatedAt)
            .Take(50)
            .Select(o => new OrderSummary(
                o.Id,
                o.Status.ToString(),
                o.Lines.Sum(l => l.UnitPrice * l.Quantity)))
            .ToListAsync(ct);

    // Streaming large result sets without materializing everything
    public IAsyncEnumerable<Order> StreamAsync(string tenantId, CancellationToken ct) =>
        db.Orders.AsNoTracking().Where(o => o.TenantId == tenantId).AsAsyncEnumerable();

    public async Task SaveAsync(Order order, CancellationToken ct)
    {
        var row = await db.Orders.SingleAsync(o => o.Id == order.Id, ct);
        row.Status = order.Status;
        await db.SaveChangesAsync(ct);
    }
}
```

```csharp
// Detecting N+1: enable sensitive logging in development only
builder.Services.AddDbContext<AppDbContext>(o =>
    o.UseNpgsql(cfg.GetConnectionString("Orders"))
     .LogTo(Console.WriteLine, LogLevel.Information)
     .EnableSensitiveDataLogging(builder.Environment.IsDevelopment()));
```

**Problem-details error handling mapped from domain exceptions:**

```csharp
app.UseExceptionHandler(handler => handler.Run(async context =>
{
    var feature = context.Features.Get<IExceptionHandlerFeature>();
    var (status, type) = feature?.Error switch
    {
        OrderNotFoundException => (StatusCodes.Status404NotFound, "/problems/not-found"),
        InvalidOrderStateException => (StatusCodes.Status409Conflict, "/problems/invalid-state"),
        PaymentDeclinedException => (StatusCodes.Status422UnprocessableEntity, "/problems/card-declined"),
        OperationCanceledException => (StatusCodes.Status504GatewayTimeout, "/problems/timeout"),
        _ => (StatusCodes.Status500InternalServerError, "/problems/internal"),
    };

    context.Response.StatusCode = status;
    await context.Response.WriteAsJsonAsync(new ProblemDetails
    {
        Type = type,
        Status = status,
        Title = status == 500 ? "Internal error" : feature?.Error.Message,
        TraceId = Activity.Current?.TraceId.ToString(),
    });
}));
```

**Production diagnostics with dotnet tools:**

```bash
# Live counters: GC, thread pool, request rate
dotnet-counters monitor --process-id 4821 \
  --counters System.Runtime[gc-heap-size,threadpool-queue-length,cpu-usage],Microsoft.AspNetCore.Hosting[requests-per-second]

# Trace a slow endpoint (captures a .nettrace for analysis in PerfView/Speedscope)
dotnet-trace collect --process-id 4821 --providers Microsoft-AspNetCore-Hosting,Microsoft-EntityFrameworkCore --duration 00:00:30

# Memory growth: GC dump comparison over time
dotnet-gcdump collect --process-id 4821 --output before.gcdump
dotnet-dump analyse --process-id 4821     # SOS: !threads, !dumpheap -stat, !syncblk
```

## 8. Quality Standards

- Nullable reference types enabled with warnings as errors; no blanket `!` suppression.
- No sync-over-async (`.Result`, `.Wait()`, `GetAwaiter().GetResult()`) in request or job paths.
- `async void` never used outside event handlers.
- `CancellationToken` flows through every async call to the database and HTTP clients.
- DI lifetimes verified: no scoped service captured by a singleton; `ValidateScopes`/`ValidateOnBuild` enabled.
- EF Core read paths use `AsNoTracking` and projections; no `Include` cartesian explosions; queries checked against generated SQL.
- All outbound HTTP has a timeout and a resilience policy.
- Domain exceptions map to explicit problem-details responses; no stack traces leak to clients.
- Analyzers and `dotnet format` pass in CI; vulnerable packages fail the build.

## 9. Verification and Testing

```bash
dotnet build -warnaserror
dotnet test --logger "console;verbosity=normal"
dotnet list package --vulnerable --include-transitive
dotnet format --verify-no-changes
```

- xUnit tests per layer; WebApplicationFactory for API tests; Testcontainers for real Postgres.
- Concurrency test: load the API and watch `threadpool-queue-length` and latency for starvation.
- Timeout test: point `IPaymentGateway` at a deliberately slow stub; assert a 504 within budget.
- DI validation test: `builder.Host.UseDefaultServiceProvider(o => {o.ValidateScopes = true; o.ValidateOnBuild = true;})` in tests and non-production.

## 10. Security Considerations

- Parameterize all SQL; EF Core does by default — never build `FromSqlRaw` with interpolated input (use `FromSqlInterpolated`/parameters).
- Never deserialize untrusted data with `BinaryFormatter` (removed/forbidden); prefer `System.Text.Json` with strict options and size limits.
- Validate and bound request bodies (`RequestSizeLimit`, model validation) to prevent memory exhaustion.
- Authentication/authorization: use ASP.NET Core Identity/JWT validation properly (validate issuer, audience, lifetime, signing key); never disable token validation for convenience.
- Secrets belong in a secret manager/key vault; never in `appsettings.json` in the repo.
- Data Protection keys must persist across instances (shared store) or tokens/cookies break and get re-encrypted on every deploy.
- Configure HSTS, secure cookies, and anti-forgery tokens for cookie-based flows.
- Publish trimmed/AOT apps with a review of reflection use; trimming can remove security-relevant code paths silently.

## 11. Failure Handling

- **Deadlock or hang:** sync-over-async somewhere in the chain; find `.Result`/`.Wait()` and remove, and check for a synchronization context in library code.
- **Thread-pool starvation:** blocking calls on the pool; make the path fully async and check `threadpool-queue-length`.
- **EF Core slow query:** client-side evaluation or N+1; capture SQL with `LogTo`, add `AsNoTracking`, projection, and the right indexes.
- **`Cannot access a disposed context`:** a scoped service used after the request scope ended (background task or `Task.Run`); create a scope explicitly.
- **Memory growth:** DbContext change-tracker bloat from long-lived contexts or unbounded queries; fix lifetime and stream large reads.

## 12. Expected Deliverables

1. Project configuration (nullable, analyzers, warnings as errors).
2. Domain model with validated records and explicit invariants.
3. Async and cancellation conventions.
4. DI registration with lifetime analysis and scope validation.
5. EF Core query patterns with projections and streaming.
6. Exception-to-problem-details mapping.
7. Diagnostics runbook (`dotnet-counters`, `dotnet-trace`, `dotnet-dump`).

## 13. References

- .NET documentation — https://learn.microsoft.com/dotnet/
- Nullable reference types — https://learn.microsoft.com/dotnet/csharp/nullable-references
- Async/await best practices — https://learn.microsoft.com/dotnet/csharp/asynchronous-programming/
- Dependency injection in ASP.NET Core — https://learn.microsoft.com/aspnet/core/fundamentals/dependency-injection
- EF Core performance — https://learn.microsoft.com/ef/core/performance/
- `Microsoft.Extensions.Http.Resilience` — https://learn.microsoft.com/dotnet/core/resilience/http-resilience
- OpenTelemetry .NET — https://opentelemetry.io/docs/languages/net/
- dotnet diagnostic tools — https://learn.microsoft.com/dotnet/core/diagnostics/
- xUnit documentation — https://xunit.net/
