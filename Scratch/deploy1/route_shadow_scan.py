"""Which declared routes are unreachable because an earlier route shadows them?

Starlette matches routes in declaration order, so a literal single-segment path
declared *after* a parameterized sibling (``/policies`` after ``/{id}``) never
reaches its handler. A handler that cannot be reached cannot be exercised by any
test either -- its guard, its scope predicate and its whole contract are
unmeasured code.

Method: flatten the included routers to full path templates in declaration
order, rebuild each as a plain Starlette Route (same template semantics), fill
every ``{param}`` with a sentinel literal, and replay the first-full-match-wins
walk. A winner that is not the declaring endpoint means the route is shadowed.
"""
import os
import re
import sys

os.environ.setdefault("ENVIRONMENT", "development")
sys.path.insert(0, r"D:\CODING\Projects\Proof-Of-Action-Final")

from starlette.routing import Match, Route  # noqa: E402

from backend.app.main import app  # noqa: E402

SENTINEL = "SENTINELID"
PARAM = re.compile(r"\{[^}]+\}")


def collect(routes, prefix, out):
    for r in routes:
        if type(r).__name__ == "_IncludedRouter":
            ic = r.include_context
            collect(ic.included_router.routes, prefix + (ic.prefix or ""), out)
        elif getattr(r, "methods", None):
            for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
                out.append((m, prefix + r.path, r))


rows = []
collect(app.router.routes, "", rows)
print(f"flattened method/route pairs: {len(rows)}")

matchers = []
for method, template, route in rows:
    if re.search(r"\{\w+:\w+\}", template):
        continue  # convertor-typed params need a typed sentinel; not exercised
    matchers.append((method, template, route,
                     Route(template, endpoint=route.endpoint, methods=[method])))

shadowed, unmatched, ok = [], [], []
for method, template, route in rows:
    if re.search(r"\{\w+:\w+\}", template):
        continue
    path = PARAM.sub(SENTINEL, template)
    scope = {"type": "http", "method": method, "path": path, "path_params": {},
             "headers": [], "query_string": b"", "root_path": ""}
    winner = None
    for candidate_method, candidate_template, candidate, matcher in matchers:
        if candidate_method != method:
            continue
        match, child = matcher.matches(dict(scope))
        if match == Match.FULL:
            winner = (candidate_template, candidate.endpoint)
            break
    if winner is None:
        unmatched.append((method, template, path))
    elif winner[1] is not route.endpoint:
        shadowed.append((method, template, path, winner))
    else:
        ok.append((method, template))

print(f"tested pairs:            {len(ok) + len(unmatched) + len(shadowed)}")
print(f"reachable as declared:   {len(ok)}")
print(f"no full match at all:    {len(unmatched)}")
print(f"SHADOWED by an earlier route: {len(shadowed)}\n")
for method, template, path, winner in sorted(shadowed):
    module = getattr(winner[1], "__module__", "?").split(".")[-1]
    owner = getattr(winner[1], "__qualname__", "?")
    print(f"  SHADOW  {method:6} {template:52} -> answered by {winner[0]}")
    print(f"          {'':6} {'':52}   ({module}:{owner})")
for method, template, path in sorted(unmatched):
    print(f"  NOMATCH {method:6} {template:52} (sentinel path {path})")
