-- SPDX-License-Identifier: Apache-2.0
-- Mã trong view, chính sách RLS và giá trị mặc định chạy ngoài hàm SECURITY DEFINER nên đổi được role bằng set_config
REVOKE EXECUTE ON FUNCTION pg_catalog.set_config(text, text, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pg_catalog.set_config(text, text, boolean) TO authenticator, core_service;

CREATE FUNCTION core.secure_app() RETURNS void
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
        AND NOT (acl.privilege_type = 'USAGE' AND grantee.rolname IN (caller, 'anon'))
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

CREATE OR REPLACE FUNCTION core.prepare_app(app text) RETURNS boolean
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    target text := replace(app, '-', '_');
    caller text := target || '_user';
    known boolean := EXISTS (SELECT FROM core.apps WHERE apps.name = app);
    taken text := (
        SELECT found.name
        FROM (
            SELECT pg_roles.rolname AS name FROM pg_catalog.pg_roles
            WHERE pg_roles.rolname IN (target, caller)
            UNION ALL
            SELECT pg_namespace.nspname FROM pg_catalog.pg_namespace
            WHERE pg_namespace.nspname = target
        ) AS found
        ORDER BY found.name
        LIMIT 1
    );
    wanted record;
BEGIN
    IF NOT known AND taken IS NOT NULL THEN
        RAISE EXCEPTION 'Role hoặc schema % đã có trong cơ sở dữ liệu nhưng không do SaigonOS tạo cho ứng dụng %', taken, app
            USING ERRCODE = 'duplicate_object', HINT = 'Hãy đặt tên khác cho ứng dụng.';
    END IF;
    IF known AND NOT (
        EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = target)
        AND EXISTS (SELECT FROM pg_catalog.pg_namespace WHERE nspname = target)
    ) THEN
        RAISE EXCEPTION 'Role hoặc schema % của ứng dụng % không còn trong cơ sở dữ liệu', target, app
            USING ERRCODE = 'undefined_object';
    END IF;
    IF NOT known THEN
        INSERT INTO core.apps (name) VALUES (app);
        EXECUTE format('CREATE ROLE %I NOLOGIN', target);
        EXECUTE format('CREATE SCHEMA %I AUTHORIZATION %I', target, target);
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = caller) THEN
        EXECUTE format('CREATE ROLE %I NOLOGIN', caller);
    END IF;
    EXECUTE format(
        'ALTER ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD NULL',
        target
    );
    EXECUTE format(
        'ALTER ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD NULL',
        caller
    );
    EXECUTE format('ALTER SCHEMA %I OWNER TO %I', target, target);
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), target);
    EXECUTE format('GRANT USAGE ON SCHEMA core TO %I', target);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I', target, caller);
    FOR wanted IN
        SELECT * FROM (VALUES
            ('authenticated', caller, true, false),
            (caller, 'authenticator', false, true),
            (caller, target, true, false)
        ) AS membership (role, member, inherit, settable)
    LOOP
        IF NOT EXISTS (
            SELECT FROM pg_catalog.pg_auth_members AS m
            WHERE m.roleid = wanted.role::regrole AND m.member = wanted.member::regrole
                AND m.inherit_option = wanted.inherit AND m.set_option = wanted.settable
        ) THEN
            EXECUTE format(
                'GRANT %I TO %I WITH INHERIT %s, SET %s',
                wanted.role, wanted.member, wanted.inherit::text, wanted.settable::text
            );
        END IF;
    END LOOP;
    EXECUTE format(
        'GRANT EXECUTE ON FUNCTION core.audit(), core.append_only(), core.run_app_sql(text), '
        'core.record_migration(text, text), core.secure_app() TO %I',
        target
    );
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I REVOKE EXECUTE ON ROUTINES FROM PUBLIC', target);
    RETURN NOT known;
END
$$;

DROP FUNCTION core.check_token(text);
CREATE FUNCTION core.check_token(search_path text) RETURNS text
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    claims jsonb := core.claims();
    target text;
    app text;
BEGIN
    IF claims IS NULL OR claims - 'role' = '{}' THEN
        RETURN NULL;
    END IF;
    IF claims ->> 'typ' IS DISTINCT FROM 'Bearer' THEN
        RAISE SQLSTATE 'PGRST' USING
            MESSAGE = json_build_object(
                'code', 'SGN01',
                'message', 'Access token không hợp lệ',
                'details', 'API chỉ chấp nhận access token'
            )::text,
            DETAIL = json_build_object(
                'status', 401,
                'headers', json_build_object('WWW-Authenticate', 'Bearer error="invalid_token"')
            )::text;
    END IF;
    target := (parse_ident(search_path, false))[1];
    IF target = 'api' THEN
        RETURN NULL;
    END IF;
    app := replace(target, '_', '-');
    IF claims ->> 'azp' IS DISTINCT FROM app THEN
        RAISE SQLSTATE 'PGRST' USING
            MESSAGE = json_build_object(
                'code', 'SGN02',
                'message', 'Access token không được cấp cho ứng dụng này',
                'details', format('Schema %s chỉ nhận access token được cấp cho client %s', target, app)
            )::text,
            DETAIL = json_build_object('status', 403, 'headers', json_build_object())::text;
    END IF;
    RETURN target || '_user';
END
$$;
GRANT EXECUTE ON FUNCTION core.check_token(text) TO anon, authenticated;

CREATE OR REPLACE FUNCTION core.pre_request() RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    caller text;
BEGIN
    DISCARD PLANS;
    PERFORM core.seal_claims();
    caller := core.check_token(pg_catalog.current_setting('search_path'));
    IF caller IS NOT NULL THEN
        EXECUTE pg_catalog.format('SET LOCAL ROLE %I', caller);
    END IF;
END
$$;

-- Mã của ứng dụng lúc phục vụ không được đổi hàm về SECURITY INVOKER hay tự cấp thêm quyền
CREATE FUNCTION core.refuse_runtime_ddl() RETURNS event_trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    IF NOT (SELECT pg_roles.rolsuper FROM pg_catalog.pg_roles WHERE pg_roles.rolname = session_user)
        AND NOT EXISTS (SELECT FROM core.apps WHERE apps.schema_name = session_user) THEN
        RAISE EXCEPTION 'Lệnh % chỉ chạy được trong file SQL khi cài đặt ứng dụng', tg_tag
            USING ERRCODE = 'insufficient_privilege';
    END IF;
END
$$;
CREATE EVENT TRIGGER refuse_runtime_ddl ON ddl_command_start
    EXECUTE FUNCTION core.refuse_runtime_ddl();
