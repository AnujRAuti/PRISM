"""BE-029 G3 preflight: decide whether the dump/restore predicate differences
in restore_verify.py are cosmetic or real.

pg_dump always re-creates CHECK constraints (and partial-index WHERE clauses)
through ALTER TABLE ADD CONSTRAINT / CREATE INDEX, and PostgreSQL stores that
form with the ::text coercion applied per array element instead of around the
whole array. So the deparsed text differs while the rule is the same:

  source    : (status)::text = ANY ((ARRAY['ACTIVE'::character varying, ...])::text[])
  restored  : (status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ...])

This script proves equivalence instead of assuming it. For every object whose
text differs it pulls out the expression and evaluates BOTH forms side by side
over every value the column actually holds, plus a value outside the allowed
set and NULL. Any row where the two forms classify differently is a real
difference and gets reported.

Usage: python check_equiv.py <source-url> <restored-url> <restore_verify.json>
"""
import json
import re
import sys

import psycopg2
from psycopg2.extras import RealDictCursor

SRC_URL, DST_URL, DATA = sys.argv[1], sys.argv[2], sys.argv[3]
data = json.load(open(DATA))
src, dst = data["source"], data["restored"]

# word-boundary replacement of the bare column name with the probe alias
COL_RE = r"\b{name}\b"


def key(entry):
    return (entry.get("table_name", ""), entry["name"])


def norm(items):
    return {key(e): e for e in items}


def text_key(entry):
    return entry["def"]


def differing(section):
    a, b = norm(src[section]), norm(dst[section])
    assert set(a) == set(b), (
        f"{section}: object NAME sets differ: {sorted(set(a) ^ set(b))}")
    return [(a[k], b[k]) for k in a if a[k]["def"] != b[k]["def"]]


def predicate(expr_text):
    """Strip the leading CHECK ( ... ) / WHERE wrapper down to the boolean expr."""
    text = expr_text.strip()
    if " WHERE " in text.upper() and not text.startswith("CHECK ("):
        # partial index: only the inferred predicate is the rule
        text = text[text.upper().index(" WHERE ") + len(" WHERE "):]
    if text.startswith("CHECK (") and text.endswith(")"):
        text = text[len("CHECK ("):-1]
        # remove the single balancing close paren belonging to CHECK (
        depth, cut = 0, len(text)
        for i, ch in enumerate(text):
            depth += ch == "("
            depth -= ch == ")"
            if depth < 0:
                cut = i
                break
        text = text[:cut]
    return text


def columns_of(expr):
    return sorted({m for m in re.findall(r"\b([a-z_][a-z0-9_]*)\b", expr)
                   if m not in {"text", "any", "array", "character", "varying",
                                "is", "null", "not", "or", "and", "true", "false",
                                "coalesce", "lower", "upper", "cast", "int",
                                "interval", "now", "numtodsinterval", "precision"}})


problems = []
checked = []
for section in ("constraints", "indexes"):
    diffs = differing(section)
    print(f"\n=== {section}: {len(diffs)} object(s) whose deparsed text differs")
    for a, b in diffs:
        table = a.get("table_name") or "public." + a["name"].split("_")[0]
        if section == "indexes":
            table = re.search(r"ON public\.(\w+)", a["def"]).group(1)
        ea, eb = predicate(a["def"]), predicate(b["def"])
        cols = [c for c in columns_of(ea) if c in {x for x in columns_of(ea)}]
        # The predicate must reference exactly one column of this table.
        with psycopg2.connect(DST_URL) as conn:
            conn.set_session(readonly=True, autocommit=True)
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT column_name AS c FROM information_schema.columns"
                        " WHERE table_schema='public' AND table_name=%s"
                        " AND column_name = ANY(%s)", (table, cols))
            real = [r["c"] for r in cur.fetchall()]
            if len(real) != 1:
                problems.append(f"{section} {a['name']}: cannot pin a single column"
                                f" (candidates {cols} -> {real}); text forms also differ")
                print(f"  SKIPPED {a['name']}: ambiguous column {cols} -> {real}")
                continue
            col = real[0]
            qa, qb = (re.sub(COL_RE.format(name=col), "s.v", e) for e in (ea, eb))
            sql = (
                f"SELECT count(*) AS n FROM ("
                f"  SELECT {col} AS v FROM \"{table}\""
                f"  UNION ALL SELECT '__BOGUS_VALUE__'"
                f"  UNION ALL SELECT NULL::text"
                f") s"
                f" WHERE ({qa}) IS DISTINCT FROM ({qb})")
            try:
                cur.execute(sql)
                mismatch = cur.fetchone()["n"]
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                # a text probe against a non-text column: cast the probe instead
                cur.execute(
                    f"SELECT pg_typeof({col}) AS t FROM \"{table}\" LIMIT 1")
                problems.append(f"{section} {a['name']}: probe failed ({exc})")
                print(f"  FAILED  {table}.{a['name']}: {exc}")
                continue
        same_shape = sorted(set(re.findall(r"'([^']*)'", ea))) == \
            sorted(set(re.findall(r"'([^']*)'", eb)))
        verdict = "EQUIVALENT" if mismatch == 0 and same_shape else "DIFFERENT"
        if verdict != "EQUIVALENT":
            problems.append(f"{section} {a['name']}: {mismatch} disagreeing value(s)"
                            f" literal_sets_equal={same_shape}")
        checked.append((section, a["name"], verdict))
        print(f"  {verdict:11} {table}.{a['name']}  literals_equal={same_shape}")

print(f"\nobjects compared: {len(checked)}")
print("VERDICT:", "ALL PREDICATE DIFFERENCES ARE DEPARSE-ONLY (SEMANTICALLY EQUAL)"
      if not problems else f"REAL DIFFERENCES: {problems}")
sys.exit(0 if not problems else 1)
