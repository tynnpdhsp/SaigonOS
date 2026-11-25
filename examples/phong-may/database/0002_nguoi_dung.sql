-- SPDX-License-Identifier: Apache-2.0
CREATE TABLE nguoi_dung (
    ma text PRIMARY KEY,
    ho_ten text NOT NULL,
    vai text[] NOT NULL,
    cap_nhat_luc timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION cap_nhat_nguoi_dung() RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    nguoi text := core.uid();
    thong_tin jsonb := core.claims();
BEGIN
    IF nguoi IS NULL THEN
        RAISE EXCEPTION 'Cần đăng nhập để ghi thông tin người dùng'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    INSERT INTO phong_may.nguoi_dung AS cu (ma, ho_ten, vai)
    VALUES (
        nguoi,
        coalesce(nullif(btrim(thong_tin ->> 'name'), ''), thong_tin ->> 'preferred_username', nguoi),
        ARRAY(
            SELECT vai
            FROM jsonb_array_elements_text(thong_tin -> 'realm_access' -> 'roles') AS vai
            WHERE vai LIKE 'phong-may.%'
            ORDER BY vai
        )
    )
    ON CONFLICT (ma) DO UPDATE
    SET ho_ten = excluded.ho_ten, vai = excluded.vai, cap_nhat_luc = now()
    WHERE (cu.ho_ten, cu.vai) IS DISTINCT FROM (excluded.ho_ten, excluded.vai);
END
$$;
GRANT EXECUTE ON FUNCTION cap_nhat_nguoi_dung() TO phong_may_user;

CREATE FUNCTION bao_vai(
    vai_nhan text, khoa text, tieu_de text, noi_dung text, duong_dan text, telegram boolean
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    nguoi record;
BEGIN
    FOR nguoi IN
        SELECT nguoi_dung.ma FROM phong_may.nguoi_dung
        WHERE bao_vai.vai_nhan = ANY (nguoi_dung.vai)
        ORDER BY nguoi_dung.ma
    LOOP
        PERFORM core.notify(nguoi.ma, khoa, tieu_de, noi_dung, duong_dan, telegram);
    END LOOP;
END
$$;
