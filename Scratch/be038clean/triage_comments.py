"""BE-038-prep: triage backend/ comment lines into noise vs decision records.

Conservative by design: a comment is only offered for deletion when its text
either (a) is commented-out code, (b) restates the line immediately after it, or
(c) carries a stale-work marker. Anything mentioning a milestone ref, a §, a
constraint, or a reason is left in the "keep" bucket unlisted.

Prints: counts per bucket, then every candidate with file:line and verbatim text.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path("D:/CODING/Projects/Proof-Of-Action-Final")
files = [f for f in subprocess.run(["git", "-C", str(REPO), "ls-files", "backend"],
                                   capture_output=True, text=True).stdout.split()
         if f.endswith(".py")]

# Comment whose body looks like Python that was switched off.
CODEISH = re.compile(
    r"^(?:@\w|def |class |import |from |return |yield |raise |if |elif |else|for |while |"
    r"try |except |with |print\(|assert |db\.|self\.|[A-Za-z_][\w.]*\([^)]*\)\s*:?|"
    r"[A-Za-z_][\w.\[\]\'\"]*\s*=[^=]|[A-Za-z_][\w.]*\s*\+=|#)",
    re.S)

# Markers that a note was about the work session, not the code.
STALE = re.compile(r"\b(TODO|FIXME|XXX|HACK|for now|temporar|remove this|delete this|"
                   r"uncomment|debug only|not used anymore|no longer|WIP)\b", re.I)

# A reason, a reference, or a constraint -> decision record, never noise.
LOAD_BEARING = re.compile(
    r"(BE-0\d\d|§|D-CHAIN|D-2|D-1|F-0\d|OQ-\d|G\d|I\d|TRUNCATE|because|so that|must|"
    r"cannot|do not|don't|never|refus|guards?|invariant|policy|hole|bypass|measured|"
    r"otherwise|instead of|requires|why|note:|caution|warn|deprecat|historical)", re.I)

WORDS = re.compile(r"[a-z0-9_]+")

noise: dict[str, list[str]] = {"commented_out_code": [], "restates_next_line": [],
                               "stale_marker": [], "empty_or_decoration": [],
                               "trailing_restatement": []}
STOP = {"the", "a", "an", "to", "of", "is", "are", "in", "on", "for", "and", "or",
        "this", "that", "it", "its", "we", "will", "be", "as", "by", "with", "use",
        "used", "uses", "returns", "return", "line", "code", "same", "here", "note"}
keep_count = 0
scanned = 0

for rel in files:
    path = REPO / rel
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        continue
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        scanned += 1
        body = stripped.lstrip("#").strip()
        tag = f"{rel}:{i}: {stripped}"
        if not body or set(body) <= {"-", "=", "#", "*", " ", "~"}:
            noise["empty_or_decoration"].append(tag)
        elif STALE.search(body):
            noise["stale_marker"].append(tag)
        elif CODEISH.match(body):
            noise["commented_out_code"].append(tag)
        elif LOAD_BEARING.search(body):
            keep_count += 1
        else:
            # restatement: every word of the comment already appears in the next
            # non-comment, non-blank line of code.
            nxt = ""
            for follow in lines[i:i + 2]:
                if follow.strip() and not follow.strip().startswith("#"):
                    nxt = follow
                    break
            cw = set(WORDS.findall(body.lower())) - STOP
            nw = set(WORDS.findall(nxt.lower())) - STOP
            if cw and cw <= nw:
                noise["restates_next_line"].append(f"{tag}   ||next: {nxt.strip()[:70]}")
            else:
                keep_count += 1
    # trailing comments: `code = 1  # code`
    for i, line in enumerate(lines, 1):
        if "#" not in line or line.strip().startswith("#"):
            continue
        code, _, tail = line.partition("#")
        body = tail.strip()
        if not body or LOAD_BEARING.search(body):
            continue
        cw = set(WORDS.findall(body.lower())) - STOP
        nw = set(WORDS.findall(code.lower())) - STOP
        if cw and cw <= nw:
            noise["trailing_restatement"].append(
                f"{rel}:{i}: {line.strip()[:120]}")

out = Path(__file__).resolve().parent / "noise_candidates.txt"
lines_out = [f"scanned {scanned} comment lines in {len(files)} files"]
for k, v in noise.items():
    lines_out.append(f"  {k}: {len(v)}")
lines_out.append(f"  kept (decision record, reason, or unclassified): {keep_count}")
lines_out.append(f"  total offered for deletion: {sum(len(v) for v in noise.values())}")
for k, v in noise.items():
    lines_out.append(f"\n===== {k} ({len(v)}) =====")
    lines_out.extend(v)
out.write_text("\n".join(lines_out) + "\n", encoding="utf-8")

print(f"scanned {scanned} comment lines in {len(files)} files")
for k, v in noise.items():
    print(f"  {k}: {len(v)}")
print(f"  kept (decision record, reason, or unclassified): {keep_count}")
print(f"  total offered for deletion: {sum(len(v) for v in noise.values())}")
print(f"full listing: {out}")
for k in ("commented_out_code", "stale_marker"):
    for item in noise[k]:
        print(f"[{k}] " + item.encode("ascii", "backslashreplace").decode())
