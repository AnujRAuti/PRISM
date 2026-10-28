"""Stage 12 step 4 — precise before/after comparison of the protected-resource checks.

Every substantive line of stage12-01 (baseline, taken before cleanup) must appear
verbatim in stage12-03 (post-cleanup), except the three lines this step re-queried
with corrected SQL (the seq_no / version() bugs) and the noise lines.
"""
import sys

base = open("stage12-01-protected-baseline-before.txt", encoding="utf-8").read().splitlines()
post = open("stage12-03-post-cleanup-verification.txt", encoding="utf-8").read()

SKIP_START = ("===", "utc=", "---")
SKIP_CONTAINS = ("template parsing error",)
# lines re-issued with corrected SQL in step 4
REPLACED = {"pg=15.13 (Debian 15.13-1.pgdg120+1)": "pg=PostgreSQL 15.13"}

checked = 0
missing = []
for line in base:
    stripped = line.strip()
    if not stripped or stripped.startswith(SKIP_START):
        continue
    if any(s in stripped for s in SKIP_CONTAINS):
        continue
    expected = REPLACED.get(stripped, stripped)
    checked += 1
    if expected not in post:
        missing.append(stripped)

print(f"baseline checks compared: {checked}")
print(f"missing/changed after cleanup: {len(missing)}")
for m in missing:
    print("  MISSING: " + m)
print("RESULT: " + ("IDENTICAL — no protected resource changed" if not missing else "DRIFT DETECTED"))
sys.exit(0 if not missing else 1)
