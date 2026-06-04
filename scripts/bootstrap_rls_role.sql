-- Idempotent bootstrap of the non-superuser, RLS-enforced runtime role `uaid_app`.
-- Run as an admin/owner role (e.g. `app`). Invoked by `make db-bootstrap-rls-role`.
--
-- The password is read from the RLS_DB_PASSWORD environment variable via psql's
-- \getenv (psql 16+), so it never appears in argv, make output, or this file.
-- Fails closed if RLS_DB_PASSWORD is unset/empty.
\set ON_ERROR_STOP on
\getenv pw RLS_DB_PASSWORD
-- Fail closed if the env var was not passed through (Makefile `require-rls-pw`
-- also rejects empty/unset before we get here).
\if :{?pw}
\else
    \echo 'ERROR: RLS_DB_PASSWORD is not set'
    \quit 1
\endif

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'uaid_app') THEN
        CREATE ROLE uaid_app
            LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;
END
$$;

-- Re-assert attributes (idempotent) and set/rotate the password from the env var.
ALTER ROLE uaid_app
    WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    PASSWORD :'pw';

-- Connect privilege on both databases (table-level grants live in migration 0002).
GRANT CONNECT ON DATABASE app TO uaid_app;
GRANT CONNECT ON DATABASE app_test TO uaid_app;

-- Slice 2: limited owner role for the SECURITY DEFINER audit functions.
-- NOLOGIN (never authenticates), no password, no privileges of its own beyond
-- what migration 0003 grants (INSERT/SELECT on audit_logs + EXECUTE on the hash
-- helper). It is the least-privilege "log writer" boundary for §16.6.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'audit_writer') THEN
        CREATE ROLE audit_writer
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;
END
$$;
ALTER ROLE audit_writer
    WITH NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

-- D4 hardening: limited owner role for the SECURITY DEFINER API-key resolver.
-- NOLOGIN (never authenticates), no password; its only privilege is SELECT on
-- tenant_api_keys (granted by migration 0013), so the resolver can look up a key
-- hash while `uaid_app` holds EXECUTE-only access (no direct key-table read).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_key_resolver') THEN
        CREATE ROLE api_key_resolver
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;
END
$$;
ALTER ROLE api_key_resolver
    WITH NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
