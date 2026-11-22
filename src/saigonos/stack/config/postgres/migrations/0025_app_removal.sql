-- SPDX-License-Identifier: Apache-2.0
ALTER TABLE core.apps ADD COLUMN removed_at timestamptz;

CREATE OR REPLACE FUNCTION core.finish_app(
    app text, title text, version text, manifest jsonb, files_ran boolean
) RETURNS boolean
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    UPDATE core.apps
    SET title = finish_app.title, version = finish_app.version, manifest = finish_app.manifest,
        applied_at = now(), removed_at = NULL
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

CREATE FUNCTION core.remove_app(app text) RETURNS boolean
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    UPDATE core.apps SET applied_at = NULL, removed_at = now()
    WHERE apps.name = app AND apps.applied_at IS NOT NULL;
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    PERFORM pg_notify('pgrst', 'reload config');
    PERFORM pg_notify('pgrst', 'reload schema');
    RETURN true;
END
$$;

CREATE FUNCTION core.purge_app(app text) RETURNS boolean
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    target text := replace(app, '-', '_');
    caller text := target || '_user';
    old_role text;
BEGIN
    IF NOT EXISTS (SELECT FROM core.apps WHERE apps.name = app) THEN
        RETURN false;
    END IF;
    PERFORM pg_catalog.pg_terminate_backend(pg_stat_activity.pid)
    FROM pg_catalog.pg_stat_activity
    WHERE pg_stat_activity.usename IN (target, caller);
    DELETE FROM core.deliveries WHERE deliveries.app = purge_app.app;
    DELETE FROM core.notifications WHERE notifications.app = purge_app.app;
    DELETE FROM core.step_runs WHERE starts_with(step_runs.function, target || '.');
    DELETE FROM core.migrations WHERE migrations.scope = app;
    EXECUTE format('DROP SCHEMA IF EXISTS %I CASCADE', target);
    FOREACH old_role IN ARRAY ARRAY[caller, target] LOOP
        IF EXISTS (SELECT FROM pg_catalog.pg_roles WHERE pg_roles.rolname = old_role) THEN
            EXECUTE format('DROP OWNED BY %I', old_role);
            EXECUTE format('DROP ROLE %I', old_role);
        END IF;
    END LOOP;
    DELETE FROM core.apps WHERE apps.name = app;
    PERFORM pg_notify('pgrst', 'reload config');
    PERFORM pg_notify('pgrst', 'reload schema');
    RETURN true;
END
$$;
