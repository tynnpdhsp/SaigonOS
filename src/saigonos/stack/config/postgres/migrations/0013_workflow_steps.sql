-- SPDX-License-Identifier: Apache-2.0
CREATE ROLE workflow NOLOGIN;
GRANT workflow TO core_service;
GRANT USAGE ON SCHEMA core TO workflow;

CREATE TABLE core.step_runs (
    external_task_id text PRIMARY KEY,
    process_instance_id text NOT NULL,
    activity_id text NOT NULL,
    function text NOT NULL,
    result jsonb,
    ran_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE ON core.step_runs TO core_service;

-- Hàm của ứng dụng chạy bên trong hàm SECURITY DEFINER nên không đổi được role của phiên
CREATE FUNCTION core.run_step(step regprocedure, variables jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    target text;
    result jsonb;
BEGIN
    SELECT pg_catalog.format('%I.%I', n.nspname, p.proname) INTO STRICT target
    FROM pg_catalog.pg_proc AS p
    JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
    WHERE p.oid = step;
    EXECUTE pg_catalog.format('SELECT %s($1)', target) INTO result USING variables;
    RETURN result;
END
$$;
ALTER FUNCTION core.run_step(regprocedure, jsonb) OWNER TO workflow;
