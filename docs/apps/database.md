<!-- SPDX-License-Identifier: Apache-2.0 -->
# Dữ liệu và API

## File SQL của ứng dụng

Mỗi ứng dụng có một schema và hai role trong cơ sở dữ liệu. Tên schema là tên ứng dụng với dấu gạch ngang đổi thành dấu gạch dưới, ví dụ `nghi_phep`. Role cùng tên sở hữu schema và chạy các file SQL. Role có thêm hậu tố `_user`, ví dụ `nghi_phep_user`, chạy các lời gọi API như mục [Gọi API của ứng dụng](#gọi-api-của-ứng-dụng). Lệnh cài đặt chạy các file `.sql` trong thư mục `database` của ứng dụng theo các quy tắc sau:

- File chạy theo thứ tự tên, bằng role sở hữu schema, không bằng superuser. Role này chỉ đăng nhập được trong lúc lệnh cài đặt chạy, với mật khẩu sinh mới mỗi lần.
- Schema của ứng dụng là `search_path` của file. Do đó, lệnh `CREATE TABLE don (...)` tạo bảng `nghi_phep.don`.
- Mỗi file chạy trong một transaction. Khi một câu lệnh bị lỗi, mọi thay đổi của file bị hủy. File không được dùng `BEGIN`, `COMMIT`, `ROLLBACK` hay `SAVEPOINT`.
- Bảng `core.migrations` ghi tên và mã băm của từng file đã chạy, với cột `scope` là tên ứng dụng. File đã chạy thì không chạy lại. File đã chạy mà bị sửa thì lệnh cài đặt dừng và báo lỗi. Để thay đổi cơ sở dữ liệu, hãy thêm một file mới.
- Role sở hữu schema không đọc được schema của ứng dụng khác và các bảng của lõi, ví dụ `core.audit_log`. Role này cũng không đổi được sang role khác bằng `SET ROLE`.
- Bảng, view và hàm mới chưa được cấp cho role nào, kể cả `PUBLIC`. File SQL cấp quyền cho role `nghi_phep_user` và `anon` bằng `GRANT`. Quyền `USAGE` trên schema đã được cấp sẵn cho role `nghi_phep_user` và role `workflow` của bước máy làm.
- Schema của ứng dụng chỉ được cấp quyền `USAGE` cho role `nghi_phep_user` và `anon`. File cấp quyền trên schema cho role khác, ví dụ `authenticated`, bị từ chối.
- Sau mỗi file, hàm không khai `SECURITY DEFINER` được đổi thành hàm `SECURITY DEFINER` của role `nghi_phep_user`. Quyền `EXECUTE` của hàm được giữ như file đã cấp. Do đó, hàm luôn chạy bằng role `nghi_phep_user`, kể cả khi lời gọi không có access token. Hàm khai `SECURITY DEFINER` chạy bằng role sở hữu schema.
- Bên trong hàm `SECURITY DEFINER`, PostgreSQL không cho đổi role. Hàm `set_config` cũng không được cấp cho mã của ứng dụng. Do đó, mã của một ứng dụng không chuyển được sang role của ứng dụng khác.
- Các lệnh DDL như `CREATE`, `ALTER`, `DROP` và `GRANT` chỉ chạy được trong file SQL khi cài đặt. Mã của ứng dụng chạy trong lúc phục vụ lời gọi không dùng được các lệnh này, kể cả `CREATE TEMP TABLE`.
- Role sở hữu schema dùng được hàm `core.audit()` để ghi audit log cho bảng và hàm `core.append_only()` để chặn sửa, xóa dòng của bảng.
- Hàm của ứng dụng gọi được `core.notify`, `core.publish` và `core.send_email` theo mục [Thông báo và kênh của ứng dụng](notifications.md#thông-báo-và-kênh-của-ứng-dụng).
- Các hàm `core.claims()`, `core.uid()`, `core.has_role()` và `core.unit()` chỉ đọc claims do PostgREST hoặc service `core` đặt cho lời gọi. Khi một hàm của ứng dụng đổi `request.jwt.claims` bằng `SET LOCAL`, các hàm này trả về `NULL`. Do đó, mã của một ứng dụng không mạo danh được người dùng khác.
- Trong chính sách RLS, viết `(SELECT core.uid())` thay cho `core.uid()`. Khi đó, PostgreSQL chỉ tính giá trị một lần cho mỗi câu truy vấn thay vì một lần cho mỗi dòng.

Khi cơ sở dữ liệu đã có role hoặc schema trùng tên mà không do SaigonOS tạo cho ứng dụng, lệnh cài đặt dừng và không đụng tới role hoặc schema đó.

Ví dụ file `database/0001_don.sql` tạo bảng đơn xin nghỉ phép. Mỗi người chỉ thấy đơn của mình:

```sql
CREATE TABLE don (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nguoi_gui text NOT NULL DEFAULT core.uid(),
    ly_do text NOT NULL
);
ALTER TABLE don ENABLE ROW LEVEL SECURITY;
CREATE POLICY cua_minh ON don USING (nguoi_gui = (SELECT core.uid()));
CREATE TRIGGER audit AFTER INSERT OR UPDATE OR DELETE ON don
    FOR EACH ROW EXECUTE FUNCTION core.audit();
GRANT SELECT, INSERT ON don TO nghi_phep_user;
```

## Gọi API của ứng dụng

Lệnh cài đặt tạo trên APISIX route `app-<tên ứng dụng>` cho API của ứng dụng. API nằm ở địa chỉ `/apps/<tên ứng dụng>/api/` của API Gateway, ví dụ `/apps/nghi-phep/api/don`. Route chuyển lời gọi tới PostgREST và tự đặt header `Accept-Profile` và `Content-Profile` là schema của ứng dụng. Header do ứng dụng gửi bị ghi đè, nên lời gọi qua địa chỉ này chỉ tới được schema của ứng dụng đó. Route kiểm tra access token khi lời gọi có header `Authorization` và giới hạn tần suất như địa chỉ `/api/`.

Lời gọi vào schema của một ứng dụng phải kèm access token được cấp cho client của ứng dụng đó, tức claim `azp` của access token là tên ứng dụng. Access token của client khác, kể cả của ứng dụng khác, nhận mã 403 với mã lỗi `SGN02`. Lời gọi có access token của ứng dụng chạy với role `<schema>_user` của ứng dụng đó, ví dụ `nghi_phep_user`. Role này có các quyền của role `authenticated` và các quyền do file SQL của ứng dụng cấp. Lời gọi không có access token vẫn chạy với role `anon`. Ví dụ:

```js
const headers = {
  Authorization: `Bearer ${accessToken}`,
  "Content-Type": "application/json",
};
await fetch("/apps/nghi-phep/api/don", {
  method: "POST",
  headers,
  body: JSON.stringify({ ly_do: "Việc gia đình" }),
});
const don = await (await fetch("/apps/nghi-phep/api/don", { headers })).json();
```

Tài liệu OpenAPI của ứng dụng nằm ở địa chỉ `/apps/<tên ứng dụng>/api/`. Tài liệu chỉ có bảng và hàm trong schema của ứng dụng, với `basePath` là địa chỉ API của ứng dụng.

Địa chỉ `/api/` chỉ phục vụ schema `api`. API Gateway ghi đè header `Accept-Profile` và `Content-Profile` của mọi lời gọi tới địa chỉ này thành `api`. Do đó, schema của ứng dụng chỉ gọi được qua địa chỉ của ứng dụng, và mọi lời gọi tới schema này đều đi qua luật truy cập của ứng dụng. Schema `api` nhận access token của mọi client.

Mỗi lần cài đặt, route được đặt lại theo bản khai, kể cả khi đã bị sửa trên Dashboard hay qua Admin API của APISIX. Route mang label `saigonos.app` có giá trị là tên ứng dụng. Khi APISIX đã có route `app-<tên ứng dụng>` mà không mang label này, lệnh cài đặt dừng trước khi thay đổi cơ sở dữ liệu và không đụng tới route đó.

Sau khi cài đặt, PostgREST nạp lại cấu hình và schema cache mà không khởi động lại. Việc này mất khoảng 1 giây.
