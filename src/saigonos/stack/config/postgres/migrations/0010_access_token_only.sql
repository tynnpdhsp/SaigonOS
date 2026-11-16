-- SPDX-License-Identifier: Apache-2.0
CREATE OR REPLACE FUNCTION core.pre_request() RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DISCARD PLANS;
    IF core.claims() - 'role' <> '{}' AND core.claims() ->> 'typ' IS DISTINCT FROM 'Bearer' THEN
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
END
$$;
