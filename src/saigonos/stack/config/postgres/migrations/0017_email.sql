-- SPDX-License-Identifier: Apache-2.0
ALTER TABLE core.deliveries
    DROP CONSTRAINT deliveries_channel_check,
    DROP CONSTRAINT deliveries_dedup,
    ALTER COLUMN notification_id DROP NOT NULL,
    ADD COLUMN address text,
    ADD CONSTRAINT deliveries_channel CHECK (channel IN ('telegram', 'email')),
    ADD CONSTRAINT deliveries_address CHECK ((address IS NOT NULL) = (channel = 'email')),
    ADD CONSTRAINT deliveries_dedup UNIQUE NULLS NOT DISTINCT (channel, address, dedup_key);

DROP INDEX core.deliveries_pending;
CREATE INDEX deliveries_pending ON core.deliveries (channel, next_attempt_at)
    WHERE status = 'pending';

CREATE FUNCTION core.check_message(dedup_key text, title text, body text, link text)
RETURNS void
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    IF dedup_key IS NULL OR length(dedup_key) NOT BETWEEN 1 AND 255 THEN
        RAISE EXCEPTION 'Khóa chống trùng không hợp lệ'
            USING
                ERRCODE = 'invalid_parameter_value',
                HINT = 'Khóa chống trùng dài từ 1 đến 255 ký tự';
    END IF;
    -- Thêm các khoảng trắng mà [:space:] của musl bỏ qua để giống str.isspace() của Python
    IF title IS NULL OR title !~ U&'[^[:space:]\00A0\1680\2007\202F]'
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
BEGIN
    IF recipient IS NULL OR recipient !~ '^[A-Za-z0-9_.-]{1,249}$' THEN
        RAISE EXCEPTION 'Người nhận % không hợp lệ', coalesce(quote_literal(recipient), 'NULL')
            USING
                ERRCODE = 'invalid_parameter_value',
                HINT = 'Người nhận là claim sub trong access token của người nhận. Giá trị này dài '
                    'tối đa 249 ký tự và chỉ gồm chữ cái không dấu, chữ số và các dấu _ . -';
    END IF;
    PERFORM core.check_message(dedup_key, title, body, link);
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

CREATE FUNCTION core.send_email(
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
    INSERT INTO core.deliveries AS d (channel, dedup_key, address, title, body, link)
    VALUES ('email', dedup_key, address, title, body, link)
    ON CONFLICT ON CONSTRAINT deliveries_dedup DO NOTHING
    RETURNING d.id INTO delivery_id;
    IF NOT FOUND THEN
        SELECT d.id INTO STRICT delivery_id
        FROM core.deliveries AS d
        WHERE d.channel = 'email'
            AND d.address = send_email.address
            AND d.dedup_key = send_email.dedup_key;
    END IF;
    RETURN delivery_id;
END
$$;
GRANT EXECUTE ON FUNCTION core.send_email(text, text, text, text, text) TO workflow;
