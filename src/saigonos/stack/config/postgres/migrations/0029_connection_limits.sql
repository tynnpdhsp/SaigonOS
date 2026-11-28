-- SPDX-License-Identifier: Apache-2.0
ALTER ROLE keycloak CONNECTION LIMIT 25;
ALTER ROLE authenticator CONNECTION LIMIT 15;
ALTER ROLE operaton CONNECTION LIMIT 15;
ALTER ROLE core_service CONNECTION LIMIT 15;
ALTER ROLE centrifugo CONNECTION LIMIT 6;

ALTER ROLE authenticator SET statement_timeout = '15s';
