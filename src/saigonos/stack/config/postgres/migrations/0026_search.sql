-- SPDX-License-Identifier: Apache-2.0
CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA core;

CREATE TEXT SEARCH CONFIGURATION core.vietnamese (COPY = pg_catalog.simple);
ALTER TEXT SEARCH CONFIGURATION core.vietnamese
    ALTER MAPPING FOR hword, hword_part, word WITH core.unaccent, pg_catalog.simple;

CREATE FUNCTION core.search_vector(VARIADIC parts text[]) RETURNS tsvector
LANGUAGE sql IMMUTABLE PARALLEL SAFE
RETURN pg_catalog.to_tsvector(
    'core.vietnamese'::pg_catalog.regconfig, pg_catalog.array_to_string(parts, ' ')
);

CREATE FUNCTION core.search_query(query text) RETURNS tsquery
LANGUAGE sql IMMUTABLE PARALLEL SAFE
RETURN pg_catalog.websearch_to_tsquery('core.vietnamese'::pg_catalog.regconfig, query);

-- Mọi role ghi vào bảng có index tìm kiếm đều phải gọi được hai hàm này
GRANT EXECUTE ON FUNCTION core.search_vector(text[]), core.search_query(text) TO PUBLIC;
