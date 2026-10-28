#!/bin/bash
# BE-037 FINAL run 7c1f1 — protected-resource baseline.
# READ-ONLY: SELECTs only, each session forced to default_transaction_read_only=on.
# No DSN/credential is printed; queries run inside the existing pofa_db container.
S=/d/CODING/Scratch/be037final/run_1013t1635_7c1f1
OUT="$S/final-00b-protected-db-baseline.txt"
exec >"$OUT" 2>&1

q() { # q <database> <sql>
  docker exec -e PGOPTIONS="-c default_transaction_read_only=on" pofa_db \
    psql -U postgres -d "$1" -tAc "$2"
}

echo "=== protected database baseline (READ-ONLY counts) ==="
echo "utc=$(date -u +%FT%TZ)"
echo "guard: every session runs with default_transaction_read_only=on (writes would abort)"
echo "columns: ledger_count seq_lo seq_hi users projects evidence analysis_jobs webhook_events public_tables"
for db in pofa_dev pofa_test template1; do
  echo "--- $db ---"
  q "$db" "SELECT 'identity: '||current_database()||'|'||current_user"
  if [ "$db" != "template1" ]; then
    q "$db" "SELECT (SELECT count(*) FROM audit_ledger_events)||'|'||
              (SELECT coalesce(min(sequence_number),0) FROM audit_ledger_events)||'|'||
              (SELECT coalesce(max(sequence_number),0) FROM audit_ledger_events)||'|'||
              (SELECT count(*) FROM users)||'|'||
              (SELECT count(*) FROM projects)||'|'||
              (SELECT count(*) FROM evidence)||'|'||
              (SELECT count(*) FROM analysis_jobs)||'|'||
              (SELECT count(*) FROM webhook_events)||'|'||
              (SELECT count(*) FROM information_schema.tables WHERE table_schema='public')"
    q "$db" "SELECT 'alembic_version: '||version_num FROM alembic_version"
  fi
  q "$db" "SELECT 'extensions: '||coalesce(string_agg(extname,',' ORDER BY extname),'(none)') FROM pg_extension"
  q "$db" "SELECT 'schemas with tables: '||coalesce(string_agg(DISTINCT nspname,',' ORDER BY nspname),'(none)')
             FROM pg_namespace n JOIN pg_class c ON c.relnamespace=n.oid
            WHERE c.relkind='r' AND n.nspname NOT IN ('pg_catalog','information_schema')"
  q "$db" "SELECT 'exemplo_dados tables: '||count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
             WHERE c.relname='exemplo_dados'"
done
echo
echo "=== databases present in the live cluster (names only) ==="
q postgres "SELECT datname FROM pg_database WHERE datistemplate=false ORDER BY datname"
echo
echo "=== containers this cluster belongs to (protected, read-only inspect) ==="
for c in pofa_db pofa_redis pofa_minio; do
  docker inspect -f 'NAME={{.Name}} ID={{.Id}} IMAGE={{.Image}} CREATED={{.Created}} STARTED={{.State.StartedAt}} RESTARTS={{.RestartCount}} RUNNING={{.State.Running}} POLICY={{.HostConfig.RestartPolicy.Name}} PROJECT={{index .Config.Labels "com.docker.compose.project"}} SERVICE={{index .Config.Labels "com.docker.compose.service"}}' "$c"
done
echo
echo "=== current tag -> image id (compare with each container's recorded IMAGE) ==="
docker images --no-trunc --format '{{.Repository}}:{{.Tag}} sha256:{{.ID}}' | grep -E 'postgres-postgis|redis|minio'
