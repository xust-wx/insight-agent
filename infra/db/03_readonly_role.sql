-- 03_readonly_role.sql: 3-tier least-privilege role separation (P0-1 & P1-1 fix).
-- Roles:
--   1. olist_admin (superuser): used strictly for offline DDL/ingestion.
--   2. __SVC_USER__ (NOSUPERUSER): backend app service role; RW on agent_state, RO on olist_clean/olist_distractor.
--   3. __RO_USER__  (NOSUPERUSER): SQL tool analyst role; strictly SELECT on olist_clean/olist_distractor, NO TEMP, NO sleep.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '__RO_USER__') THEN
        EXECUTE format(
            'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L',
            '__RO_USER__', '__RO_PASSWORD__'
        );
    ELSE
        EXECUTE format(
            'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L',
            '__RO_USER__', '__RO_PASSWORD__'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '__SVC_USER__') THEN
        EXECUTE format(
            'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L',
            '__SVC_USER__', '__SVC_PASSWORD__'
        );
    ELSE
        EXECUTE format(
            'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L',
            '__SVC_USER__', '__SVC_PASSWORD__'
        );
    END IF;
END
$$;

-- Hard database-level lockdowns: block TEMP table creation and PUBLIC connect
REVOKE ALL ON DATABASE "__DB_NAME__" FROM PUBLIC;
REVOKE TEMP ON DATABASE "__DB_NAME__" FROM "__RO_USER__";
GRANT CONNECT ON DATABASE "__DB_NAME__" TO "__RO_USER__";
GRANT CONNECT, TEMPORARY ON DATABASE "__DB_NAME__" TO "__SVC_USER__";

-- Revoke pg_sleep execution from PUBLIC so readonly_analyst cannot sleep-DoS even without AST guard
DO $$
BEGIN
    EXECUTE 'REVOKE EXECUTE ON FUNCTION pg_catalog.pg_sleep(double precision) FROM PUBLIC';
    EXECUTE 'REVOKE EXECUTE ON FUNCTION pg_catalog.pg_sleep_for(interval) FROM PUBLIC';
    EXECUTE 'REVOKE EXECUTE ON FUNCTION pg_catalog.pg_sleep_until( timestamp with time zone ) FROM PUBLIC';
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pg_sleep revoke skipped: %', SQLERRM;
END
$$;

-- Default session guards for readonly_analyst (enforced again per-transaction by ReadonlyExecutor)
ALTER ROLE "__RO_USER__" SET default_transaction_read_only = on;
ALTER ROLE "__RO_USER__" SET statement_timeout = '15s';
ALTER ROLE "__RO_USER__" SET lock_timeout = '5s';
ALTER ROLE "__RO_USER__" SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE "__RO_USER__" SET search_path = olist_clean;

-- Clean up schema permissions: allow USAGE on public (for pgvector extension types/operators)
-- while strictly revoking CREATE on public!
REVOKE CREATE ON SCHEMA public FROM PUBLIC, "__RO_USER__", "__SVC_USER__";
GRANT USAGE ON SCHEMA public TO "__RO_USER__", "__SVC_USER__";
REVOKE ALL ON SCHEMA olist_raw FROM PUBLIC, "__RO_USER__", "__SVC_USER__";
REVOKE ALL ON ALL TABLES IN SCHEMA olist_raw FROM PUBLIC, "__RO_USER__", "__SVC_USER__";

REVOKE ALL ON SCHEMA agent_state FROM PUBLIC, "__RO_USER__";
REVOKE ALL ON ALL TABLES IN SCHEMA agent_state FROM PUBLIC, "__RO_USER__";
REVOKE ALL ON ALL SEQUENCES IN SCHEMA agent_state FROM PUBLIC, "__RO_USER__";

REVOKE CREATE ON SCHEMA olist_clean FROM PUBLIC, "__RO_USER__", "__SVC_USER__";
REVOKE CREATE ON SCHEMA olist_distractor FROM PUBLIC, "__RO_USER__", "__SVC_USER__";

-- Grant strictly SELECT on olist_clean and olist_distractor to readonly_analyst
GRANT USAGE ON SCHEMA olist_clean TO "__RO_USER__";
GRANT SELECT ON ALL TABLES IN SCHEMA olist_clean TO "__RO_USER__";
ALTER DEFAULT PRIVILEGES IN SCHEMA olist_clean GRANT SELECT ON TABLES TO "__RO_USER__";

GRANT USAGE ON SCHEMA olist_distractor TO "__RO_USER__";
GRANT SELECT ON ALL TABLES IN SCHEMA olist_distractor TO "__RO_USER__";
ALTER DEFAULT PRIVILEGES IN SCHEMA olist_distractor GRANT SELECT ON TABLES TO "__RO_USER__";

-- Grant agent_service RW on agent_state (including CREATE for LangGraph checkpointer tables) + RO on clean/distractor
GRANT USAGE, CREATE ON SCHEMA agent_state TO "__SVC_USER__";
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA agent_state TO "__SVC_USER__";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA agent_state TO "__SVC_USER__";
ALTER DEFAULT PRIVILEGES IN SCHEMA agent_state
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO "__SVC_USER__";
ALTER DEFAULT PRIVILEGES IN SCHEMA agent_state
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO "__SVC_USER__";

GRANT USAGE ON SCHEMA olist_clean TO "__SVC_USER__";
GRANT SELECT ON ALL TABLES IN SCHEMA olist_clean TO "__SVC_USER__";
ALTER DEFAULT PRIVILEGES IN SCHEMA olist_clean GRANT SELECT ON TABLES TO "__SVC_USER__";

GRANT USAGE ON SCHEMA olist_distractor TO "__SVC_USER__";
GRANT SELECT ON ALL TABLES IN SCHEMA olist_distractor TO "__SVC_USER__";
ALTER DEFAULT PRIVILEGES IN SCHEMA olist_distractor GRANT SELECT ON TABLES TO "__SVC_USER__";
