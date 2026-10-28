#!/bin/bash
# BE-037 I1 live outage run 3 - plain docker stop/start so nothing resurrects
# Redis. Run 2's `docker compose up -d worker_iso` started its depends_on
# services, including the Redis container that had just been stopped, so no
# outage actually occurred there.
LOG=/d/CODING/Scratch/be037phasea/phaseB_remed_c95222/remed-14-live-i1-run3.txt
exec >>"$LOG" 2>&1
say() { printf '\n>>> %s | %s\n' "$(date -u +%H:%M:%S.%3N)" "$*"; }
REPO=/d/CODING/Projects/Proof-Of-Action-Final
SCRATCH=/d/CODING/Scratch/be037phasea/phaseB_remed_c95222
cd "$SCRATCH" || exit 9

backoffs() { docker logs be037remc95222_worker_iso 2>&1 | grep -c "backing off"; }

say "phase 0 - stop the worker (plain docker stop), confirm Redis up and queue empty"
docker stop -t 2 be037remc95222_worker_iso
say "stop exit=$?"
docker inspect -f 'worker={{.State.Status}} redis={{.State.Status}}' be037remc95222_worker_iso be037remc95222_redis
docker exec be037remc95222_redis redis-cli LLEN pofa:analysis:jobs

say "phase 1 - enqueue three payloads through the live enforcing API"
(
  cd "$REPO" || exit 1
  set -a; . "$SCRATCH/secrets.env"; set +a
  export PYTHONPATH="$REPO" \
    DATABASE_URL="postgresql+psycopg2://be037rem_owner:${PG_OWNER_PW}@127.0.0.1:55432/be037rem_app" \
    REDIS_URL="redis://127.0.0.1:56379/0" S3_ENDPOINT="http://127.0.0.1:59000" \
    S3_ACCESS_KEY="$MINIO_ROOT_USER" S3_SECRET_KEY="$MINIO_ROOT_PW" \
    JWT_SECRET="$DISP_JWT_SECRET" ENVIRONMENT=development AUTH_MODE=development
  "$REPO/backend/.venv312_repro/Scripts/python.exe" "$SCRATCH/be037rem_i1_setup.py"
)
say "enqueue exit=$?"

say "phase 2 - queue holds the payloads, worker is stopped"
docker exec be037remc95222_redis redis-cli LLEN pofa:analysis:jobs
docker exec be037remc95222_redis redis-cli LLEN pofa:analysis:jobs:processing

say "phase 3 - OUTAGE: docker stop be037remc95222_redis"
docker stop -t 2 be037remc95222_redis
say "redis stop exit=$?"

say "phase 4 - start the worker INTO the outage (plain docker start)"
docker start be037remc95222_worker_iso
say "start exit=$?"
for i in 1 2 3 4 5 6; do
  sleep 10
  say "t+${i}0s status=$(docker inspect -f '{{.State.Status}} exit={{.State.ExitCode}} restarts={{.RestartCount}}' be037remc95222_worker_iso) backoff_lines=$(backoffs)"
done

say "phase 5 - backoff log during the outage (timestamps + delays)"
docker logs --timestamps be037remc95222_worker_iso 2>&1 | grep -E "backing off|redis unavailable|worker started"

say "phase 6 - SIGTERM while the worker is inside a backoff wait"
say "TERM sent at $(date -u +%H:%M:%S.%3N)"
docker kill --signal=TERM be037remc95222_worker_iso
say "kill exit=$?"
for i in 1 2 3; do
  sleep 1
  say "+${i}s status=$(docker inspect -f '{{.State.Status}} exit={{.State.ExitCode}} finishedAt={{.State.FinishedAt}}' be037remc95222_worker_iso)"
done
say "last lines after SIGTERM"
docker logs --timestamps --tail 6 be037remc95222_worker_iso 2>&1 | grep -vE "site-packages|botocore"

say "phase 7 - restart the worker into the still-live outage"
docker start be037remc95222_worker_iso
say "start exit=$?"
sleep 25
say "after 25s status=$(docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' be037remc95222_worker_iso) backoff_lines=$(backoffs)"

say "phase 8 - RESTORE: docker start be037remc95222_redis, then read the queue at once"
docker start be037remc95222_redis
say "redis start exit=$?"
say "queue right after restore=$(docker exec be037remc95222_redis redis-cli LLEN pofa:analysis:jobs) processing=$(docker exec be037remc95222_redis redis-cli LLEN 'pofa:analysis:jobs:processing')"

say "phase 9 - observe recovery for 60s"
for i in 1 2 3; do
  sleep 20
  say "t+${i}x20s queue=$(docker exec be037remc95222_redis redis-cli LLEN pofa:analysis:jobs) processing=$(docker exec be037remc95222_redis redis-cli LLEN 'pofa:analysis:jobs:processing') status=$(docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' be037remc95222_worker_iso)"
done

say "phase 10 - worker log: outage -> recovery"
docker logs --timestamps be037remc95222_worker_iso 2>&1 | grep -E "INFO:__main__|WARNING:__main__|ERROR:__main__" | grep -vE "site-packages|botocore"

say "phase 11 - egress check from the isolated network"
docker exec be037remc95222_worker_iso python -c "import socket
for target in (('1.1.1.1',443),('download.pytorch.org',443)):
    try:
        socket.create_connection(target,timeout=4); print('REACHABLE',target)
    except Exception as e: print('BLOCKED',target,type(e).__name__,e)"
say "egress check exit=$?"

say "driver 3 done"
