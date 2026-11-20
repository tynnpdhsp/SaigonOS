-- SPDX-License-Identifier: Apache-2.0
CREATE TABLE core.deliveries (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel text NOT NULL CHECK (channel IN ('telegram')),
    dedup_key text NOT NULL,
    notification_id uuid NOT NULL REFERENCES core.notifications (id),
    title text NOT NULL,
    body text,
    link text,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'sending', 'sent', 'failed', 'unknown', 'skipped')),
    failures integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    sent_id text,
    error text,
    CONSTRAINT deliveries_dedup UNIQUE (channel, dedup_key)
);
CREATE INDEX deliveries_pending ON core.deliveries (next_attempt_at) WHERE status = 'pending';

CREATE FUNCTION core.deliveries_notify() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM pg_notify('core_deliveries', '');
    RETURN NULL;
END
$$;

CREATE TRIGGER notify AFTER INSERT ON core.deliveries
    FOR EACH ROW EXECUTE FUNCTION core.deliveries_notify();

GRANT SELECT, UPDATE (status, failures, next_attempt_at, finished_at, sent_id, error)
    ON core.deliveries TO core_service;

DROP FUNCTION core.notify(text, text, text, text, text);
CREATE FUNCTION core.notify(
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
BEGIN
    IF recipient IS NULL OR recipient !~ '^[A-Za-z0-9_.-]{1,249}$' THEN
        RAISE EXCEPTION 'Người nhận % không hợp lệ', coalesce(quote_literal(recipient), 'NULL')
            USING
                ERRCODE = 'invalid_parameter_value',
                HINT = 'Người nhận là claim sub trong access token của người nhận. Giá trị này dài '
                    'tối đa 249 ký tự và chỉ gồm chữ cái không dấu, chữ số và các dấu _ . -';
    END IF;
    IF dedup_key IS NULL OR length(dedup_key) NOT BETWEEN 1 AND 255 THEN
        RAISE EXCEPTION 'Khóa chống trùng không hợp lệ'
            USING
                ERRCODE = 'invalid_parameter_value',
                HINT = 'Khóa chống trùng dài từ 1 đến 255 ký tự';
    END IF;
    -- Thêm các khoảng trắng mà [:space:] của musl bỏ qua để giống str.isspace() của Python
    IF title IS NULL OR title !~ '[^[:space:]    ]'
        OR title ~ '[[:cntrl:]]' OR length(title) > 200 THEN
        RAISE EXCEPTION 'Tiêu đề không hợp lệ'
            USING
                ERRCODE = 'invalid_parameter_value',
                HINT = 'Tiêu đề dài tối đa 200 ký tự và có ít nhất một ký tự khác khoảng trắng. '
                    'Tiêu đề không chứa ký tự điều khiển, ví dụ dấu xuống dòng';
    END IF;
    IF length(body) > 2000 THEN
        RAISE EXCEPTION 'Nội dung dài quá 2000 ký tự'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF link !~ '^/([^/\\]|$)' OR link ~ '[[:cntrl:]]' OR length(link) > 1000 THEN
        RAISE EXCEPTION 'Đường dẫn % không hợp lệ', quote_literal(link)
            USING
                ERRCODE = 'invalid_parameter_value',
                HINT = 'Đường dẫn trỏ tới một trang trong hệ thống và bắt đầu bằng một dấu /, ví '
                    'dụ /yeu-cau/YC-001. Đường dẫn dài tối đa 1000 ký tự và không chứa ký tự '
                    'điều khiển';
    END IF;
    INSERT INTO core.notifications AS n (recipient, dedup_key, title, body, link)
    VALUES (recipient, dedup_key, title, body, link)
    ON CONFLICT ON CONSTRAINT notifications_dedup DO NOTHING
    RETURNING n.* INTO notification;
    IF NOT FOUND THEN
        SELECT n.id INTO STRICT notification.id
        FROM core.notifications AS n
        WHERE n.recipient = notify.recipient AND n.dedup_key = notify.dedup_key;
        RETURN notification.id;
    END IF;
    PERFORM core.publish('user:#' || recipient, jsonb_build_object('notification', jsonb_build_object(
        'id', notification.id,
        'title', notification.title,
        'body', notification.body,
        'link', notification.link,
        'created_at',
            to_char(notification.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
        'read_at', NULL
    )));
    IF telegram THEN
        INSERT INTO core.deliveries (channel, dedup_key, notification_id, title, body, link)
        VALUES (
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
GRANT EXECUTE ON FUNCTION core.notify(text, text, text, text, text, boolean) TO workflow;
