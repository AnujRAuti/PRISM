---
name: cpp-engineering
description: Write modern C++ safely—RAII and smart pointers, move semantics, bounded undefined behavior, ASan/UBSan in CI, and CMake target hygiene.
metadata:
  domain: programming-languages
  version: 1.0.0
  risk: high
---

# C++ Engineering

## 1. Purpose

Produce C++ that does not corrupt memory, leak resources, or behave differently under optimization. C++ gives you control and removes your safety net: dangling pointers, use-after-free, out-of-bounds indexing, unsigned underflow, and data races are all silently permitted. This skill covers RAII and ownership, smart pointers, move semantics, containers, sanitizer-driven testing, CMake structure, and a discipline for the small amount of manual memory management that remains.

**Scope:** your own code and dependencies. C++ can read and write arbitrary memory and files: never run untrusted binaries or test suites with privileges, never disable sanitizers to hide failures, and treat third-party native libraries as a supply-chain risk requiring pinning and review.

## 2. Activation Conditions

- New C++ component, library, or native extension.
- Crashes, memory growth, or "works in debug, fails in release".
- Migrating legacy C++ (raw pointers, manual `new`/`delete`) to modern idioms.
- Adding sanitizers, fuzzing, or static analysis to a build.
- Keywords: C++, C++20, RAII, smart pointers, unique_ptr, shared_ptr, move semantics, UBSan, ASan, TSan, valgrind, CMake, clang-tidy, rules for raw pointers, bounds checking, fuzzing, undefined behavior.

## 3. When Not to Use

- Projects where a memory-safe language meets the requirements (prefer Rust or Go for new code where feasible).
- Numeric prototyping better served by Python/Julia (though performance-critical kernels may end up in C++).
- Build-system-only questions for other ecosystems.

## 4. Required Context

1. Standard version (C++17/20/23) and compiler matrix (GCC, Clang, MSVC).
2. Platform targets and ABI constraints.
3. Existing codebase style and legacy constraints.
4. Build system and dependency management (CMake + FetchContent/vcpkg/Conan).
5. Safety-critical or performance-critical requirements.

## 5. Operating Procedure

1. **Default to value semantics and RAII.** Every resource (memory, file, socket, lock, GPU buffer) is owned by an object whose destructor releases it.
2. **Use `std::unique_ptr` for exclusive ownership**, `std::shared_ptr` only when ownership is genuinely shared (and with `std::weak_ptr` to break cycles). Raw pointers and references are non-owning observers only.
3. **Never call `new`/`delete` directly**; use `std::make_unique`/`std::make_shared` or stack objects and containers.
4. **Prefer `std::vector`, `std::string`, `std::array`, `std::span`** over raw arrays; use `.at()` at trust boundaries and unchecked `[]` only where the index is proven.
5. **Make moves meaningful**: follow the Rule of Zero (no user-declared destructor/copy/move when members manage themselves); if you declare one, declare all; mark moves `noexcept`.
6. **Make everything `const` that can be**, pass by `const&` or `std::string_view`/`std::span` for read-only parameters.
7. **Bounds-check at trust boundaries**: parse untrusted input with explicit length checks; never trust a length field.
8. **Run sanitizers in CI on every commit**: ASan+UBSan in debug, TSan for concurrency tests; treat any finding as a bug.
9. **Enable compiler warnings as errors** (`-Wall -Wextra -Wpedantic -Wconversion`), plus `clang-tidy` with the C++ Core Guidelines checks.
10. **Fuzz parsers** with libFuzzer/AFL++ under ASan.
11. **Keep CMake targets precise**: `target_include_directories`/`target_link_libraries` with `PUBLIC`/`PRIVATE`, no global flags, no `file(GLOB)` for sources.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Compilers | GCC 13+, Clang 17+, MSVC 19.3x |
| Build | CMake ≥ 3.28, Ninja, Conan/vcpkg |
| Sanitizers | ASan, UBSan, TSan, MSan (Clang) |
| Static analysis | clang-tidy, cppcheck, Coverity, PVS-Studio |
| Dynamic analysis | Valgrind (memcheck, helgrind), sanitizers |
| Fuzzing | libFuzzer, AFL++, OSS-Fuzz |
| Testing | GoogleTest, Catch2, doctest |
| Profiling | `perf`, VTune, Tracy, `gprofng` |
| Guidelines | C++ Core Guidelines, Google C++ Style Guide |

## 7. Practical Implementation

**RAII ownership with `unique_ptr` and Rule of Zero:**

```cpp
#include <cstdio>
#include <memory>
#include <string>
#include <vector>

// Owns a C FILE* and closes it on destruction; safe under exceptions.
class FileHandle {
public:
    explicit FileHandle(const std::string& path, const char* mode)
        : handle_(std::fopen(path.c_str(), mode)) {
        if (!handle_) throw std::runtime_error("cannot open file: " + path);
    }
    ~FileHandle() { if (handle_) std::fclose(handle_); }

    FileHandle(const FileHandle&) = delete;             // no copies
    FileHandle& operator=(const FileHandle&) = delete;
    FileHandle(FileHandle&& other) noexcept : handle_(std::exchange(other.handle_, nullptr)) {}
    FileHandle& operator=(FileHandle&& other) noexcept {
        if (this != &other) {
            if (handle_) std::fclose(handle_);
            handle_ = std::exchange(other.handle_, nullptr);
        }
        return *this;
    }

    std::FILE* get() const noexcept { return handle_; }

private:
    std::FILE* handle_;
};

// Rule of Zero: members manage themselves; no destructor/copy/move needed.
struct Session {
    std::string token;
    std::vector<std::byte> payload;
};
```

**Non-owning views at API boundaries (`std::span`, `std::string_view`):**

```cpp
#include <span>
#include <string_view>
#include <cstdint>

// Accepts any contiguous buffer; no copies, no length parameter mistakes.
std::uint32_t checksum(std::span<const std::byte> data) noexcept {
    std::uint32_t sum = 0;
    for (auto b : data) sum = (sum << 1) ^ static_cast<std::uint8_t>(b);
    return sum;
}

// Caller keeps ownership; callee must not store the view.
bool is_valid_sku(std::string_view sku) noexcept {
    return sku.size() >= 4 && sku.size() <= 32 && sku.substr(0, 4) == "SKU-";
}
```

**Bounds-safe parsing of untrusted input:**

```cpp
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>

struct Header {
    std::uint32_t length;
    std::uint16_t type;
};

// Parses a fixed-size header; returns nullopt instead of reading out of bounds.
std::optional<Header> parse_header(std::span<const std::byte> buf) noexcept {
    constexpr std::size_t kSize = 6;
    if (buf.size() < kSize) return std::nullopt;

    auto byte_at = [&](std::size_t i) { return static_cast<std::uint8_t>(buf[i]); };
    Header h{
        .length = (std::uint32_t{byte_at(0)} << 24) | (std::uint32_t{byte_at(1)} << 16) |
                  (std::uint32_t{byte_at(2)} << 8)  |  std::uint32_t{byte_at(3)},
        .type   = static_cast<std::uint16_t>((byte_at(4) << 8) | byte_at(5)),
    };

    // Reject implausible lengths before any downstream use.
    if (h.length > 64u * 1024u * 1024u) return std::nullopt;
    return h;
}
```

**Thread-safe sharing without manual locking errors:**

```cpp
#include <atomic>
#include <memory>
#include <mutex>
#include <unordered_map>

// Readers use shared_ptr snapshots; writers replace the map atomically.
class PriceCache {
public:
    void update(std::string sku, std::int64_t cents) {
        std::lock_guard<std::mutex> lock(write_mutex_);
        auto copy = std::make_shared<Map>(*snapshot_.load());
        (*copy)[std::move(sku)] = cents;
        snapshot_.store(std::move(copy));       // store shared_ptr<const Map>
    }

    std::optional<std::int64_t> get(const std::string& sku) const {
        auto current = snapshot_.load();
        auto it = current->find(sku);
        return it == current->end() ? std::nullopt : std::optional{it->second};
    }

private:
    using Map = std::unordered_map<std::string, std::int64_t>;
    std::atomic<std::shared_ptr<const Map>> snapshot_{std::make_shared<const Map>()};
    std::mutex write_mutex_;
};
```

**CMake with target-based configuration and sanitizer flags:**

```cmake
cmake_minimum_required(VERSION 3.28)
project(orders LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

add_library(orders_core src/pricing.cpp src/parser.cpp)
target_include_directories(orders_core PUBLIC include)
target_compile_options(orders_core PRIVATE
  -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror)
target_link_libraries(orders_core PUBLIC fmt::fmt)   # explicit, no globals

option(ORDERS_SANITIZE "Enable ASan/UBSan" OFF)
if(ORDERS_SANITIZE)
  target_compile_options(orders_core PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
  target_link_options(orders_core PRIVATE -fsanitize=address,undefined)
endif()

enable_testing()
add_executable(orders_tests tests/pricing_test.cpp tests/parser_test.cpp)
target_link_libraries(orders_tests PRIVATE orders_core GTest::gtest_main)
include(GoogleTest)
gtest_discover_tests(orders_tests)
```

```bash
# Build and test with sanitizers in CI
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Debug -DORDERS_SANITIZE=ON
cmake --build build -j"$(nproc)"
ctest --test-dir build --output-on-failure

# Static analysis over the full compilation database
clang-tidy -p build src/*.cpp --checks='-*,cppcoreguidelines-*,bugprone-*,performance-*,readability-*'
```

**AddressSanitizer output is a bug report — read the frames:**

```text
==4821==ERROR: AddressSanitizer: heap-use-after-free on address 0x6020000000f0
READ of size 4 at 0x6020000000f0 thread T0
    #0 0x55a2 in Order::total() src/pricing.cpp:42
    #1 0x55d9 in main tests/repro.cpp:12
freed by thread T0 here:
    #0 0x7f1a in operator delete(void*) ...
    #1 0x55a1 in OrderList::clear() src/order_list.cpp:31
# The object was destroyed by clear() while a reference was still in use.
```

**Fuzz target for a parser (libFuzzer + ASan):**

```cpp
#include <cstddef>
#include <cstdint>
#include <span>
#include "parser.hpp"

extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* data, std::size_t size) {
    auto bytes = std::span<const std::byte>(reinterpret_cast<const std::byte*>(data), size);
    auto header = parse_header(bytes);           // must never read out of bounds
    if (header) {
        (void)parse_payload(bytes.subspan(6, header->length < bytes.size() - 6
                                                ? header->length : bytes.size() - 6));
    }
    return 0;
}
```

```bash
clang++ -std=c++20 -g -fsanitize=fuzzer,address,undefined -Iinclude \
  fuzz/parse_fuzz.cpp src/parser.cpp -o build/fuzz_parse
./build/fuzz_parse -max_total_time=300 -rss_limit_mb=2048 corpus/
```

## 8. Quality Standards

- No direct `new`/`delete`; ownership is expressed with smart pointers or values.
- No raw owning pointers; raw pointers and references are non-owning and documented as such.
- Class of resource-owning types has Rule of Zero, or all five special members if any is declared.
- Moves are `noexcept`; moved-from objects are left valid.
- Untrusted input is length-checked before indexing; `.at()` or explicit checks at boundaries.
- `-Wall -Wextra -Wpedantic -Wconversion -Werror` and `clang-tidy` pass in CI.
- ASan+UBSan run on all unit tests; TSan runs on concurrency tests.
- No `reinterpret_cast` between unrelated types; `std::bit_cast` used where appropriate.
- CMake uses target-scoped settings; no global include paths or compile flags leaking between targets.

## 9. Verification and Testing

```bash
cmake --build build && ctest --test-dir build --output-on-failure
valgrind --leak-check=full --error-exitcode=1 ./build/orders_tests
clang++ -fsanitize=thread -g tests/race_test.cpp src/cache.cpp -o build/race && ./build/race
./build/fuzz_parse -runs=100000 corpus/
```

- Run the test suite with ASan, UBSan, and (for concurrency code) TSan in CI matrix jobs.
- Valgrind memcheck as a second opinion on allocation/leak behavior in a slower job.
- Fuzz parsers and protocol handlers with a committed corpus.
- Benchmark with `perf`/Google Benchmark before and after optimization; state the metric.

## 10. Security Considerations

- Buffer overflows and use-after-free are exploitable: sanitizers plus bounds checking at trust boundaries are mandatory, not optional.
- Never disable sanitizer failures, ignore compiler warnings, or cast away `const` to work around a design problem.
- Integer overflow/underflow is undefined behavior for signed types: use checked arithmetic, or unsigned with explicit range logic, and validate sizes before allocation.
- Avoid `strcpy`/`sprintf`/`gets`; use `std::string`, `std::format`, `snprintf` with bounds.
- Format-string vulnerabilities: never pass user input as a format string.
- `std::shared_ptr` cycles leak; use `weak_ptr` for back-references.
- Dependencies are compiled native code with full process privileges: pin versions/hashes, vendor with a manifest, and audit.
- Run services as non-root with seccomp/AppArmor where possible; a memory bug in C++ is often a privilege escalation.
- Uninitialized memory reads leak data across requests: initialize members, prefer in-class initializers.

## 11. Failure Handling

- **Crash only in Release:** undefined behavior surfacing under optimization — build with `-O2` plus sanitizers/UBSan and fix the finding; do not "fix" by lowering optimization.
- **ASan reports a leak:** take ownership—either it is a real leak (fix with RAII) or a deliberate global; use `__lsan_ignore_object` only with a written justification.
- **TSan reports a race:** add synchronization or restructure ownership; never silence by adding `std::atomic` to unrelated fields.
- **Link errors after dependency changes:** ABI/standard mismatch; align compilers and standard flags across targets, and rebuild dependencies.
- **Build times too long:** reduce template instantiation in headers, use precompiled headers or unity builds carefully, and split translation units.

## 12. Expected Deliverables

1. Ownership model documentation (who owns what per module).
2. CMake target structure with warnings and sanitizer options.
3. Bounds-checked parsing at all trust boundaries.
4. Sanitizer + static-analysis CI matrix.
5. Fuzz targets with committed corpora.
6. Benchmarks for performance-critical paths.
7. Third-party dependency inventory with pinning and provenance.

## 13. References

- C++ Core Guidelines — https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines
- cppreference — https://en.cppreference.com/w/
- Google C++ Style Guide — https://google.github.io/styleguide/cppguide.html
- CMake documentation — https://cmake.org/documentation/
- AddressSanitizer — https://clang.llvm.org/docs/AddressSanitizer.html
- UndefinedBehaviorSanitizer — https://clang.llvm.org/docs/UndefinedBehaviorSanitizer.html
- ThreadSanitizer — https://clang.llvm.org/docs/ThreadSanitizer.html
- libFuzzer — https://llvm.org/docs/LibFuzzer/
- clang-tidy — https://clang.llvm.org/extra/clang-tidy/
- Valgrind — https://valgrind.org/docs/manual/manual.html
