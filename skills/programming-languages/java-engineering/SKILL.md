---
name: java-engineering
description: Build modern Java services—records and sealed types, streams used with restraint, virtual threads, dependency injection hygiene, and JVM diagnostics.
metadata:
  domain: programming-languages
  version: 1.0.0
  risk: medium
---

# Java Engineering

## 1. Purpose

Write Java that is clear, fast enough, and diagnosable in production. Legacy habits (getter/setter beans, deep inheritance, `catch (Exception e) {}`) persist into new codebases and create the same problems: unreadable data flow, streams that hide N+1 queries, thread pools exhausted by blocking calls, and heap issues nobody can diagnose because there is no dump or profile. This skill covers modern language features, concurrency (including virtual threads), DI and layering, and JVM observability.

**Scope:** your own code and dependencies. Build tools download and execute plugins: pin versions, use a repository manager with allowlisting where available, and never run a build from an untrusted source with credentials in the environment.

## 2. Activation Conditions

- New service or a modernization of a legacy Java codebase.
- Thread pool exhaustion, latency spikes, or GC pauses.
- Maven/Gradle builds slow or non-reproducible.
- Streams/lambdas used in ways that hurt readability or clarity.
- Keywords: Java, JDK 21, records, sealed, pattern matching, virtual threads, CompletableFuture, Spring Boot, Maven, Gradle, JUnit 5, JFR, JMX, heap dump, GC tuning.

## 3. When Not to Use

- Android-specific development (different toolchain and runtime constraints).
- Choosing a language for a new project (use a research/decision skill).
- Deep JVM tuning without measurements (profile first).

## 4. Required Context

1. JDK version (LTS target) and runtime environment (container, cloud).
2. Framework: Spring Boot, Quarkus, Micronaut, plain.
3. Concurrency model: platforms threads, virtual threads, reactive.
4. Build tool and dependency policy.
5. Observability stack (metrics, logs, traces, JFR).

## 5. Operating Procedure

1. **Target a current LTS JDK** and use what it offers: `record` for data carriers, `sealed` interfaces + pattern matching for closed hierarchies, `var` for local inference, and `switch` expressions.
2. **Prefer immutability**: records, `List.copyOf`, `final` fields, and unmodifiable collections at boundaries.
3. **Use streams for transformation, loops for control flow**: no streams with side effects in `forEach` for I/O, no nested streams over database calls (N+1), and no `parallelStream()` on I/O or shared mutable state.
4. **Handle exceptions at the right level**: catch what you can handle, wrap with context, never swallow, and use checked exceptions only at process boundaries (not in lambdas).
5. **Choose concurrency deliberately**:
   - Virtual threads (JDK 21+) for blocking I/O at high concurrency; pin only where necessary, and never pool virtual threads.
   - Bounded platform-thread pools for CPU-bound work (size ≈ cores).
   - `CompletableFuture` for composition, with explicit executors — not the common pool for request work.
6. **Bound every remote call** with timeouts and retries (resilience4j or framework equivalents); propagate context for tracing.
7. **Keep DI honest**: constructor injection only, no field injection, no service locators; explicit wiring beats magic.
8. **Wire observability in from day one**: Micrometer metrics, structured logs with correlation IDs, and JFR recording available in production.
9. **Make builds reproducible**: pin plugin and dependency versions, use the wrapper (`./mvnw`, `./gradlew`), and enable dependency lockfiles or a BOM.
10. **Diagnose with data**: JFR + `jcmd` + heap dumps before changing threads, pools, or GC settings.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Build | Maven (`pom.xml`), Gradle (Kotlin DSL), wrappers, BOM imports |
| Frameworks | Spring Boot 3.x, Quarkus, Micronaut |
| Testing | JUnit 5, AssertJ, Testcontainers, Mockito (minimal) |
| Concurrency | `java.util.concurrent`, virtual threads, `CompletableFuture` |
| Resilience | resilience4j, framework timeouts/retries |
| Diagnostics | JFR, `jcmd`, `jstack`, `jmap`, async-profiler, `jdeps` |
| Observability | Micrometer, OpenTelemetry Java agent, Logback/Log4j2 JSON |
| Quality | SpotBugs, Error Prone, Checkstyle, `mvn dependency:analyze` |

## 7. Practical Implementation

**Records, sealed types, and exhaustive pattern matching:**

```java
package com.acme.orders;

import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

public record OrderLine(int productId, int quantity, BigDecimal unitPrice) {
    public OrderLine {
        if (quantity <= 0) throw new IllegalArgumentException("quantity must be positive");
        Objects.requireNonNull(unitPrice, "unitPrice");
        if (unitPrice.signum() < 0) throw new IllegalArgumentException("unitPrice must be >= 0");
    }

    public BigDecimal subtotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}

public sealed interface PaymentResult permits Approved, Declined, ProviderError {}

record Approved(String chargeId, BigDecimal captured) implements PaymentResult {}

record Declined(String code, String message) implements PaymentResult {}

record ProviderError(String message, Throwable cause) implements PaymentResult {}

public final class PaymentOutcome {

    public static String describe(PaymentResult result) {
        // Exhaustive switch: adding a variant breaks compilation, not production.
        return switch (result) {
            case Approved a -> "captured " + a.captured() + " as " + a.chargeId();
            case Declined d -> "declined (" + d.code() + "): " + d.message();
            case ProviderError e -> "provider error: " + e.message();
        };
    }
}
```

**Streams used appropriately (transformation, not I/O or side effects):**

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public final class Reporting {

    public static Map<String, BigDecimal> revenueByStatus(List<Order> orders) {
        // Pure transformation: safe and readable.
        return orders.stream()
                .filter(o -> o.total().signum() > 0)
                .collect(Collectors.groupingBy(
                        Order::status,
                        Collectors.reducing(BigDecimal.ZERO, Order::total, BigDecimal::add)));
    }

    // BAD: I/O inside a stream's forEach — ordering, error handling, and back-pressure are lost
    // orders.stream().forEach(o -> repository.save(o));

    // GOOD: a plain loop for I/O, explicit error handling and batching
    public static void persistAll(List<Order> orders, OrderRepository repository) {
        for (int i = 0; i < orders.size(); i += 500) {
            List<Order> batch = orders.subList(i, Math.min(i + 500, orders.size()));
            repository.saveAll(batch);          // one round trip per batch
        }
    }
}
```

**Virtual threads for blocking I/O (JDK 21+):**

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class EnrichmentService implements AutoCloseable {

    // One virtual thread per task; do NOT pool them (they are cheap and per-task)
    private final ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor();

    public Quote fetchWithTimeout(QuoteClient client, String sku) throws Exception {
        Future<Quote> future = executor.submit(() -> client.fetch(sku));  // blocking client is fine
        try {
            return future.get(java.time.Duration.ofSeconds(2));           // always bound the wait
        } catch (java.util.concurrent.TimeoutException e) {
            future.cancel(true);
            throw new QuoteTimeoutException(sku, e);
        }
    }

    @Override
    public void close() {
        executor.close();   // AutoCloseable in JDK 19+: waits for tasks, then shuts down
    }
}
```

```yaml
# Spring Boot 3.2+: virtual threads for request handling
spring:
  threads:
    virtual:
      enabled: true
```

**CompletableFuture with an explicit executor and timeouts:**

```java
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

public final class OrderAggregator {
    private final ExecutorService ioPool;   // bounded: sized to the downstream's capacity

    public OrderView aggregate(String orderId) {
        var order = CompletableFuture.supplyAsync(() -> orderClient.get(orderId), ioPool);
        var payment = CompletableFuture.supplyAsync(() -> paymentClient.get(orderId), ioPool);

        // Explicit timeout on the composition, not just per-call
        CompletableFuture.allOf(order, payment).orTimeout(3, TimeUnit.SECONDS).join();

        return new OrderView(order.join(), payment.join());
    }
}
```

**Constructor injection and clean layering:**

```java
@Service
public final class OrderService {
    private final OrderRepository repository;
    private final PaymentGateway payments;
    private final Clock clock;

    // Constructor injection only; no @Autowired fields, no static service lookups.
    public OrderService(OrderRepository repository, PaymentGateway payments, Clock clock) {
        this.repository = repository;
        this.payments = payments;
        this.clock = clock;
    }

    @Transactional
    public Order pay(String orderId) {
        Order order = repository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));
        if (order.status() != Status.PLACED) {
            throw new InvalidStateException(orderId, order.status());
        }
        PaymentResult result = payments.charge(order.id(), order.total());
        if (result instanceof Declined declined) {
            throw new PaymentDeclinedException(declined.code());
        }
        return repository.save(order.paid(clock.instant()));
    }
}
```

**Structured logging with correlation (MDC), no secrets:**

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class RequestFilter {
    private static final Logger log = LoggerFactory.getLogger(RequestFilter.class);

    public void handle(String requestId, String userId, Runnable body) {
        try (MDC.MDCCloseable a = MDC.putCloseable("request_id", requestId);
             MDC.MDCCloseable b = MDC.putCloseable("user_id", userId)) {
            long start = System.nanoTime();
            try {
                body.run();
            } finally {
                log.info("request.completed duration_ms={}", (System.nanoTime() - start) / 1_000_000);
            }
        }
    }
}
```

**Diagnostics in production (no restart required):**

```bash
# Continuous profiling with low overhead
jcmd 4821 JFR.start name=diag settings=profile duration=60s filename=/tmp/diag.jfr
jcmd 4821 JFR.dump name=diag filename=/tmp/diag.jfr

# Thread dump: find blocked or pinned threads
jcmd 4821 Thread.print -l > /tmp/threads.txt
grep -A12 '"virtual"' /tmp/threads.txt | head -40      # virtual threads appear in the dump

# Heap histogram then a dump if growth is confirmed
jcmd 4821 GC.class_histogram | head -20
jcmd 4821 GC.heap_dump /tmp/heap.hprof

# GC behaviour (which collector, pause times)
jcmd 4821 GC.heap_info
java -XX:+PrintFlagsFinal -version | grep -E 'Use(G1|Z|Parallel)GC'
```

**Build hygiene (Maven):**

```xml
<project>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-dependencies</artifactId>
        <version>3.3.4</version>
        <type>pom</type><scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-enforcer-plugin</artifactId>
        <version>3.5.0</version>
        <executions><execution>
          <goals><goal>enforce</goal></goals>
          <configuration><rules>
            <requireJavaVersion><version>[21,)</version></requireJavaVersion>
            <dependencyConvergence/>
          </rules></configuration>
        </execution></executions>
      </plugin>
    </plugins>
  </build>
</project>
```

```bash
./mvnw -B -ntp verify                       # reproducible, offline-friendly
./mvnw dependency:analyze                   # unused/undeclared dependencies
./mvnw org.owasp:dependency-check-maven:check   # CVE scan
```

## 8. Quality Standards

- Current LTS JDK; records for data, sealed types for closed hierarchies, exhaustive `switch`.
- Immutable objects at boundaries; no mutable static state.
- No side-effectful streams; no `parallelStream()` for I/O or shared state.
- All remote calls have timeouts; retries are bounded and jittered.
- Virtual threads only for blocking I/O, never pooled; CPU work uses bounded platform pools.
- Constructor injection only; no field injection or hidden singletons.
- Structured logs with correlation IDs; no secrets or full PII.
- Builds are reproducible with the wrapper, a BOM, and enforcer rules.
- JFR available in production and heap dumps configured to a known location.

## 9. Verification and Testing

```bash
./mvnw -B verify
./mvnw -Dtest=OrderServiceTest test
./mvnw -Pit verify        # integration tests with Testcontainers
./mvnw spotbugs:check
```

- JUnit 5 + AssertJ tests per layer; Testcontainers for real Postgres/Kafka in integration tests.
- Concurrency test: run the service under load and check thread counts, virtual-thread pinning (`-Djdk.tracePinnedThreads=full`), and queue depth.
- Timeout test: make a dependency hang; assert the request fails within the configured budget.
- Verify graceful shutdown drains in-flight requests (Spring `server.shutdown=graceful`).
- Compare JFR results before/after a performance change.

## 10. Security Considerations

- Deserialization of untrusted data is a classic exploit: never use Java serialization across trust boundaries; prefer JSON with strict schemas.
- SQL injection: use prepared statements/JPA parameter binding; never concatenate queries.
- XML: disable external entity processing (`XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES=false`) to prevent XXE.
- Spring Security: keep defaults, enforce method-level authorization on service methods, and never disable CSRF "temporarily" for state-changing browser flows.
- Secrets come from a secret manager/env, never `application.properties` in git; scrub them from logs and actuator endpoints.
- Actuator endpoints must be authenticated and restricted (`management.endpoints.web.exposure.include` minimal).
- Dependency CVEs are the dominant risk: OWASP dependency-check/`osv-scanner` in CI, with SLAs for high severity.
- Run as non-root in containers, with a read-only filesystem and a bounded heap (`-XX:MaxRAMPercentage`).

## 11. Failure Handling

- **`OutOfMemoryError: Java heap space`:** take a heap dump (`-XX:+HeapDumpOnOutOfMemoryError`), analyze the dominator tree, and fix the retention path — do not just raise the heap.
- **Thread pool exhausted:** blocking calls on a fixed pool; move I/O to virtual threads or a dedicated pool, and add a bounded queue with rejection handling.
- **High GC pause:** check allocation rate with JFR; reduce garbage rather than switching collectors blindly.
- **Virtual threads "pinned":** `synchronized` blocks around blocking calls or native frames — replace `synchronized` with `ReentrantLock` in those paths.
- **Build fails on a clean machine:** missing wrapper, unpinned plugin, or a repository that is not in the mirror; fix and verify in a container.

## 12. Expected Deliverables

1. Project layout with module boundaries and constructor-injected services.
2. Domain model using records/sealed types with validated invariants.
3. Concurrency configuration (executors, virtual threads, timeouts, pools).
4. Exception taxonomy and HTTP/transport mapping.
5. Observability configuration (metrics, logs with MDC, JFR).
6. Build pipeline with enforcer, dependency analysis, and vulnerability scanning.
7. Runbook for JVM diagnostics (JFR, thread dumps, heap dumps).

## 13. References

- Java SE documentation — https://docs.oracle.com/en/java/javase/
- JEP 444: Virtual Threads — https://openjdk.org/jeps/444
- JEP 395: Records — https://openjdk.org/jeps/395
- JEP 409: Sealed Classes — https://openjdk.org/jeps/409
- Spring Boot reference — https://docs.spring.io/spring-boot/docs/current/reference/html/
- JUnit 5 user guide — https://junit.org/junit5/docs/current/user-guide/
- Testcontainers for Java — https://java.testcontainers.org/
- JDK Flight Recorder — https://docs.oracle.com/en/java/javase/21/jfcs/
- OWASP Java security cheat sheets — https://cheatsheetseries.owasp.org/
