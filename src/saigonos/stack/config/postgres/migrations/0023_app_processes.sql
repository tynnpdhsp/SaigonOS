-- SPDX-License-Identifier: Apache-2.0
GRANT SELECT (schema_name) ON core.apps TO core_service;

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
        AND NOT (acl.privilege_type = 'USAGE' AND grantee.rolname IN (caller, 'anon', 'workflow'))
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
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I, workflow', target, caller);
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
    EXECUTE format(
        'GRANT EXECUTE ON FUNCTION core.send_email(text, text, text, text, text) TO %I, %I',
        target, caller
    );
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I REVOKE EXECUTE ON ROUTINES FROM PUBLIC', target);
    RETURN NOT known;
END
$$;
