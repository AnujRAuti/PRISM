"""The container healthcheck has to probe readiness, not liveness.

M-BE-01 measured the four operational paths against a live stack and against two
injected outages (`/ready` reports which component is unhealthy and answers 503,
while `/health` keeps answering 200 with the database gone). So a healthcheck
pointed at `/health` cannot see an outage: the container stays "healthy" while
every request 500s, and the orchestrator never learns. This pins the compose
`api` healthcheck to a dependency-aware path, and pins the probe budget to the
measured response times so the check cannot flap a healthy container.

A healthy-stack `/healthz` answered in 2.09s and `/ready` in 2.54s here; the
floor below leaves room for a slow-but-alive dependency.
"""

import re
from pathlib import Path
from urllib.parse import urlparse

import pytest
import yaml

COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"

#: Paths whose verdict changes when a required dependency dies. `/health` is
#: documented as dependency-agnostic, so it is deliberately not in this set.
READINESS_PATHS = {"/healthz", "/ready"}


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _probe_path(healthcheck: dict) -> str:
    """The URL path the CMD-SHELL probe actually requests."""
    command = " ".join(healthcheck["test"][1:])
    found = re.search(r"http://[^\s'\"()]+", command)
    assert found, f"healthcheck probe requests no URL: {command!r}"
    return urlparse(found.group(0)).path


def test_api_healthcheck_probes_a_readiness_path(compose):
    healthcheck = compose["services"]["api"]["healthcheck"]
    assert _probe_path(healthcheck) in READINESS_PATHS, (
        "the api healthcheck must probe a path that turns unhealthy when a "
        f"dependency dies; probed {_probe_path(healthcheck)!r}"
    )


def test_api_healthcheck_budget_covers_the_measured_probe_time(compose):
    healthcheck = compose["services"]["api"]["healthcheck"]
    timeout = int(str(healthcheck["timeout"]).rstrip("s"))
    start_period = int(str(healthcheck["start_period"]).rstrip("s"))
    # 2.54s was the slowest live readiness answer measured on the candidate; a
    # probe cheaper than that margin makes Docker mark a working API unhealthy.
    assert timeout >= 10, f"healthcheck timeout {timeout}s is below the measured budget"
    # Importing the ML stack takes ~20s before uvicorn binds at all.
    assert start_period >= 45, f"start_period {start_period}s is shorter than image boot"
