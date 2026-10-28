#!/bin/bash
# BE-037 remediation run c95222: post-teardown protected-resource check.
# READ-ONLY: counts and server facts only, against the live pofa_db container.
# Compare with remed-00b-protected-db-baseline.txt.
OUT=/d/CODING/Scratch/be037phasea/phaseB_remed_c95222/remed-21-post-teardown-protected-check.txt
exec >"$OUT" 2>&1

echo "=== post-teardown protected check $(date -u +%FT%TZ) ==="
echo
echo "=== this run's owned resources (must be empty) ==="
docker ps -a --format '{{.Names}}' | grep be037rem || echo "no be037rem containers"
docker volume ls --format '{{.Name}}' | grep be037rem || echo "no be037rem volumes"
docker network ls --format '{{.Name}}' | grep be037rem || echo "no be037rem networks"
echo
echo "=== protected containers: id / started / restarts / running ==="
for c in pofa_db pofa_redis pofa_minio; do
  docker inspect -f 'NAME={{.Name}} ID={{.Id}} STARTED={{.State.StartedAt}} RESTARTS={{.RestartCount}} RUNNING={{.State.Running}}' "$c"
done
echo
echo "=== protected live services still listening ==="
docker ps --format '{{.ID}}|{{.Names}}|{{.Status}}|{{.Ports}}' | grep -E 'pofa_db|pofa_redis|pofa_minio'
echo
echo "=== pofa_minio restart observation (StartedAt differs from the baseline) ==="
echo "health/live http_code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:9000/minio/health/live)"
docker inspect -f 'ID={{.Id}} RestartPolicy={{.HostConfig.RestartPolicy.Name}} Created={{.Created}} StartedAt={{.State.StartedAt}} FinishedAt={{.State.FinishedAt}} ExitCode={{.State.ExitCode}} OOM={{.State.OOMKilled}}' pofa_minio
echo "--- mounts (the data-bearing volume must be the original) ---"
docker inspect -f '{{range .Mounts}}{{.Name}} {{.Type}} {{.Source}}{{"\n"}}{{end}}' pofa_minio
echo "--- last 5 log lines before/after the transition ---"
docker logs --tail 5 pofa_minio 2>&1
echo "--- this run's scripts never name pofa_minio (grep over the scratch dir) ---"
grep -rl "pofa_minio" /d/CODING/Scratch/be037phasea/phaseB_remed_c95222 --include='*.sh' | sed 's#.*/##'
echo
echo "columns: ledger_count lo hi users projects evidence analysis_jobs webhook_events public_tables"
for db in pofa_dev pofa_test; do
  echo "--- $db ---"
  docker exec pofa_db psql -U postgres -d "$db" -tAc \
    "SELECT (SELECT count(*) FROM audit_ledger_events)||'|'||
            (SELECT coalesce(min(sequence_number),0) FROM audit_ledger_events)||'|'||
            (SELECT coalesce(max(sequence_number),0) FROM audit_ledger_events)||'|'||
            (SELECT count(*) FROM users)||'|'||
            (SELECT count(*) FROM projects)||'|'||
            (SELECT count(*) FROM evidence)||'|'||
            (SELECT count(*) FROM analysis_jobs)||'|'||
            (SELECT count(*) FROM webhook_events)||'|'||
            (SELECT count(*) FROM information_schema.tables WHERE table_schema='public');"
  docker exec pofa_db psql -U postgres -d "$db" -tAc "SELECT version();"
  docker exec pofa_db psql -U postgres -d "$db" -tAc "SELECT current_database(), current_user;"
  docker exec pofa_db psql -U postgres -d "$db" -tAc "SELECT version_num FROM alembic_version;"
done
echo
echo "=== databases present in the live cluster (names only) ==="
docker exec pofa_db psql -U postgres -d postgres -tAc \
  "SELECT datname FROM pg_database WHERE datistemplate=false ORDER BY datname;"
echo
echo "=== git (must match the pre-creation baseline exactly) ==="
cd /d/CODING/Projects/Proof-Of-Action-Final || exit 9
git rev-parse HEAD
git status --short
