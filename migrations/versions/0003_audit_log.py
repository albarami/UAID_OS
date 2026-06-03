"""append-only hash-chained audit log

Slice 2 (§16.6). Tenant-event-only, GUC-derived audit log with a SHA-256 hash
chain and DB-enforced append-only semantics.

Design (plan v4):
- `audit_logs` is written ONLY through the SECURITY DEFINER function
  `audit_append`, owned by the limited NOLOGIN role `audit_writer`. The runtime
  role `uaid_app` gets EXECUTE on `audit_append` only — no table privileges.
- Tenant identity is derived from the transaction-local GUC `app.current_tenant`
  (fail-closed); callers cannot forge another tenant's or platform (NULL) rows.
- `audit_append` returns a MINIMAL surface (id, entry_hash, created_at) so the
  global chain's `seq`/`prev_hash` are never exposed to the runtime.
- Append-only is enforced by REVOKE UPDATE/DELETE + a BEFORE UPDATE/DELETE/TRUNCATE
  trigger. Tamper-evident (not tamper-proof): a superuser can still disable the
  trigger and recompute the chain.
- Canonicalization lives in ONE shared helper `audit_entry_hash` used by both
  `audit_append` and `audit_verify` (no drift).

Requires the `audit_writer` role to exist (created by `make db-bootstrap-rls-role`).
Run with ADMIN credentials only.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-03

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APPEND_SIG = "public.audit_append(text, text, text, jsonb)"
_VERIFY_SIG = "public.audit_verify()"
_HASH_SIG = "public.audit_entry_hash(bigint, uuid, text, text, text, jsonb, timestamptz, text)"


def upgrade() -> None:
    op.execute("CREATE SEQUENCE public.audit_logs_seq")

    op.execute(
        """
        CREATE TABLE public.audit_logs (
            id          uuid NOT NULL DEFAULT gen_random_uuid(),
            seq         bigint NOT NULL,
            tenant_id   uuid,
            actor       text NOT NULL,
            action      text NOT NULL,
            target      text,
            payload     jsonb NOT NULL DEFAULT '{}'::jsonb,
            prev_hash   text,
            entry_hash  text NOT NULL,
            created_at  timestamptz NOT NULL,
            CONSTRAINT pk_audit_logs PRIMARY KEY (id),
            CONSTRAINT uq_audit_logs_seq UNIQUE (seq),
            CONSTRAINT uq_audit_logs_entry_hash UNIQUE (entry_hash),
            CONSTRAINT fk_audit_logs_tenant_id_tenants
                FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE RESTRICT
        )
        """
    )
    op.execute("CREATE INDEX ix_audit_logs_tenant_id ON public.audit_logs (tenant_id)")
    op.execute("CREATE INDEX ix_audit_logs_created_at ON public.audit_logs (created_at)")

    # --- shared, injective canonicalization + hash (STABLE) -------------------
    op.execute(
        """
        CREATE FUNCTION public.audit_entry_hash(
            p_seq bigint, p_tenant_id uuid, p_actor text, p_action text,
            p_target text, p_payload jsonb, p_created_at timestamptz, p_prev_hash text)
        RETURNS text LANGUAGE sql STABLE SET search_path = pg_catalog AS $fn$
            SELECT encode(sha256(convert_to(
                jsonb_build_object(
                    'seq', p_seq,
                    'tenant_id', p_tenant_id,
                    'actor', p_actor,
                    'action', p_action,
                    'target', p_target,
                    'payload', coalesce(p_payload, '{}'::jsonb),
                    'created_at', to_char(p_created_at AT TIME ZONE 'UTC',
                                          'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
                    'prev_hash', p_prev_hash
                )::text, 'UTF8')), 'hex');
        $fn$
        """
    )

    # --- append-only mutation guard ------------------------------------------
    op.execute(
        """
        CREATE FUNCTION public.audit_logs_block_mutation() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only (no UPDATE/DELETE/TRUNCATE)';
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_logs_no_update_delete
            BEFORE UPDATE OR DELETE ON public.audit_logs
            FOR EACH ROW EXECUTE FUNCTION public.audit_logs_block_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_logs_no_truncate
            BEFORE TRUNCATE ON public.audit_logs
            FOR EACH STATEMENT EXECUTE FUNCTION public.audit_logs_block_mutation()
        """
    )

    # --- tenant append (GUC-derived, minimal return) -------------------------
    op.execute(
        """
        CREATE FUNCTION public.audit_append(
            p_actor text, p_action text, p_target text, p_payload jsonb)
        RETURNS TABLE(id uuid, entry_hash text, created_at timestamptz)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $fn$
        DECLARE
            v_tenant  uuid;
            v_seq     bigint;
            v_created timestamptz := now();
            v_prev    text;
            v_hash    text;
            v_id      uuid;
        BEGIN
            v_tenant := NULLIF(current_setting('app.current_tenant', true), '')::uuid;
            IF v_tenant IS NULL THEN
                RAISE EXCEPTION
                    'audit_append requires app.current_tenant to be set (tenant context)';
            END IF;
            PERFORM pg_advisory_xact_lock(421);
            v_seq := nextval('public.audit_logs_seq');
            SELECT a.entry_hash INTO v_prev
                FROM public.audit_logs a ORDER BY a.seq DESC LIMIT 1;
            v_hash := public.audit_entry_hash(
                v_seq, v_tenant, p_actor, p_action, p_target,
                coalesce(p_payload, '{}'::jsonb), v_created, v_prev);
            INSERT INTO public.audit_logs(
                seq, tenant_id, actor, action, target, payload, prev_hash, entry_hash, created_at)
            VALUES (
                v_seq, v_tenant, p_actor, p_action, p_target,
                coalesce(p_payload, '{}'::jsonb), v_prev, v_hash, v_created)
            RETURNING public.audit_logs.id INTO v_id;
            RETURN QUERY SELECT v_id, v_hash, v_created;
        END
        $fn$
        """
    )
    op.execute(f"ALTER FUNCTION {_APPEND_SIG} OWNER TO audit_writer")

    # --- full-chain verification (admin/owner only) --------------------------
    op.execute(
        """
        CREATE FUNCTION public.audit_verify()
        RETURNS TABLE(ok boolean, first_bad_seq bigint)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $fn$
        DECLARE
            r           record;
            v_expect    text := NULL;   -- expected prev_hash for the next row
            v_recomputed text;
        BEGIN
            ok := true;
            first_bad_seq := NULL;
            FOR r IN SELECT * FROM public.audit_logs ORDER BY seq ASC LOOP
                v_recomputed := public.audit_entry_hash(
                    r.seq, r.tenant_id, r.actor, r.action, r.target,
                    r.payload, r.created_at, r.prev_hash);
                IF r.prev_hash IS DISTINCT FROM v_expect
                   OR r.entry_hash IS DISTINCT FROM v_recomputed THEN
                    ok := false;
                    first_bad_seq := r.seq;
                    RETURN NEXT;
                    RETURN;
                END IF;
                v_expect := r.entry_hash;
            END LOOP;
            RETURN NEXT;
        END
        $fn$
        """
    )
    op.execute(f"ALTER FUNCTION {_VERIFY_SIG} OWNER TO audit_writer")

    # --- privileges -----------------------------------------------------------
    # audit_writer (definer of both functions) needs exactly: insert/select on the
    # table, usage/select on the sequence, execute on the hash helper.
    op.execute("GRANT INSERT, SELECT ON public.audit_logs TO audit_writer")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE public.audit_logs_seq TO audit_writer")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_HASH_SIG} TO audit_writer")

    # Lock everything down from PUBLIC; grant uaid_app ONLY the tenant append.
    op.execute(f"REVOKE ALL ON FUNCTION {_HASH_SIG} FROM PUBLIC")
    op.execute(f"REVOKE ALL ON FUNCTION {_APPEND_SIG} FROM PUBLIC")
    op.execute(f"REVOKE ALL ON FUNCTION {_VERIFY_SIG} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_APPEND_SIG} TO uaid_app")
    op.execute("REVOKE UPDATE, DELETE ON public.audit_logs FROM PUBLIC")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {_VERIFY_SIG}")
    op.execute(f"DROP FUNCTION IF EXISTS {_APPEND_SIG}")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_truncate ON public.audit_logs")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_update_delete ON public.audit_logs")
    op.execute("DROP FUNCTION IF EXISTS public.audit_logs_block_mutation()")
    op.execute(f"DROP FUNCTION IF EXISTS {_HASH_SIG}")
    op.execute("DROP TABLE IF EXISTS public.audit_logs")
    op.execute("DROP SEQUENCE IF EXISTS public.audit_logs_seq")
