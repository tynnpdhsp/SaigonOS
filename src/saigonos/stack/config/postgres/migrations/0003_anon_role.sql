-- SPDX-License-Identifier: Apache-2.0
CREATE ROLE anon NOLOGIN;
GRANT anon TO authenticator;
GRANT USAGE ON SCHEMA api, core TO anon;

ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON ROUTINES FROM PUBLIC;
REVOKE EXECUTE ON ALL ROUTINES IN SCHEMA api FROM PUBLIC;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA api TO authenticated;

-- PostgreSQL không kiểm tra lại quyền EXECUTE khi dùng lại query plan đã lập cho role khác
CREATE FUNCTION core.pre_request() RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DISCARD PLANS;
END
$$;
GRANT EXECUTE ON FUNCTION core.pre_request TO anon, authenticated;
