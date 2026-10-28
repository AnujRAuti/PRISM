"""Live anonymous-probe of every route at HEAD with AUTH_MODE=enforcing.

For each route/method on the committed app, send a request with NO credential
and record the status. A guarded route must refuse before its handler runs, so
anything that answers 2xx/3xx (or 404, which would mean the handler ran and
looked the resource up) is an authorization gap.

Runs against the armed disposable database; nothing is written because every
refused request never reaches its handler.
"""
import os
import re
import sys
import uuid

sys.path.insert(0, r"D:\CODING\Projects\Proof-Of-Action-Final")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from armfull import arm_env  # noqa: E402

env = arm_env()
os.environ.update(env)
os.environ["ENVIRONMENT"] = "development"
os.environ["AUTH_MODE"] = "enforcing"
os.environ["AUTH_DEV_TOKENS_ENABLED"] = "false"
os.environ["AUTH_OIDC_ENABLED"] = "false"
os.environ["DATABASE_URL"] = env["TEST_DATABASE_URL"]

from fastapi.testclient import TestClient  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.core.config import settings  # noqa: E402

assert settings.auth_mode == "enforcing", settings.auth_mode
assert settings.auth_dev_tokens_enabled is False
assert settings.auth_oidc_enabled is False
print(f"auth_mode={settings.auth_mode} dev_tokens={settings.auth_dev_tokens_enabled} "
      f"oidc={settings.auth_oidc_enabled} db={os.environ['DATABASE_URL'].split('@')[-1]}")

PARAM = re.compile(r"\{([^}]+)\}")


def collect(routes, prefix, out):
    for r in routes:
        if type(r).__name__ == "_IncludedRouter":
            ic = r.include_context
            collect(ic.included_router.routes, prefix + (ic.prefix or ""), out)
        elif getattr(r, "methods", None) and hasattr(r, "dependant"):
            for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
                out.append((m, prefix + r.path))


targets = []
collect(app.router.routes, "", targets)
print(f"probing {len(targets)} route/method pairs anonymously")

results = []
with TestClient(app) as client:
    for method, template in sorted(targets, key=lambda t: (t[1], t[0])):
        path = PARAM.sub(lambda _m: str(uuid.uuid4()), template)
        try:
            response = client.request(method, path)
            status_code = response.status_code
        except Exception as error:  # a refusal that crashed is still a finding
            status_code = f"EXC:{type(error).__name__}"
        results.append((method, template, status_code))

refusing = [r for r in results if r[2] in (401, 403)]
other = [r for r in results if r[2] not in (401, 403)]

with open("anon_probe.txt", "w", encoding="utf-8") as fh:
    for method, template, status_code in results:
        fh.write(f"{status_code!s:12} {method:6} {template}\n")
    fh.write(f"\ntotal={len(results)} refused(401/403)={len(refusing)} "
             f"other={len(other)}\n\n=== NOT refused ===\n")
    for method, template, status_code in other:
        fh.write(f"{status_code!s:12} {method:6} {template}\n")

print(f"total={len(results)} refused(401/403)={len(refusing)} other={len(other)}")
print("\n=== NOT refused by authentication ===")
for method, template, status_code in other:
    print(f"{status_code!s:12} {method:6} {template}")
