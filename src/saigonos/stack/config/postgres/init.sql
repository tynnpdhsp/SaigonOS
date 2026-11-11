-- SPDX-License-Identifier: Apache-2.0
\set ON_ERROR_STOP on
\getenv keycloak_password KEYCLOAK_DB_PASSWORD
\getenv postgrest_password POSTGREST_DB_PASSWORD

CREATE ROLE keycloak LOGIN PASSWORD :'keycloak_password';
CREATE DATABASE keycloak OWNER keycloak;
REVOKE CONNECT ON DATABASE keycloak FROM PUBLIC;

CREATE ROLE authenticator LOGIN NOINHERIT PASSWORD :'postgrest_password';
CREATE ROLE authenticated NOLOGIN;
GRANT authenticated TO authenticator;
REVOKE CONNECT ON DATABASE saigonos FROM PUBLIC;
GRANT CONNECT ON DATABASE saigonos TO authenticator;

CREATE SCHEMA api;
GRANT USAGE ON SCHEMA api TO authenticated;
