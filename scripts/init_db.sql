-- One-time database bootstrap. Run as a PostgreSQL superuser:
--   psql -d postgres -f scripts/init_db.sql
-- Idempotent: safe to re-run.
--
-- Local dev uses passwordless roles (Homebrew/Postgres.app default to trust auth
-- for localhost). If your server uses password auth, set passwords with
--   ALTER ROLE nl2sql_owner PASSWORD '...';
-- and put them in DATABASE_URL / READONLY_DATABASE_URL in .env.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nl2sql_owner') THEN
        CREATE ROLE nl2sql_owner LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nl2sql_readonly') THEN
        CREATE ROLE nl2sql_readonly LOGIN;
    END IF;
END
$$;

SELECT 'CREATE DATABASE nl2sql_research OWNER nl2sql_owner'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'nl2sql_research')
\gexec

-- Defense in depth for the executor role: even if the SQL validator is bypassed,
-- every session of this role is read-only, time-limited and only sees olist.
ALTER ROLE nl2sql_readonly SET default_transaction_read_only = on;
ALTER ROLE nl2sql_readonly SET statement_timeout = '15s';
ALTER ROLE nl2sql_readonly SET search_path = olist;

\connect nl2sql_research

-- pgvector must be created by a superuser.
CREATE EXTENSION IF NOT EXISTS vector;

REVOKE ALL ON DATABASE nl2sql_research FROM PUBLIC;
GRANT CONNECT ON DATABASE nl2sql_research TO nl2sql_owner, nl2sql_readonly;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
