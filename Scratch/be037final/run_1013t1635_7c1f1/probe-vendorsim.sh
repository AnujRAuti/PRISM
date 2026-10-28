#!/bin/bash
# BE-037 final run 7c1f1: measure what the image's own vendor init script puts
# into a first-boot database when the repository's docker/pg-init is NOT mounted.
# READ-ONLY against the throwaway simulator container this run created.
OUT=/d/CODING/Scratch/be037final/run_1013t1635_7c1f1/final-06b-vendorsim-measured.txt
exec >"$OUT" 2>&1

C=be037fin7c1f1_vendorsim
DB=be037fin7c1f1_vsim

echo "=== vendor-init first boot (no repo mount) $(date -u +%FT%TZ) ==="
for i in $(seq 1 20); do
  if docker exec "$C" pg_isready -U postgres -d "$DB" >/dev/null 2>&1; then
    echo "ready after $i polls"
    break
  fi
  sleep 3
done

q() { docker exec "$C" psql -U postgres -d "$DB" -tAc "$2"; }

echo
echo "--- which init scripts the entrypoint saw (nothing mounted => the baked file) ---"
docker exec "$C" sh -c 'ls -la /docker-entrypoint-initdb.d/'
docker logs "$C" 2>&1 | grep -i 'running /docker-entrypoint-initdb' | head -5

echo
echo "--- extensions created in the application database by the vendor script ---"
q x "SELECT string_agg(extname||' '||extversion, ', ' ORDER BY extname) FROM pg_extension;"

echo
echo "--- public object inventory ---"
q x "SELECT 'information_schema tables+views='||count(*) FROM information_schema.tables WHERE table_schema='public';"
q x "SELECT 'real tables='||count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r';"
q x "SELECT 'public indexes='||count(*) FROM pg_indexes WHERE schemaname='public';"

echo
echo "--- the demo table the drift report could not account for ---"
q x "SELECT 'exemplo_dados exists='||count(*) FROM pg_class WHERE relname='exemplo_dados';"
q x "SELECT 'rows='||count(*) FROM exemplo_dados;"
q x "SELECT 'owner='||pg_get_userbyid(relowner) FROM pg_class WHERE relname='exemplo_dados';"
q x "SELECT 'extension-depended rows in pg_depend='||count(*) FROM pg_depend d JOIN pg_class c ON c.oid=d.objid WHERE c.relname='exemplo_dados' AND d.deptype='e';"
q x "SELECT string_agg(indexname, ', ') FROM pg_indexes WHERE tablename='exemplo_dados';"

echo
echo "--- the same query against THIS RUN's properly bootstrapped application database ---"
A=be037fin7c1f1_db
AD=be037fin7c1f1_app
docker exec "$A" psql -U postgres -d "$AD" -tAc "SELECT string_agg(extname||' '||extversion, ', ' ORDER BY extname) FROM pg_extension;"
docker exec "$A" psql -U postgres -d "$AD" -tAc "SELECT 'information_schema tables+views='||count(*) FROM information_schema.tables WHERE table_schema='public';"
docker exec "$A" psql -U postgres -d "$AD" -tAc "SELECT 'real tables='||count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r';"
docker exec "$A" psql -U postgres -d "$AD" -tAc "SELECT 'public indexes='||count(*) FROM pg_indexes WHERE schemaname='public';"
docker exec "$A" psql -U postgres -d "$AD" -tAc "SELECT 'exemplo_dados exists='||count(*) FROM pg_class WHERE relname='exemplo_dados';"
docker exec "$A" psql -U postgres -d "$AD" -tAc "SELECT 'alembic revision='||version_num FROM alembic_version;"

echo
echo "=== done ==="
