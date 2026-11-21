-- SPDX-License-Identifier: Apache-2.0
CREATE FUNCTION core.check_token(search_path text) RETURNS void
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    claims jsonb := core.claims();
    target text;
    app text;
BEGIN
    IF claims IS NULL OR claims - 'role' = '{}' THEN
        RETURN;
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
        RETURN;
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
END
$$;
GRANT EXECUTE ON FUNCTION core.check_token(text) TO anon, authenticated;

-- PostgREST đặt schema của lời gọi lên đầu search_path, nên hàm này không có SET search_path riêng
CREATE OR REPLACE FUNCTION core.pre_request() RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DISCARD PLANS;
    PERFORM core.check_token(pg_catalog.current_setting('search_path'));
END
$$;
