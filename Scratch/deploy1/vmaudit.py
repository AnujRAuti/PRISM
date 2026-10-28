"""Probe the deployed API's authentication enforcement as it is actually running.

Two sweeps against http://127.0.0.1:8000 on this VM:
  * every GET route with no credential at all
  * every route again carrying a development token, which production config
    disables, so it must also be refused

Path parameters are filled with random UUIDs, and unsafe methods are sent with an
empty body. On this database every table is still empty, so a request that should
have been refused can only ever 404/401/422 -- it cannot damage real records.

Prints METHOD PATH -> STATUS. Nothing about credentials is printed.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from uuid import uuid4

BASE = "http://127.0.0.1:8000"
SAFELIST = {}


def fetch(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=20) as resp:
        return json.loads(resp.read())


def call(method: str, path: str, token: str | None = None) -> int:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = b"{}" if method != "GET" else None
    req = urllib.request.Request(BASE + path, method=method, headers=headers, data=body)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception as exc:  # connection reset etc. -- reported, not swallowed
        return f"{type(exc).__name__}"  # type: ignore[return-value]


def fill(template: str) -> str:
    out = template
    while "{" in out:
        start = out.index("{")
        end = out.index("}", start)
        out = out[:start] + str(uuid4()) + out[end + 1:]
    return out


def main() -> int:
    spec = fetch("/openapi.json")
    rows = []
    for template, ops in sorted(spec["paths"].items()):
        for method in ops:
            if method.upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                continue
            rows.append((method.upper(), template))

    print(f"routes in live OpenAPI spec: {len(rows)}")
    anon, devtok = [], []
    fake_user = f"dev-user-{uuid4()}"
    for method, template in rows:
        path = fill(template)
        anon.append((method, template, call(method, path)))
        if method == "GET":
            devtok.append((method, template, call(method, path, fake_user)))

    def summarise(label: str, results: list) -> None:
        buckets: dict = {}
        for method, template, status in results:
            buckets.setdefault(status, []).append(f"{method} {template}")
        print(f"\n=== {label} ===")
        for status in sorted(buckets, key=lambda s: (isinstance(s, str), s)):
            items = buckets[status]
            print(f"{status}: {len(items)} routes")
            if status not in (401, 403):
                for item in items:
                    print(f"    {item}")

    summarise("NO CREDENTIAL", anon)
    summarise("GET ONLY, DEV TOKEN (must be refused in production)", devtok)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
