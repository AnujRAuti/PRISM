"""Severity read-out for credential-shaped text in tracked files, with values masked.

Prints only: file, line, whether the URL carries a password, that password's
length, and a host class. No credential value is ever emitted.
"""

import re
import subprocess
import sys

URL = re.compile(r"([a-z+]{3,24})://(?:([^\s\"'@/:]*)(:([^\s\"'@/]*))?@)?([^\s\"'@/\n]+)")
TARGETS = sys.argv[1:]


def host_class(host: str) -> str:
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return "local"
    if re.fullmatch(r"(\d{1,3}\.){3}\d{1,3}", host):
        return "public-ip" if not host.startswith(("10.", "192.168.", "172.16.", "127.")) else "private-ip"
    if "supabase" in host or "azure" in host or "github" in host:
        return "saas:" + host
    return "hostname:" + host.split(".")[0]


def main() -> int:
    root = r"D:/CODING/Projects/Proof-Of-Action-Final"
    for name in TARGETS:
        exists = subprocess.run(["git", "ls-files", "--error-unmatch", name],
                                cwd=root, capture_output=True).returncode == 0
        try:
            lines = open(f"{root}/{name}", encoding="utf-8", errors="replace").read().splitlines()
        except OSError as error:
            print(f"{name} :: unreadable ({error.__class__.__name__}) tracked={exists}")
            continue
        print(f"\n### {name}  tracked_at_head_index={exists}  bytes={sum(len(l)+1 for l in lines)}")
        for number, line in enumerate(lines, 1):
            for match in URL.finditer(line):
                password = match.group(4)
                if password is None and match.group(2) is None:
                    continue
                print(f"  line {number}: scheme={match.group(1)} host={host_class(match.group(5))} "
                      f"user={(match.group(2) or '')[:16]} password_len={len(password) if password else 0}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
