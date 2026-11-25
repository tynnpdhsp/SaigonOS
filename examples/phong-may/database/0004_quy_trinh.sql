-- SPDX-License-Identifier: Apache-2.0
CREATE FUNCTION ghi_don(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    gio_bat_dau timestamptz := (bien ->> 'bat_dau')::timestamptz;
    gio_ket_thuc timestamptz := (bien ->> 'ket_thuc')::timestamptz;
    so_may_can integer := (bien ->> 'so_may')::integer;
    loi text[];
    ban_ghi phong_may.don;
BEGIN
    loi := phong_may.kiem_tra_don(bien ->> 'ma_phong', gio_bat_dau, gio_ket_thuc, so_may_can);
    IF cardinality(loi) > 0 THEN
        PERFORM core.notify(
            recipient => bien ->> 'initiator',
            dedup_key => 'don-chua-ghi:' || gen_random_uuid(),
            title => 'Đơn đặt phòng chưa được ghi',
            body => array_to_string(loi, ' '),
            link => '/apps/phong-may/'
        );
        RETURN jsonb_build_object('hop_le', false);
    END IF;
    INSERT INTO phong_may.don (
        phong_id, nguoi_gui, ten_nguoi_gui, lop, muc_dich, bat_dau, ket_thuc, so_may,
        phan_mem, ghi_chu, han_duyet
    )
    SELECT
        phong.id,
        bien ->> 'initiator',
        coalesce(
            (SELECT nguoi_dung.ho_ten FROM phong_may.nguoi_dung
             WHERE nguoi_dung.ma = bien ->> 'initiator'),
            'Chưa rõ tên'
        ),
        btrim(bien ->> 'lop'),
        bien ->> 'muc_dich',
        gio_bat_dau,
        gio_ket_thuc,
        so_may_can,
        nullif(btrim(bien ->> 'phan_mem'), ''),
        nullif(btrim(bien ->> 'ghi_chu'), ''),
        date_trunc('second', least(now() + interval '24 hours', gio_bat_dau - interval '2 hours'))
    FROM phong_may.phong
    WHERE phong.ma = bien ->> 'ma_phong'
    RETURNING * INTO ban_ghi;
    RETURN jsonb_build_object(
        'hop_le', true,
        'ma_don', ban_ghi.id,
        'han_duyet', to_char(ban_ghi.han_duyet AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
    );
END
$$;
GRANT EXECUTE ON FUNCTION ghi_don(jsonb) TO workflow;

CREATE FUNCTION nhac_duyet(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    ban_ghi record;
BEGIN
    SELECT don.id, don.trang_thai, don.lop, don.bat_dau, don.ket_thuc, phong.ten AS ten_phong
    INTO ban_ghi
    FROM phong_may.don
    JOIN phong_may.phong ON phong.id = don.phong_id
    WHERE don.id = (bien ->> 'ma_don')::bigint;
    IF ban_ghi.trang_thai = 'cho_duyet' THEN
        PERFORM phong_may.bao_vai(
            'phong-may.phu-trach',
            'don:' || ban_ghi.id || ':nhac-duyet',
            format('Đơn đặt phòng số %s đã tới hạn duyệt', ban_ghi.id),
            format(
                '%s, %s. Lớp hoặc học phần: %s.',
                ban_ghi.ten_phong, phong_may.mo_ta_gio(ban_ghi.bat_dau, ban_ghi.ket_thuc), ban_ghi.lop
            ),
            '/apps/phong-may/?don=' || ban_ghi.id,
            true
        );
    END IF;
    RETURN NULL;
END
$$;
GRANT EXECUTE ON FUNCTION nhac_duyet(jsonb) TO workflow;

CREATE FUNCTION ghi_ket_qua(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    ma bigint := (bien ->> 'ma_don')::bigint;
    y_kien_nhap text := nullif(btrim(bien ->> 'y_kien'), '');
    duoc_duyet boolean := bien ->> 'ket_qua' = 'dong_y';
    ban_ghi phong_may.don;
    ten_phong text;
BEGIN
    IF duoc_duyet THEN
        BEGIN
            UPDATE phong_may.don SET trang_thai = 'da_duyet', y_kien = y_kien_nhap
            WHERE don.id = ma AND don.trang_thai = 'cho_duyet'
            RETURNING * INTO ban_ghi;
        EXCEPTION WHEN exclusion_violation THEN
            duoc_duyet := false;
            y_kien_nhap := 'Phòng đã có lịch trùng giờ với một đơn khác vừa được duyệt.';
        END;
    END IF;
    IF NOT duoc_duyet THEN
        UPDATE phong_may.don SET trang_thai = 'tu_choi', y_kien = coalesce(y_kien_nhap, 'Không ghi lý do.')
        WHERE don.id = ma AND don.trang_thai = 'cho_duyet'
        RETURNING * INTO ban_ghi;
    END IF;
    IF ban_ghi.id IS NULL THEN
        RAISE EXCEPTION 'Đơn % không ở trạng thái chờ duyệt', ma;
    END IF;
    SELECT phong.ten INTO ten_phong FROM phong_may.phong WHERE phong.id = ban_ghi.phong_id;
    PERFORM core.notify(
        recipient => ban_ghi.nguoi_gui,
        dedup_key => 'don:' || ban_ghi.id || ':ket-qua',
        title => format(
            'Đơn đặt phòng số %s %s',
            ban_ghi.id,
            CASE WHEN duoc_duyet THEN 'đã được duyệt' ELSE 'bị từ chối' END
        ),
        body => format('%s, %s.', ten_phong, phong_may.mo_ta_gio(ban_ghi.bat_dau, ban_ghi.ket_thuc))
            || coalesce(' Ý kiến: ' || ban_ghi.y_kien, ''),
        link => '/apps/phong-may/?don=' || ban_ghi.id
    );
    IF duoc_duyet THEN
        PERFORM phong_may.bao_vai(
            'phong-may.chuyen-vien',
            'don:' || ban_ghi.id || ':chuan-bi',
            format('Cần chuẩn bị %s cho đơn số %s', ten_phong, ban_ghi.id),
            format(
                'Thời gian %s. Cần %s máy.',
                phong_may.mo_ta_gio(ban_ghi.bat_dau, ban_ghi.ket_thuc), ban_ghi.so_may
            ) || coalesce(' Phần mềm cần cài: ' || ban_ghi.phan_mem, ''),
            '/apps/phong-may/?don=' || ban_ghi.id,
            false
        );
    END IF;
    RETURN jsonb_build_object('da_duyet', duoc_duyet);
END
$$;
GRANT EXECUTE ON FUNCTION ghi_ket_qua(jsonb) TO workflow;

CREATE FUNCTION ghi_san_sang(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    ban_ghi phong_may.don;
    ten_phong text;
BEGIN
    UPDATE phong_may.don
    SET trang_thai = 'san_sang',
        so_may_san_sang = (bien ->> 'so_may_san_sang')::integer,
        ghi_chu_chuan_bi = nullif(btrim(bien ->> 'ghi_chu_chuan_bi'), '')
    WHERE don.id = (bien ->> 'ma_don')::bigint AND don.trang_thai = 'da_duyet'
    RETURNING * INTO ban_ghi;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Đơn % không ở trạng thái đã duyệt', bien ->> 'ma_don';
    END IF;
    SELECT phong.ten INTO ten_phong FROM phong_may.phong WHERE phong.id = ban_ghi.phong_id;
    PERFORM core.notify(
        recipient => ban_ghi.nguoi_gui,
        dedup_key => 'don:' || ban_ghi.id || ':san-sang',
        title => format('%s đã sẵn sàng cho đơn số %s', ten_phong, ban_ghi.id),
        body => format('Có %s máy sẵn sàng, đơn cần %s máy.', ban_ghi.so_may_san_sang, ban_ghi.so_may)
            || coalesce(' Ghi chú: ' || ban_ghi.ghi_chu_chuan_bi, ''),
        link => '/apps/phong-may/?don=' || ban_ghi.id
    );
    RETURN NULL;
END
$$;
GRANT EXECUTE ON FUNCTION ghi_san_sang(jsonb) TO workflow;
