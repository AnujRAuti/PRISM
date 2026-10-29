"""PRISM Phase 1a: attribute every sensitive-flagged path to the unpublished
commits that carry it, and classify each credential-shaped match.

Prints variable names, DSN user/host pairs and value LENGTHS/digests only. A
matched secret value is never written to stdout, so this output is safe to
commit.
"""
import hashlib
import re
import subprocess
import sys
from collections import Counter

UPSTREAM = sys.argv[1] if len(sys.argv) > 1 else "origin/Backend"

DSN = re.compile(r"postgres(?:ql)?(?:\+\w+)?://([^\s/@]*):([^\s@]+)@([^\s\"'`,)]*)")
ASSIGN = re.compile(
    r"(?i)^\s*(?:export\s+)?([A-Za-z0-9_]*(?:SECRET|PASSWORD|PASSWD|TOKEN|KEY|_PW|CREDENTIAL)"
    r"[A-Za-z0-9_]*)\s*[=:]\s*[\"']?([^\"'\s]+)[\"']?\s*$"
)
TEMPLATE = re.compile(
    r"<[^>]*>|\{\{|\{[A-Za-z_][A-Za-z0-9_]*\}|\$\{?\w|%\w|\(.*\)"
    r"|example|placeholder|changeme|change_me|your_|dummy|fake|xxx+|test_secret", re.I)

NAME_BUCKETS = [
    ("DATABASE_DUMP", r"(?i)\.(dump|sql\.gz)$"),
    ("BINARY_ARCHIVE", r"(?i)\.(tar|tgz|zip|gz)$"),
    ("PASSWORD_FILE", r"(?i)password|passwd|credential"),
    ("SECRET_ENV", r"(?i)(secrets?\.env|env\.owner|\.env\.bak|\.env\.backup|env\.bak)$"),
    ("DIFF_SNAPSHOT", r"(?i)staged\.diff$"),
    ("URL_DUMP", r"(?i)_testurl\.txt$"),
    ("ENV_FILE", r"(?i)\.env$"),
    ("SQL_DATA_EXPORT", r"(?i)\.sql$"),
]
NAME_BUCKETS = [(name, re.compile(rx)) for name, rx in NAME_BUCKETS]

LOCAL_DEV_DEFAULTS = {"postgres", "poa_runtime", "poa_owner"}


def git(*args):
    proc = subprocess.run(["git", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.stdout


def digest(value):
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:10]


def is_template(text):
    return bool(TEMPLATE.search(text or ""))


def shape(value):
    v = (value or "").strip("'\"")
    if is_template(v):
        return "TEMPLATE"
    if re.search(r"[A-Za-z_]\w*[.(\[]|^f[\"']|settings\.|self\.|=\s*\w", v):
        return "CODE-REF"
    if v.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", v) or v.endswith((".env", ".txt", ".sql", ".json")):
        return "FILE-PATH"
    if v.startswith("eyJ"):
        return "JWT"
    if len(v) < 8:
        return "SHORT"
    if re.fullmatch(r"[0-9a-fA-F]+", v) and len(v) >= 16:
        return "HEX-SECRET"
    if re.fullmatch(r"[A-Za-z0-9_\-./+=]+", v) and len(v) >= 20:
        return "BASE64-ISH"
    return "PLAINTEXT"


def main():
    new_to_old = [c for c in git("rev-list", f"{UPSTREAM}..HEAD").split() if c]
    oldest_first = list(reversed(new_to_old))
    short = {c: c[:8] for c in new_to_old}

    trees = {short[c]: set(git("ls-tree", "-r", "--name-only", c).split())
             for c in new_to_old}
    newest, oldest = short[new_to_old[0]], short[oldest_first[0]]

    flagged = sorted({p for paths in trees.values()
                      for p in paths
                      if any(rx.search(p) for _, rx in NAME_BUCKETS)})

    print(f"unpublished commits analysed          : {len(new_to_old)}"
          f"  ({oldest} .. {newest})")
    print(f"paths flagged by artifact name        : {len(flagged)}")
    print()
    print("PATH".ljust(60), "CLASS".ljust(17), "ATTRIBUTION")
    for p in flagged:
        cls = next((n for n, rx in NAME_BUCKETS if rx.search(p)), "?")
        carriers = [c for c in [short[x] for x in oldest_first] if p in trees[c]]
        print(p[:59].ljust(60), cls.ljust(17),
              f"first={carriers[0]} last={carriers[-1]} in={len(carriers)}/{len(trees)}")
    print()
    counter = Counter(next((n for n, rx in NAME_BUCKETS if rx.search(p))
                           for p in flagged))
    print("per-class path counts: " + ", ".join(f"{k}={v}" for k, v in counter.most_common()))
    at_head = sorted(trees[newest] & set(flagged))
    head_counter = Counter(next(n for n, rx in NAME_BUCKETS if rx.search(p)) for p in at_head)
    print("still present at HEAD: "
          + ", ".join(f"{k}={v}" for k, v in head_counter.most_common())
          + f" (total {len(at_head)})")

    print()
    print("== credential-shaped content at HEAD (values never printed) ==")
    decisions = []
    decision_values = []
    inert_kinds = Counter()
    known_dev = {digest(v) for v in LOCAL_DEV_DEFAULTS}
    INERT_SHAPES = {"TEMPLATE", "CODE-REF", "FILE-PATH", "SHORT"}
    flagged_set = set(flagged)
    for p in sorted(trees[newest]):
        if p in flagged_set:
            continue
        blob = subprocess.run(["git", "show", f"{newest}:{p}"],
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        if blob.returncode != 0:
            continue
        t = blob.stdout
        if "\x00" in t[:8000] or len(t) > 4_000_000:
            continue
        for i, line in enumerate(t.splitlines(), 1):
            for m in DSN.finditer(line):
                user, pw, host = m.group(1), m.group(2), m.group(3)
                tag = shape(pw)
                if tag in INERT_SHAPES:
                    inert_kinds[f"dsn-{tag}"] += 1
                elif digest(pw) in known_dev and re.search(
                        r"(?i)local|127\.0\.0\.1|db:|host\.|\{", host):
                    inert_kinds["dsn-local-dev-or-container-default"] += 1
                else:
                    decisions.append(("DSN", shape(pw),
                                      f"user={user[:24] or '(none)'} "
                                      f"host={host[:44] or '(none)'} pw_len={len(pw)}",
                                      f"{p}:{i}"))
                    decision_values.append(pw)
            for m in ASSIGN.finditer(line):
                name, val = m.group(1), m.group(2)
                tag = shape(val)
                if tag in INERT_SHAPES or digest(val) in known_dev:
                    inert_kinds[f"assign-{tag}"] += 1
                else:
                    decisions.append(("ASSIGN", tag, f"var={name} val_len={len(val)}",
                                      f"{p}:{i}"))
                    decision_values.append(val)
    print(f"inert matches : {sum(inert_kinds.values())} "
          + " ".join(f"({k}={v})" for k, v in sorted(inert_kinds.items())))
    print(f"literal credential-shaped matches : {len(decisions)}")
    grouped = {}
    for (kind, tag, detail, loc), value in zip(decisions, decision_values):
        key = digest(value)
        entry = grouped.setdefault(key, {"shape": tag, "len": len(value),
                                        "kind": kind, "where": [], "detail": detail})
        entry["where"].append(loc)
    print(f"distinct literal values : {len(grouped)}")
    for key, e in sorted(grouped.items(), key=lambda kv: -len(kv[1]["where"])):
        print(f"   sha256:{key} [{e['kind']}/{e['shape']}] len={e['len']} "
              f"places={len(e['where'])} :: {e['detail']}")
        for w in e["where"][:4]:
            print(f"        {w}")
        if len(e["where"]) > 4:
            print(f"        … {len(e['where']) - 4} more")


if __name__ == "__main__":
    main()
