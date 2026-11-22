-- SPDX-License-Identifier: Apache-2.0
CREATE TABLE core.apps (
    name text PRIMARY KEY CHECK (name ~ '^[a-z][a-z0-9]*(-[a-z0-9]+)*$' AND length(name) <= 32),
    schema_name text GENERATED ALWAYS AS (replace(name, '-', '_')) STORED UNIQUE,
    title text,
    version text,
    manifest jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    applied_at timestamptz
);

CREATE TRIGGER audit AFTER INSERT OR UPDATE OR DELETE ON core.apps
    FOR EACH ROW EXECUTE FUNCTION core.audit();

-- PostgREST không nạp được schema cache khi danh sách có một schema không còn tồn tại
CREATE FUNCTION core.pre_config() RETURNS void
LANGUAGE sql SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT pg_catalog.set_config('pgrst.db_schemas', pg_catalog.concat_ws(',', 'api', (
        SELECT pg_catalog.string_agg(apps.schema_name, ',' ORDER BY apps.name)
        FROM core.apps
        JOIN pg_catalog.pg_namespace ON pg_namespace.nspname = apps.schema_name
        WHERE apps.applied_at IS NOT NULL
    )), true);
$$;
GRANT USAGE ON SCHEMA core TO authenticator;
GRANT EXECUTE ON FUNCTION core.pre_config() TO authenticator;

-- Chạy file SQL bên trong hàm để file không dùng được COMMIT, ROLLBACK hay SAVEPOINT
CREATE FUNCTION core.run_app_sql(script text) RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    EXECUTE script;
END
$$;

CREATE FUNCTION core.record_migration(name text, checksum text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    app text;
BEGIN
    SELECT apps.name INTO app FROM core.apps WHERE apps.schema_name = session_user;
    IF app IS NULL THEN
        RAISE EXCEPTION 'Chỉ role của ứng dụng gọi được hàm core.record_migration'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    INSERT INTO core.migrations (scope, name, checksum)
    VALUES (app, record_migration.name, record_migration.checksum);
END
$$;

CREATE FUNCTION core.prepare_app(app text) RETURNS boolean
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    target text := replace(app, '-', '_');
    known boolean := EXISTS (SELECT FROM core.apps WHERE apps.name = app);
    role_exists boolean := EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = target);
    schema_exists boolean := EXISTS (SELECT FROM pg_catalog.pg_namespace WHERE nspname = target);
BEGIN
    IF NOT known AND (role_exists OR schema_exists) THEN
        RAISE EXCEPTION 'Role hoặc schema % đã có trong cơ sở dữ liệu nhưng không do SaigonOS tạo cho ứng dụng %', target, app
            USING ERRCODE = 'duplicate_object', HINT = 'Hãy đặt tên khác cho ứng dụng.';
    END IF;
    IF known AND NOT (role_exists AND schema_exists) THEN
        RAISE EXCEPTION 'Role hoặc schema % của ứng dụng % không còn trong cơ sở dữ liệu', target, app
            USING ERRCODE = 'undefined_object';
    END IF;
    IF NOT known THEN
        INSERT INTO core.apps (name) VALUES (app);
        EXECUTE format('CREATE ROLE %I NOLOGIN', target);
        EXECUTE format('CREATE SCHEMA %I AUTHORIZATION %I', target, target);
    END IF;
    EXECUTE format(
        'ALTER ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD NULL',
        target
    );
    EXECUTE format('ALTER SCHEMA %I OWNER TO %I', target, target);
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), target);
    EXECUTE format('GRANT USAGE ON SCHEMA core TO %I', target);
    EXECUTE format(
        'GRANT EXECUTE ON FUNCTION core.audit(), core.append_only(), core.run_app_sql(text), '
        'core.record_migration(text, text) TO %I',
        target
    );
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I REVOKE EXECUTE ON ROUTINES FROM PUBLIC', target);
    RETURN NOT known;
END
$$;

CREATE FUNCTION core.open_app_login(app text, password text) RETURNS void
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    EXECUTE format(
        'ALTER ROLE %I LOGIN PASSWORD %L VALID UNTIL %L',
        (SELECT apps.schema_name FROM core.apps WHERE apps.name = app),
        password,
        now() + interval '10 minutes'
    );
END
$$;

CREATE FUNCTION core.close_app_login(app text) RETURNS void
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    target text := (SELECT apps.schema_name FROM core.apps WHERE apps.name = app);
BEGIN
    EXECUTE format('ALTER ROLE %I NOLOGIN PASSWORD NULL', target);
    PERFORM pg_terminate_backend(pid) FROM pg_catalog.pg_stat_activity WHERE usename = target;
END
$$;

CREATE FUNCTION core.finish_app(
    app text, title text, version text, manifest jsonb, files_ran boolean
) RETURNS boolean
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    UPDATE core.apps
    SET title = finish_app.title, version = finish_app.version, manifest = finish_app.manifest,
        applied_at = now()
    WHERE apps.name = app AND (
        files_ran OR apps.applied_at IS NULL
        OR (apps.title, apps.version, apps.manifest)
            IS DISTINCT FROM (finish_app.title, finish_app.version, finish_app.manifest)
    );
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    PERFORM pg_notify('pgrst', 'reload config');
    PERFORM pg_notify('pgrst', 'reload schema');
    RETURN true;
END
$$;
