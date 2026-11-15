-- SPDX-License-Identifier: Apache-2.0
CREATE FUNCTION core.claims() RETURNS jsonb
LANGUAGE sql STABLE
RETURN nullif(current_setting('request.jwt.claims', true), '')::jsonb;

CREATE FUNCTION core.uid() RETURNS text
LANGUAGE sql STABLE
RETURN core.claims() ->> 'sub';

CREATE FUNCTION core.has_role(role text) RETURNS boolean
LANGUAGE sql STABLE
RETURN coalesce(core.claims() -> 'realm_access' -> 'roles' ? role, false);

CREATE FUNCTION core.unit() RETURNS text
LANGUAGE sql STABLE
RETURN core.claims() ->> 'unit';

GRANT USAGE ON SCHEMA core TO authenticated;
