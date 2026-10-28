#!/usr/bin/env bash
# BE-032: run read-only chain verification against a named protected DB.
# Derives the URL from .env's DATABASE_URL by swapping the trailing db segment.
# Never prints the credential. usage: run_chain_verify.sh <pofa_test|pofa_dev>
set -euo pipefail
cd /d/CODING/Projects/Proof-Of-Action-Final
TARGET="${1:?need target db name}"
RAW=$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2-)
# DATABASE_URL in .env points at pofa_dev; rewrite the trailing db name to TARGET.
URL=$(printf '%s' "$RAW" | sed -E 's#/(pofa_dev|pofa_test)([?]|$)#/'"$TARGET"'\2#')
case "$URL" in
  */"$TARGET"*) : ;;
  *) echo "DERIVED_URL_NOT_$TARGET"; exit 2 ;;
esac
echo "resolved_target=$(printf '%s' "$URL" | grep -oE 'pofa_[a-z]+' | tail -1)"
export DATABASE_URL="$URL"
exec backend/.venv312_repro/Scripts/python.exe D:/CODING/Scratch/be032_chain_verify.py "$TARGET"
