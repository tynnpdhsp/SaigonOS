-- SPDX-License-Identifier: Apache-2.0
CREATE SCHEMA thu_nghiem;
GRANT USAGE ON SCHEMA thu_nghiem TO workflow;

CREATE TABLE thu_nghiem.yeu_cau (
    ma text PRIMARY KEY,
    trang_thai text NOT NULL DEFAULT 'moi',
    ket_qua text
);
CREATE TRIGGER audit AFTER INSERT OR UPDATE OR DELETE ON thu_nghiem.yeu_cau
    FOR EACH ROW EXECUTE FUNCTION core.audit();
GRANT SELECT, UPDATE ON thu_nghiem.yeu_cau TO workflow;

CREATE TABLE thu_nghiem.lan_chay (ma text NOT NULL, ham text NOT NULL);
GRANT SELECT, INSERT ON thu_nghiem.lan_chay TO workflow;
CREATE SEQUENCE thu_nghiem.lan_goi;
GRANT USAGE ON SEQUENCE thu_nghiem.lan_goi TO workflow;

CREATE FUNCTION thu_nghiem.ghi_ket_qua(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE thu_nghiem.yeu_cau SET trang_thai = 'da_xu_ly', ket_qua = bien ->> 'ket_qua'
    WHERE ma = bien ->> 'ma_yeu_cau';
    RETURN jsonb_build_object('da_cap_nhat', FOUND);
END
$$;
GRANT EXECUTE ON FUNCTION thu_nghiem.ghi_ket_qua(jsonb) TO workflow;

CREATE FUNCTION thu_nghiem.nguoi_chay(bien jsonb) RETURNS jsonb
LANGUAGE sql
RETURN jsonb_build_object(
    'vai_tro', current_user, 'role', current_setting('role'), 'bien', bien::text
);
GRANT EXECUTE ON FUNCTION thu_nghiem.nguoi_chay(jsonb) TO workflow;

CREATE FUNCTION thu_nghiem.chua_khai(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO thu_nghiem.lan_chay VALUES (bien ->> 'ma', 'chua_khai');
    RETURN NULL;
END
$$;

CREATE FUNCTION thu_nghiem.cong_khai(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO thu_nghiem.lan_chay VALUES (bien ->> 'ma', 'cong_khai');
    RETURN NULL;
END
$$;
GRANT EXECUTE ON FUNCTION thu_nghiem.cong_khai(jsonb) TO PUBLIC;

CREATE FUNCTION thu_nghiem.nhan_chuoi(bien text) RETURNS jsonb
LANGUAGE sql
RETURN NULL::jsonb;
GRANT EXECUTE ON FUNCTION thu_nghiem.nhan_chuoi(text) TO workflow;

CREATE FUNCTION thu_nghiem.tra_chuoi(bien jsonb) RETURNS text
LANGUAGE sql
RETURN 'xong';
GRANT EXECUTE ON FUNCTION thu_nghiem.tra_chuoi(jsonb) TO workflow;

CREATE FUNCTION thu_nghiem.ghi_initiator(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO thu_nghiem.lan_chay VALUES (bien ->> 'ma', 'ghi_initiator');
    RETURN jsonb_build_object('initiator', 'nguoi-khac');
END
$$;
GRANT EXECUTE ON FUNCTION thu_nghiem.ghi_initiator(jsonb) TO workflow;

CREATE FUNCTION thu_nghiem.loi_lan_dau(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql
AS $$
BEGIN
    IF nextval('thu_nghiem.lan_goi') = 1 THEN
        RAISE EXCEPTION 'Lỗi thử ở lần gọi đầu';
    END IF;
    RETURN jsonb_build_object('lan_goi', currval('thu_nghiem.lan_goi'));
END
$$;
GRANT EXECUTE ON FUNCTION thu_nghiem.loi_lan_dau(jsonb) TO workflow;

CREATE FUNCTION thu_nghiem.luon_loi(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Không đủ dữ liệu để xử lý' USING HINT = 'Kiểm tra biến ma_yeu_cau';
END
$$;
GRANT EXECUTE ON FUNCTION thu_nghiem.luon_loi(jsonb) TO workflow;

CREATE FUNCTION thu_nghiem.doi_role(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql
AS $$
BEGIN
    RESET ROLE;
    RETURN jsonb_build_object('vai_tro', current_user);
END
$$;
GRANT EXECUTE ON FUNCTION thu_nghiem.doi_role(jsonb) TO workflow;

CREATE FUNCTION thu_nghiem.cham(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO thu_nghiem.lan_chay VALUES (bien ->> 'ma', 'cham');
    PERFORM pg_sleep((bien ->> 'cho')::float);
    RETURN jsonb_build_object('so_lan', (
        SELECT count(*) FROM thu_nghiem.lan_chay WHERE ma = bien ->> 'ma' AND ham = 'cham'
    ));
END
$$;
GRANT EXECUTE ON FUNCTION thu_nghiem.cham(jsonb) TO workflow;
