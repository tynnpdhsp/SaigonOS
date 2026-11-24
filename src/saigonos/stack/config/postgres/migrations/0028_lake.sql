-- SPDX-License-Identifier: Apache-2.0
CREATE ROLE lake NOLOGIN BYPASSRLS;
GRANT lake TO core_service;
GRANT USAGE ON SCHEMA core TO lake;

CREATE TABLE core.lineage (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    kind text NOT NULL CHECK (kind IN ('check', 'file')),
    job text NOT NULL CHECK (job IN ('archive', 'snapshot')),
    started_by text NOT NULL CHECK (started_by IN ('timer', 'command')),
    app text NOT NULL,
    source text NOT NULL,
    period text CHECK (period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    time_from timestamptz,
    time_to timestamptz NOT NULL,
    rows bigint NOT NULL CHECK (rows >= 0),
    passed boolean,
    results jsonb,
    check_id bigint REFERENCES core.lineage (id),
    file text UNIQUE,
    size bigint CHECK (size >= 0),
    sha256 text CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT lineage_kind CHECK (
        CASE kind
            WHEN 'check' THEN passed IS NOT NULL AND results IS NOT NULL
                AND num_nulls(check_id, file, size, sha256) = 4
            ELSE passed IS NULL AND results IS NULL AND period IS NOT NULL
                AND num_nonnulls(check_id, file, size, sha256) = 4
        END
    )
);
CREATE UNIQUE INDEX lineage_snapshot ON core.lineage (app, source, period)
    WHERE kind = 'file' AND job = 'snapshot';
CREATE INDEX lineage_check ON core.lineage (check_id);

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON core.lineage
    FOR EACH STATEMENT EXECUTE FUNCTION core.append_only();
ALTER TABLE core.lineage ENABLE ALWAYS TRIGGER append_only;
CREATE TRIGGER audit AFTER INSERT ON core.lineage
    FOR EACH ROW EXECUTE FUNCTION core.audit();

GRANT SELECT, INSERT ON core.lineage TO lake;

CREATE FUNCTION core.alert_admins(dedup_key text, title text, body text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    PERFORM core.check_message(alert_admins.dedup_key, alert_admins.title, alert_admins.body, NULL);
    INSERT INTO core.deliveries (channel, dedup_key, title, body)
    VALUES ('telegram', alert_admins.dedup_key, alert_admins.title, alert_admins.body)
    ON CONFLICT ON CONSTRAINT deliveries_dedup DO NOTHING;
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    PERFORM core.publish('role:admin', pg_catalog.jsonb_build_object('alert', pg_catalog.jsonb_build_object(
        'title', alert_admins.title,
        'body', alert_admins.body,
        'created_at',
            pg_catalog.to_char(pg_catalog.clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
    )));
    RETURN true;
END
$$;
GRANT EXECUTE ON FUNCTION core.alert_admins(text, text, text) TO lake;

CREATE FUNCTION core.lake_counts() RETURNS TABLE (
    app text, job text, failed_checks bigint, files bigint, rows numeric, bytes numeric
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT lineage.app, lineage.job,
        count(*) FILTER (WHERE lineage.kind = 'check' AND NOT lineage.passed),
        count(*) FILTER (WHERE lineage.kind = 'file'),
        coalesce(sum(lineage.rows) FILTER (WHERE lineage.kind = 'file'), 0),
        coalesce(sum(lineage.size) FILTER (WHERE lineage.kind = 'file'), 0)
    FROM core.lineage
    GROUP BY lineage.app, lineage.job
    ORDER BY lineage.app, lineage.job
$$;
GRANT EXECUTE ON FUNCTION core.lake_counts() TO core_service;

CREATE FUNCTION core.base_type(type oid) RETURNS oid
LANGUAGE sql STABLE
SET search_path = ''
AS $$
    WITH RECURSIVE chain AS (
        SELECT t.oid, t.typtype, t.typbasetype FROM pg_catalog.pg_type AS t WHERE t.oid = base_type.type
        UNION ALL
        SELECT t.oid, t.typtype, t.typbasetype
        FROM pg_catalog.pg_type AS t
        JOIN chain ON t.oid = chain.typbasetype
        WHERE chain.typtype = 'd'
    )
    SELECT chain.oid FROM chain WHERE chain.typtype <> 'd'
$$;
GRANT EXECUTE ON FUNCTION core.base_type(oid) TO lake;

CREATE FUNCTION core.check_lake_entry(
    section text, relation oid, label text, entry jsonb, time_column text
) RETURNS void
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    rule jsonb;
    column_name text;
    column_type oid;
BEGIN
    FOR column_name IN
        SELECT time_column
        UNION ALL
        SELECT pg_catalog.jsonb_array_elements_text(r.value -> 'columns')
        FROM pg_catalog.jsonb_array_elements(entry -> 'rules') AS r
        UNION ALL
        SELECT r.value ->> 'column'
        FROM pg_catalog.jsonb_array_elements(entry -> 'rules') AS r
        WHERE r.value ? 'column'
    LOOP
        IF NOT EXISTS (
            SELECT FROM pg_catalog.pg_attribute AS a
            WHERE a.attrelid = relation AND a.attname = column_name AND a.attnum > 0
                AND NOT a.attisdropped
        ) THEN
            RAISE EXCEPTION 'Mục % khai cột % của %, nhưng % không có cột này',
                section, column_name, label, label
                USING ERRCODE = 'invalid_parameter_value';
        END IF;
    END LOOP;
    SELECT core.base_type(a.atttypid) INTO column_type
    FROM pg_catalog.pg_attribute AS a
    WHERE a.attrelid = relation AND a.attname = time_column;
    IF column_type NOT IN (
        'pg_catalog.timestamptz'::pg_catalog.regtype,
        'pg_catalog.timestamp'::pg_catalog.regtype,
        'pg_catalog.date'::pg_catalog.regtype
    ) THEN
        RAISE EXCEPTION 'Cột % của % có kiểu %. Cột thời gian phải có kiểu timestamptz, timestamp hoặc date',
            time_column, label, column_type::pg_catalog.regtype
            USING ERRCODE = 'datatype_mismatch';
    END IF;
    FOR rule IN SELECT r.value FROM pg_catalog.jsonb_array_elements(entry -> 'rules') AS r LOOP
        IF rule ->> 'rule' = 'range' THEN
            SELECT core.base_type(a.atttypid) INTO column_type
            FROM pg_catalog.pg_attribute AS a
            WHERE a.attrelid = relation AND a.attname = rule ->> 'column';
            IF column_type NOT IN (
                'pg_catalog.int2'::pg_catalog.regtype,
                'pg_catalog.int4'::pg_catalog.regtype,
                'pg_catalog.int8'::pg_catalog.regtype,
                'pg_catalog.numeric'::pg_catalog.regtype,
                'pg_catalog.float4'::pg_catalog.regtype,
                'pg_catalog.float8'::pg_catalog.regtype
            ) THEN
                RAISE EXCEPTION 'Cột % của % có kiểu %. Luật range chỉ nhận cột kiểu số',
                    rule ->> 'column', label, column_type::pg_catalog.regtype
                    USING ERRCODE = 'datatype_mismatch';
            END IF;
        ELSIF rule ->> 'rule' = 'unique' THEN
            SELECT a.attname, core.base_type(a.atttypid) INTO column_name, column_type
            FROM pg_catalog.pg_attribute AS a
            WHERE a.attrelid = relation
                AND a.attname IN (SELECT pg_catalog.jsonb_array_elements_text(rule -> 'columns'))
                AND core.base_type(a.atttypid) IN (
                    'pg_catalog.json'::pg_catalog.regtype, 'pg_catalog.xml'::pg_catalog.regtype
                )
            LIMIT 1;
            IF FOUND THEN
                RAISE EXCEPTION 'Cột % của % có kiểu %. Luật unique không so sánh được giá trị của kiểu này',
                    column_name, label, column_type::pg_catalog.regtype
                    USING ERRCODE = 'datatype_mismatch';
            END IF;
        END IF;
    END LOOP;
END
$$;

CREATE FUNCTION core.apply_lake(app text, archive jsonb, snapshots jsonb) RETURNS text[]
LANGUAGE plpgsql
SET search_path = ''
SET client_min_messages = warning
AS $apply$
DECLARE
    target text := (SELECT apps.schema_name FROM core.apps WHERE apps.name = app);
    old jsonb := coalesce((SELECT apps.manifest FROM core.apps WHERE apps.name = app), '{}');
    said text[] := ARRAY[]::text[];
    entry jsonb;
    name text;
    relation oid;
    kind "char";
    referencing record;
    granted record;
    deleted text[] := ARRAY[]::text[];
    selected text[] := ARRAY[]::text[];
BEGIN
    FOR entry IN SELECT value FROM pg_catalog.jsonb_array_elements(archive) LOOP
        name := entry ->> 'table';
        relation := NULL;
        SELECT c.oid, c.relkind INTO relation, kind
        FROM pg_catalog.pg_class AS c
        WHERE c.relnamespace = target::pg_catalog.regnamespace AND c.relname = name;
        IF relation IS NULL OR kind NOT IN ('r', 'p') THEN
            RAISE EXCEPTION 'Mục archive khai bảng %, nhưng schema % không có bảng này', name, target
                USING ERRCODE = 'invalid_parameter_value';
        END IF;
        PERFORM core.check_lake_entry('archive', relation, 'bảng ' || name, entry, entry ->> 'column');
        SELECT c.conrelid::pg_catalog.regclass AS other, c.confdeltype INTO referencing
        FROM pg_catalog.pg_constraint AS c
        WHERE c.contype = 'f' AND c.confrelid = relation AND c.confdeltype IN ('c', 'n', 'd')
        ORDER BY c.conname
        LIMIT 1;
        IF FOUND THEN
            RAISE EXCEPTION 'Bảng % được bảng % tham chiếu với ON DELETE %. Khi dòng cũ được chuyển xuống hồ, dòng của bảng % bị đổi theo mà không được lưu vào hồ',
                name, referencing.other,
                CASE referencing.confdeltype WHEN 'c' THEN 'CASCADE' WHEN 'n' THEN 'SET NULL' ELSE 'SET DEFAULT' END,
                referencing.other
                USING ERRCODE = 'invalid_parameter_value',
                    HINT = format('Hãy đổi khóa ngoại sang ON DELETE RESTRICT hoặc bỏ bảng %s khỏi mục archive.', name);
        END IF;
        deleted := deleted || name;
        selected := selected || name;
    END LOOP;
    FOR entry IN SELECT value FROM pg_catalog.jsonb_array_elements(snapshots) LOOP
        name := entry ->> 'view';
        relation := NULL;
        SELECT c.oid, c.relkind INTO relation, kind
        FROM pg_catalog.pg_class AS c
        WHERE c.relnamespace = target::pg_catalog.regnamespace AND c.relname = name;
        IF relation IS NULL OR kind NOT IN ('r', 'p', 'v', 'm') THEN
            RAISE EXCEPTION 'Mục snapshots khai %, nhưng schema % không có view hay bảng này', name, target
                USING ERRCODE = 'invalid_parameter_value';
        END IF;
        PERFORM core.check_lake_entry('snapshots', relation, name, entry, entry ->> 'column');
        selected := selected || name;
    END LOOP;
    FOR granted IN
        SELECT c.relname, bool_or(acl.privilege_type = 'DELETE') AS deletes
        FROM pg_catalog.pg_class AS c
        CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
        WHERE c.relnamespace = target::pg_catalog.regnamespace
            AND acl.grantee = 'lake'::pg_catalog.regrole
        GROUP BY c.relname
        ORDER BY c.relname
    LOOP
        IF NOT granted.relname = ANY (selected) THEN
            EXECUTE format('REVOKE ALL ON %I.%I FROM lake', target, granted.relname);
        ELSIF granted.deletes AND NOT granted.relname = ANY (deleted) THEN
            EXECUTE format('REVOKE DELETE ON %I.%I FROM lake', target, granted.relname);
        END IF;
    END LOOP;
    IF pg_catalog.cardinality(selected) = 0 THEN
        EXECUTE format('REVOKE USAGE ON SCHEMA %I FROM lake', target);
    ELSE
        EXECUTE format('GRANT USAGE ON SCHEMA %I TO lake', target);
    END IF;
    FOREACH name IN ARRAY selected LOOP
        EXECUTE format('GRANT SELECT ON %I.%I TO lake', target, name);
    END LOOP;
    FOREACH name IN ARRAY deleted LOOP
        EXECUTE format('GRANT DELETE ON %I.%I TO lake', target, name);
    END LOOP;
    FOR name IN
        SELECT value ->> 'table' FROM pg_catalog.jsonb_array_elements(archive)
        EXCEPT SELECT value ->> 'table' FROM pg_catalog.jsonb_array_elements(coalesce(old -> 'archive', '[]'))
        ORDER BY 1
    LOOP
        said := said || format('Đã bật lưu trữ cho bảng %s.', name);
    END LOOP;
    FOR name IN
        SELECT value ->> 'table' FROM pg_catalog.jsonb_array_elements(coalesce(old -> 'archive', '[]'))
        EXCEPT SELECT value ->> 'table' FROM pg_catalog.jsonb_array_elements(archive)
        ORDER BY 1
    LOOP
        said := said || format('Đã tắt lưu trữ của bảng %s.', name);
    END LOOP;
    FOR name IN
        SELECT value ->> 'view' FROM pg_catalog.jsonb_array_elements(snapshots)
        EXCEPT SELECT value ->> 'view' FROM pg_catalog.jsonb_array_elements(coalesce(old -> 'snapshots', '[]'))
        ORDER BY 1
    LOOP
        said := said || format('Đã bật chốt số liệu cho %s.', name);
    END LOOP;
    FOR name IN
        SELECT value ->> 'view' FROM pg_catalog.jsonb_array_elements(coalesce(old -> 'snapshots', '[]'))
        EXCEPT SELECT value ->> 'view' FROM pg_catalog.jsonb_array_elements(snapshots)
        ORDER BY 1
    LOOP
        said := said || format('Đã tắt chốt số liệu của %s.', name);
    END LOOP;
    RETURN said;
END
$apply$;

CREATE OR REPLACE FUNCTION core.secure_app() RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    target text;
    caller text;
    granted record;
    routine record;
BEGIN
    SELECT apps.schema_name INTO target FROM core.apps WHERE apps.schema_name = session_user;
    IF target IS NULL THEN
        RAISE EXCEPTION 'Chỉ role của ứng dụng gọi được hàm core.secure_app'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    caller := target || '_user';
    SELECT acl.privilege_type, coalesce('role ' || grantee.rolname, 'PUBLIC') AS grantee
    INTO granted
    FROM pg_catalog.pg_namespace AS n
    CROSS JOIN LATERAL pg_catalog.aclexplode(n.nspacl) AS acl
    LEFT JOIN pg_catalog.pg_roles AS grantee ON grantee.oid = acl.grantee
    WHERE n.nspname = target
        AND acl.grantee <> n.nspowner
        AND NOT (acl.privilege_type = 'USAGE' AND grantee.rolname IN (caller, 'anon', 'workflow', 'lake'))
    LIMIT 1;
    IF FOUND THEN
        RAISE EXCEPTION 'Schema % chỉ được cấp quyền USAGE cho role % và role anon', target, caller
            USING ERRCODE = 'insufficient_privilege',
                HINT = format(
                    'Hãy bỏ lệnh cấp quyền %s trên schema %s cho %s.',
                    granted.privilege_type, target, granted.grantee
                );
    END IF;
    FOR routine IN
        SELECT p.oid::regprocedure AS name,
            pg_catalog.has_function_privilege(caller, p.oid, 'EXECUTE') AS callable
        FROM pg_catalog.pg_proc AS p
        JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
        WHERE n.nspname = target AND p.prokind IN ('f', 'p') AND NOT p.prosecdef
    LOOP
        EXECUTE format('ALTER ROUTINE %s SECURITY DEFINER', routine.name);
        EXECUTE format('ALTER ROUTINE %s OWNER TO %I', routine.name, caller);
        EXECUTE format('REVOKE EXECUTE ON ROUTINE %s FROM %I', routine.name, caller);
        EXECUTE format('GRANT EXECUTE ON ROUTINE %s TO %I', routine.name, target);
        IF routine.callable THEN
            EXECUTE format('GRANT EXECUTE ON ROUTINE %s TO %I', routine.name, caller);
        END IF;
    END LOOP;
END
$$;
