-- SPDX-License-Identifier: Apache-2.0
CREATE TABLE don (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    phong_id smallint NOT NULL REFERENCES phong (id),
    nguoi_gui text NOT NULL,
    ten_nguoi_gui text NOT NULL,
    lop text NOT NULL CHECK (lop = btrim(lop) AND length(lop) BETWEEN 1 AND 100),
    muc_dich text NOT NULL CHECK (muc_dich IN ('day_hoc', 'thi')),
    bat_dau timestamptz NOT NULL,
    ket_thuc timestamptz NOT NULL,
    so_may integer NOT NULL CHECK (so_may BETWEEN 1 AND 500),
    phan_mem text CHECK (length(phan_mem) <= 1000),
    ghi_chu text CHECK (length(ghi_chu) <= 1000),
    trang_thai text NOT NULL DEFAULT 'cho_duyet'
        CHECK (trang_thai IN ('cho_duyet', 'da_duyet', 'tu_choi', 'san_sang')),
    han_duyet timestamptz NOT NULL,
    y_kien text CHECK (length(y_kien) <= 1000),
    so_may_san_sang integer CHECK (so_may_san_sang BETWEEN 0 AND 500),
    ghi_chu_chuan_bi text CHECK (length(ghi_chu_chuan_bi) <= 1000),
    gui_luc timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT gio_hop_le CHECK (ket_thuc > bat_dau AND ket_thuc - bat_dau <= interval '12 hours'),
    CONSTRAINT tu_choi_co_y_kien CHECK (trang_thai <> 'tu_choi' OR y_kien IS NOT NULL),
    CONSTRAINT san_sang_co_so_may CHECK ((trang_thai = 'san_sang') = (so_may_san_sang IS NOT NULL)),
    CONSTRAINT khong_trung_lich EXCLUDE USING gist (
        int4range(phong_id, phong_id, '[]') WITH =,
        tstzrange(bat_dau, ket_thuc) WITH &&
    ) WHERE (trang_thai IN ('da_duyet', 'san_sang'))
);
CREATE INDEX don_nguoi_gui ON don (nguoi_gui);
CREATE INDEX don_bat_dau ON don (bat_dau);
ALTER TABLE don ENABLE ROW LEVEL SECURITY;
CREATE POLICY cua_minh ON don FOR SELECT USING (nguoi_gui = (SELECT core.uid()));
CREATE POLICY phu_trach_xem ON don FOR SELECT
    USING ((SELECT core.has_role('phong-may.phu-trach')));
CREATE POLICY chuyen_vien_xem ON don FOR SELECT
    USING ((SELECT core.has_role('phong-may.chuyen-vien')) AND trang_thai IN ('da_duyet', 'san_sang'));
CREATE TRIGGER audit AFTER INSERT OR UPDATE OR DELETE ON don
    FOR EACH ROW EXECUTE FUNCTION core.audit();
GRANT SELECT ON don TO phong_may_user;

CREATE VIEW lich WITH (security_barrier) AS
SELECT don.id, phong.ma AS ma_phong, phong.ten AS ten_phong, don.bat_dau, don.ket_thuc,
    don.lop, don.muc_dich, don.ten_nguoi_gui, don.trang_thai
FROM don
JOIN phong ON phong.id = don.phong_id
WHERE don.trang_thai IN ('da_duyet', 'san_sang');
GRANT SELECT ON lich TO phong_may_user;

CREATE FUNCTION mo_ta_gio(bat_dau timestamptz, ket_thuc timestamptz) RETURNS text
LANGUAGE sql STABLE
SET search_path = ''
RETURN CASE
    WHEN (bat_dau AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        = (ket_thuc AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        THEN 'từ ' || to_char(bat_dau AT TIME ZONE 'Asia/Ho_Chi_Minh', 'HH24:MI')
            || ' đến ' || to_char(ket_thuc AT TIME ZONE 'Asia/Ho_Chi_Minh', 'HH24:MI "ngày" DD/MM/YYYY')
    ELSE 'từ ' || to_char(bat_dau AT TIME ZONE 'Asia/Ho_Chi_Minh', 'HH24:MI "ngày" DD/MM/YYYY')
        || ' đến ' || to_char(ket_thuc AT TIME ZONE 'Asia/Ho_Chi_Minh', 'HH24:MI "ngày" DD/MM/YYYY')
END;

CREATE FUNCTION kiem_tra_don(ma_phong text, bat_dau timestamptz, ket_thuc timestamptz, so_may integer)
RETURNS text[]
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    loi text[] := ARRAY[]::text[];
    phong_chon phong_may.phong;
    trung phong_may.don;
BEGIN
    SELECT * INTO phong_chon FROM phong_may.phong WHERE phong.ma = kiem_tra_don.ma_phong;
    IF NOT FOUND THEN
        RETURN ARRAY[format('Không có phòng %s.', coalesce(kiem_tra_don.ma_phong, ''))];
    END IF;
    IF kiem_tra_don.bat_dau IS NULL OR kiem_tra_don.ket_thuc IS NULL OR kiem_tra_don.so_may IS NULL THEN
        RETURN ARRAY['Cần nhập đủ giờ bắt đầu, giờ kết thúc và số máy.'];
    END IF;
    IF kiem_tra_don.bat_dau <= now() THEN
        loi := array_append(loi, 'Giờ bắt đầu phải sau thời điểm hiện tại.');
    END IF;
    IF kiem_tra_don.ket_thuc <= kiem_tra_don.bat_dau THEN
        loi := array_append(loi, 'Giờ kết thúc phải sau giờ bắt đầu.');
    ELSIF kiem_tra_don.ket_thuc - kiem_tra_don.bat_dau > interval '12 hours' THEN
        loi := array_append(loi, 'Mỗi đơn dài tối đa 12 giờ.');
    ELSE
        SELECT * INTO trung FROM phong_may.don
        WHERE don.phong_id = phong_chon.id
            AND don.trang_thai IN ('da_duyet', 'san_sang')
            AND tstzrange(don.bat_dau, don.ket_thuc)
                && tstzrange(kiem_tra_don.bat_dau, kiem_tra_don.ket_thuc)
        ORDER BY don.bat_dau
        LIMIT 1;
        IF FOUND THEN
            loi := array_append(loi, format(
                '%s đã có lịch %s.', phong_chon.ten, phong_may.mo_ta_gio(trung.bat_dau, trung.ket_thuc)
            ));
        END IF;
    END IF;
    IF kiem_tra_don.so_may < 1 THEN
        loi := array_append(loi, 'Số máy cần phải từ 1 trở lên.');
    ELSIF kiem_tra_don.so_may > phong_chon.so_may THEN
        loi := array_append(loi, format(
            '%s chỉ có %s máy dùng được.', phong_chon.ten, phong_chon.so_may
        ));
    END IF;
    RETURN loi;
END
$$;
GRANT EXECUTE ON FUNCTION kiem_tra_don(text, timestamptz, timestamptz, integer) TO phong_may_user;
