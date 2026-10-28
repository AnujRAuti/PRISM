"""BE-037A-D3 verification runner.

Builds TEST_DATABASE_URL for pofa_test from the local dev superuser credentials
that docker-compose.yml already declares, publishes it into the environment, and
delegates to pytest. Credential values are never printed.

Usage: python run_tests.py <pytest args...>
"""
import os
import re
import sys

import yaml


REPO = "D:/CODING/Projects/Proof-Of-Action-Final"


def _interpolate(value, env_file):
    match = re.fullmatch(r"\$\{(\w+)(?::-([^}]*))?\}", str(value))
    if not match:
        return value
    name, default = match.group(1), match.group(2)
    return env_file.get(name) or default


def owner_password():
    with open(os.path.join(REPO, "docker-compose.yml"), encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    env = document["services"]["db"]["environment"]
    with open(os.path.join(REPO, ".env"), encoding="utf-8") as handle:
        env_file = dict(
            line.split("=", 1)
            for line in (l.strip() for l in handle)
            if "=" in line and not line.startswith("#")
        )
    value = _interpolate(env["POSTGRES_PASSWORD"], env_file)
    if not isinstance(value, str) or not value:
        raise SystemExit("could not resolve the local dev superuser password")
    return value


os.environ["TEST_DATABASE_URL"] = (
    f"postgresql+psycopg2://postgres:{owner_password()}@localhost:5432/pofa_test"
)

import pytest  # noqa: E402  (must follow the env publish)

sys.exit(pytest.main(sys.argv[1:]))
