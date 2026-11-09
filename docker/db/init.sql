-- Runs once, on first start of an empty data volume (connected to the POSTGRES_DB database).
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE DATABASE audit_test;
\connect audit_test
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
