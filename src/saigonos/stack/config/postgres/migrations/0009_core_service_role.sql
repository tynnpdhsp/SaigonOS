-- SPDX-License-Identifier: Apache-2.0
\getenv core_password CORE_DB_PASSWORD
CREATE ROLE core_service LOGIN NOINHERIT PASSWORD :'core_password';
GRANT anon, authenticated TO core_service;
GRANT CONNECT ON DATABASE saigonos TO core_service;
