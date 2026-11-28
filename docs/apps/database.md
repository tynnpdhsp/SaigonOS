<!-- SPDX-License-Identifier: Apache-2.0 -->
# Dữ liệu và API

Mỗi ứng dụng có một schema và hai role trong cơ sở dữ liệu. Tên schema là tên ứng dụng với dấu gạch ngang đổi thành dấu gạch dưới, ví dụ `phong_may`. Role cùng tên sở hữu schema và chạy các file SQL của ứng dụng. Role có thêm hậu tố `_user`, ví dụ `phong_may_user`, chạy các lời gọi API của ứng dụng.

## File SQL của ứng dụng

Lệnh cài đặt chạy các file `.sql` trong thư mục `database` của ứng dụng theo các quy tắc sau:

- File chạy theo thứ tự tên, bằng role sở hữu schema. Schema của ứng dụng là `search_path` của file. Do đó, lệnh `CREATE TABLE phong (...)` tạo bảng `phong_may.phong`.
- Mỗi file chạy trong một transaction. Khi một câu lệnh bị lỗi, mọi thay đổi của file bị hủy. File không được dùng `BEGIN`, `COMMIT`, `ROLLBACK` hay `SAVEPOINT`.
- File đã chạy thì không chạy lại. File đã chạy mà bị sửa thì lệnh cài đặt dừng và báo lỗi. Để thay đổi cơ sở dữ liệu, thêm một file mới.
- Bảng, view và hàm mới chưa được cấp cho role nào. File SQL cấp quyền cho role `phong_may_user` và role `anon` bằng `GRANT`. Quyền `USAGE` trên schema đã được cấp sẵn cho role `phong_may_user`. Role `anon` chỉ dùng được schema khi file SQL cấp thêm quyền này. File cấp quyền trên schema cho role khác bị từ chối.
- Hàm không khai `SECURITY DEFINER` được đổi thành hàm `SECURITY DEFINER` của role `phong_may_user`. Do đó, hàm luôn chạy bằng role này, kể cả khi lời gọi không có access token. Hàm khai `SECURITY DEFINER` chạy bằng role sở hữu schema.
- Mã của ứng dụng không đọc được schema của ứng dụng khác và các bảng của lõi, và không đổi được sang role khác.
- Các lệnh DDL như `CREATE`, `ALTER`, `DROP` và `GRANT` chỉ chạy được trong file SQL lúc cài đặt.
- Để mỗi người chỉ thấy và sửa được một số dòng của bảng, bật Row-Level Security (RLS) cho bảng rồi khai các chính sách (policy), như ví dụ ở cuối mục này.
- Trong chính sách RLS, viết `(SELECT core.uid())` thay cho `core.uid()`. Khi đó, PostgreSQL chỉ tính giá trị một lần cho mỗi câu truy vấn thay vì một lần cho mỗi dòng.

Mã của ứng dụng dùng được các hàm sau của lõi:

| Hàm | Ý nghĩa |
|---|---|
| `core.uid()` | Mã người gọi, tức claim `sub` của access token |
| `core.has_role(role)` | Người gọi có realm role `role` hay không |
| `core.unit()` | Claim `unit` của access token |
| `core.claims()` | Toàn bộ claims của access token, kiểu `jsonb` |
| `core.audit()` | Hàm trigger ghi [audit log](../admin/audit-log.md) cho bảng |
| `core.append_only()` | Hàm trigger chặn sửa và xóa dòng của bảng |
| `core.notify`, `core.send_email` | Gửi thông báo và email, như ở trang [Thông báo](notifications.md) |
| `core.publish` | Gửi tin tới một kênh, như ở trang [Cập nhật tức thời](realtime.md#gửi-tin-từ-cơ-sở-dữ-liệu) |

Bốn hàm đầu chỉ đọc claims do PostgREST hoặc service `core` đặt cho lời gọi. Khi mã của ứng dụng đổi `request.jwt.claims`, các hàm này trả về `NULL`. Do đó, mã của một ứng dụng không mạo danh được người dùng khác.

Ví dụ, file [`database/0001_phong.sql`](https://github.com/tynnpdhsp/SaigonOS/blob/main/examples/phong-may/database/0001_phong.sql) của ứng dụng mẫu tạo bảng phòng máy. Mọi người dùng của ứng dụng xem được các phòng. Chỉ phụ trách phòng sửa được số máy:

```sql
CREATE TABLE phong (
    id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma text NOT NULL UNIQUE CHECK (ma ~ '^[A-Z0-9][A-Z0-9.-]{0,19}$'),
    ten text NOT NULL CHECK (ten = btrim(ten) AND length(ten) BETWEEN 1 AND 100),
    so_may integer NOT NULL CHECK (so_may BETWEEN 0 AND 500)
);
ALTER TABLE phong ENABLE ROW LEVEL SECURITY;
CREATE POLICY moi_nguoi_xem ON phong FOR SELECT USING (true);
CREATE POLICY phu_trach_sua ON phong FOR UPDATE
    USING ((SELECT core.has_role('phong-may.phu-trach')))
    WITH CHECK ((SELECT core.has_role('phong-may.phu-trach')));
CREATE TRIGGER audit AFTER INSERT OR UPDATE OR DELETE ON phong
    FOR EACH ROW EXECUTE FUNCTION core.audit();
GRANT SELECT, UPDATE (so_may) ON phong TO phong_may_user;
```

## Gọi API của ứng dụng

API của ứng dụng nằm ở địa chỉ `/apps/<tên ứng dụng>/api/`, ví dụ `/apps/phong-may/api/phong`. Địa chỉ này chỉ tới được schema của ứng dụng. Lời gọi phải kèm access token do client của ứng dụng cấp, tức claim `azp` của access token là tên ứng dụng. Access token của client khác, kể cả của ứng dụng khác, nhận mã 403 với mã lỗi `SGN02`. Lời gọi có access token chạy bằng role `phong_may_user`. Role này có các quyền của role `authenticated` và các quyền do file SQL cấp. Lời gọi không có access token chạy bằng role `anon`.

API theo cú pháp của [PostgREST](https://docs.postgrest.org/), gồm bộ lọc, `select`, `order` và `limit`. Hàm của ứng dụng được gọi ở địa chỉ `rpc/<tên hàm>`. Ví dụ:

```js
const headers = { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" };
const rooms = await (await fetch("/apps/phong-may/api/phong?order=ma", { headers })).json();
await fetch("/apps/phong-may/api/phong?ma=eq.PM2", {
  method: "PATCH",
  headers,
  body: JSON.stringify({ so_may: 38 }),
});
```

Mỗi lời gọi chỉ được chạy trong một thời gian giới hạn, như ở trang [Tài liệu API](../reference/api.md#rest-api-của-dữ-liệu).

Tài liệu OpenAPI của ứng dụng nằm ở địa chỉ `/apps/<tên ứng dụng>/api/`. Tài liệu chỉ gồm các bảng và hàm trong schema của ứng dụng mà người gọi được dùng. Lời gọi tới địa chỉ này cũng đi qua [luật truy cập của ứng dụng](access-rules.md).
