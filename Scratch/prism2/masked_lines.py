"""Print selected lines with credential-shaped substrings masked."""
import re
import sys

DSN_PW = re.compile(r"(://[^:/@\s]{1,40}:)([^\s@\"']{4,})(@)")
QUOTED_ASSIGN = re.compile(
    r"(?i)^(\s*(?:export\s+)?[A-Za-z0-9_]*(?:SECRET|PASSWORD|TOKEN|_PW|KEY)[A-Za-z0-9_]*"
    r"\s*=\s*)(['\"])(.+?)\2(.*)$"
)


def mask(line):
    def repl(m):
        head, pw, tail = m.group(1), m.group(2), m.group(3)
        return head + "*" * len(pw) + tail
    line = DSN_PW.sub(repl, line)
    m = QUOTED_ASSIGN.match(line)
    if m and not re.search(r"token_hex|secrets\.|os\.environ|getenv|settings\.|\{|\(", m.group(3)):
        return f"{m.group(1)}<masked {len(m.group(3))} chars>{m.group(4)}"
    return line


for path in sys.argv[2:]:
    spec = sys.argv[1]
    lo, _, hi = spec.partition("-")
    print(f"### {path}")
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    start = int(lo) if lo.isdigit() else 1
    end = int(hi) if hi.isdigit() else len(lines)
    for n in range(start, min(end, len(lines)) + 1):
        print(f"{n:>4} {mask(lines[n - 1])[:120]}")
