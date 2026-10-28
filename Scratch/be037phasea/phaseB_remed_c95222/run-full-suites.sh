#!/bin/bash
# BE-037 remediation Stage 3: full unit + full integration suites, run
# sequentially against the disposable target only.
LOG=/d/CODING/Scratch/be037phasea/phaseB_remed_c95222/remed-16-full-suites.txt
exec >>"$LOG" 2>&1
say() { printf '\n>>> %s | %s\n' "$(date -u +%H:%M:%S)" "$*"; }
cd /d/CODING/Projects/Proof-Of-Action-Final || exit 9
set -a; . /d/CODING/Scratch/be037phasea/phaseB_remed_c95222/secrets.env; set +a
export TEST_DATABASE_URL="postgresql+psycopg2://be037rem_owner:${PG_OWNER_PW}@127.0.0.1:55432/be037rem_app" \
  REDIS_URL="redis://127.0.0.1:56379/0" S3_ENDPOINT="http://127.0.0.1:59000" \
  S3_ACCESS_KEY="$MINIO_ROOT_USER" S3_SECRET_KEY="$MINIO_ROOT_PW" \
  JWT_SECRET="$DISP_JWT_SECRET" ENVIRONMENT=development
PY=/d/CODING/Projects/Proof-Of-Action-Final/backend/.venv312_repro/Scripts/python.exe

say "FULL UNIT SUITE"
"$PY" -m pytest tests/unit -q
say "unit exit=$?"

say "FULL INTEGRATION SUITE"
"$PY" -m pytest tests/integration -q
say "integration exit=$?"

say "full suites done"
