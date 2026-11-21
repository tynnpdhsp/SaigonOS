-- SPDX-License-Identifier: Apache-2.0
CREATE TABLE core.outbox (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    method text NOT NULL,
    payload jsonb NOT NULL,
    partition integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION core.outbox_notify() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM pg_notify('core_outbox', NEW.partition::text);
    RETURN NULL;
END
$$;

CREATE TRIGGER notify AFTER INSERT ON core.outbox
    FOR EACH ROW EXECUTE FUNCTION core.outbox_notify();

GRANT CONNECT ON DATABASE saigonos TO centrifugo;
GRANT USAGE ON SCHEMA core TO centrifugo;
GRANT SELECT, DELETE ON core.outbox TO centrifugo;

CREATE FUNCTION core.publish(channel text, data jsonb) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    message_id uuid := gen_random_uuid();
BEGIN
    IF channel IS NULL OR length(channel) > 255
        OR channel !~ '^(public:|user:#|role:)[A-Za-z0-9_.-]+$' THEN
        RAISE EXCEPTION 'Kênh % không hợp lệ', coalesce(quote_literal(channel), 'NULL')
            USING
                ERRCODE = 'invalid_parameter_value',
                HINT = 'Kênh có dạng public:<tên>, user:#<sub> hoặc role:<realm role> '
                    'và dài tối đa 255 ký tự. Tên, sub và realm role chỉ gồm chữ cái '
                    'không dấu, chữ số và các dấu _ . -';
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
GRANT EXECUTE ON FUNCTION core.publish(text, jsonb) TO workflow;
