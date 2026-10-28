-- BE-037 Phase B — disposable cluster initialization.
--
-- The repository's docker/pg-init/init.sql does `\connect pofa_dev`, which would
-- fail (or worse, point at the protected database) in a differently-named
-- disposable cluster, so this run ships its own version. The entrypoint already
-- runs .sql files against $POSTGRES_DB (be037b_app) as $POSTGRES_USER
-- (be037b_owner), so no \connect is used here.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;

SELECT 'postgis ' || postgis_full_version() AS extension_probe;
SELECT 'pgvector ' || extversion AS extension_probe
FROM pg_extension WHERE extname = 'vector';
