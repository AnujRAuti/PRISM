-- Initialize database extensions and schema for PoA
\connect pofa_dev
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
