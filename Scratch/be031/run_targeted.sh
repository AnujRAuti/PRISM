#!/usr/bin/env bash
# BE-031 targeted verification harness. Derives TEST_DATABASE_URL by swapping the
# database name in .env's DATABASE_URL to pofa_test, WITHOUT printing the secret.
set -euo pipefail
cd /d/CODING/Projects/Proof-Of-Action-Final
RAW=$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2-)
# Replace only the trailing /pofa_dev path segment with /pofa_test.
export TEST_DATABASE_URL=$(printf '%s' "$RAW" | sed -E 's#/pofa_dev([?]|$)#/pofa_test\1#')
# Safety: confirm the derived URL names pofa_test and refuse if not.
case "$TEST_DATABASE_URL" in
  */pofa_test*|*/pofa_test) : ;;
  *) echo "DERIVED_URL_NOT_POFATEST db=$(printf '%s' "$TEST_DATABASE_URL" | grep -oE 'pofa_[a-z]+' | tail -1)"; exit 2 ;;
esac
echo "target_database_name=$(printf '%s' "$TEST_DATABASE_URL" | grep -oE 'pofa_[a-z]+' | tail -1)"
exec backend/.venv312_repro/Scripts/python.exe -m pytest -p no:cacheprovider -q -rs "$@"
