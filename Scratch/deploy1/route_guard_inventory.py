"""Route -> guard inventory for the committed app (fastapi 0.141 lazy routers).

Classifies every endpoint by the protection actually attached to it:
  AUTHZ-GUARD     an authorization dependency (require/require_global/require_target)
  AUTHZ-LOCAL     a dependency or the handler body that calls enforce()/scope helpers
  AUTHN-ONLY      resolves a principal, no permission/scope evaluation found
  ANONYMOUS       no authentication dependency at all

Detection reads the real dependency tree plus source, so it cannot be fooled by a
route that merely looks guarded in a docstring.
"""
import inspect
import os
import re
import sys

os.environ.setdefault("ENVIRONMENT", "development")
sys.path.insert(0, r"D:\CODING\Projects\Proof-Of-Action-Final")

from backend.app.main import app  # noqa: E402

AUTHZ = "backend.security.authorization"
AUTHN = "backend.security.authentication"
GUARD_QUALS = ("require.<locals>", "require_global.<locals>", "require_target.<locals>")
AUTHZ_CALLS = re.compile(
    r"\benforce\(|\bcan\(|filter_by_project_scope|visible_project_ids|filter_graph_edges"
)


def closure_vars(fn):
    out = {}
    code = getattr(fn, "__code__", None)
    free = getattr(code, "co_freevars", ()) if code else ()
    for name, cell in zip(free, getattr(fn, "__closure__", None) or ()):
        try:
            out[name] = cell.cell_contents
        except ValueError:
            out[name] = "<empty>"
    return out


def walk(dependant, skip=None):
    fn = getattr(dependant, "call", None)
    if fn is not None and fn is not skip:
        yield fn
    for sub in getattr(dependant, "dependencies", ()) or ():
        yield from walk(sub, skip)


def source_of(fn):
    try:
        return inspect.getsource(fn)
    except (OSError, TypeError):
        return ""


import ast  # noqa: E402

_graph_cache: dict = {}


def called_names(fn):
    """Names called directly in this function body (cached)."""
    key = (getattr(fn, "__module__", "?"), getattr(fn, "__qualname__", "?"), id(fn))
    if key in _graph_cache:
        return _graph_cache[key]
    src = source_of(fn)
    names = set()
    try:
        tree = ast.parse(src[src.index("def ") if src else 0:] or "pass")
    except (SyntaxError, ValueError):
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name):
                    names.add(f.id)
                elif isinstance(f, ast.Attribute):
                    names.add(f.attr)
    _graph_cache[key] = names
    return names


def authz_reachable(fn, depth=4):
    """Return the helper chain that reaches a real authorization decision."""
    module = sys.modules.get(getattr(fn, "__module__", "") or "")
    seen, frontier, chain = set(), [fn], []
    for _ in range(depth):
        next_frontier = []
        for current in frontier:
            if current in seen:
                continue
            seen.add(current)
            src = source_of(current)
            if src and AUTHZ_CALLS.search(src):
                chain.append(getattr(current, "__qualname__", "?"))
                continue
            for name in called_names(current):
                target = getattr(module, name, None)
                if callable(target) and getattr(target, "__module__", None) == \
                        getattr(fn, "__module__", None):
                    next_frontier.append(target)
        frontier = next_frontier
        if not frontier:
            break
    return chain


def classify(endpoint, dep_fns, all_fns):
    guards = []
    authn = False
    local_authz = []
    for fn in dep_fns:
        mod = getattr(fn, "__module__", "") or ""
        qual = getattr(fn, "__qualname__", "") or ""
        if mod == AUTHN and qual.startswith("get_current_principal"):
            authn = True
        if mod == AUTHZ and any(qual.startswith(g) for g in GUARD_QUALS):
            v = closure_vars(fn)
            guards.append(f"require(action={v.get('action')}, resource={v.get('resource_type')}, "
                          f"id_param={v.get('id_param')})".replace("require(",
                          f"{qual.split('.')[0]}("))
    for fn in all_fns:
        chain = authz_reachable(fn)
        if chain:
            label = getattr(fn, "__qualname__", "?")
            local_authz.append(f"{label} -> {'/'.join(chain)}")
    if guards:
        return "AUTHZ-GUARD", "; ".join(guards)
    if local_authz:
        return "AUTHZ-LOCAL", "; ".join(sorted(set(local_authz)))
    if authn:
        return "AUTHN-ONLY", "principal only"
    return "ANONYMOUS", "no auth dependency"


rows = []


def collect(routes, prefix, inherited):
    for r in routes:
        if type(r).__name__ == "_IncludedRouter":
            ic = r.include_context
            sub = r.original_router
            extra = [d for d in (ic.dependencies or [])] + list(sub.dependencies or [])
            collect(sub.routes, prefix + (ic.prefix or ""), inherited + extra)
        elif getattr(r, "methods", None):
            methods = sorted(m for m in r.methods if m != "HEAD")
            if not methods:
                continue
            if not hasattr(r, "dependant"):
                rows.append((prefix + r.path, methods, "FRAMEWORK", "not an endpoint"))
                continue
            endpoint = r.dependant.call
            dep_fns = list(walk(r.dependant, skip=endpoint))
            fns = dep_fns + [endpoint] + [getattr(d, "dependency", d) for d in inherited]
            kind, detail = classify(endpoint, dep_fns + [getattr(d, "dependency", d)
                                                         for d in inherited], fns)
            rows.append((prefix + r.path, methods, kind, detail))


collect(app.router.routes, "", [])
rows.sort(key=lambda x: (x[2], x[0], x[1]))

counts = {}
for _p, _m, kind, _d in rows:
    counts[kind] = counts.get(kind, 0) + 1

with open("route_guard_inventory.txt", "w", encoding="utf-8") as fh:
    for path, methods, kind, detail in rows:
        fh.write(f"{kind:12} {','.join(methods):20} {path:64} {detail}\n")
    fh.write("\n" + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())) +
             f"  total={len(rows)}\n")

print("  ".join(f"{k}={v}" for k, v in sorted(counts.items())) + f"  total={len(rows)}")
print("\n=== NOT protected by an authorization decision ===")
for path, methods, kind, detail in rows:
    if kind in ("AUTHN-ONLY", "ANONYMOUS"):
        print(f"{kind:12} {','.join(methods):20} {path:64} {detail}")
