#!/bin/bash
# Stage 3 classification probe. Builds target DSNs locally; never echoes them.
cd /d/CODING/Projects/Proof-Of-Action-Final || exit 9
set -a; . /d/CODING/Scratch/be037phasea/phaseB_remed_c95222/secrets.env; set +a
export DISPOSABLE_URL="postgresql+psycopg2://be037rem_owner:${PG_OWNER_PW}@127.0.0.1:55432/be037rem_app"
export SHARED_TEST_URL="postgresql+psycopg2://${POFA_SHARED_USER:-postgres}:${POFA_SHARED_PW:-postgres}@127.0.0.1:5432/pofa_test"
export DATABASE_URL="$DISPOSABLE_URL"
export ENVIRONMENT=development
PY=/d/CODING/Projects/Proof-Of-Action-Final/backend/.venv312_repro/Scripts/python.exe
"$PY" /d/CODING/Scratch/be037phasea/phaseB_remed_c95222/be037rem_drift_classification.py
echo "probe exit=$?"
