<!-- SPDX-License-Identifier: Apache-2.0 -->
# Cơ sở dữ liệu

Cơ sở dữ liệu `saigonos` được cập nhật bằng các file SQL trong thư mục [`src/saigonos/stack/config/postgres/migrations`](https://github.com/tynnpdhsp/SaigonOS/tree/main/src/saigonos/stack/config/postgres/migrations). Mỗi lần hệ thống khởi động, service `migrate` chạy các file chưa chạy theo thứ tự tên. Bảng `core.migrations` ghi lại tên và mã băm SHA-256 của từng file đã chạy.

Mỗi thay đổi của cơ sở dữ liệu được viết thành một file mới theo các quy tắc sau:

- Tên file gồm số thứ tự tiếp theo với 4 chữ số, dấu gạch dưới và một mô tả ngắn viết bằng chữ thường không dấu. Ví dụ: [`0004_audit_log.sql`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/config/postgres/migrations/0004_audit_log.sql).
- Mỗi file chạy trong một transaction. Khi một câu lệnh bị lỗi, mọi thay đổi của file bị hủy. Do đó, file không được chứa `BEGIN`, `COMMIT` hoặc câu lệnh không chạy được trong transaction, ví dụ `CREATE INDEX CONCURRENTLY`.
- Không sửa hoặc xóa file đã được merge vào `main`. Service `migrate` dừng và báo lỗi khi nội dung của một file đã chạy bị thay đổi. Để sửa một thay đổi cũ, thêm một file mới.
- File [`init.sql`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/config/postgres/init.sql) chỉ chạy một lần khi cơ sở dữ liệu được tạo. Do đó, không thêm thay đổi mới vào file này.

Kiểm thử [`tests/test_migrations.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/tests/test_migrations.py) kiểm tra tên và số thứ tự của các file.

## Cấp quyền cho lời gọi API

Mỗi lời gọi API chạy với một trong hai role của cơ sở dữ liệu. Lời gọi có access token hợp lệ chạy với role `authenticated`. Lời gọi không có access token chạy với role `anon`. Bảng, view và hàm mới chưa được cấp cho role nào. Do đó, file SQL cấp quyền theo các quy tắc sau:

- Cấp quyền cho từng role bằng lệnh `GRANT`. Role `authenticated` không có sẵn các quyền của role `anon`. Bảng, view hoặc hàm dành cho mọi người cần được cấp cho cả hai role.
- Chỉ cấp cho role `anon` những gì người chưa đăng nhập được dùng.
- Không cấp quyền cho `PUBLIC`.

PostgreSQL không kiểm tra lại quyền `EXECUTE` của hàm khi dùng lại một query plan đã lập cho role khác. Do đó, hàm `core.pre_request()` xóa các query plan đã lưu trước mỗi lời gọi API và PostgREST không dùng prepared statement. Không bỏ hai thiết lập `PGRST_DB_PRE_REQUEST` và `PGRST_DB_PREPARED_STATEMENTS` trong file [`compose.yaml`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/compose.yaml). Kiểm thử `test_anon_cannot_reuse_query_plan_made_for_user` trong [`tests/integration/test_database.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/tests/integration/test_database.py) kiểm tra điều này.

Hàm `core.pre_request()` cũng chỉ chấp nhận access token. Lời gọi kèm token có claim `typ` khác `Bearer`, ví dụ ID token, nhận mã 401. Kiểm thử `test_api_accepts_access_token_only` trong cùng file kiểm tra việc này.

Khi lời gọi vào schema của một ứng dụng, hàm còn đòi claim `azp` của access token là tên ứng dụng. PostgREST đặt schema của lời gọi lên đầu `search_path`. Do đó, hàm `core.pre_request()` không có `SET search_path` riêng mà truyền giá trị này cho hàm `core.check_token(search_path)`. Hàm `core.check_token` có `SET search_path = ''`, nên hàm hay toán tử mà ứng dụng tạo trong schema của mình không thay được hàm hay toán tử mà phần kiểm tra dùng. Kiểm thử `test_schema_of_app_takes_only_access_token_of_its_client` trong [`tests/integration/test_apps.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/tests/integration/test_apps.py) kiểm tra việc này.

Trước hai việc kiểm tra trên, hàm `core.pre_request()` gọi `core.seal_claims()` để niêm phong claims của lời gọi. Hàm này ghi vào `saigonos.claims_seal` mã HMAC-SHA256 của claims, mã tiến trình và thời điểm bắt đầu transaction. Khóa nằm trong bảng `core.claims_key` mà chỉ superuser đọc được. Hàm `core.claims()` tính lại mã này và trả về `NULL` khi mã không khớp. Do đó, hàm của ứng dụng đổi `request.jwt.claims` thì `core.uid()` trả về `NULL`, và claims chép từ lời gọi trước không dùng lại được.

Hàm `core.seal_claims()` được cấp cho các role mà mã của ứng dụng cũng dùng, ví dụ `authenticated`. Do đó, hàm chỉ niêm phong khi câu lệnh đang chạy, tức giá trị của `current_query()`, đúng là câu lệnh PostgREST dùng để gọi `core.pre_request()` hoặc hằng số `SEAL_CLAIMS` của service `core`. Mã của ứng dụng chỉ chạy bên trong câu lệnh do PostgREST hay service `core` gửi tới, nên không tạo được câu lệnh này. Phiên của superuser cũng niêm phong được, để kiểm thử đặt claims bằng `psql`. Khi nâng phiên bản PostgREST, kiểm tra câu lệnh gọi hàm `db-pre-request` trong mã nguồn của PostgREST. Câu lệnh khác đi thì mọi lời gọi API báo lỗi. Service `core` gọi `SEAL_CLAIMS` ngay sau khi đặt claims trong `Database.session`, `Database.service_session` và bước máy làm. Kiểm thử `test_function_of_app_cannot_pass_itself_off_as_another_user` trong `tests/integration/test_apps.py` thử từng cách giả claims.

Khi cần sửa hàm `core.pre_request()`, viết lại toàn bộ hàm trong một file SQL mới và giữ cả bốn việc trên.

Tài liệu OpenAPI ở địa chỉ `/api/` cũng theo các quyền này. Bảng và view được liệt kê khi role có ít nhất một quyền trên bảng hoặc view đó. Hàm được liệt kê khi role có quyền `EXECUTE`. Với mỗi bảng hoặc view được liệt kê, tài liệu ghi mọi cột và mọi thao tác mà bảng hoặc view hỗ trợ, kể cả cột và thao tác chưa được cấp quyền. Do đó, để giấu một cột, tạo một view không có cột đó thay vì chỉ cấp quyền theo cột. Kiểm thử `test_api_document_lists_only_tables_and_functions_granted_to_caller` trong `tests/integration/test_database.py` so sánh tài liệu với quyền của từng role trong cơ sở dữ liệu.

View đọc bảng bằng quyền của role sở hữu view. Các file SQL được chạy bằng role `postgres`. Role này là superuser nên không bị RLS giới hạn. Do đó, view đọc một bảng có RLS cần thiết lập `security_invoker = true`. Với thiết lập này, view đọc bảng bằng quyền của người gọi và RLS của bảng được áp dụng. Role của người gọi khi đó cần quyền trên cả view và bảng. Để người gọi không đọc thẳng bảng qua API, đặt bảng ngoài schema `api`, vì PostgREST chỉ phục vụ schema `api`. Kiểm thử `test_view_with_security_invoker_masks_contacts_and_keeps_row_security` trong `tests/integration/test_database.py` kiểm tra cách làm này.

## Che dữ liệu cá nhân

Hàm `core.mask_phone()` và `core.mask_email()` che một phần số điện thoại và email:

| Hàm | Cách che | Ví dụ |
| --- | --- | --- |
| `core.mask_phone(phone)` | Giữ 3 ký tự đầu và 3 ký tự cuối. Phần giữa được thay bằng `****`. Khi giá trị có ít hơn 10 ký tự, mọi ký tự được thay bằng dấu `*` | `0912345678` thành `091****678` |
| `core.mask_email(email)` | Giữ nguyên phần từ dấu `@` cuối cùng. Phần trước dấu `@` giữ 3 ký tự đầu, mỗi ký tự còn lại được thay bằng một dấu `*`. Khi phần này có ít hơn 6 ký tự, mọi ký tự của phần này được thay bằng dấu `*` | `nguyenvana@gmail.com` thành `ngu*******@gmail.com` |

Hai hàm trả về `NULL` khi giá trị là `NULL`. Role `anon` và `authenticated` gọi được hai hàm này. Để chỉ hiện đủ dữ liệu cho người có quyền, dùng hai hàm trong view. Ví dụ, view sau chỉ hiện đủ số điện thoại và email cho người có realm role `quan-ly`:

```sql
GRANT USAGE ON SCHEMA app TO authenticated;
GRANT SELECT ON app.contacts TO authenticated;
CREATE VIEW api.contacts WITH (security_invoker = true) AS
SELECT id, name,
    CASE WHEN core.has_role('quan-ly') THEN phone ELSE core.mask_phone(phone) END AS phone,
    CASE WHEN core.has_role('quan-ly') THEN email ELSE core.mask_email(email) END AS email
FROM app.contacts;
GRANT SELECT ON api.contacts TO authenticated;
```

## Ghi audit log cho bảng

Bảng `core.audit_log` lưu audit log của cơ sở dữ liệu. Để ghi audit log cho một bảng, file SQL gắn hàm `core.audit()` vào bảng đó bằng một trigger. Ví dụ với bảng `api.notes`:

```sql
CREATE TRIGGER audit AFTER INSERT OR UPDATE OR DELETE ON api.notes
    FOR EACH ROW EXECUTE FUNCTION core.audit();
```

Sau đó, mỗi lần một dòng của bảng được thêm, sửa hoặc xóa, trigger ghi một dòng vào `core.audit_log` với các cột sau:

| Cột | Nội dung |
| --- | --- |
| `id` | Số thứ tự của dòng audit log. Số này tăng liên tục và không bỏ số nào |
| `occurred_at` | Thời điểm ghi audit log |
| `actor` | Mã người dùng trong access token, giống giá trị của `core.uid()`. Cột này trống khi thay đổi không đi qua API |
| `db_role` | Role của cơ sở dữ liệu đã thực hiện thay đổi, ví dụ `authenticated`, `anon` hoặc `postgres` |
| `table_schema`, `table_name` | Schema và tên của bảng có thay đổi |
| `operation` | Thao tác `INSERT`, `UPDATE` hoặc `DELETE` |
| `old_row`, `new_row` | Giá trị của dòng trước và sau thay đổi ở dạng JSON |
| `hash` | Mã băm SHA-256 của dòng audit log |

Hàm `core.audit_hash()` tính mã băm của một dòng từ mã băm của dòng trước và nội dung của dòng đó. Do đó, các dòng audit log nối thành một chuỗi. Khi một dòng audit log bị sửa hoặc bị xóa, chuỗi mã băm không còn khớp.

Bảng `core.audit_log` chỉ cho phép thêm dòng. Trigger `append_only` của bảng gọi hàm `core.append_only()` để từ chối các lệnh `UPDATE`, `DELETE` và `TRUNCATE`. Trigger được bật bằng `ENABLE ALWAYS` nên vẫn chạy khi `session_replication_role` là `replica`. Hàm `core.append_only()` cũng dùng được cho bảng khác bằng một trigger `BEFORE UPDATE OR DELETE OR TRUNCATE ... FOR EACH STATEMENT`.

Khi dùng audit log, cần tuân theo các quy tắc sau:

- Trigger phải chạy sau thao tác và chạy cho từng dòng (`AFTER ... FOR EACH ROW`). Với kiểu trigger khác, hàm `core.audit()` báo lỗi.
- Để các dòng audit log nối thành một chuỗi duy nhất, trigger giữ một khóa cho tới khi transaction kết thúc. Trong thời gian đó, các transaction khác phải chờ khi ghi vào bảng có audit log. Do đó, transaction ghi vào các bảng này cần kết thúc nhanh.
- Transaction ở mức `REPEATABLE READ` hoặc `SERIALIZABLE` có thể nhận lỗi trùng `id` khi một transaction khác vừa ghi audit log. Khi đó, cần chạy lại transaction.
- Không cấp quyền trên `core.audit_log` cho role `anon` và `authenticated`.
- Không thay đổi cách tính mã băm của các dòng đã ghi. Khi `core.audit_log` có thêm cột, hàm `core.audit_hash()` chỉ đưa cột mới vào mã băm khi cột đó có giá trị. Nhờ đó, mã băm của các dòng cũ vẫn khớp.
- Lệnh `saigonos audit verify` tính lại chuỗi mã băm bằng câu truy vấn trong [`src/saigonos/audit.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/audit.py) và không gọi hàm `core.audit_hash()`. Nhờ đó, kết quả kiểm tra không phụ thuộc hàm lưu trong cơ sở dữ liệu. Khi cách tính mã băm thay đổi, cần sửa cả hai nơi.

## Ghi sự đồng ý

Bảng `core.consents` ghi sự đồng ý của người dùng với một chính sách, ví dụ chính sách bảo vệ dữ liệu cá nhân. Mỗi lần người dùng đồng ý, ứng dụng thêm một dòng với các cột sau:

| Cột | Nội dung |
| --- | --- |
| `id` | Số thứ tự của dòng |
| `subject` | Mã của người đồng ý. Giá trị mặc định là `core.uid()`, tức mã người dùng trong access token |
| `policy` | Tên chính sách, ví dụ `du-lieu-ca-nhan` |
| `policy_version` | Phiên bản chính sách mà người dùng đã đồng ý |
| `given_at` | Thời điểm đồng ý. Giá trị mặc định là thời điểm bắt đầu transaction trên máy chủ |

Ba cột `subject`, `policy` và `policy_version` không được để trống. Bảng chỉ cho phép thêm dòng bằng trigger `append_only` như bảng `core.audit_log`. Bảng cũng có audit log. Do đó, mỗi lần đồng ý đều nằm trong chuỗi mã băm của audit log.

Role `anon` và `authenticated` không có quyền trên bảng này. Ứng dụng ghi sự đồng ý bằng một hàm `SECURITY DEFINER`. Ví dụ:

```sql
CREATE FUNCTION api.accept_policy(version text) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = ''
BEGIN ATOMIC
    INSERT INTO core.consents (policy, policy_version) VALUES ('du-lieu-ca-nhan', version);
END;
GRANT EXECUTE ON FUNCTION api.accept_policy TO authenticated;
```

Khi ghi sự đồng ý, cần tuân theo các quy tắc sau:

- Hàm `SECURITY DEFINER` chạy bằng quyền của role `postgres` và không bị RLS giới hạn. Do đó, hàm cần đặt `search_path` rỗng và không nhận `subject` từ tham số do người gọi gửi.
- Lời gọi không có access token không có `core.uid()`. Khi đó, hàm tự đặt `subject` từ dữ liệu của ứng dụng, ví dụ mã khách hàng mà hàm vừa tạo.
- `subject` là một mã, không phải họ tên, số điện thoại hay email. Bảng chỉ cho phép thêm dòng, nên dữ liệu trong bảng không xóa được khi người dùng yêu cầu xóa dữ liệu cá nhân.
- Ghi sự đồng ý trong cùng transaction với dữ liệu mà người dùng gửi. Nhờ đó, dữ liệu và sự đồng ý cùng được lưu hoặc cùng bị hủy.
- Không lấy thời điểm đồng ý từ trình duyệt. Cột `given_at` dùng giá trị mặc định do máy chủ ghi.

## Số kết nối

PostgreSQL nhận tối đa 100 kết nối, đặt bằng tham số `max_connections` trong `compose.yaml`. Khi gần hết, 3 kết nối cuối chỉ dành cho superuser. Mỗi role đăng nhập của một service có giới hạn số kết nối riêng, đặt trong file [`0029_connection_limits.sql`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/config/postgres/migrations/0029_connection_limits.sql). Service mở quá giới hạn của role nhận lỗi `too many connections for role`, còn các service khác vẫn kết nối được.

| Service | Role | Số kết nối tối đa của service | Giới hạn của role |
|---|---|---|---|
| Keycloak | `keycloak` | 20, đặt bằng `KC_DB_POOL_MAX_SIZE` | 25 |
| PostgREST | `authenticator` | 10, đặt bằng `PGRST_DB_POOL`, thêm 1 kết nối LISTEN và 1 kết nối của service `jwks` | 15 |
| Operaton | `operaton` | 10, đặt bằng `hikari.maximum-pool-size` trong `config/operaton/production.yml` | 15 |
| Core API | `core_service` | 10, đặt bằng `POOL_SIZE` trong `saigonos_core/database.py`, thêm 1 kết nối LISTEN và 1 kết nối của lệnh `saigonos lake` | 15 |
| Centrifugo | `centrifugo` | 4, đặt bằng `pool_max_conns` trong DSN | 6 |

Tổng giới hạn của các role là 76. Phần còn lại dành cho superuser và role tạm của ứng dụng khi chạy `saigonos apply`. Khi đổi số kết nối của một service, sửa cả giới hạn của role bằng một migration mới. Kiểm thử `test_connection_pools_fit_limits_of_roles_and_max_connections` trong [`tests/test_compose_file.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/tests/test_compose_file.py) kiểm tra mỗi service mở ít kết nối hơn giới hạn của role, và tổng giới hạn còn chỗ cho superuser.

Role `authenticator` có `statement_timeout` 15 giây, nên mỗi lời gọi REST API chạy tối đa 15 giây. Role `core_service` không có giới hạn chung này và không có `idle_in_transaction_session_timeout`, vì hồ dữ liệu ghi file Parquet lên SeaweedFS trong một transaction dài. Hàm của bước máy làm vẫn có giới hạn riêng 20 giây.