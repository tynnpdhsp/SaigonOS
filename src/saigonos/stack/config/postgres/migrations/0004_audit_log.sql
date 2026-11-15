-- SPDX-License-Identifier: Apache-2.0
CREATE TABLE core.audit_log (
    id bigint PRIMARY KEY,
    occurred_at timestamptz NOT NULL,
    actor text,
    db_role text NOT NULL,
    table_schema text NOT NULL,
    table_name text NOT NULL,
    operation text NOT NULL,
    old_row jsonb,
    new_row jsonb,
    hash text NOT NULL
);

CREATE FUNCTION core.audit_hash(previous text, entry core.audit_log) RETURNS text
LANGUAGE sql STABLE
RETURN encode(sha256(convert_to(coalesce(previous, repeat('0', 64)) || jsonb_build_object(
    'id', entry.id,
    'occurred_at', to_char(entry.occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'actor', entry.actor,
    'db_role', entry.db_role,
    'table_schema', entry.table_schema,
    'table_name', entry.table_name,
    'operation', entry.operation,
    'old_row', entry.old_row,
    'new_row', entry.new_row
)::text, 'UTF8')), 'hex');

CREATE FUNCTION core.audit() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
SET timezone = 'UTC'
AS $$
DECLARE
    previous_id bigint;
    previous_hash text;
    entry core.audit_log;
BEGIN
    IF TG_WHEN <> 'AFTER' OR TG_LEVEL <> 'ROW' THEN
        RAISE EXCEPTION 'Hàm core.audit() chỉ dùng cho trigger AFTER INSERT OR UPDATE OR DELETE ... FOR EACH ROW';
    END IF;
    -- Khóa giữ tới hết transaction để mỗi dòng audit log nối đúng vào dòng đã commit ngay trước nó
    PERFORM pg_advisory_xact_lock('core.audit_log'::regclass::oid::bigint);
    SELECT id, hash INTO previous_id, previous_hash FROM core.audit_log ORDER BY id DESC LIMIT 1;
    entry.id := coalesce(previous_id, 0) + 1;
    entry.occurred_at := clock_timestamp();
    entry.actor := core.uid();
    entry.db_role := coalesce(nullif(current_setting('role'), 'none'), session_user);
    entry.table_schema := TG_TABLE_SCHEMA;
    entry.table_name := TG_TABLE_NAME;
    entry.operation := TG_OP;
    IF TG_OP <> 'INSERT' THEN
        entry.old_row := to_jsonb(OLD);
    END IF;
    IF TG_OP <> 'DELETE' THEN
        entry.new_row := to_jsonb(NEW);
    END IF;
    entry.hash := core.audit_hash(previous_hash, entry);
    INSERT INTO core.audit_log VALUES (entry.*);
    RETURN NULL;
END
$$;
