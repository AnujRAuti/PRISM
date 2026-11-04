-- Initialize database extensions and schema for PoA
--
-- The image entrypoint runs this file against $POSTGRES_DB, so it must not name
-- a database. The `\connect pofa_dev` this replaced pinned every deployment to
-- that one database name, so a disposable bootstrap that used any other
-- POSTGRES_DB failed here — and the workaround people reached for (dropping the
-- mount) let the image's own vendor init script run instead, which installs
-- extra extensions and a demo table into the application database and shows up
-- as unexplained schema drift (BE-037 Phase B / final run).
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
