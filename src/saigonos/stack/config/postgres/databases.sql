-- SPDX-License-Identifier: Apache-2.0
\getenv operaton_password OPERATON_DB_PASSWORD
\getenv centrifugo_password CENTRIFUGO_DB_PASSWORD

SELECT NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'operaton') AS missing_role \gset
\if :missing_role
CREATE ROLE operaton LOGIN PASSWORD :'operaton_password';
\echo Đã tạo role operaton
\endif

SELECT NOT EXISTS (SELECT FROM pg_database WHERE datname = 'operaton') AS missing_database \gset
\if :missing_database
CREATE DATABASE operaton OWNER operaton;
\echo Đã tạo cơ sở dữ liệu operaton
\endif

REVOKE CONNECT ON DATABASE operaton FROM PUBLIC;

SELECT NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'centrifugo') AS missing_centrifugo \gset
\if :missing_centrifugo
CREATE ROLE centrifugo LOGIN PASSWORD :'centrifugo_password';
\echo Đã tạo role centrifugo
\endif
