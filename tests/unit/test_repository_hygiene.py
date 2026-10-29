"""PRISM Phase 1: the repository-hygiene rules must be real and must pass.

Two obligations: the rule set has to catch the artifacts that were actually
measured in the unpushed history (otherwise it is decoration), and the tracked
tree has to be clean now that those artifacts have been removed from it.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check_repository_hygiene.py"

spec = importlib.util.spec_from_file_location("check_repository_hygiene", SCRIPT)
hygiene = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hygiene)

# Every one of these was reachable from refs/heads/Backend before sanitization.
MEASURED_ARTIFACTS = [
    ("DATABASE_DUMP", "Scratch/be029/backups/pofa_dev_20261009T150626Z_pre-be029.dump"),
    ("DATABASE_DUMP", "Scratch/be033/be033_pofa_dev.dump"),
    ("DATABASE_DUMP", "Scratch/be034/be034_pofa_dev_current.dump"),
    ("DATABASE_DUMP", "Scratch/be035/be035_pofa_dev_current.dump"),
    ("ARCHIVE_OR_IMAGE_TAR", "Scratch/deploy1/poa-backend-mbe01-wt1.tar"),
    ("PASSWORD_FILE", "Scratch/be033/poa_runtime_password.txt"),
    ("SECRET_ENV_STORE", "Scratch/be037phasea/phaseB_remed_c95222/secrets.env"),
    ("SECRET_ENV_STORE", "Scratch/be035/env.owner.backup"),
    ("RAW_URL_DUMP", "Scratch/be030/_testurl.txt"),
    ("ENV_FILE_NOT_EXAMPLE", "Scratch/be029/phase2_ts.env"),
]


def rule_for(path):
    import re
    return [name for name, rx in hygiene.NAME_RULES if re.search(rx, path)]


DSN_RX = dict(hygiene.CONTENT_RULES)["DSN_WITH_PASSWORD"]


def dsn_match(line):
    import re
    return next(iter(re.finditer(DSN_RX, line)))


def test_measured_artifacts_are_all_named_by_a_rule():
    for expected, path in MEASURED_ARTIFACTS:
        assert expected in rule_for(path), f"{path} not caught by {expected}"


def test_example_templates_are_not_flagged():
    assert rule_for(".env.example") == []
    assert rule_for("docker-compose.yml") == []
    assert rule_for("backend/core/config.py") == []


def test_local_dev_default_password_is_inert():
    line = 'url = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_dev"'
    assert hygiene.dsn_is_inert(line, dsn_match(line)) is True


def test_interpolation_site_is_inert():
    line = 'f"postgresql+psycopg2://{owner}:{new[\'POSTGRES_PASSWORD\']}@db:5432/{database}"'
    assert hygiene.dsn_is_inert(line, dsn_match(line)) is True


def test_generated_password_is_a_finding_even_on_a_compose_host():
    line = ('"DATABASE_URL": "postgresql+psycopg2://be037wf7e3_runtime:'
            '0f1e2d3c4b5a6978@db:5432/be037wf7e3_app"')
    assert hygiene.dsn_is_inert(line, dsn_match(line)) is False


def test_generated_password_on_a_real_host_is_a_finding():
    line = ("url = 'postgresql+psycopg2://poa_owner:9f3a1c7be2d4f6a8"
            "@db.internal.example:5432/poa_prod'")
    assert hygiene.dsn_is_inert(line, dsn_match(line)) is False


def test_tracked_tree_is_clean():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--all"], cwd=REPO,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
