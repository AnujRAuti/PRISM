#!/bin/bash
# BE-037 I1 live outage driver (disposable stack run c95222).
# Appends timestamped evidence to remed-12-live-i1.txt.
LOG=/d/CODING/Scratch/be037phasea/phaseB_remed_c95222/remed-12-live-i1.txt
exec >>"$LOG" 2>&1
say() { printf '\n>>> %s | %s\n' "$(date -u +%H:%M:%S)" "$*"; }

cd /d/CODING/Scratch/be037phasea/phaseB_remed_c95222 || exit 9

say "phase 0 - pre-outage state"
docker exec be037remc95222_redis redis-cli LLEN pofa:analysis:jobs
docker exec be037remc95222_redis redis-cli LLEN pofa:analysis:jobs:processing

say "phase 1 - inject Redis outage for the isolated worker only"
say "command: docker network disconnect be037remc95222_iso be037remc95222_redis"
docker network disconnect be037remc95222_iso be037remc95222_redis
say "disconnect exit=$?"
say "api-side redis still reachable (proof the outage is scoped to the iso net):"
docker exec be037remc95222_redis redis-cli -h 127.0.0.1 ping

say "phase 2 - start the isolated worker against the outage"
docker compose --project-name be037remc95222 --env-file secrets.env -f compose.remed.yml --profile tools up -d worker_iso
say "up exit=$?"
for i in 1 2 3 4 5 6; do
  sleep 10
  say "t+${i}0s worker container status: $(docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' be037remc95222_worker_iso 2>&1)"
done

say "phase 3 - worker log during the outage (bounded backoff evidence)"
docker logs --timestamps be037remc95222_worker_iso 2>&1 | tail -40

say "phase 4 - queue contents during the outage (payload preservation)"
docker exec be037remc95222_redis redis-cli LLEN pofa:analysis:jobs
docker exec be037remc95222_redis redis-cli LLEN pofa:analysis:jobs:processing

say "phase 5 - SIGTERM while the worker is inside a backoff wait"
say "kill signal sent at: $(date -u +%H:%M:%S.%N)"
docker kill --signal=TERM be037remc95222_worker_iso
say "docker kill exit=$?"
sleep 4
say "container status 4s after SIGTERM: $(docker inspect -f '{{.State.Status}} exit={{.State.ExitCode}} finishedAt={{.State.FinishedAt}}' be037remc95222_worker_iso 2>&1)"
say "worker log tail after SIGTERM"
docker logs --timestamps --tail 25 be037remc95222_worker_iso 2>&1

say "driver done"
