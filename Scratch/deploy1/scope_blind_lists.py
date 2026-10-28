"""Which list/read endpoints check a permission but not a project scope?

A guard of the form require(action) with no resource only proves the caller
holds the permission in ANY scope. If the handler then lists rows without
restricting them to visible projects, a reviewer granted PROJECT scope for one
project can read other projects' records.
"""
import ast
import inspect
import os
import sys

os.environ.setdefault("ENVIRONMENT", "development")
sys.path.insert(0, r"D:\CODING\Projects\Proof-Of-Action-Final")

from backend.app.main import app  # noqa: E402

AUTHZ = "backend.security.authorization"
SCOPE_HELPERS = ("visible_project_ids", "filter_by_project_scope", "filter_graph_edges")


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


def module_functions_source(fn):
    """Source of fn plus every same-module function, for a text scope scan."""
    module = sys.modules.get(getattr(fn, "__module__", "") or "")
    parts = []
    try:
        parts.append(inspect.getsource(fn))
    except (OSError, TypeError):
        pass
    for name in dir(module or ()):
        obj = getattr(module, name, None)
        if inspect.isfunction(obj) and obj.__module__ == getattr(fn, "__module__", None):
            try:
                parts.append(inspect.getsource(obj))
            except (OSError, TypeError):
                pass
    return "\n".join(parts)


def collect(routes, prefix, out):
    for r in routes:
        if type(r).__name__ == "_IncludedRouter":
            ic = r.include_context
            collect(ic.included_router.routes, prefix + (ic.prefix or ""), out)
        elif getattr(r, "methods", None) and hasattr(r, "dependant"):
            endpoint = r.dependant.call
            guards = []
            for fn in walk(r.dependant, skip=endpoint):
                if getattr(fn, "__module__", "") == AUTHZ:
                    v = closure_vars(fn)
                    guards.append((getattr(fn, "__qualname__", "").split(".")[0],
                                   v.get("action"), v.get("resource_type"),
                                   v.get("id_param")))
            for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
                out.append((m, prefix + r.path, guards, endpoint))


rows = []
collect(app.router.routes, "", rows)

# Read-shaped routes (GET list/collection) whose guard checks no resource scope.
findings = []
for method, template, guards, endpoint in rows:
    if method != "GET":
        continue
    unscoped = [g for g in guards if g[0] == "require" and g[2] is None]
    if not unscoped:
        continue
    src = module_functions_source(endpoint)
    scopes = [h for h in SCOPE_HELPERS if f"{h}(" in src]
    if scopes:
        continue
    findings.append((template, endpoint, unscoped, guards))

print(f"GET routes whose guard checks permission-in-any-scope only: {len(findings)}\n")
for template, endpoint, unscoped, guards in sorted(findings):
    detail = ", ".join(f"{g[1]}" for g in unscoped)
    kind = "resource-less require" if guards else "none"
    print(f"{template:60} guard={kind:22} actions={detail} "
          f"({endpoint.__module__.split('.')[-1]}:{endpoint.__qualname__})")
