-- SPDX-License-Identifier: Apache-2.0
CREATE FUNCTION core.mask_phone(phone text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
RETURN CASE
    WHEN length(phone) < 10 THEN repeat('*', length(phone))
    ELSE left(phone, 3) || '****' || right(phone, 3)
END;

CREATE FUNCTION core.mask_email(email text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
RETURN (
    SELECT CASE
        WHEN length(name) < 6 THEN repeat('*', length(name))
        ELSE left(name, 3) || repeat('*', length(name) - 3)
    END || domain
    FROM (VALUES (
        coalesce(substring(email FROM '^(.*)@'), email),
        coalesce(substring(email FROM '@[^@]*$'), '')
    )) AS parts (name, domain)
);

GRANT EXECUTE ON FUNCTION core.mask_phone, core.mask_email TO anon, authenticated;
