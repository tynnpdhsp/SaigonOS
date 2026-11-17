<!-- SPDX-License-Identifier: Apache-2.0 -->
# Đóng góp cho SaigonOS

Cảm ơn bạn đã quan tâm đến SaigonOS. Mọi đóng góp được tiếp nhận qua issue và pull request trên GitHub.

## Báo lỗi và đề xuất

Để báo lỗi hoặc đề xuất tính năng, hãy mở một [issue](https://github.com/tynnpdhsp/SaigonOS/issues/new/choose) và chọn mẫu phù hợp. Riêng lỗ hổng bảo mật thì không báo qua issue mà làm theo hướng dẫn trong [SECURITY.md](SECURITY.md).

## Chuẩn bị môi trường

Yêu cầu Python 3.11 trở lên, Git và make.

```bash
git clone https://github.com/tynnpdhsp/SaigonOS.git
cd SaigonOS
conda create -n saigonos python=3.12
conda activate saigonos
pip install -r requirements-dev.txt
pip install --no-deps -e .
```

## Kiểm tra trước khi commit

```bash
make check
```

Lệnh này thực hiện các bước sau:

- Kiểm tra thông tin giấy phép của mọi file bằng `reuse lint`.
- Kiểm tra lỗi và định dạng mã bằng `ruff`.
- Đối chiếu [DEPENDENCIES.md](DEPENDENCIES.md) với các lock file, file `compose.yaml` và `Dockerfile` của service `core`.
- Chạy kiểm thử bằng `pytest` và đo coverage.

Để tự động sửa định dạng mã, chạy `make format`.

## Kiểm thử tích hợp

Kiểm thử tích hợp chạy cả bộ Docker Compose trên máy, do đó cần Docker đang hoạt động. Ở lần chạy đầu tiên, Docker tải các image với tổng dung lượng khoảng 2 GB. Mỗi nhóm kiểm thử dựng một bộ riêng và cần khoảng 2 GB RAM.

```bash
make integration
```

Lệnh này chạy sáu nhóm kiểm thử trong thư mục `tests/integration`. File `test_stack.py` dùng cấu hình mặc định. File `test_database.py` kiểm tra cơ sở dữ liệu, ví dụ service `migrate`, phân quyền từng dòng, role `anon` và audit log, với cấu hình mặc định. File `test_storage.py` kiểm tra SeaweedFS và ClamAV với cấu hình mặc định. File `test_core.py` kiểm tra service `core`, ví dụ access token giả, access token hết hạn và việc đổi khóa ký. File `test_files.py` kiểm tra việc khai báo file, gửi nội dung, quét mã độc, chuyển file sạch sang bucket `clean` và tải file về. File `test_caddy.py` bật Caddy với chứng chỉ do Caddy tự cấp. Với mỗi nhóm, lệnh thực hiện các bước sau:

- Tạo một thư mục làm việc tạm bằng `saigonos init` với các cổng còn trống.
- Khởi động hệ thống bằng `saigonos up`.
- Chạy các kiểm thử của nhóm.
- Xóa container và dữ liệu bằng `saigonos down --volumes`, sau đó xóa image của service `core` vừa build.

SeaweedFS không mở cổng S3 ra máy cài đặt và nằm trong mạng Docker `storage` riêng. Do đó, nhóm kiểm thử SeaweedFS gọi S3 từ một container tạm gắn vào mạng này. Tương tự, ClamAV nằm trong mạng Docker `scan` riêng. Kiểm thử gửi file tới ClamAV từ một container tạm gắn vào mạng `scan`. Kiểm thử dùng file EICAR làm mẫu mã độc. Đây là một file thử nghiệm vô hại mà mọi phần mềm diệt virus đều nhận ra.

Kiểm thử `test_only_one_of_concurrent_uploads_is_kept` trong `test_files.py` gửi nội dung của cùng một file bằng nhiều lời gọi cùng lúc. Trong lúc đó, kiểm thử tạm dừng SeaweedFS bằng `docker compose pause`. Lời gọi đầu tiên phải chờ ở bước ghi nội dung, nên các lời gọi còn lại chắc chắn chạy chồng lên nó.

Kiểm thử `test_file_waits_while_clamav_is_down_and_is_scanned_after_restart` trong `test_files.py` dừng ClamAV, gửi nội dung của một file, rồi khởi động lại service `core`. File phải chờ ở trạng thái `pending_scan` và chỉ được quét sau khi ClamAV chạy lại.

Kiểm thử `test_file_not_scanned_yet_cannot_be_downloaded` trong `test_files.py` tạm dừng ClamAV bằng `docker compose pause` để giữ file ở trạng thái `pending_scan`. Một số kiểm thử tải file về tự ký đường dẫn bằng khóa `CORE_DOWNLOAD_KEY` trong file `.env`. Nhờ đó, kiểm thử đường dẫn hết hạn không phải chờ 60 giây.

Nhóm kiểm thử Caddy tạo thêm hai mạng Docker tạm với dải địa chỉ `192.0.2.0/28` và `2001:db8:5a1:9::/64`. Lời gọi từ hai mạng này giả lập máy gọi từ Internet qua IPv4 và IPv6. Do đó, máy chạy kiểm thử cần hỗ trợ IPv6.

Một lượt chạy mất khoảng 11 phút. Lệnh `make check` không chạy các kiểm thử này. CI chạy chúng ở job `integration` của mỗi pull request.

## Quy ước

- Mỗi file mới phải bắt đầu bằng một dòng `SPDX-License-Identifier` với giá trị `Apache-2.0`. Dòng này được viết dưới dạng comment theo cú pháp của loại file đó.
- Tính năng mới phải có kiểm thử đi kèm.
- Mỗi commit message chỉ gồm một dòng theo quy ước [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/). Ví dụ: `feat(cli): thêm lệnh doctor`.
- Mỗi thay đổi được thực hiện trên một branch riêng, sau đó mở pull request vào `main`. Pull request chỉ được merge khi CI chạy thành công.
- Những thay đổi ảnh hưởng đến người dùng được ghi vào mục "Chưa phát hành" của [CHANGELOG.md](CHANGELOG.md).

## Thêm thư viện

Chỉ sử dụng thư viện có giấy phép nguồn mở được OSI công nhận. Không sao chép mã nguồn của dự án khác vào repo.

1. Khai báo thư viện trong `pyproject.toml`. Thư viện của lệnh `saigonos` nằm trong `dependencies`. Thư viện của service `core` nằm trong nhóm `core` của `[dependency-groups]`.
2. Thêm một mô tả ngắn cho thư viện vào `DESCRIPTIONS` trong `scripts/dependencies.py`.
3. Chạy `make lock` để tạo lại các lock file.
4. Chạy `pip install -r requirements-dev.txt` để cài đặt đúng các phiên bản trong lock file.
5. Chạy `make dependencies` để tạo lại [DEPENDENCIES.md](DEPENDENCIES.md).

Ở bước 5, lệnh sẽ báo lỗi "Giấy phép ngoài danh sách cho phép" nếu giấy phép của thư viện chưa có trong danh sách cho phép ở `scripts/dependencies.py`. Khi đó, hãy mở một issue để thảo luận trước khi thêm thư viện.

## Thêm hoặc đổi phiên bản image Docker

Chỉ sử dụng phần mềm có giấy phép nguồn mở được OSI công nhận. Mỗi image phải ghi rõ phiên bản và không dùng tag `latest`.

1. Sửa dòng `image` trong `src/saigonos/stack/compose.yaml`. Với base image của service `core`, sửa dòng `FROM` trong `src/saigonos/stack/core/Dockerfile`, gồm cả tag và digest.
2. Đọc file giấy phép trong mã nguồn của đúng phiên bản đó.
3. Khai báo image trong `IMAGES` ở `scripts/dependencies.py`. Mỗi image cần giấy phép, mô tả và địa chỉ mã nguồn của phiên bản đó.
4. Chạy `make dependencies` để tạo lại [DEPENDENCIES.md](DEPENDENCIES.md).

Lệnh `make lint` báo lỗi khi một image trong `compose.yaml` chưa được khai báo. Giấy phép chưa có trong danh sách cho phép cũng bị báo lỗi. Khi đó, hãy mở một issue để thảo luận trước khi thêm image.

## Thay đổi cơ sở dữ liệu

Cơ sở dữ liệu `saigonos` được cập nhật bằng các file SQL trong thư mục `src/saigonos/stack/config/postgres/migrations`. Mỗi lần hệ thống khởi động, service `migrate` chạy các file chưa chạy theo thứ tự tên. Bảng `core.migrations` ghi lại tên và mã băm SHA-256 của từng file đã chạy.

Mỗi thay đổi của cơ sở dữ liệu được viết thành một file mới theo các quy tắc sau:

- Tên file gồm số thứ tự tiếp theo với 4 chữ số, dấu gạch dưới và một mô tả ngắn viết bằng chữ thường không dấu. Ví dụ: `0004_audit_log.sql`.
- Mỗi file chạy trong một transaction. Khi một câu lệnh bị lỗi, mọi thay đổi của file bị hủy. Do đó, file không được chứa `BEGIN`, `COMMIT` hoặc câu lệnh không chạy được trong transaction, ví dụ `CREATE INDEX CONCURRENTLY`.
- Không sửa hoặc xóa file đã được merge vào `main`. Service `migrate` dừng và báo lỗi khi nội dung của một file đã chạy bị thay đổi. Để sửa một thay đổi cũ, hãy thêm một file mới.
- File `init.sql` chỉ chạy một lần khi cơ sở dữ liệu được tạo. Do đó, không thêm thay đổi mới vào file này.

Kiểm thử `tests/test_migrations.py` kiểm tra tên và số thứ tự của các file.

### Cấp quyền cho lời gọi API

Mỗi lời gọi API chạy với một trong hai role của cơ sở dữ liệu. Lời gọi có access token hợp lệ chạy với role `authenticated`. Lời gọi không có access token chạy với role `anon`. Bảng, view và hàm mới chưa được cấp cho role nào. Do đó, file SQL cấp quyền theo các quy tắc sau:

- Cấp quyền cho từng role bằng lệnh `GRANT`. Role `authenticated` không có sẵn các quyền của role `anon`. Bảng, view hoặc hàm dành cho mọi người cần được cấp cho cả hai role.
- Chỉ cấp cho role `anon` những gì người chưa đăng nhập được dùng.
- Không cấp quyền cho `PUBLIC`.

PostgreSQL không kiểm tra lại quyền `EXECUTE` của hàm khi dùng lại một query plan đã lập cho role khác. Do đó, hàm `core.pre_request()` xóa các query plan đã lưu trước mỗi lời gọi API và PostgREST không dùng prepared statement. Không bỏ hai thiết lập `PGRST_DB_PRE_REQUEST` và `PGRST_DB_PREPARED_STATEMENTS` trong file `compose.yaml`. Kiểm thử `test_anon_cannot_reuse_query_plan_made_for_user` trong `tests/integration/test_database.py` kiểm tra điều này.

Hàm `core.pre_request()` cũng chỉ chấp nhận access token. Lời gọi kèm token có claim `typ` khác `Bearer`, ví dụ ID token, nhận mã 401. Khi cần sửa hàm này, viết lại toàn bộ hàm trong một file SQL mới và giữ cả hai việc trên. Kiểm thử `test_api_accepts_access_token_only` trong cùng file kiểm tra việc này.

Tài liệu OpenAPI ở địa chỉ `/api/` cũng theo các quyền này. Bảng và view được liệt kê khi role có ít nhất một quyền trên bảng hoặc view đó. Hàm được liệt kê khi role có quyền `EXECUTE`. Với mỗi bảng hoặc view được liệt kê, tài liệu ghi mọi cột và mọi thao tác mà bảng hoặc view hỗ trợ, kể cả cột và thao tác chưa được cấp quyền. Do đó, để giấu một cột, hãy tạo một view không có cột đó thay vì chỉ cấp quyền theo cột. Kiểm thử `test_api_document_lists_only_tables_and_functions_granted_to_caller` trong `tests/integration/test_database.py` so sánh tài liệu với quyền của từng role trong cơ sở dữ liệu.

View đọc bảng bằng quyền của role sở hữu view. Các file SQL được chạy bằng role `postgres`. Role này là superuser nên không bị RLS giới hạn. Do đó, view đọc một bảng có RLS cần thiết lập `security_invoker = true`. Với thiết lập này, view đọc bảng bằng quyền của người gọi và RLS của bảng được áp dụng. Role của người gọi khi đó cần quyền trên cả view và bảng. Để người gọi không đọc thẳng bảng qua API, hãy đặt bảng ngoài schema `api`, vì PostgREST chỉ phục vụ schema `api`. Kiểm thử `test_view_with_security_invoker_masks_contacts_and_keeps_row_security` trong `tests/integration/test_database.py` kiểm tra cách làm này.

### Che dữ liệu cá nhân

Hàm `core.mask_phone()` và `core.mask_email()` che một phần số điện thoại và email:

| Hàm | Cách che | Ví dụ |
| --- | --- | --- |
| `core.mask_phone(phone)` | Giữ 3 ký tự đầu và 3 ký tự cuối. Phần giữa được thay bằng `****`. Khi giá trị có ít hơn 10 ký tự, mọi ký tự được thay bằng dấu `*` | `0912345678` thành `091****678` |
| `core.mask_email(email)` | Giữ nguyên phần từ dấu `@` cuối cùng. Phần trước dấu `@` giữ 3 ký tự đầu, mỗi ký tự còn lại được thay bằng một dấu `*`. Khi phần này có ít hơn 6 ký tự, mọi ký tự của phần này được thay bằng dấu `*` | `nguyenvana@gmail.com` thành `ngu*******@gmail.com` |

Hai hàm trả về `NULL` khi giá trị là `NULL`. Role `anon` và `authenticated` gọi được hai hàm này. Để chỉ hiện đủ dữ liệu cho người có quyền, hãy dùng hai hàm trong view. Ví dụ, view sau chỉ hiện đủ số điện thoại và email cho người có realm role `quan-ly`:

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

### Ghi audit log cho bảng

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
- Lệnh `saigonos audit verify` tính lại chuỗi mã băm bằng câu truy vấn trong `src/saigonos/audit.py` và không gọi hàm `core.audit_hash()`. Nhờ đó, kết quả kiểm tra không phụ thuộc hàm lưu trong cơ sở dữ liệu. Khi cách tính mã băm thay đổi, cần sửa cả hai nơi.

Kiểm thử `test_audit_chain_stays_unbroken_when_many_connections_write_at_once` trong `tests/integration/test_database.py` tính lại cả chuỗi mã băm sau khi nhiều kết nối ghi cùng lúc. Các kiểm thử `test_audit_verify_points_at_*` trong cùng file dùng quyền superuser để sửa tay audit log, sau đó kiểm tra lệnh `saigonos audit verify` chỉ ra đúng dòng sai.

### Ghi sự đồng ý

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

Các kiểm thử `test_consent_*` và `test_consents_*` trong `tests/integration/test_database.py` kiểm tra các quy tắc của bảng.

## Thay đổi realm của Keycloak

Keycloak chỉ đọc file `src/saigonos/stack/config/keycloak/realm.json` một lần khi tạo realm `saigonos`. Do đó, không thêm thiết lập mới vào file này.

Thiết lập mới của realm được thêm vào script `setup-realm.lua` trong cùng thư mục. Mỗi lần hệ thống khởi động, service `realm` chạy script này và gọi Admin REST API của Keycloak. Script tuân theo các quy tắc sau:

- Chỉ thêm thiết lập còn thiếu. Khi thiết lập đã có, script không ghi đè, vì quản trị viên có thể đã sửa thiết lập đó.
- Chạy lại nhiều lần vẫn cho cùng một kết quả.
- In một dòng cho mỗi thiết lập vừa thêm.

Mỗi thiết lập mới cần một kiểm thử tích hợp. Kiểm thử xóa thiết lập khỏi realm, chạy `saigonos up` rồi kiểm tra thiết lập đã được thêm lại. Cách này giả lập một realm được tạo từ phiên bản cũ.

Script cũng cập nhật realm master. Keycloak tự tạo realm này khi khởi động lần đầu, nên mọi thiết lập của realm master đều nằm trong script. Riêng Frontend URL của realm master luôn được đặt theo giá trị `SAIGONOS_KEYCLOAK_PORT` trong file `.env`, kể cả khi quản trị viên đã sửa giá trị này. Sau khi đổi Frontend URL, script đăng nhập lại. Access token cũ mang địa chỉ cũ trong claim `iss` nên bị Keycloak từ chối.

API Gateway chặn mọi địa chỉ của realm master. Do đó, kiểm thử tích hợp gọi Admin REST API của Keycloak qua cổng `SAIGONOS_KEYCLOAK_PORT`, ví dụ bằng hàm `Stack.admin()` trong `tests/integration/conftest.py`.

## Service core

Mã nguồn của service `core` nằm trong thư mục `src/saigonos/stack/core`. Lệnh `saigonos init` sao chép thư mục này vào thư mục làm việc. Docker Compose build image của service từ file `Dockerfile` trong thư mục đó.

Khi sửa service `core`, cần tuân theo các quy tắc sau:

- Thư viện của service được khai báo trong nhóm `core` của `pyproject.toml`. Lệnh `make lock` tạo lock file `src/saigonos/stack/core/requirements.txt` cho Python 3.14, kèm mã băm của từng file. Không sửa tay lock file này.
- Mọi truy vấn tới cơ sở dữ liệu chạy trong `Database.session(caller)` hoặc `Database.service_session(caller)`. Hai hàm này mở một transaction và xóa các query plan đã lưu. Hàm `session` đặt thêm role và nội dung access token của người gọi. Việc không có người gọi, ví dụ quét file và gửi file qua đường dẫn tải về, chạy trong `Database.transaction()`. Không truy vấn bằng kết nối lấy thẳng từ pool.
- API dành cho người đã đăng nhập nhận tham số kiểu `User`. Khi đó, lời gọi không có access token hợp lệ của người dùng có realm role `authenticated` nhận mã 401.
- Không bật Swagger UI và ReDoc của FastAPI, vì hai trang này tải script từ máy chủ bên ngoài.
- Đường dẫn của API không có dấu `/` ở cuối. Service không chuyển hướng địa chỉ có dấu `/` ở cuối, vì API Gateway bỏ tiền tố `/core` trước khi chuyển lời gọi tới service. Địa chỉ chuyển hướng khi đó thiếu tiền tố này.
- Nội dung của file chỉ đi qua service `core`. Không thêm route tới SeaweedFS hoặc ClamAV ở API Gateway.
- Bảng `core.files` chỉ được ghi trong `Database.service_session(caller)`. Phiên này chạy bằng role `core_service` và mang nội dung access token của người gọi. Nhờ đó, audit log ghi đúng người gọi. Lời gọi đọc thông tin file chạy trong `Database.session(caller)` để chính sách phân quyền từng dòng được áp dụng.
- Danh sách loại file được phép nằm trong `KINDS` ở `saigonos_core/kinds.py`. Mỗi loại gồm các phần mở rộng và mẫu của phần đầu nội dung. Khi thêm một loại, cần thêm mẫu nội dung vào `tests/core/test_kinds.py` và thêm một dòng vào bảng loại file trong README. Kiểm thử `test_readme_lists_every_allowed_file_type` so sánh bảng này với `KINDS`.
- Lời gọi S3 được ký bằng SigV4 trong `saigonos_core/storage.py`. Header `x-amz-content-sha256` mang mã băm SHA-256 của nội dung. SeaweedFS từ chối nội dung không khớp mã băm này.
- Việc quét mã độc nằm trong `saigonos_core/scans.py`. Bảng `core.files` là hàng đợi quét. Mỗi lần quét lấy một file ở trạng thái `pending_scan` bằng `FOR UPDATE SKIP LOCKED`. Không giữ danh sách file chờ quét trong bộ nhớ của service, vì danh sách này mất khi service khởi động lại.
- Nội dung được ghi vào bucket `clean` là chính nội dung vừa được quét. Trước khi quét, mã băm SHA-256 của nội dung được so với mã băm đã ghi trong bảng `core.files`.
- Đường dẫn tải về được ký bằng HMAC-SHA256 trong `saigonos_core/downloads.py`. Chữ ký được tính từ mã file và thời điểm hết hạn. Lời gọi tải về không có access token. Do đó, service kiểm tra chữ ký và thời hạn trước khi đọc cơ sở dữ liệu hoặc kho file. Trạng thái `clean` được kiểm tra cả lúc cấp đường dẫn và lúc gửi file.
- File được gửi về luôn kèm các header `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff` và `Cache-Control: no-store`. Trước khi gửi, nội dung được so với mã băm SHA-256 đã ghi.
- Trong `src/saigonos/stack/config/clamav/clamd.conf`, giá trị `MaxFileSize` phải lớn hơn `MaxScanSize`. Nếu không, ClamAV chỉ quét phần đầu của một file lớn bên trong file nén mà không báo. Kiểm thử trong `tests/test_clamd_conf.py` kiểm tra điều kiện này.

Kiểm thử đơn vị của service nằm trong thư mục `tests/core` và chạy cùng lệnh `make check`. Kiểm thử tích hợp nằm trong hai file `tests/integration/test_core.py` và `tests/integration/test_files.py`. Kiểm thử `test_anon_cannot_reuse_query_plan_made_for_user` trong file `test_core.py` kiểm tra việc xóa query plan ở mỗi phiên.

## Phát hành phiên bản mới

Phần này dành cho maintainer của repo.

1. Cập nhật `version` trong `pyproject.toml` và `__version__` trong `src/saigonos/stack/core/saigonos_core/__init__.py` thành số phiên bản mới, sau đó chạy lại `pip install --no-deps -e .`.
2. Trong [CHANGELOG.md](CHANGELOG.md), đổi tiêu đề mục "Chưa phát hành" thành `## [X.Y.Z] - YYYY-MM-DD`. Thêm một mục "Chưa phát hành" trống ở phía trên và cập nhật các đường dẫn ở cuối file.
3. Mở pull request và merge sau khi CI chạy thành công.
4. Tạo tag trên `main` rồi push tag lên GitHub:

```bash
git switch main
git pull
git tag vX.Y.Z
git push origin vX.Y.Z
```

Khi nhận được tag mới, CI thực hiện các bước sau:

- Chạy lại toàn bộ kiểm tra.
- Đóng gói `saigonos-X.Y.Z.tar.gz` kèm file `SHA256SUMS`.
- Tạo draft release và đính kèm hai file trên.
- Công bố release.

Release sau khi công bố sẽ không thể chỉnh sửa. Do đó, chỉ push tag khi CI trên `main` đã chạy thành công.

## Giấy phép của phần đóng góp

Mọi đóng góp được phát hành theo giấy phép Apache-2.0, giống như phần còn lại của dự án.
