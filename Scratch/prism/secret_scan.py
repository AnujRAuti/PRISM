"""Report which tracked files embed credential-bearing URLs, with the secret masked.

Never prints a password: every match has its userinfo rewritten before output.
"""

import re
import subprocess
import sys

URL = re.compile(rb"([a-z+]{3,24})://([^\s\"'@/]{1,64}):([^\s\"'@/]{1,128})@([^\s\"'@\n]{1,96})")
KEY = re.compile(rb"(?i)(secret|password|token|key|credentials?)[\"']?\s*[:=]\s*[\"']([A-Za-z0-9_\-./+=]{8,})[\"']")


def files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=r"D:/CODING/Projects/Proof-Of-Action-Final",
                         capture_output=True, check=True).stdout
    return [f.decode() for f in out.splitlines()]


def classify(value: bytes) -> str:
    text = value.decode("utf-8", "replace")
    local = ("localhost" in text or "127.0.0.1" in text or "pofa_db" in text
             or "postgres" == text.split(":")[0])
    obvious_placeholder = text in {"postgres", "password", "changeme", "secret",
                                   "test", "replace-me", "your_password_here"}
    if obvious_placeholder:
        return "placeholder"
    if local:
        return "local-development"
    return "EXTERNAL-HOST"


def main() -> int:
    root = r"D:/CODING/Projects/Proof-Of-Action-Final"
    rows = []
    for name in files():
        try:
            with open(f"{root}/{name}", "rb") as handle:
                blob = handle.read()
        except OSError:
            continue
        hits = []
        for match in URL.finditer(blob):
            hits.append(classify(match.group(4)))
        for match in KEY.finditer(blob):
            value = match.group(2)
            if len(value) >= 24 and not any(c in value for c in (b" ", b"\t", b"\n")):
                hits.append("candidate-secret:" + match.group(1).decode())
        if hits:
            rows.append((name, sorted(set(hits))))
    for name, kinds in rows:
        print(f"{name} :: {', '.join(kinds)}")
    print(f"--- {len(rows)} tracked files carry credential-shaped text ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
