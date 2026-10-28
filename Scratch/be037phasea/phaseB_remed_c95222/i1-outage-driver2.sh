#!/bin/bash
# BE-037 I1 live outage run 2 - real Redis stop/start on the disposable stack.
# Run 1 (remed-12-live-i1.txt) tried to inject the outage with
# `docker network disconnect be037remc95222_iso be037remc95222_redis` and the
# worker still reached Redis, so no outage occurred. This run stops the
# disposable Redis container itself, which is this run's own resource.
LOG=/d/CODING/Scratch/be037phasea/phaseB_remed_c95222/remed-13-live-i1-run2.txt
exec >>"$LOG" 2>&1
say() { printf '\n>>> %s | %s\n' "$(date -u +%H:%M:%S)" "$*"; }
cd /d/CODING/Scratch/be037phasea/phaseB_remed_c95222 || exit 9

say "phase 0 - remove the exited worker so its log starts clean"
docker rm be037remc95222_worker_iso
say "rm exit=$?"

say "phase 1 - queue is empty and Redis is up"
docker exec be037remc95222_redis redis-cli LLEN pofa:analysis:jobs
docker exec be037remc95222_redis redis-cli ping

say "phase 2 - enqueue three real payloads through the live API"
say "(see remed-11-i1-setup.txt for the enqueue command output)"
docker exec be037remc95222_redis redis-cli LLEN pofa:analysis:jobs

say "phase 3 - STOP the disposable Redis (outage begins)"
docker stop -t 2 be037remc95222_redis
say "stop exit=$? at $(date -u +%H:%M:%S)"

say "phase 4 - start the worker INTO the outage"
docker compose --project-name be037remc95222 --env-file secrets.env -f compose.remed.yml --profile tools up -d worker_iso
say "up exit=$?"
for i in 1 2 3 4 5; do
  sleep 10
  say "t+${i}0s status: $(docker inspect -f '{{.State.Status}} exit={{.State.ExitCode}} restarts={{.RestartCount}} startedAt={{.State.StartedAt}}' be037remc95222_worker_iso 2>&1)"
done

say "phase 5 - worker log during the outage"
docker logs --timestamps be037remc95222_worker_iso 2>&1

say "phase 6 - SIGTERM while the worker is inside a backoff wait"
say "sending TERM at $(date -u +%H:%M:%S.%3N)"
docker kill --signal=TERM be037remc95222_worker_iso
say "kill exit=$?"
for i in 1 2 3; do
  sleep 2
  say "+${i}x2s status: $(docker inspect -f '{{.State.Status}} exit={{.State.ExitCode}} finishedAt={{.State.FinishedAt}}' be037remc95222_worker_iso 2>&1)"
done
say "worker log tail after SIGTERM"
docker logs --timestamps --tail 12 be037remc95222_worker_iso 2>&1

say "phase 7 - restart the worker into the still-live outage"
docker compose --project-name be037remc95222 --env-file secrets.env -f compose.remed.yml --profile tools up -d worker_iso
say "up exit=$?"
sleep 25
say "25s later status: $(docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' be037remc95222_worker_iso 2>&1)"

say "phase 8 - RESTORE Redis (outage ends) at $(date -u +%H:%M:%S)"
docker start be037remc95222_redis
say "start exit=$?"
sleep 8
say "queue length right after restore: $(docker exec be037remc95222_redis redis-cli LLEN pofa:analysis:jobs 2>&1)"
say "processing list length right after restore: $(docker exec be037remc95222_redis redis-cli LLEN pofa:analysis:jobs:processing 2>&1)"

say "phase 9 - observe recovery for 60s"
for i in 1 2 3; do
  sleep 20
  say "t+${i}x20s queue=$(docker exec be037remc95222_redis redis-cli LLEN pofa:analysis:jobs 2>&1) processing=$(docker exec be037remc95222_redis redis-cli LLEN 'pofa:analysis:jobs:processing' 2>&1) status=$(docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' be037remc95222_worker_iso 2>&1)"
done

say "phase 10 - worker log after recovery"
docker logs --timestamps be037remc95222_worker_iso 2>&1 | grep -E "INFO|WARNING|ERROR" | grep -vE "site-packages|botocore|Traceback" | tail -30

say "driver 2 done"
