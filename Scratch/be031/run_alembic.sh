#!/usr/bin/env bash
# BE-031 alembic read-only checks against pofa_test (no DDL emitted by `check`/`heads`).
set -euo pipefail
cd /d/CODING/Projects/Proof-Of-Action-Final
RAW=$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2-)
export DATABASE_URL=$(printf '%s' "$RAW" | sed -E 's#/pofa_dev([?]|$)#/pofa_test\1#')
case "$DATABASE_URL" in
  */pofa_test*|*/pofa_test) : ;;
  *) echo "DERIVED_URL_NOT_POFATEST"; exit 2 ;;
esac
echo "alembic_database=$(printf '%s' "$DATABASE_URL" | grep -oE 'pofa_[a-z]+' | tail -1)"
echo "=== heads ==="; backend/.venv312_repro/Scripts/python.exe -m alembic -c alembic.ini heads
echo "=== current (server-reported alembic_version) ==="; backend/.venv312_repro/Scripts/python.exe -m alembic -c alembic.ini current
echo "=== check ==="; backend/.venv312_repro/Scripts/python.exe -m alembic -c alembic.ini check
