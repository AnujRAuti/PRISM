#!/bin/bash
# BE-037 remediation Stage 3 classification: the single unit failure was
# attributed to my own JWT_SECRET override, not to the changed code. Re-run the
# full unit suite against the same disposable target WITHOUT that override so
# the loaded-credentials test sees the documented development/staging default.
LOG=/d/CODING/Scratch/be037phasea/phaseB_remed_c95222/remed-17-unit-no-jwt-override.txt
exec >>"$LOG" 2>&1
say() { printf '\n>>> %s | %s\n' "$(date -u +%H:%M:%S)" "$*"; }
cd /d/CODING/Projects/Proof-Of-Action-Final || exit 9
set -a; . /d/CODING/Scratch/be037phasea/phaseB_remed_c95222/secrets.env; set +a
export TEST_DATABASE_URL="postgresql+psycopg2://be037rem_owner:${PG_OWNER_PW}@127.0.0.1:55432/be037rem_app" \
  REDIS_URL="redis://127.0.0.1:56379/0" S3_ENDPOINT="http://127.0.0.1:59000" \
  S3_ACCESS_KEY="$MINIO_ROOT_USER" S3_SECRET_KEY="$MINIO_ROOT_PW" \
  ENVIRONMENT=development
say "full unit suite, JWT_SECRET intentionally NOT exported"
PY=/d/CODING/Projects/Proof-Of-Action-Final/backend/.venv312_repro/Scripts/python.exe
"$PY" -m pytest tests/unit -q
say "unit exit=$?"
