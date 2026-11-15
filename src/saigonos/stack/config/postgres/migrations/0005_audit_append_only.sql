-- SPDX-License-Identifier: Apache-2.0
CREATE FUNCTION core.append_only() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Bảng %.% chỉ cho phép thêm dòng, không cho phép %', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP;
END
$$;

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON core.audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION core.append_only();
-- ENABLE ALWAYS để trigger vẫn chạy khi session_replication_role là replica
ALTER TABLE core.audit_log ENABLE ALWAYS TRIGGER append_only;
