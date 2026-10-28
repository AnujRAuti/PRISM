-- BE-037A-D3 verification: build a uniquely named, disposable isolation target.
-- Touches ONLY poa_be037a_disp / poa_be037a_rt. pofa_dev and pofa_test are never
-- referenced here, and the pre-existing poa_runtime role is deliberately left alone
-- (roles are cluster-wide: ALTER ROLE poa_runtime would break the live dev app).

\set ON_ERROR_STOP on

CREATE ROLE poa_be037a_rt LOGIN
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS
  PASSWORD '__RTPW__';

CREATE DATABASE poa_be037a_disp;

-- The runtime role gets the F-05 grant shape (scripts/provision_runtime_roles.sql):
-- ordinary DML everywhere, ledger SELECT+INSERT only, no schema CREATE. The schema
-- itself is created by the migration run under the owner identity.
\connect poa_be037a_disp

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO poa_be037a_rt;
