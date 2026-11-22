-- SPDX-License-Identifier: Apache-2.0
CREATE FUNCTION core.calling_app() RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    found text;
BEGIN
    SELECT apps.name INTO found
    FROM core.apps
    WHERE apps.schema_name = session_user
        OR apps.schema_name || '_user' = pg_catalog.current_setting('role');
    IF found IS NOT NULL THEN
        RETURN found;
    END IF;
    IF NULLIF(pg_catalog.current_setting('request.jwt.claims', true), '') IS NOT NULL
        AND core.claims() IS NULL THEN
        RAISE EXCEPTION 'Claims của lời gọi đã bị sửa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    SELECT apps.name INTO found FROM core.apps WHERE apps.name = core.claims() ->> 'azp';
    RETURN found;
END
$$;
GRANT EXECUTE ON FUNCTION core.calling_app() TO authenticated, core_service;

ALTER TABLE core.notifications
    ADD COLUMN app text,
    DROP CONSTRAINT notifications_dedup,
    ADD CONSTRAINT notifications_dedup UNIQUE NULLS NOT DISTINCT (app, recipient, dedup_key);
DROP POLICY recipient_only ON core.notifications;
CREATE POLICY recipient_only ON core.notifications TO authenticated, core_service
    USING (recipient = (SELECT core.uid()) AND app IS NOT DISTINCT FROM (SELECT core.calling_app()));

ALTER TABLE core.deliveries
    ADD COLUMN app text,
    DROP CONSTRAINT deliveries_dedup,
    ADD CONSTRAINT deliveries_dedup UNIQUE NULLS NOT DISTINCT (app, channel, address, dedup_key);

CREATE OR REPLACE FUNCTION core.publish(channel text, data jsonb) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    message_id uuid := gen_random_uuid();
    sender text := core.calling_app();
BEGIN
    IF channel IS NULL OR length(channel) > 255
        OR channel !~ '^((public:|user:#|role:)|user:[a-z][a-z0-9-]*\.)[A-Za-z0-9_.-]+$' THEN
        RAISE EXCEPTION 'Kênh % không hợp lệ', coalesce(quote_literal(channel), 'NULL')
            USING
                ERRCODE = 'invalid_parameter_value',
                HINT = 'Kênh có dạng public:<tên>, user:#<sub>, user:<tên ứng dụng>.<sub> '
                    'hoặc role:<realm role> và dài tối đa 255 ký tự. Tên, sub và realm role chỉ '
                    'gồm chữ cái không dấu, chữ số và các dấu _ . -';
    END IF;
    IF sender IS NOT NULL AND NOT (
        starts_with(channel, 'role:' || sender || '.')
        OR starts_with(channel, 'public:' || sender || '.')
        OR starts_with(channel, 'user:' || sender || '.')
    ) THEN
        RAISE EXCEPTION 'Ứng dụng % không gửi được tin vào kênh %', sender, quote_literal(channel)
            USING
                ERRCODE = 'insufficient_privilege',
                HINT = format(
                    'Ứng dụng chỉ gửi được tin vào kênh role:%1$s.<vai trò>, public:%1$s.<tên> '
                    'và user:%1$s.<sub>',
                    sender
                );
    END IF;
    IF data IS NULL THEN
        RAISE EXCEPTION 'Nội dung của tin không được là NULL'
            USING ERRCODE = 'null_value_not_allowed';
    END IF;
    INSERT INTO core.outbox (method, payload)
    VALUES ('publish', jsonb_build_object(
        'channel', channel,
        'data', data,
        'tags', jsonb_build_object('id', message_id),
        'idempotency_key', message_id
    ));
    RETURN message_id;
END
$$;

CREATE OR REPLACE FUNCTION core.notify(
    recipient text,
    dedup_key text,
    title text,
    body text DEFAULT NULL,
    link text DEFAULT NULL,
    telegram boolean DEFAULT false
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    notification core.notifications;
    sender text := core.calling_app();
BEGIN
    IF recipient IS NULL OR recipient !~ '^[A-Za-z0-9_.-]{1,249}$' THEN
        RAISE EXCEPTION 'Người nhận % không hợp lệ', coalesce(quote_literal(recipient), 'NULL')
            USING
                ERRCODE = 'invalid_parameter_value',
                HINT = 'Người nhận là claim sub trong access token của người nhận. Giá trị này dài '
                    'tối đa 249 ký tự và chỉ gồm chữ cái không dấu, chữ số và các dấu _ . -';
    END IF;
    PERFORM core.check_message(dedup_key, title, body, link);
    INSERT INTO core.notifications AS n (app, recipient, dedup_key, title, body, link)
    VALUES (sender, recipient, dedup_key, title, body, link)
    ON CONFLICT ON CONSTRAINT notifications_dedup DO NOTHING
    RETURNING n.* INTO notification;
    IF NOT FOUND THEN
        SELECT n.id INTO STRICT notification.id
        FROM core.notifications AS n
        WHERE n.app IS NOT DISTINCT FROM sender
            AND n.recipient = notify.recipient
            AND n.dedup_key = notify.dedup_key;
        RETURN notification.id;
    END IF;
    PERFORM core.publish(
        CASE WHEN sender IS NULL THEN 'user:#' ELSE 'user:' || sender || '.' END || recipient,
        jsonb_build_object('notification', jsonb_build_object(
            'id', notification.id,
            'title', notification.title,
            'body', notification.body,
            'link', notification.link,
            'created_at',
                to_char(notification.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
            'read_at', NULL
        ))
    );
    IF telegram THEN
        INSERT INTO core.deliveries (app, channel, dedup_key, notification_id, title, body, link)
        VALUES (
            sender,
            'telegram',
            notification.dedup_key,
            notification.id,
            notification.title,
            notification.body,
            notification.link
        )
        ON CONFLICT ON CONSTRAINT deliveries_dedup DO NOTHING;
    END IF;
    RETURN notification.id;
END
$$;

CREATE OR REPLACE FUNCTION core.send_email(
    address text,
    dedup_key text,
    title text,
    body text DEFAULT NULL,
    link text DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    delivery_id bigint;
    sender text := core.calling_app();
BEGIN
    IF address IS NULL OR length(address) > 254 OR address !~ ('^[A-Za-z0-9.!#$%&''*+/=?^_`{|}~-]+'
        '@[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$')
    THEN
        RAISE EXCEPTION 'Địa chỉ email % không hợp lệ', coalesce(quote_literal(address), 'NULL')
            USING
                ERRCODE = 'invalid_parameter_value',
                HINT = 'Địa chỉ email có dạng ten@ten-mien, ví dụ nguyen.van.a@example.com. Địa '
                    'chỉ chỉ gồm chữ cái không dấu, chữ số và một số dấu, dài tối đa 254 ký tự';
    END IF;
    PERFORM core.check_message(dedup_key, title, body, link);
    INSERT INTO core.deliveries AS d (app, channel, dedup_key, address, title, body, link)
    VALUES (sender, 'email', dedup_key, address, title, body, link)
    ON CONFLICT ON CONSTRAINT deliveries_dedup DO NOTHING
    RETURNING d.id INTO delivery_id;
    IF NOT FOUND THEN
        SELECT d.id INTO STRICT delivery_id
        FROM core.deliveries AS d
        WHERE d.app IS NOT DISTINCT FROM sender
            AND d.channel = 'email'
            AND d.address = send_email.address
            AND d.dedup_key = send_email.dedup_key;
    END IF;
    RETURN delivery_id;
END
$$;

CREATE OR REPLACE FUNCTION core.prepare_app(app text) RETURNS boolean
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    target text := replace(app, '-', '_');
    caller text := target || '_user';
    known boolean := EXISTS (SELECT FROM core.apps WHERE apps.name = app);
    taken text := (
        SELECT found.name
        FROM (
            SELECT pg_roles.rolname AS name FROM pg_catalog.pg_roles
            WHERE pg_roles.rolname IN (target, caller)
            UNION ALL
            SELECT pg_namespace.nspname FROM pg_catalog.pg_namespace
            WHERE pg_namespace.nspname = target
        ) AS found
        ORDER BY found.name
        LIMIT 1
    );
    wanted record;
BEGIN
    IF NOT known AND taken IS NOT NULL THEN
        RAISE EXCEPTION 'Role hoặc schema % đã có trong cơ sở dữ liệu nhưng không do SaigonOS tạo cho ứng dụng %', taken, app
            USING ERRCODE = 'duplicate_object', HINT = 'Hãy đặt tên khác cho ứng dụng.';
    END IF;
    IF known AND NOT (
        EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = target)
        AND EXISTS (SELECT FROM pg_catalog.pg_namespace WHERE nspname = target)
    ) THEN
        RAISE EXCEPTION 'Role hoặc schema % của ứng dụng % không còn trong cơ sở dữ liệu', target, app
            USING ERRCODE = 'undefined_object';
    END IF;
    IF NOT known THEN
        INSERT INTO core.apps (name) VALUES (app);
        EXECUTE format('CREATE ROLE %I NOLOGIN', target);
        EXECUTE format('CREATE SCHEMA %I AUTHORIZATION %I', target, target);
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = caller) THEN
        EXECUTE format('CREATE ROLE %I NOLOGIN', caller);
    END IF;
    EXECUTE format(
        'ALTER ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD NULL',
        target
    );
    EXECUTE format(
        'ALTER ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD NULL',
        caller
    );
    EXECUTE format('ALTER SCHEMA %I OWNER TO %I', target, target);
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), target);
    EXECUTE format('GRANT USAGE ON SCHEMA core TO %I', target);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I, workflow', target, caller);
    FOR wanted IN
        SELECT * FROM (VALUES
            ('authenticated', caller, true, false),
            (caller, 'authenticator', false, true),
            (caller, target, true, false)
        ) AS membership (role, member, inherit, settable)
    LOOP
        IF NOT EXISTS (
            SELECT FROM pg_catalog.pg_auth_members AS m
            WHERE m.roleid = wanted.role::regrole AND m.member = wanted.member::regrole
                AND m.inherit_option = wanted.inherit AND m.set_option = wanted.settable
        ) THEN
            EXECUTE format(
                'GRANT %I TO %I WITH INHERIT %s, SET %s',
                wanted.role, wanted.member, wanted.inherit::text, wanted.settable::text
            );
        END IF;
    END LOOP;
    EXECUTE format(
        'GRANT EXECUTE ON FUNCTION core.audit(), core.append_only(), core.run_app_sql(text), '
        'core.record_migration(text, text), core.secure_app() TO %I',
        target
    );
    EXECUTE format(
        'GRANT EXECUTE ON FUNCTION core.send_email(text, text, text, text, text), '
        'core.notify(text, text, text, text, text, boolean), core.publish(text, jsonb) TO %I, %I',
        target, caller
    );
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I REVOKE EXECUTE ON ROUTINES FROM PUBLIC', target);
    RETURN NOT known;
END
$$;
