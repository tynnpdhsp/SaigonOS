-- SPDX-License-Identifier: Apache-2.0
CREATE FUNCTION core.apply_search(app text, wanted jsonb) RETURNS text[]
LANGUAGE plpgsql
SET search_path = ''
SET client_min_messages = warning
AS $apply$
DECLARE
    target text := (SELECT apps.schema_name FROM core.apps WHERE apps.name = app);
    caller text := target || '_user';
    said text[] := ARRAY[]::text[];
    existing record;
    entry jsonb;
    table_name text;
    columns text[];
    relation oid;
    kind "char";
    column_name text;
    column_type oid;
    label text;
    current_label text;
    function_name text;
    index_name text;
BEGIN
    FOR existing IN
        SELECT p.oid::pg_catalog.regprocedure AS routine, d.description
        FROM pg_catalog.pg_proc AS p
        JOIN pg_catalog.pg_description AS d ON d.classoid = 'pg_catalog.pg_proc'::pg_catalog.regclass
            AND d.objoid = p.oid AND d.objsubid = 0
        WHERE p.pronamespace = target::pg_catalog.regnamespace
            AND pg_catalog.starts_with(d.description, 'saigonos:search ')
        ORDER BY d.description
    LOOP
        table_name := pg_catalog.split_part(existing.description, ' ', 2);
        IF NOT wanted @> pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('table', table_name)) THEN
            EXECUTE format('DROP FUNCTION %s', existing.routine);
            EXECUTE format('DROP INDEX IF EXISTS %I.%I', target, 'saigonos_search_' || table_name);
            said := said || format('Đã gỡ tìm kiếm của bảng %s.', table_name);
        END IF;
    END LOOP;
    FOR entry IN SELECT value FROM pg_catalog.jsonb_array_elements(wanted) LOOP
        table_name := entry ->> 'table';
        columns := ARRAY(SELECT pg_catalog.jsonb_array_elements_text(entry -> 'columns'));
        function_name := 'search_' || table_name;
        index_name := 'saigonos_search_' || table_name;
        label := format('saigonos:search %s %s 1', table_name, pg_catalog.array_to_string(columns, ','));
        SELECT c.oid, c.relkind INTO relation, kind
        FROM pg_catalog.pg_class AS c
        WHERE c.relnamespace = target::pg_catalog.regnamespace AND c.relname = table_name;
        IF relation IS NULL OR kind NOT IN ('r', 'p') THEN
            RAISE EXCEPTION 'Mục search khai bảng %, nhưng schema % không có bảng này', table_name, target
                USING ERRCODE = 'invalid_parameter_value';
        END IF;
        FOREACH column_name IN ARRAY columns LOOP
            SELECT CASE WHEN t.typtype = 'd' THEN t.typbasetype ELSE t.oid END INTO column_type
            FROM pg_catalog.pg_attribute AS a
            JOIN pg_catalog.pg_type AS t ON t.oid = a.atttypid
            WHERE a.attrelid = relation AND a.attname = column_name AND a.attnum > 0
                AND NOT a.attisdropped;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Mục search khai cột % của bảng %, nhưng bảng không có cột này',
                    column_name, table_name
                    USING ERRCODE = 'invalid_parameter_value';
            END IF;
            IF column_type NOT IN (
                'pg_catalog.text'::pg_catalog.regtype,
                'pg_catalog.varchar'::pg_catalog.regtype,
                'pg_catalog.bpchar'::pg_catalog.regtype
            ) THEN
                RAISE EXCEPTION 'Cột % của bảng % có kiểu %. Mục search chỉ nhận cột kiểu text, varchar hoặc char',
                    column_name, table_name, column_type::pg_catalog.regtype
                    USING ERRCODE = 'datatype_mismatch';
            END IF;
        END LOOP;
        current_label := NULL;
        SELECT d.description INTO current_label
        FROM pg_catalog.pg_proc AS p
        LEFT JOIN pg_catalog.pg_description AS d ON d.classoid = 'pg_catalog.pg_proc'::pg_catalog.regclass
            AND d.objoid = p.oid AND d.objsubid = 0
        WHERE p.pronamespace = target::pg_catalog.regnamespace AND p.proname = function_name
        ORDER BY d.description IS NULL DESC
        LIMIT 1;
        IF FOUND AND NOT pg_catalog.starts_with(coalesce(current_label, ''), 'saigonos:search ') THEN
            RAISE EXCEPTION 'Schema % đã có hàm % nhưng không do SaigonOS tạo', target, function_name
                USING ERRCODE = 'duplicate_function',
                    HINT = format('Hãy đổi tên hàm này hoặc bỏ bảng %s khỏi mục search.', table_name);
        END IF;
        IF current_label IS NULL AND pg_catalog.to_regclass(format('%I.%I', target, index_name)) IS NOT NULL THEN
            RAISE EXCEPTION 'Schema % đã có % nhưng không do SaigonOS tạo', target, index_name
                USING ERRCODE = 'duplicate_object',
                    HINT = format('Hãy đổi tên %s hoặc bỏ bảng %s khỏi mục search.', index_name, table_name);
        END IF;
        IF current_label = label
            AND pg_catalog.to_regclass(format('%I.%I', target, index_name)) IS NOT NULL THEN
            CONTINUE;
        END IF;
        IF current_label IS NOT NULL THEN
            EXECUTE format('DROP FUNCTION %I.%I(text)', target, function_name);
        END IF;
        EXECUTE format('DROP INDEX IF EXISTS %I.%I', target, index_name);
        EXECUTE format('SET LOCAL ROLE %I', target);
        EXECUTE format(
            'CREATE INDEX %I ON %I.%I USING gin (core.search_vector(%s))',
            index_name, target, table_name,
            (SELECT pg_catalog.string_agg(format('%I', name), ', ') FROM pg_catalog.unnest(columns) AS name)
        );
        EXECUTE format(
            $create$CREATE FUNCTION %1$I.%2$I(q text) RETURNS SETOF %1$I.%3$I
                LANGUAGE sql STABLE SECURITY DEFINER
                SET search_path = ''
                AS $body$
                    SELECT item.* FROM %1$I.%3$I AS item
                    WHERE core.search_vector(%4$s) @@ core.search_query(q)
                    ORDER BY pg_catalog.ts_rank(core.search_vector(%4$s), core.search_query(q)) DESC
                $body$$create$,
            target, function_name, table_name,
            (SELECT pg_catalog.string_agg(format('item.%I', name), ', ') FROM pg_catalog.unnest(columns) AS name)
        );
        RESET ROLE;
        EXECUTE format('ALTER FUNCTION %I.%I(text) OWNER TO %I', target, function_name, caller);
        EXECUTE format('GRANT EXECUTE ON FUNCTION %I.%I(text) TO %I, %I', target, function_name, target, caller);
        EXECUTE format('COMMENT ON FUNCTION %I.%I(text) IS %L', target, function_name, label);
        said := said || format(
            CASE WHEN current_label IS NULL THEN 'Đã tạo tìm kiếm cho bảng %s.'
                ELSE 'Đã cập nhật tìm kiếm của bảng %s.' END,
            table_name
        );
    END LOOP;
    RETURN said;
END
$apply$;
