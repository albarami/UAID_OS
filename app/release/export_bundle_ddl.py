"""DDL helpers for Slice-60 migration ``0059`` only.

Not imported by the runtime repository path. Keeps ``0059_export_bundles.py``
under the house 500-line cap.
"""

from __future__ import annotations

from alembic import op

PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
TABLES: tuple[str, ...] = (
    "evidence_pack_export_records",
    "evidence_pack_export_files",
    "evidence_pack_manifest_signatures",
)

RECORD_GUARD_SQL = r"""
CREATE FUNCTION public.evidence_pack_export_records_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
DECLARE pack_hash text; pack_rc uuid; pack_cp uuid; log_ref text;
        v_tenant uuid; v_project uuid; v_pack uuid; v_hash text;
BEGIN
    IF NEW.as_of IS DISTINCT FROM transaction_timestamp() THEN
        RAISE EXCEPTION 'as_of must equal transaction_timestamp()';
    END IF;
    IF NEW.expires_at IS DISTINCT FROM (NEW.as_of + INTERVAL '720 hours') THEN
        RAISE EXCEPTION 'expires_at must equal as_of + 720 hours';
    END IF;
    SELECT core_content_hash, release_candidate_id, audit_checkpoint_id
      INTO pack_hash, pack_rc, pack_cp
      FROM public.evidence_packs
     WHERE id = NEW.evidence_pack_id
       AND project_id = NEW.project_id
       AND tenant_id = NEW.tenant_id;
    IF pack_hash IS DISTINCT FROM NEW.core_content_hash THEN
        RAISE EXCEPTION 'core_content_hash must match evidence_packs';
    END IF;
    IF NEW.release_candidate_id IS DISTINCT FROM pack_rc
       OR NEW.audit_checkpoint_id IS DISTINCT FROM pack_cp THEN
        RAISE EXCEPTION 'release_candidate_id and audit_checkpoint_id must match the pack';
    END IF;
    SELECT verified_through_entry_hash INTO log_ref
      FROM public.audit_chain_verifications
     WHERE id = NEW.audit_checkpoint_id;
    IF log_ref IS DISTINCT FROM NEW.immutable_log_reference THEN
        RAISE EXCEPTION 'immutable_log_reference must match audit checkpoint';
    END IF;
    SELECT tenant_id, project_id, evidence_pack_id, core_content_hash
      INTO v_tenant, v_project, v_pack, v_hash
      FROM public.release_verdicts
     WHERE id = NEW.release_verdict_id;
    IF v_tenant IS DISTINCT FROM NEW.tenant_id
       OR v_project IS DISTINCT FROM NEW.project_id
       OR v_pack IS DISTINCT FROM NEW.evidence_pack_id
       OR v_hash IS DISTINCT FROM NEW.core_content_hash THEN
        RAISE EXCEPTION 'release_verdict_id must belong to the same pack';
    END IF;
    IF NEW.file_count IS DISTINCT FROM 4 THEN
        RAISE EXCEPTION 'file_count must be 4';
    END IF;
    RETURN NEW;
END
$fn$
"""

FILE_GUARD_SQL = r"""
CREATE FUNCTION public.evidence_pack_export_files_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
BEGIN
    IF NEW.byte_count IS DISTINCT FROM octet_length(NEW.content) THEN
        RAISE EXCEPTION 'byte_count must equal octet_length(content)';
    END IF;
    IF NEW.content_sha256 IS DISTINCT FROM
       ('sha256:' || encode(sha256(NEW.content), 'hex')) THEN
        RAISE EXCEPTION 'content_sha256 must equal sha256(content)';
    END IF;
    RETURN NEW;
END
$fn$
"""

SIGNATURE_GUARD_SQL = r"""
CREATE FUNCTION public.evidence_pack_manifest_signatures_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
DECLARE parent_digest text; parent_key text;
BEGIN
    SELECT manifest_digest, signing_key_id INTO parent_digest, parent_key
      FROM public.evidence_pack_export_records
     WHERE id = NEW.export_record_id
       AND project_id = NEW.project_id
       AND tenant_id = NEW.tenant_id;
    IF NEW.signed_bytes_digest IS DISTINCT FROM parent_digest THEN
        RAISE EXCEPTION 'signed_bytes_digest must equal parent manifest_digest';
    END IF;
    IF NEW.signing_key_id IS DISTINCT FROM parent_key THEN
        RAISE EXCEPTION 'signing_key_id must equal parent signing_key_id';
    END IF;
    RETURN NEW;
END
$fn$
"""

PARENT_MATCH_SQL = r"""
CREATE FUNCTION public.evidence_pack_export_records_count_match() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
DECLARE n_files int; n_sig int; byte_sum bigint; manifest_hash text; sig_bytes bytea; b64 text;
BEGIN
    SELECT count(*) INTO n_files
      FROM public.evidence_pack_export_files WHERE export_record_id = NEW.id;
    SELECT count(*) INTO n_sig
      FROM public.evidence_pack_manifest_signatures WHERE export_record_id = NEW.id;
    SELECT COALESCE(sum(byte_count), 0) INTO byte_sum
      FROM public.evidence_pack_export_files WHERE export_record_id = NEW.id;
    SELECT content_sha256 INTO manifest_hash
      FROM public.evidence_pack_export_files
     WHERE export_record_id = NEW.id AND ordinal = 3;
    SELECT content INTO sig_bytes
      FROM public.evidence_pack_export_files
     WHERE export_record_id = NEW.id AND ordinal = 4;
    SELECT signature_b64 INTO b64
      FROM public.evidence_pack_manifest_signatures
     WHERE export_record_id = NEW.id;
    IF n_files IS DISTINCT FROM 4 OR NEW.file_count IS DISTINCT FROM 4 THEN
        RAISE EXCEPTION 'export record % must have 4 file children', NEW.id;
    END IF;
    IF n_sig IS DISTINCT FROM 1 THEN
        RAISE EXCEPTION 'export record % must have exactly one signature', NEW.id;
    END IF;
    IF byte_sum IS DISTINCT FROM NEW.total_byte_count THEN
        RAISE EXCEPTION 'total_byte_count must equal sum of file byte_count';
    END IF;
    IF manifest_hash IS DISTINCT FROM NEW.manifest_digest THEN
        RAISE EXCEPTION 'manifest_digest must equal ordinal 3 content_sha256';
    END IF;
    IF b64 IS NULL OR decode(b64, 'base64') IS DISTINCT FROM sig_bytes THEN
        RAISE EXCEPTION 'signature_b64 must equal ordinal 4 content';
    END IF;
    RETURN NULL;
END
$fn$
"""

CHILD_MATCH_SQL = r"""
CREATE FUNCTION public.evidence_pack_export_children_count_match() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
DECLARE stored_count int; parent_bytes bigint; n_files int; n_sig int;
        byte_sum bigint; manifest_hash text; parent_digest text;
        sig_bytes bytea; b64 text; rec uuid;
BEGIN
    rec := COALESCE(NEW.export_record_id, OLD.export_record_id);
    SELECT file_count, total_byte_count, manifest_digest
      INTO stored_count, parent_bytes, parent_digest
      FROM public.evidence_pack_export_records WHERE id = rec;
    SELECT count(*) INTO n_files
      FROM public.evidence_pack_export_files WHERE export_record_id = rec;
    SELECT count(*) INTO n_sig
      FROM public.evidence_pack_manifest_signatures WHERE export_record_id = rec;
    SELECT COALESCE(sum(byte_count), 0) INTO byte_sum
      FROM public.evidence_pack_export_files WHERE export_record_id = rec;
    SELECT content_sha256 INTO manifest_hash
      FROM public.evidence_pack_export_files WHERE export_record_id = rec AND ordinal = 3;
    SELECT content INTO sig_bytes
      FROM public.evidence_pack_export_files WHERE export_record_id = rec AND ordinal = 4;
    SELECT signature_b64 INTO b64
      FROM public.evidence_pack_manifest_signatures WHERE export_record_id = rec;
    IF stored_count IS DISTINCT FROM 4 OR n_files IS DISTINCT FROM 4 THEN
        RAISE EXCEPTION 'export record % must have 4 file children', rec;
    END IF;
    IF n_sig IS DISTINCT FROM 1 THEN
        RAISE EXCEPTION 'export record % must have exactly one signature', rec;
    END IF;
    IF byte_sum IS DISTINCT FROM parent_bytes THEN
        RAISE EXCEPTION 'total_byte_count must equal sum of file byte_count';
    END IF;
    IF manifest_hash IS DISTINCT FROM parent_digest THEN
        RAISE EXCEPTION 'manifest_digest must equal ordinal 3 content_sha256';
    END IF;
    IF b64 IS NULL OR decode(b64, 'base64') IS DISTINCT FROM sig_bytes THEN
        RAISE EXCEPTION 'signature_b64 must equal ordinal 4 content';
    END IF;
    RETURN NULL;
END
$fn$
"""


def enable_append_only(table: str) -> None:
    """Block UPDATE/DELETE/TRUNCATE on an append-only export-bundle table."""
    op.execute(
        f"""CREATE FUNCTION public.{table}_block_dml() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        BEGIN RAISE EXCEPTION '{table} is append-only'; END $fn$"""
    )
    op.execute(
        f"CREATE TRIGGER {table}_no_update_delete BEFORE UPDATE OR DELETE ON public.{table} "
        f"FOR EACH ROW EXECUTE FUNCTION public.{table}_block_dml()"
    )
    op.execute(
        f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON public.{table} "
        f"FOR EACH STATEMENT EXECUTE FUNCTION public.{table}_block_dml()"
    )


def enable_rls(table: str) -> None:
    """ENABLE+FORCE RLS with tenant_isolation and SELECT/INSERT for uaid_app."""
    op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON public.{table} "
        f"USING ({PREDICATE}) WITH CHECK ({PREDICATE})"
    )
    op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT ON public.{table} TO uaid_app")


def install_export_bundle_guards() -> None:
    """Install INSERT guards, deferred cardinality binders, RLS, and append-only."""
    op.execute(RECORD_GUARD_SQL)
    op.execute(
        "CREATE TRIGGER evidence_pack_export_records_guard "
        "BEFORE INSERT ON public.evidence_pack_export_records "
        "FOR EACH ROW EXECUTE FUNCTION public.evidence_pack_export_records_guard()"
    )
    op.execute(FILE_GUARD_SQL)
    op.execute(
        "CREATE TRIGGER evidence_pack_export_files_guard "
        "BEFORE INSERT ON public.evidence_pack_export_files "
        "FOR EACH ROW EXECUTE FUNCTION public.evidence_pack_export_files_guard()"
    )
    op.execute(SIGNATURE_GUARD_SQL)
    op.execute(
        "CREATE TRIGGER evidence_pack_manifest_signatures_guard "
        "BEFORE INSERT ON public.evidence_pack_manifest_signatures "
        "FOR EACH ROW EXECUTE FUNCTION public.evidence_pack_manifest_signatures_guard()"
    )
    op.execute(PARENT_MATCH_SQL)
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER evidence_pack_export_records_count_match
            AFTER INSERT ON public.evidence_pack_export_records
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.evidence_pack_export_records_count_match()
        """
    )
    op.execute(CHILD_MATCH_SQL)
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER evidence_pack_export_files_count_match
            AFTER INSERT ON public.evidence_pack_export_files
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.evidence_pack_export_children_count_match()
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER evidence_pack_manifest_signatures_count_match
            AFTER INSERT ON public.evidence_pack_manifest_signatures
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.evidence_pack_export_children_count_match()
        """
    )
    for table in TABLES:
        enable_append_only(table)
        enable_rls(table)


def drop_export_bundle_guards() -> None:
    """Reverse ``install_export_bundle_guards`` after the populated-downgrade check."""
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON public.{table}")
        op.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE SELECT, INSERT ON public.{table} FROM uaid_app")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON public.{table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_dml()")
    op.execute(
        "DROP TRIGGER IF EXISTS evidence_pack_manifest_signatures_count_match "
        "ON public.evidence_pack_manifest_signatures"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS evidence_pack_export_files_count_match "
        "ON public.evidence_pack_export_files"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS evidence_pack_export_records_count_match "
        "ON public.evidence_pack_export_records"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS evidence_pack_manifest_signatures_guard "
        "ON public.evidence_pack_manifest_signatures"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS evidence_pack_export_files_guard "
        "ON public.evidence_pack_export_files"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS evidence_pack_export_records_guard "
        "ON public.evidence_pack_export_records"
    )
    op.execute("DROP FUNCTION IF EXISTS public.evidence_pack_export_children_count_match()")
    op.execute("DROP FUNCTION IF EXISTS public.evidence_pack_export_records_count_match()")
    op.execute("DROP FUNCTION IF EXISTS public.evidence_pack_manifest_signatures_guard()")
    op.execute("DROP FUNCTION IF EXISTS public.evidence_pack_export_files_guard()")
    op.execute("DROP FUNCTION IF EXISTS public.evidence_pack_export_records_guard()")


def populated_downgrade_sql() -> str:
    """Refuse a populated 0059→0058 downgrade if any Slice-60 table has rows."""
    return """
        DO $fn$
        BEGIN
            IF EXISTS (SELECT 1 FROM public.evidence_pack_export_records)
               OR EXISTS (SELECT 1 FROM public.evidence_pack_export_files)
               OR EXISTS (SELECT 1 FROM public.evidence_pack_manifest_signatures) THEN
                RAISE EXCEPTION 'cannot downgrade Slice 60 while export-bundle rows exist';
            END IF;
        END
        $fn$
        """
