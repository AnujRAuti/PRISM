#!/usr/bin/env bash
# BE-026 Stage E: launch two enforcing-mode uvicorn processes against pofa_test.
# Two processes are required for genuine contention: POST /field/sync is `async def`
# and performs blocking DB work, so a single process serializes concurrent requests.
# DATABASE_URL is passed per-process: the repo .env points at pofa_dev, and a real
# environment variable takes precedence over it.
# PY must be an interpreter that actually has uvicorn: .venv312_clean has lost
# click/uvicorn, so it exits immediately with "No module named 'click'".
# .venv312_repro is the complete 3.12 environment used for the harness too.
set -u
REPO="/d/CODING/Projects/Proof-Of-Action-Final"
SCRATCH="/d/CODING/Scratch/poa_stageE_be026"
PY="$REPO/backend/.venv312_repro/Scripts/python.exe"
DB="postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test"

cd "$REPO" || exit 1
for PORT in 8121 8122; do
  AUTH_MODE=enforcing DATABASE_URL="$DB" \
    "$PY" -m uvicorn backend.app.main:app --host 127.0.0.1 --port "$PORT" \
    --no-access-log >> "$SCRATCH/server$PORT.log" 2>&1 &
  echo "launched uvicorn on $PORT (pid $!)"
done
wait
