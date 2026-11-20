-- SPDX-License-Identifier: Apache-2.0
CREATE TABLE core.notifications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient text NOT NULL,
    dedup_key text NOT NULL,
    title text NOT NULL,
    body text,
    link text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    read_at timestamptz,
    CONSTRAINT notifications_dedup UNIQUE (recipient, dedup_key)
);
CREATE INDEX notifications_recipient ON core.notifications (recipient, created_at, id);

CREATE TRIGGER audit AFTER INSERT OR UPDATE OR DELETE ON core.notifications
    FOR EACH ROW EXECUTE FUNCTION core.audit();

ALTER TABLE core.notifications ENABLE ROW LEVEL SECURITY;
CREATE POLICY recipient_only ON core.notifications TO authenticated, core_service
    USING (recipient = core.uid());

GRANT SELECT ON core.notifications TO authenticated;
GRANT SELECT, UPDATE (read_at) ON core.notifications TO core_service;

CREATE FUNCTION core.notify(
    recipient text, dedup_key text, title text, body text DEFAULT NULL, link text DEFAULT NULL
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
    IF title IS NULL OR title !~ '[^[:space:]\u00a0\u1680\u2007\u202f]'
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
    RETURN notification.id;
END
$$;
GRANT EXECUTE ON FUNCTION core.notify(text, text, text, text, text) TO workflow;
