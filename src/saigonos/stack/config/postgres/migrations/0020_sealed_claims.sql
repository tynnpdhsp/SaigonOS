-- SPDX-License-Identifier: Apache-2.0
CREATE EXTENSION pgcrypto WITH SCHEMA core;

CREATE TABLE core.claims_key (
    only_row boolean PRIMARY KEY DEFAULT true CHECK (only_row),
    key bytea NOT NULL
);
INSERT INTO core.claims_key (key) VALUES (core.gen_random_bytes(32));

-- Mã gắn với tiến trình và thời điểm bắt đầu transaction, nên claims của lời gọi trước không dùng lại được
CREATE FUNCTION core.claims_seal(claims text, key bytea) RETURNS text
LANGUAGE sql STABLE
RETURN pg_catalog.encode(core.hmac(
    pg_catalog.convert_to(pg_catalog.concat_ws(
        ':',
        pg_catalog.pg_backend_pid(),
        EXTRACT(epoch FROM pg_catalog.transaction_timestamp()),
        claims
    ), 'UTF8'),
    key,
    'sha256'
), 'hex');
REVOKE EXECUTE ON FUNCTION core.claims_seal(text, bytea) FROM PUBLIC;

-- Mã của ứng dụng chỉ chạy bên trong câu lệnh do PostgREST hay service core gửi tới
CREATE FUNCTION core.seal_claims() RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    IF pg_catalog.current_query() <> ALL (ARRAY['select "core"."pre_request"()', 'SELECT core.seal_claims()'])
        AND NOT (SELECT pg_roles.rolsuper FROM pg_catalog.pg_roles WHERE pg_roles.rolname = session_user) THEN
        RAISE EXCEPTION 'Hàm core.seal_claims() chỉ dành cho PostgREST và service core'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    PERFORM pg_catalog.set_config(
        'saigonos.claims_seal',
        core.claims_seal(
            pg_catalog.current_setting('request.jwt.claims', true),
            (SELECT claims_key.key FROM core.claims_key)
        ),
        true
    );
END
$$;
GRANT EXECUTE ON FUNCTION core.seal_claims() TO anon, authenticated, workflow, core_service;

CREATE OR REPLACE FUNCTION core.claims() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = ''
RETURN (
    SELECT request.claims::jsonb
    FROM (SELECT NULLIF(pg_catalog.current_setting('request.jwt.claims', true), '') AS claims) AS request,
        core.claims_key
    WHERE pg_catalog.current_setting('saigonos.claims_seal', true)
        = core.claims_seal(request.claims, claims_key.key)
);

CREATE OR REPLACE FUNCTION core.pre_request() RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DISCARD PLANS;
    PERFORM core.seal_claims();
    PERFORM core.check_token(pg_catalog.current_setting('search_path'));
END
$$;
