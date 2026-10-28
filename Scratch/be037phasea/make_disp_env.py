"""BE-037A-D3: emit the two disposable-container env files without printing secrets.

Writes (mode 600, deleted during cleanup):
  .env.migrate  -- owner identity, alembic guard armed for the throwaway DB only
  .env.runtime  -- least-privilege runtime identity + an isolated Redis DB index

Nothing is echoed; the only stdout is the list of files written.
"""
import os
import re
import stat

import yaml


REPO = "D:/CODING/Projects/Proof-Of-Action-Final"
SCRATCH = os.path.dirname(os.path.abspath(__file__))
DB_HOST, DB_PORT, DISP_DB, DISP_ROLE = "db", "5432", "poa_be037a_disp", "poa_be037a_rt"
# The live application uses Redis DB 0; the disposable worker gets its own keyspace so
# it can never dequeue (and drop) a message belonging to the live development queue.
REDIS_DB_INDEX = os.environ.get("POA_DISP_REDIS_DB", "15")


def read_env_file(path):
    values = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def interpolate(value, env_file):
    match = re.fullmatch(r"\$\{(\w+)(?::-([^}]*))?\}", str(value))
    if not match:
        return str(value)
    return env_file.get(match.group(1)) or match.group(2) or ""


repo_env = read_env_file(os.path.join(REPO, ".env"))
with open(os.path.join(REPO, "docker-compose.yml"), encoding="utf-8") as handle:
    compose = yaml.safe_load(handle)
db_env = compose["services"]["db"]["environment"]
owner_password = interpolate(db_env["POSTGRES_PASSWORD"], repo_env)

with open(os.path.join(SCRATCH, ".disp_pw"), encoding="utf-8") as handle:
    runtime_password = handle.read().strip()

auth_mode = repo_env.get("AUTH_MODE", "development") or "development"

migrate_lines = [
    f"DATABASE_URL=postgresql+psycopg2://postgres:{owner_password}@{DB_HOST}:{DB_PORT}/{DISP_DB}",
    "POA_DATABASE_CONTEXT=verification",
    f"POA_AUTHORIZED_DATABASE_NAME={DISP_DB}",
    f"REDIS_URL=redis://{DB_HOST.replace('db', 'redis')}:6379/{REDIS_DB_INDEX}",
    "ENVIRONMENT=development",
]
runtime_lines = [
    f"DATABASE_URL=postgresql+psycopg2://{DISP_ROLE}:{runtime_password}@{DB_HOST}:{DB_PORT}/{DISP_DB}",
    f"REDIS_URL=redis://redis:6379/{REDIS_DB_INDEX}",
    "ENVIRONMENT=development",
    f"AUTH_MODE={auth_mode}",
]

for name, lines in ((".env.migrate", migrate_lines), (".env.runtime", runtime_lines)):
    path = os.path.join(SCRATCH, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    print(f"wrote {name} ({len(lines)} keys)")
