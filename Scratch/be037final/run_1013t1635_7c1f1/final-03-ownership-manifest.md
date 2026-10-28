# BE-037 FINAL run 7c1f1 — ownership manifest, captured BEFORE any container was created
# Capture time: see final-02-pre-stack-snapshot.txt (16:57:04Z) and this file's git-less mtime.
#
# Everything under "OWNED" is created by this run and is the only set cleanup may
# target. "PROTECTED" must be byte-identical before and after; cleanup never names them.

OWNED (this run, all names carry the run id 7c1f1):
  compose project   : be037fin7c1f1
  containers        : be037fin7c1f1_db, be037fin7c1f1_redis, be037fin7c1f1_minio
  volumes           : be037fin7c1f1_db_data, be037fin7c1f1_redis_data, be037fin7c1f1_minio_data
  network           : be037fin7c1f1_net
  side containers   : be037fin7c1f1_vendorsim (only if the A/B bootstrap proof is run)
  host ports        : 127.0.0.1:15432 (db), 127.0.0.1:16379 (redis), 127.0.0.1:19000/19001 (minio)
  databases         : be037fin7c1f1_app (application), plus disposable clones/roles named be037fin7c1f1_*
  buckets           : pofa-evidence / pofa-quarantine INSIDE be037fin7c1f1_minio only
                      (the bucket names come from settings defaults; the server is this run's)

PROTECTED (read-only for this run — never stop/restart/recreate/reconfigure/prune):
  containers        : pofa_db, pofa_redis, pofa_minio, pofa_minio_init
  compose project   : proof-of-action-final
  volumes           : proof-of-action-final_db_data, proof-of-action-final_minio_data
  network           : proof-of-action-final_default
  databases         : pofa_dev, pofa_test  (no writes, no migrations, no fixtures, no write-based tests)

Cleanup rule: `docker compose -p be037fin7c1f1 -f be037fin7c1f1.compose.yml down -v`
scoped to this project file only, then verify by exact name — never a broad pattern,
and never a prune of any kind.
