#!/bin/sh
# PRISM Phase 1b index filter: run once per unpublished commit, never touching
# the working tree. Two obligations, in order:
#   1. delete the artifact classes that must not be publishable at all;
#   2. redact the one retained evidence file that echoes a generated DSN.
# Redaction is done by rewriting the staged blob, so the credential leaves
# every commit, not just the checkout.

PURGE="
Scratch/be029/backups/pofa_dev_20261009T150626Z_pre-be029.dump
Scratch/be029/backups/pofa_dev_20261009T152259Z_pre-migration.dump
Scratch/be033/be033_pofa_dev.dump
Scratch/be034/be034_pofa_dev_current.dump
Scratch/be035/be035_pofa_dev_current.dump
Scratch/be037phasea/phaseB_remed_c95222/secrets.env
Scratch/be037phasea/phaseb_be037b65cee2/secrets.env
Scratch/be033/poa_runtime_password.txt
Scratch/be035/env.owner.backup
Scratch/be029/phase2_ts.env
Scratch/be030/_testurl.txt
Scratch/deploy1/poa-backend-mbe01-wt1.tar
"

REDACT=Scratch/be037final/run_WSF_be037wf7e3/evidence/wsf-03-f2.json
RUNTIME=be037wf7e3_runtime

for path in $PURGE; do
    git rm --cached --ignore-unmatch -q -- "$path" 2>/dev/null
done

if git rev-parse -q --verify ":$REDACT" >/dev/null 2>&1; then
    tmp="$(git rev-parse --git-dir)/prism_redact_tmp"
    git show ":$REDACT" \
        | sed "s#${RUNTIME}:[^\"'@ ]*@#${RUNTIME}:REDACTED@#g" > "$tmp"
    if [ -s "$tmp" ]; then
        blob=$(git hash-object -w --stdin < "$tmp")
        git update-index --cacheinfo 100644 "$blob" "$REDACT"
    fi
    rm -f "$tmp"
fi

exit 0
