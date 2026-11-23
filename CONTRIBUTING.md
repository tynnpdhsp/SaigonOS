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

## Integration test

Integration test chạy cả bộ Docker Compose trên máy, do đó cần Docker đang hoạt động. Ở lần chạy đầu tiên, Docker tải các image với tổng dung lượng khoảng 1,5 GB. Mỗi nhóm kiểm thử dựng một bộ riêng và cần khoảng 3 GB RAM.

```bash
make integration
```

Lệnh này chạy chín nhóm kiểm thử trong thư mục `tests/integration`. File `test_apps.py` soát ứng dụng bằng service `apps` mà không khởi động hệ thống, rồi dựng một bộ để kiểm tra việc cài đặt ứng dụng. File `test_stack.py` dùng cấu hình mặc định. File `test_database.py` kiểm tra cơ sở dữ liệu, ví dụ service `migrate`, phân quyền từng dòng, role `anon` và audit log, với cấu hình mặc định. File `test_storage.py` kiểm tra SeaweedFS và ClamAV với cấu hình mặc định. File `test_core.py` kiểm tra service `core`, ví dụ access token giả, access token hết hạn, việc đổi khóa ký và việc API Gateway trả lời lại sau khi `core` khởi động lại. File `test_files.py` kiểm tra việc khai báo file, gửi nội dung, quét mã độc, chuyển file sạch sang bucket `clean` và tải file về. File `test_workflow.py` kiểm tra Operaton, ví dụ đăng nhập Cockpit bằng OTP, việc từ chối tài khoản không có realm role `admin`, các đường dẫn tới REST API của Operaton, việc bắt đầu quy trình và danh sách việc qua service `core`, hẹn giờ trên biên của việc và việc dọn lịch sử. File `test_realtime.py` kiểm tra Centrifugo, ví dụ kết nối WebSocket bằng access token, access token giả, access token hết hạn, ID token, quyền nghe kênh, history và Admin web. File này cũng kiểm tra thông báo cho người dùng và việc gửi tin Telegram tới một Bot API giả. File `test_caddy.py` bật Caddy với chứng chỉ do Caddy tự cấp. Với mỗi nhóm có khởi động hệ thống, lệnh thực hiện các bước sau:

- Tạo một thư mục làm việc tạm bằng `saigonos init` với các cổng còn trống.
- Khởi động hệ thống bằng `saigonos up`.
- Chạy các kiểm thử của nhóm.
- Xóa container và dữ liệu bằng `saigonos down --volumes`, sau đó xóa image của service `core` vừa build.

SeaweedFS không mở cổng S3 ra máy cài đặt và nằm trong mạng Docker `storage` riêng. Do đó, nhóm kiểm thử SeaweedFS gọi S3 từ một container tạm gắn vào mạng này. Tương tự, ClamAV nằm trong mạng Docker `scan` riêng. Kiểm thử gửi file tới ClamAV từ một container tạm gắn vào mạng `scan`. Kiểm thử dùng file EICAR làm mẫu mã độc. Đây là một file thử nghiệm vô hại mà mọi phần mềm diệt virus đều nhận ra.

Kiểm thử `test_only_one_of_concurrent_uploads_is_kept` trong `test_files.py` gửi nội dung của cùng một file bằng nhiều lời gọi cùng lúc. Trong lúc đó, kiểm thử tạm dừng SeaweedFS bằng `docker compose pause`. Lời gọi đầu tiên phải chờ ở bước ghi nội dung, nên các lời gọi còn lại chắc chắn chạy chồng lên nó.

Kiểm thử `test_file_waits_while_clamav_is_down_and_is_scanned_after_restart` trong `test_files.py` dừng ClamAV, gửi nội dung của một file, rồi khởi động lại service `core`. File phải chờ ở trạng thái `pending_scan` và chỉ được quét sau khi ClamAV chạy lại.

Kiểm thử `test_file_not_scanned_yet_cannot_be_downloaded` trong `test_files.py` tạm dừng ClamAV bằng `docker compose pause` để giữ file ở trạng thái `pending_scan`. Một số kiểm thử tải file về tự ký đường dẫn bằng khóa `CORE_DOWNLOAD_KEY` trong file `.env`. Nhờ đó, kiểm thử đường dẫn hết hạn không phải chờ 60 giây.

Kiểm thử `test_deadline_passed_while_operaton_was_stopped_fires_once_it_starts` trong `test_workflow.py` dừng Operaton bằng `docker compose stop` cho tới khi một hẹn giờ quá hạn, rồi chạy lại Operaton. Hẹn giờ phải chạy ngay khi Operaton sẵn sàng. Kiểm thử `test_history_cleanup_removes_only_history_past_time_to_live` chạy việc dọn lịch sử ngay bằng REST API của Operaton thay cho việc chờ tới khung giờ ban đêm.

Sau khi được tạo lại hoặc khởi động lại, một service có thể nhận địa chỉ IP mới. API Gateway cần khoảng 1 giây để nhận địa chỉ này. Do đó, kiểm thử dùng hàm `Stack.up()` thay cho lệnh `saigonos up`. Hàm này chờ tới khi API Gateway trả lời ở `/auth`, `/api/` và `/core/health`. Sau khi kill hoặc khởi động lại một service, kiểm thử gọi `Stack.wait_until_answers()` trước khi gọi API qua API Gateway. Trước đó, kiểm thử chờ container chạy lại và `healthy` bằng `docker inspect`, không gọi API Gateway trong lúc service đang dừng. Lý do là trong lúc service đang dừng, API Gateway trả mã 502 hoặc 503, và worker của APISIX còn giữ lỗi DNS thêm khoảng 1 giây. Kiểm thử `test_gateway_follows_new_address_of_core_within_seconds` trong `test_core.py` đổi địa chỉ IP của service `core` và kiểm tra API Gateway nhận địa chỉ mới trong vài giây.

Nhóm kiểm thử Caddy tạo thêm hai mạng Docker tạm với dải địa chỉ `192.0.2.0/28` và `2001:db8:5a1:9::/64`. Lời gọi từ hai mạng này giả lập máy gọi từ Internet qua IPv4 và IPv6. Do đó, máy chạy kiểm thử cần hỗ trợ IPv6.

Một lượt chạy mất khoảng 20 phút. Lệnh `make check` không chạy các kiểm thử này. CI chạy chúng ở job `integration` của mỗi pull request.

## Quy ước

- Mỗi file mới phải bắt đầu bằng một dòng `SPDX-License-Identifier` với giá trị `Apache-2.0`. Dòng này được viết dưới dạng comment theo cú pháp của loại file đó.
- Tính năng mới phải có kiểm thử đi kèm.
- Id của kiểm thử có tham số được viết bằng chữ thường không dấu, các từ nối với nhau bằng dấu gạch ngang. Ví dụ: `khoang-trang`. Khi gặp id có chữ có dấu, pytest dừng ngay ở bước thu thập kiểm thử.
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

Khi đổi phiên bản Operaton, kiểm tra lại file `src/saigonos/stack/config/operaton/sso-logout.js`. File này thay plugin đăng xuất của Operaton, vì plugin gốc của bản 2.2.1 không tìm thấy nút đăng xuất trong menu tài khoản. Kiểm thử `test_logout_button_ends_session_of_operaton` báo lỗi khi menu tài khoản không còn thẻ `a` có class `logout`.

Khi đổi phiên bản APISIX, kiểm tra lại file `src/saigonos/stack/config/apisix/saigonos-dns.lua`. APISIX nạp file này qua thiết lập `lua_module_hook` trong `config.yaml`. File bọc hàm `new` của module `apisix.core.dns.client` để đặt `emptyTtl` 1 giây, vì thư viện DNS của APISIX mặc định giữ lỗi `name error` 30 giây. Không sửa thẳng module `resty.dns.client`, vì APISIX nạp lại module này mỗi lần tạo client DNS. Kiểm thử `test_gateway_answers_within_seconds_after_stopped_core_starts_again` trong `test_core.py` cho APISIX dùng DNS giả trong `tests/integration/fake_dns.py`, dừng `core` 3 giây rồi chạy lại. Kiểm thử báo lỗi khi API Gateway còn trả lỗi sau khi `core` đã `healthy` 3 giây.

Mỗi service chạy lâu dài trong `compose.yaml` cần một healthcheck thật. Không tắt healthcheck bằng `disable: true`. Với service như vậy, lệnh `docker compose up --wait` của Docker Compose 2.x báo lỗi "has no healthcheck configured", dù Docker Compose 5 vẫn chạy được. Kiểm thử trong `tests/test_compose_file.py` kiểm tra quy tắc này.

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

Hàm `core.pre_request()` cũng chỉ chấp nhận access token. Lời gọi kèm token có claim `typ` khác `Bearer`, ví dụ ID token, nhận mã 401. Kiểm thử `test_api_accepts_access_token_only` trong cùng file kiểm tra việc này.

Khi lời gọi vào schema của một ứng dụng, hàm còn đòi claim `azp` của access token là tên ứng dụng. PostgREST đặt schema của lời gọi lên đầu `search_path`. Do đó, hàm `core.pre_request()` không có `SET search_path` riêng mà truyền giá trị này cho hàm `core.check_token(search_path)`. Hàm `core.check_token` có `SET search_path = ''`, nên hàm hay toán tử mà ứng dụng tạo trong schema của mình không thay được hàm hay toán tử mà phần kiểm tra dùng. Kiểm thử `test_schema_of_app_takes_only_access_token_of_its_client` trong `tests/integration/test_apps.py` kiểm tra việc này.

Trước hai việc kiểm tra trên, hàm `core.pre_request()` gọi `core.seal_claims()` để niêm phong claims của lời gọi. Hàm này ghi vào `saigonos.claims_seal` mã HMAC-SHA256 của claims, mã tiến trình và thời điểm bắt đầu transaction. Khóa nằm trong bảng `core.claims_key` mà chỉ superuser đọc được. Hàm `core.claims()` tính lại mã này và trả về `NULL` khi mã không khớp. Do đó, hàm của ứng dụng đổi `request.jwt.claims` thì `core.uid()` trả về `NULL`, và claims chép từ lời gọi trước không dùng lại được.

Hàm `core.seal_claims()` được cấp cho các role mà mã của ứng dụng cũng dùng, ví dụ `authenticated`. Do đó, hàm chỉ niêm phong khi câu lệnh đang chạy, tức giá trị của `current_query()`, đúng là câu lệnh PostgREST dùng để gọi `core.pre_request()` hoặc hằng số `SEAL_CLAIMS` của service `core`. Mã của ứng dụng chỉ chạy bên trong câu lệnh do PostgREST hay service `core` gửi tới, nên không tạo được câu lệnh này. Phiên của superuser cũng niêm phong được, để kiểm thử đặt claims bằng `psql`. Khi nâng phiên bản PostgREST, kiểm tra câu lệnh gọi hàm `db-pre-request` trong mã nguồn của PostgREST. Câu lệnh khác đi thì mọi lời gọi API báo lỗi. Service `core` gọi `SEAL_CLAIMS` ngay sau khi đặt claims trong `Database.session`, `Database.service_session` và bước máy làm. Kiểm thử `test_function_of_app_cannot_pass_itself_off_as_another_user` trong `tests/integration/test_apps.py` thử từng cách giả claims.

Khi cần sửa hàm `core.pre_request()`, viết lại toàn bộ hàm trong một file SQL mới và giữ cả bốn việc trên.

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

Mỗi thiết lập mới cần một integration test. Kiểm thử xóa thiết lập khỏi realm, chạy `saigonos up` rồi kiểm tra thiết lập đã được thêm lại. Cách này giả lập một realm được tạo từ phiên bản cũ.

Script cũng cập nhật realm master. Keycloak tự tạo realm này khi khởi động lần đầu, nên mọi thiết lập của realm master đều nằm trong script. Riêng Frontend URL của realm master luôn được đặt theo giá trị `SAIGONOS_KEYCLOAK_PORT` trong file `.env`, kể cả khi quản trị viên đã sửa giá trị này. Sau khi đổi Frontend URL, script đăng nhập lại. Access token cũ mang địa chỉ cũ trong claim `iss` nên bị Keycloak từ chối.

API Gateway chặn mọi địa chỉ của realm master. Do đó, integration test gọi Admin REST API của Keycloak qua cổng `SAIGONOS_KEYCLOAK_PORT`, ví dụ bằng hàm `Stack.admin()` trong `tests/integration/conftest.py`.

Client `operaton` và luồng đăng nhập riêng của client này cũng là ngoại lệ. Script kiểm tra từng bước của luồng đăng nhập ở mỗi lần chạy. Khi luồng khác với thiết kế, script tắt client, xóa luồng, tạo lại luồng rồi bật lại client. Do đó, không có lúc nào client dùng luồng đăng nhập chung của realm. Các thiết lập bảo mật của client cũng được đặt lại ở mỗi lần chạy.

Bước từ chối trong luồng này dùng thông báo có khóa `saigonos-operaton-admin-only`, khai báo trong thiết lập `denyErrorMessage` của bước. Nội dung tiếng Việt và tiếng Anh của thông báo nằm trong Realm overrides của realm `saigonos`. Script chỉ thêm nội dung còn thiếu, nên nội dung mà quản trị viên đã sửa được giữ nguyên.

Mapper `audience saigonos` của client scope `roles` cũng là ngoại lệ. Mapper này thêm audience `saigonos` vào access token, không thêm vào ID token. Centrifugo chỉ nhận access token có audience này. Khi mapper bị sửa hoặc bị xóa, script đặt lại mapper ở lần chạy sau.

Mapper `amr` của client scope `basic` và giá trị `default.reference.value` của các bước đăng nhập cũng là ngoại lệ. Luật OPA của trang quản trị dựa vào claim `amr`, nên script đặt lại các thiết lập này khi bị sửa. Mapper phải bật `lightweight.claim`, vì client `security-admin-console` dùng lightweight access token. Keycloak chỉ ghi vào claim `amr` các bước có giá trị `default.reference.value`. Do đó, bước mật khẩu có giá trị `pwd` và bước OTP có giá trị `otp`, ở cả các luồng `saigonos browser*` và luồng `saigonos operaton`. Khi không tìm thấy bước mật khẩu hay bước OTP trong luồng `saigonos browser*`, service `realm` báo lỗi. Keycloak không ghi bước OTP khi người dùng cài đặt OTP bằng required action `CONFIGURE_TOTP`, nên lần đăng nhập đó chỉ có `pwd`.

## Service core

Mã nguồn của service `core` nằm trong thư mục `src/saigonos/stack/core`. Lệnh `saigonos init` sao chép thư mục này vào thư mục làm việc. Docker Compose build image của service từ file `Dockerfile` trong thư mục đó.

Khi sửa service `core`, cần tuân theo các quy tắc sau:

- Thư viện của service được khai báo trong nhóm `core` của `pyproject.toml`. Lệnh `make lock` tạo lock file `src/saigonos/stack/core/requirements.txt` cho Python 3.14, kèm mã băm của từng file. Không sửa tay lock file này.
- Mọi truy vấn tới cơ sở dữ liệu chạy trong `Database.session(caller)` hoặc `Database.service_session(caller)`. Hai hàm này mở một transaction và xóa các query plan đã lưu. Hàm `session` đặt thêm role và nội dung access token của người gọi. Việc không có người gọi, ví dụ quét file và gửi file qua đường dẫn tải về, chạy trong `Database.transaction()`. Không truy vấn bằng kết nối lấy thẳng từ pool.
- API dành cho người đã đăng nhập nhận tham số kiểu `User`. Khi đó, lời gọi không có access token hợp lệ của người dùng có realm role `authenticated` nhận mã 401.
- Không bật Swagger UI và ReDoc của FastAPI, vì hai trang này tải script từ máy chủ bên ngoài.
- Lỗi 422 của FastAPI được trả qua hàm `invalid_request` trong `saigonos_core/main.py`. Hàm này bỏ trường `input` khỏi mỗi lỗi, vì JSON không biểu diễn được giá trị `NaN` và `Infinity` mà người gọi có thể gửi.
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

Unit test của service nằm trong thư mục `tests/core` và chạy cùng lệnh `make check`. Integration test nằm trong hai file `tests/integration/test_core.py` và `tests/integration/test_files.py`. Kiểm thử `test_anon_cannot_reuse_query_plan_made_for_user` trong file `test_core.py` kiểm tra việc xóa query plan ở mỗi phiên.

## Operaton

Cấu hình của Operaton nằm trong file `src/saigonos/stack/config/operaton/production.yml`. File này được gắn đè lên file cùng tên trong image. Các mật khẩu được lấy từ biến môi trường, không ghi trong file. Thiết lập `server.servlet.context-path` đặt mọi đường dẫn của Operaton dưới `/operaton/`, kể cả đường dẫn đăng nhập OAuth2.

Khi sửa cấu hình hoặc route của Operaton, cần tuân theo các quy tắc sau:

- Route `operaton` của API Gateway chỉ liệt kê các đường dẫn mà Cockpit, Tasklist và Admin cần. Không thêm REST API `/operaton/engine-rest` hoặc đường dẫn `/operaton/health` vào route.
- Tomcat của Operaton bỏ phần sau dấu `;` trong mỗi đoạn của đường dẫn, còn APISIX so khớp cả phần này. Ví dụ, APISIX coi `/operaton/app/..;/engine-rest` là một đường dẫn của `/operaton/app/`, còn Tomcat hiểu đó là `/operaton/engine-rest`. Do đó, route từ chối mọi đường dẫn có dấu `;` và chỉ gửi tới Operaton đường dẫn đã được APISIX chuẩn hóa. Không bỏ thiết lập `vars` và `proxy-rewrite` của route.
- Không bật `normalize_uri_like_servlet` của APISIX. Ở phiên bản 3.19.0, thiết lập này làm mất query string của các route không có `proxy-rewrite`, ví dụ route của Keycloak.
- Operaton nhận nhóm của người dùng từ claim `groups`. Mapper của client `operaton` đưa các realm role vào claim này. Realm role `admin` có toàn quyền trong Operaton.
- Service `processes` triển khai mỗi file BPMN thành một bản triển khai riêng. Tên của bản triển khai là tên file, nguồn là `saigonos`. Operaton dựa vào tên và nguồn để bỏ qua file không thay đổi. Do đó, không đổi tên hoặc nguồn của bản triển khai.
- Service `core` chờ service `processes` với điều kiện `service_completed_successfully`. Không bỏ điều kiện này. Lệnh `docker compose up --wait` báo lỗi khi một service chỉ chạy một lần mà không có service nào chờ nó.
- Trước khi triển khai, script `deploy-processes.lua` gọi Operaton một lần để kiểm tra tài khoản `core`. Khi mật khẩu sai, script dừng ngay. Nhờ đó, mỗi lần chạy chỉ tốn một lần đăng nhập sai.
- Service `core` chỉ gọi REST API của Operaton qua lớp `Operaton` trong `saigonos_core/operaton.py`. Sau mỗi lần Operaton trả mã 401, lớp này ngừng gọi Operaton trong 60 giây. Sau 5 lần liên tiếp, lớp này ngừng gọi hẳn. Các lời gọi gửi cùng lúc và cùng nhận mã 401 chỉ tính là một lần. Do đó, service `core` không bao giờ làm Operaton khóa hẳn tài khoản `core`.
- Operaton chỉ lưu thuộc tính `candidateStarterGroups` mà không kiểm tra thuộc tính này khi quy trình được bắt đầu qua REST API. Do đó, service `core` đọc thuộc tính từ file BPMN của phiên bản mới nhất và kiểm tra realm role của người gọi. Sau đó, service bắt đầu đúng phiên bản vừa kiểm tra bằng mã phiên bản, không bằng mã quy trình. Thuộc tính trong namespace của Operaton được đọc trước, thuộc tính trong namespace của Camunda chỉ được đọc khi thiếu, giống Operaton.
- File BPMN được đọc bằng `xml.etree.ElementTree`, nên quy tắc S314 của Ruff được tắt cho `saigonos_core/processes.py` trong `pyproject.toml`. File này đến từ Operaton và đã được Operaton kiểm tra khi triển khai.
- Biến `initiator` và biến ghi trong thuộc tính `initiator` của điểm bắt đầu luôn do service `core` ghi bằng claim `sub`. Operaton tự ghi tên tài khoản `core` vào biến này, rồi giá trị mà service `core` gửi ghi đè lên.
- Danh sách việc được lấy bằng lời gọi `POST /task` với `orQueries` gồm `assignee` và `candidateGroups`. Với điều kiện `candidateGroups`, Operaton chỉ trả về việc chưa có người nhận. Không bật `includeAssignedTasks`, vì khi đó danh sách có cả việc mà người khác đã nhận. Danh sách realm role được gửi dạng mảng JSON, không gửi qua query string, vì Operaton tách query string theo dấu phẩy.
- Nhận việc dùng lời gọi `POST /task/{id}/claim` của Operaton. Không dùng lời gọi đặt người nhận `POST /task/{id}/assignee`, vì lời gọi này ghi đè người đã nhận việc. Khi hai lời gọi claim chạy cùng lúc, Operaton chỉ ghi một lời gọi nhờ cột revision của việc. Lời gọi còn lại nhận mã 500 với lỗi `OptimisticLockingException` hoặc `TaskAlreadyClaimedException`.
- Lời gọi claim với `userId` rỗng hoặc `null` bỏ người nhận của việc mà không báo lỗi. Do đó, `Operaton.claim` từ chối mã người nhận rỗng trước khi gọi Operaton.
- Trước khi nhận việc, service `core` tìm việc bằng `POST /task` với `taskId`, `candidateGroups` và `includeAssignedTasks`. Lời gọi này chỉ trả về việc khi người gọi có một realm role nằm trong nhóm ứng viên, kể cả khi việc đã có người nhận.
- Hoàn thành việc luôn dùng lời gọi `POST /task/{id}/submit-form`, không dùng `POST /task/{id}/complete`. Nhờ đó, Operaton luôn kiểm tra form của việc. Operaton không kiểm tra người nhận khi hoàn thành việc. Do đó, service `core` kiểm tra người nhận trước khi gọi Operaton.
- Khi Operaton từ chối lời gọi claim hoặc submit-form, service `core` đọc lại việc rồi trả mã theo trạng thái mới của việc. Ví dụ, việc đã kết thúc nhận mã 404, việc đã có người khác nhận nhận mã 409. Chỉ lỗi không giải thích được bằng trạng thái của việc mới nhận mã 502.
- Service `core` tự kiểm tra form trong `saigonos_core/forms.py` trước khi gọi `submit-form`, không dựa vào Operaton. Lý do là Operaton 2.2.1 ghi mọi biến không có trong form vào quy trình. Ràng buộc `required` và `minlength` của Operaton nhận chuỗi chỉ có khoảng trắng. Với form của việc, ràng buộc `required` của Operaton coi trường là đã nhập khi quy trình đã có biến cùng tên. Trường `boolean` của Operaton nhận chuỗi bất kỳ. Trường `date` đọc chuỗi theo mẫu `dd/MM/yyyy` và tự đổi ngày sai như `32/13/2026` thành một ngày khác. Khi giá trị không đạt, Operaton trả mã 500 thay cho 400.
- Form được đọc từ file BPMN của phiên bản quy trình, cùng lúc với `candidateStarterGroups`. Form bắt đầu là form của điểm bắt đầu không có event definition, giống Operaton. Ở mỗi cấp của phần `formData`, thẻ trong namespace của Operaton được đọc trước, thẻ trong namespace của Camunda chỉ được đọc khi thiếu. Khi hai trường trùng `id`, chỉ trường đầu tiên có tác dụng. Độ dài chuỗi được tính theo đơn vị UTF-16 như Java. Nhờ đó, giá trị đã qua bước kiểm tra của service `core` không bị Operaton từ chối.
- Giá trị của trường kiểu `date` được gửi với kiểu biến `Date` theo giờ UTC, dạng `yyyy-MM-dd'T'HH:mm:ss.SSSZ` của REST API. Operaton từ chối múi giờ có dấu hai chấm, ví dụ `+07:00`.
- Bước máy làm được xử lý trong `saigonos_core/steps.py`. Service `core` lấy từng việc của topic `saigonos-function` bằng `fetchAndLock`, chờ theo kiểu long polling tối đa 5 giây và khóa việc trong 60 giây. Long polling tỉnh ngay khi có việc mới hoặc việc được mở khóa, nhưng không tỉnh khi hết thời gian chờ thử lại.
- Hàm của bước máy làm chạy với `statement_timeout` 20 giây. Giá trị này phải nhỏ hơn thời gian khóa việc và nhỏ hơn `COMMAND_TIMEOUT` của pool kết nối. Nếu không, hàm chạy quá lâu bị thư viện asyncpg ngắt và không được tính là lỗi của hàm.
- Dòng của bảng `core.step_runs` được ghi trong cùng transaction với lời gọi hàm, trước khi gọi hàm. Lệnh `INSERT ... ON CONFLICT DO NOTHING` chờ transaction khác đang ghi cùng mã việc. Do đó, mỗi external task chỉ chạy hàm một lần. Không gọi hàm ngoài transaction này.
- Hàm của ứng dụng luôn được gọi qua `core.run_step`. Hàm này là `SECURITY DEFINER` của role `workflow`, nên hàm bên trong không đổi được role của phiên. Khi gọi thẳng, một hàm thường có thể dùng `RESET ROLE` để quay về role `core_service`.
- Hàm được coi là đã khai báo khi `proacl` có quyền `EXECUTE` cấp riêng cho role `workflow`. Không dùng `has_function_privilege`, vì hàm này tính cả quyền cấp cho `PUBLIC`.
- Khi service `core` chết trong lúc chờ long polling, lời gọi đang chờ vẫn nằm trong Operaton tới hết 5 giây. Trong thời gian đó, Operaton có thể giao một việc cho lời gọi đã chết và khóa việc này 60 giây.

Integration test nằm trong file `tests/integration/test_workflow.py`. Kiểm thử `test_gateway_does_not_open_rest_of_operaton` gửi các đường dẫn vòng tới REST API của Operaton qua API Gateway. Kiểm thử `test_bpmn_file_cannot_take_process_of_another_file` kiểm tra việc gỡ bản triển khai khai báo lại mã quy trình của file khác. Quy trình thử của các lời gọi qua service `core` nằm trong thư mục `tests/integration/processes`. Form của quy trình thử có đủ các kiểu trường và các ràng buộc mà service `core` kiểm tra. Các kiểm thử form gửi cả những giá trị mà Operaton tự nhận, ví dụ chuỗi `true` cho trường `boolean` và chuỗi có khoảng trắng ở hai đầu cho ràng buộc `minlength`. Kiểm thử `test_core_stops_calling_operaton_while_it_refuses_account_of_core` tạm khóa tài khoản `core` bằng một lần đăng nhập sai, rồi kiểm tra service `core` chỉ gọi Operaton một lần. Sau đó, kiểm thử khởi động lại service `core`. Các kiểm thử nhận việc hoặc hoàn thành việc cùng lúc tạm dừng container của Operaton bằng `docker compose pause`, gửi các lời gọi, rồi chạy lại container. Nhờ đó, các lời gọi đều qua bước kiểm tra của service `core` và tới Operaton cùng lúc.

Các hàm thử của bước máy làm nằm trong file `tests/integration/processes/yeu-cau-thu.sql`, được chạy như một migration của ứng dụng. Kiểm thử `test_function_runs_once_when_core_dies_before_reporting` giành khóa của việc bằng worker `kiem-thu` trong lúc hàm đang chạy, rồi giết tiến trình của service `core`. Sau đó, kiểm thử chờ hết thời gian long polling rồi mới mở khóa việc. Các kiểm thử làm Operaton tạm khóa tài khoản `core` thì khởi động lại service `core` khi kết thúc. Lý do là vòng lặp bước máy làm gặp lần khóa này và ngừng gọi Operaton trong 60 giây.

## Centrifugo

Cấu hình của Centrifugo nằm trong file `src/saigonos/stack/config/centrifugo/config.yaml`. Các mật khẩu và các giá trị phụ thuộc file `.env` được đặt bằng biến môi trường `CENTRIFUGO_*` trong file `compose.yaml`. Biến môi trường được ưu tiên hơn file cấu hình.

Khi sửa cấu hình hoặc route của Centrifugo, cần tuân theo các quy tắc sau:

- Route `realtime` của API Gateway chỉ khớp đúng đường dẫn `/realtime/connection/websocket` và luôn gửi tới đường dẫn `/connection/websocket` của Centrifugo. Không thêm route tới cổng nội bộ 9000. Cổng này phục vụ API của server, Admin web và `/health`.
- Giữ thiết lập `client.token.audience`. Nếu bỏ thiết lập này, Centrifugo nhận cả ID token.
- Giữ thiết lập `client.disallow_anonymous_connection_tokens`. Access token của client không dùng client scope `basic` không có claim `sub`. Nếu bỏ thiết lập này, Centrifugo coi kết nối bằng access token đó là kết nối ẩn danh.
- Biến `CENTRIFUGO_CLIENT_ALLOWED_ORIGINS` lấy giá trị `CENTRIFUGO_ALLOWED_ORIGIN` mà lệnh `saigonos init` ghi vào file `.env`. Centrifugo so header `Origin` với giá trị này như một mẫu glob, nên hàm `origin_pattern` trong `src/saigonos/home.py` thêm dấu `\` trước mỗi ký tự trong `GLOB_SPECIALS`. Nếu thiếu bước này, địa chỉ IPv6 như `http://[2001:db8::1]:9080` trở thành một lớp ký tự. Khi đó, trang ở đúng địa chỉ này bị từ chối, còn Origin `http://1:9080` lại được nhận. Khi danh sách này rỗng, Centrifugo từ chối mọi kết nối có header `Origin`, kể cả từ chính địa chỉ của hệ thống. Không dùng giá trị `*`.
- Khi đổi phiên bản Centrifugo, kiểm tra thư viện glob mà Centrifugo dùng để so header `Origin`. Phiên bản 6.10.3 dùng `github.com/gobwas/glob` v1.1.0. `GLOB_SPECIALS` phải gồm đủ các ký tự mà hàm `QuoteMeta` của thư viện này thêm dấu `\` ở trước.
- Giữ thiết lập `usage_stats.disabled`. Nếu bỏ thiết lập này, Centrifugo gửi thống kê ẩn danh tới nhà phát triển lần đầu sau 24 đến 48 giờ mà không ghi log.

Integration test nằm trong file `tests/integration/test_realtime.py`. Client WebSocket của kiểm thử là lớp `Realtime` trong `tests/integration/conftest.py`, được viết bằng thư viện chuẩn của Python. Kiểm thử `test_expired_access_token_is_refused` dùng một client có thời hạn access token 1 giây, nên không phải chờ 60 giây. Kiểm thử `test_access_token_of_other_issuer_is_refused` tạm đặt Frontend URL của realm `saigonos` để Keycloak cấp access token có issuer khác, rồi xóa thiết lập này. Kiểm thử `test_access_token_without_user_is_refused` dùng một client chỉ có client scope `roles`. Kiểm thử `test_websocket_of_centrifugo_works_through_caddy` trong `test_caddy.py` kết nối qua HTTPS của Caddy. Kiểm thử `test_centrifugo_accepts_only_page_at_ipv6_url` chạy `saigonos init` với một địa chỉ IPv6 trong một thư mục riêng, lấy giá trị của `CENTRIFUGO_CLIENT_ALLOWED_ORIGINS` qua `docker compose config`, rồi chạy một container Centrifugo riêng với giá trị này. Do đó, kiểm thử dùng đúng cách Docker Compose đọc file `.env` và đúng cách Centrifugo so mẫu glob.

### Quyền nghe kênh

Quyền nghe kênh được khai báo theo namespace trong `channel.namespaces`. Khi sửa namespace hoặc token kênh, cần tuân theo các quy tắc sau:

- Namespace `public` có `allow_subscribe_for_client`. Namespace `user` chỉ có `allow_user_limited_channels`. Namespace `role` không có thiết lập nào, nên chỉ nghe được bằng token kênh. Không thêm `allow_subscribe_for_client` vào namespace `user` hoặc `role`.
- Token kênh hợp lệ mở được đúng kênh ghi trong token ở mọi namespace đã khai báo, kể cả kênh `user:#<sub>` của người khác và kênh không có namespace. Do đó, lời gọi `POST /core/realtime/token` chỉ cấp token cho kênh `role:<realm role>` sau khi kiểm tra realm role của người gọi, và cho kênh `user:<tên ứng dụng>.<sub>` sau khi kiểm tra `azp` và `sub` của người gọi. Khóa `CENTRIFUGO_SUBSCRIPTION_KEY` không được dùng vào việc khác.
- Giữ thiết lập `client.subscription_token.enabled`. Thiết lập này cho Centrifugo kiểm token kênh bằng khóa trong biến `CENTRIFUGO_CLIENT_SUBSCRIPTION_TOKEN_HMAC_SECRET_KEY`. Biến này và biến `SUBSCRIPTION_KEY` của service `core` cùng lấy giá trị `CENTRIFUGO_SUBSCRIPTION_KEY`. Nếu bỏ thiết lập này, Centrifugo kiểm token kênh bằng JWKS của Keycloak nên mọi token kênh bị từ chối.
- Token kênh hết hạn không muộn hơn access token dùng để lấy token. Nhờ đó, người bị gỡ realm role không giữ được token kênh lâu hơn access token cũ. Centrifugo cho client thêm 25 giây để gửi token mới (`client.expired_sub_close_delay`) và kiểm hạn của kênh 27 giây một lần (`client.presence_update_interval`). Do đó, kênh không có token mới bị ngừng từ 25 đến 52 giây sau khi token hết hạn.

Các kiểm thử quyền nghe kênh nằm trong file `tests/integration/test_realtime.py`. Client nghe kênh bằng lệnh subscribe của chính client. Kiểm thử `test_expired_channel_token_is_refused` ký token kênh bằng khóa `CENTRIFUGO_SUBSCRIPTION_KEY` trong file `.env` của bộ thử, nên không phải chờ token hết hạn.

### Gửi tin qua bảng outbox

Bảng `core.outbox` theo mẫu của Centrifugo. Consumer `outbox` của Centrifugo khóa partition bằng advisory lock của PostgreSQL, đọc các dòng theo thứ tự `id`, gửi từng tin rồi xóa các dòng đã gửi. Khi cập nhật bảng hoặc consumer, cần tuân theo các quy tắc sau:

- Role `centrifugo` chỉ có quyền `SELECT` và `DELETE` trên bảng `core.outbox`. Centrifugo không cần quyền nào khác. Không cấp thêm quyền cho role này.
- Trigger `notify` của bảng gửi NOTIFY tới kênh `core_outbox` khi có dòng mới. Giá trị `partition_notification_channel` trong file cấu hình phải trùng tên kênh này. Nếu hai tên lệch nhau, Centrifugo chỉ đọc bảng 5 giây một lần theo `partition_poll_interval`.
- Chuỗi kết nối của consumer chứa mật khẩu, nên được đặt bằng biến `CENTRIFUGO_CONSUMERS_OUTBOX_POSTGRESQL_DSN` trong file `compose.yaml`. Tên biến chứa tên consumer viết hoa. Khi đổi tên consumer, cần đổi cả tên biến.
- Centrifugo dừng ngay khi không kết nối được cơ sở dữ liệu lúc khởi động. Do đó, service `centrifugo` chờ service `migrate` chạy xong. Service `migrate` chờ service `databases` tạo role `centrifugo`.
- Với lỗi không thể thử lại, ví dụ kênh thuộc namespace chưa khai báo, Centrifugo ghi log rồi bỏ tin. Do đó, khi thêm namespace, cần khai báo namespace trong `channel.namespaces` và thêm vào biểu thức kiểm tra kênh của hàm `core.publish`.
- Với lỗi tạm thời, Centrifugo thử lại tin bị lỗi sau tối đa 5 giây. Các tin sau phải chờ tin này.

Các kiểm thử gửi tin nằm trong file `tests/integration/test_realtime.py`. Client nghe kênh bằng lệnh `subscribe` của API của server, nên kiểm thử không phụ thuộc quy tắc nghe kênh của từng namespace. Kiểm thử `test_row_and_message_written_together_reach_listener_within_one_second` gửi ba tin liên tiếp và chờ mỗi tin tối đa 1 giây. Khi trigger `notify` bị xóa hoặc tên kênh NOTIFY lệch, tin chờ tới lần đọc bảng tiếp theo nên kiểm thử báo lỗi.

### History

Mỗi namespace có bốn thiết lập `history_size`, `history_ttl`, `force_recovery` và `allow_history_for_subscriber`. Khi sửa history, cần tuân theo các quy tắc sau:

- Ba namespace dùng cùng `history_size` và `history_ttl`. README ghi hai giá trị này. Kiểm thử `test_readme_states_history_of_centrifugo` báo lỗi khi README và file cấu hình lệch nhau.
- Không dùng `allow_history_for_client`. Thiết lập này cho mọi client đọc history mà không cần nghe kênh, nên lộ tin của kênh `user:#<sub>` và `role:`. Thiết lập `allow_history_for_subscriber` chỉ cho client đang nghe kênh đọc history, nên quyền đọc history đi theo quyền nghe kênh.
- History nằm trong bộ nhớ của Centrifugo và mất khi Centrifugo khởi động lại. Khi 1.000 kênh đều đầy 100 tin khoảng 200 byte, Centrifugo dùng thêm khoảng 130 MiB RAM. Phần này được trả lại sau `history_ttl`.

Kiểm thử `test_messages_written_while_centrifugo_is_stopped_reach_client_after_restart` dừng Centrifugo đúng 60 giây, nên `make integration` lâu thêm khoảng 1 phút. JSON của Centrifugo bỏ các trường có giá trị false, ví dụ `recovered`. Do đó, kiểm thử đọc các trường này với giá trị mặc định là false.

## Thông báo cho người dùng

Bảng `core.notifications` và hàm `core.notify` được tạo trong file `0015_notifications.sql`. Hai lời gọi đọc thông báo và đánh dấu đã đọc nằm trong `saigonos_core/notifications.py`. Khi sửa phần thông báo, cần tuân theo các quy tắc sau:

- Bảng `core.notifications` chỉ được thêm dòng qua hàm `core.notify`. Không cấp quyền `INSERT` trên bảng cho role nào. Role `authenticated` chỉ có quyền `SELECT`. Role `core_service` chỉ có quyền `SELECT` và quyền `UPDATE` trên cột `read_at`.
- Chính sách `recipient_only` chỉ cho hai role trên thấy thông báo có người nhận trùng claim `sub` của người gọi. Các câu truy vấn của service `core` cũng lọc theo `core.uid()`. Nhờ đó, mỗi lớp tự chặn được thông báo của người khác. Lời gọi đánh dấu đã đọc chạy trong `Database.service_session(caller)`, nên audit log ghi đúng người gọi.
- Tin gửi tới kênh `user:#<sub>` có dạng `{"notification": {...}}` với đúng các trường của model `Notification`. Khi thêm hoặc đổi trường, cần sửa cả hàm `core.notify` và bảng trường trong README. Kiểm thử `test_notification_reaches_recipient_within_one_second_as_listed` so tin này với kết quả của `GET /core/notifications`. Kiểm thử `test_readme_lists_every_notification_field` so bảng trường trong README với model.
- Người nhận dài tối đa 249 ký tự, vì tên kênh `user:#<sub>` dài tối đa 255 ký tự.
- Không bỏ kiểm tra đường dẫn của hàm `core.notify`. Ứng dụng dựa vào kiểm tra này để hiển thị đường dẫn mà không kiểm tra lại. Trình duyệt bỏ dấu tab và dấu xuống dòng trong địa chỉ. Ví dụ, đường dẫn gồm dấu `/`, một dấu tab và `/web-khac.example` trở thành `//web-khac.example`, tức một địa chỉ của web khác. Do đó, hàm từ chối mọi ký tự điều khiển trong đường dẫn.

Các integration test nằm trong file `tests/integration/test_realtime.py`. Kiểm thử `test_notify_waits_for_other_transaction_with_same_key` giữ một transaction đã gọi `core.notify` trong 2 giây bằng `pg_sleep`, rồi gọi lại với cùng khóa từ một kết nối khác.

### Gửi tin Telegram

Bảng `core.deliveries` và phiên bản mới của hàm `core.notify` được tạo trong file `0016_deliveries.sql`. Vòng lặp gửi tin nằm trong `saigonos_core/deliveries.py`. Client của Bot API nằm trong `saigonos_core/telegram.py` và dùng `http.client`, không thêm thư viện. Khi sửa phần này, cần tuân theo các quy tắc sau:

- Bảng `core.deliveries` chỉ được thêm dòng qua hàm `core.notify` và hàm `core.send_email`. Role `core_service` chỉ có quyền `SELECT` và quyền `UPDATE` trên các cột trạng thái. Không cấp thêm quyền cho role nào.
- Tiêu đề, nội dung và đường dẫn được chép vào bảng `core.deliveries`. Vòng lặp gửi tin không có người gọi, nên chính sách `recipient_only` của bảng `core.notifications` không cho vòng lặp đọc thông báo.
- Dòng được chuyển sang `sending` và commit trước khi gọi Telegram. Không giữ khóa dòng trong lúc gọi Telegram. Nếu giữ khóa, transaction bị hủy khi service `core` chết, dòng trở về `pending` và tin được gửi lại dù Telegram có thể đã nhận tin.
- Khi service `core` khởi động, các dòng còn ở `sending` chuyển sang `unknown`. Do đó, chỉ chạy một container của service `core`.
- Lỗi xảy ra trước khi gửi xong lời gọi, ví dụ không kết nối được hoặc lỗi TLS, được gửi lại. Lỗi xảy ra sau khi đã gửi xong lời gọi cho kết quả `unknown`. Không gửi lại tin `unknown`.
- Khi service `core` dừng trong lúc gửi, vòng lặp chờ Telegram trả lời rồi ghi kết quả, nhờ `asyncio.shield`. Khi lời gọi `run_in_threadpool` bị hủy thẳng, thread vẫn gửi tin nhưng kết quả bị mất.
- Token của bot nằm trong đường dẫn của lời gọi. Không ghi đường dẫn hoặc token vào log. Token được kiểm tra dạng `<số>:<chuỗi>` lúc khởi động, nên `http.client` không báo lỗi `InvalidURL` chứa đường dẫn.
- Cấu hình Telegram sai không làm service `core` dừng. Service ghi lý do vào log và chuyển tin sang `skipped`.
- Trigger `notify` của bảng gửi NOTIFY tới kênh `core_deliveries` khi có dòng mới. Service `core` nghe kênh này bằng một kết nối riêng, mở bằng `Database.listen`. Khi không có NOTIFY, service đọc bảng 10 giây một lần.

Bot API giả nằm trong file `tests/integration/fake_telegram.py`. Fixture `bot_api` chạy file này trong một container từ image của service `core`, gắn container vào mạng `default` của bộ thử với tên `telegram-gia`, rồi ghi cấu hình Telegram trỏ tới container này vào file `.env`. Bot API giả trả lời theo kế hoạch mà kiểm thử gửi tới `/plan`, ví dụ mã 500, mã 429 kèm `retry_after`, ngắt kết nối hoặc trả lời sau 30 giây. Kiểm thử `test_telegram_message_is_skipped_while_telegram_is_not_configured` phải đứng trước các kiểm thử dùng fixture `bot_api`, vì fixture này bật Telegram cho cả bộ thử. Kiểm thử `test_notification_reaches_telegram_group_once_within_two_seconds` gửi hai tin liên tiếp. Khi trigger `notify` bị xóa, tin thứ hai chờ tới lần đọc bảng tiếp theo nên kiểm thử báo lỗi.

### Gửi email

Hàm `core.send_email` và hàm `core.check_message` được tạo trong file `0017_email.sql`. Client SMTP nằm trong `saigonos_core/smtp.py` và dùng `smtplib`, không thêm thư viện. Khi sửa phần này, cần tuân theo các quy tắc sau:

- Hàm `core.check_message` kiểm tra khóa chống trùng, tiêu đề, nội dung và đường dẫn cho cả `core.notify` và `core.send_email`. Quy tắc của các giá trị này chỉ được sửa ở hàm này.
- Hàm `core.send_email` và `saigonos_core/smtp.py` kiểm tra địa chỉ email theo cùng một mẫu. Mẫu này là định nghĩa địa chỉ email hợp lệ của HTML và chỉ nhận ký tự ASCII. Do đó, máy chủ SMTP không cần hỗ trợ SMTPUTF8.
- Nội dung email được mã hóa bằng quoted-printable hoặc base64 nhờ policy `cte_type="7bit"`, nên chỉ gồm ký tự ASCII. Do đó, máy chủ SMTP không cần hỗ trợ 8BITMIME.
- Mỗi kênh có một vòng gửi `Deliveries` riêng, với cấu hình `Channel` trong `saigonos_core/deliveries.py`. Mọi câu truy vấn của vòng gửi lọc theo cột `channel`. Nhờ đó, lệnh chờ `retry_after` của Telegram không làm chậm email.
- Luôn truyền `ssl.create_default_context()` cho `starttls()` và `SMTP_SSL`. Khi không nhận context, `smtplib` vẫn mã hóa kết nối nhưng không kiểm tra chứng chỉ.
- Không bỏ qua STARTTLS khi máy chủ không hỗ trợ. Cấu hình có mật khẩu mà `SMTP_SECURITY` là `none` bị từ chối lúc khởi động.
- Nội dung email được gửi bằng `docmd("DATA")`, `send()` và `getreply()`, không dùng `sendmail()`. Nhờ đó, client phân biệt được nội dung chưa gửi xong, được gửi lại, với câu trả lời bị mất sau khi đã gửi xong nội dung, cho kết quả `unknown`.

Máy chủ SMTP giả nằm trong file `tests/integration/fake_smtp.py` và chỉ dùng thư viện chuẩn của Python. Unit test trong `tests/core/test_smtp.py` nạp file này theo đường dẫn và chạy máy chủ trong cùng tiến trình. Fixture `mail_server` của integration test chạy file này trong một container từ image của service `core`, gắn container vào mạng `default` của bộ thử với tên `smtp-gia`. Hàm `make_certificates` dùng thư viện `cryptography` để tạo một CA thử và chứng chỉ của máy chủ giả. Chứng chỉ có đủ các extension mà Python 3.13 trở lên đòi hỏi khi kiểm tra chứng chỉ. Fixture ghi file `compose.override.yaml` để service `core` tin CA thử qua biến `SSL_CERT_FILE`. Kiểm thử `test_email_is_skipped_while_smtp_is_not_configured` phải đứng trước các kiểm thử dùng fixture `mail_server`. `smtplib` của Python 3.14 gửi `mail from:` và `rcpt to:` bằng chữ thường, nên máy chủ giả ghi lại hai lệnh này bằng chữ hoa.

## OPA

Luật của lõi nằm trong thư mục `src/saigonos/stack/config/opa`. Unit test của luật nằm trong thư mục `tests/opa`, mỗi file luật có một file `_test.rego`. Lệnh `make opa-test` chạy `opa fmt`, `opa check --strict` và `opa test` bằng image `openpolicyagent/opa` ghi trong `compose.yaml`. Độ phủ của unit test phải đạt 100%.

- Quyết định cho API Gateway nằm ở tài liệu `decision` trong một package con của `saigonos`, ví dụ `data.saigonos.admin.decision`. File `system.rego` chỉ cho API của OPA nhận lời gọi `POST` tới các tài liệu này và lời gọi `GET /health`.
- Image của OPA không có shell. Healthcheck dùng lệnh `opa eval` với hàm `http.send` để gọi `/health`. Khi đổi phiên bản OPA, kiểm tra lại healthcheck này và tùy chọn tắt việc kiểm tra phiên bản mới của lệnh `opa run`.
- Plugin `openid-connect` chạy ở pha rewrite, trước plugin `opa` ở pha access. Luật đọc claims bằng `io.jwt.decode` mà không kiểm tra lại chữ ký. Do đó, chỉ đọc claims của access token trên route có plugin `openid-connect` với `bearer_only`.
- Khi không kết nối được OPA, plugin `opa` của APISIX trả mã 403. Khi OPA trả lời không có `result`, plugin trả mã 503. Kiểm thử `test_admin_routes_are_refused_while_opa_is_stopped` kiểm tra cách từ chối này.
- Service `policies` soát luật bằng `opa eval` thay cho `opa check`, vì lệnh này vừa biên dịch mọi file luật vừa kiểm tra `SAIGONOS_ADMIN_NETWORKS` qua tập `config_errors`.
- Luật trong trường `access` của bản khai được ghi thành label `saigonos.access.<số thứ tự>` của route `app-<tên>`, mỗi label là JSON không có khoảng trắng. Plugin `opa` của route gửi cả route cho OPA nhờ `with_route`, nên `apps.rego` đọc luật từ `input.route.labels`. Label của APISIX dài tối đa 256 ký tự, nên model `AccessRule` từ chối luật dài hơn. Khi đổi phiên bản APISIX, kiểm tra lại giới hạn này.
- Plugin `opa` trên route của ứng dụng có `_meta.priority` là 1000, thấp hơn 1002 của `limit-count`. Do đó, lời gọi bị giới hạn tần suất trước khi tới OPA.
- Label hỏng làm `apps.rego` từ chối mọi lời gọi với mã 503, không bỏ qua luật hỏng.
- Schema của ứng dụng chỉ được phục vụ qua route `app-<tên>`. Route `api` ghi đè header `Accept-Profile` và `Content-Profile` thành `api`. Không thêm route nào khác tới PostgREST, vì lời gọi qua route đó sẽ không qua luật của ứng dụng.

## Ứng dụng

Model của bản khai `saigonos-app.json` nằm trong `saigonos_core/manifest.py` của service `core`. Lệnh của service `apps` nằm trong `saigonos_core/apps.py`. Service `apps` chạy với thư mục làm việc `/app` của image và tự ghép tên ứng dụng với thư mục `/apps`. Do đó, file trong thư mục `apps` không nằm trên `sys.path` của Python.

Khi sửa bản khai, cần tuân theo các quy tắc sau:

- File `schemas/saigonos-app.schema.json` được sinh từ model bằng lệnh `make schema`. Không sửa tay file này. Kiểm thử `test_schema_file_matches_model` báo lỗi khi file khác với model.
- Trình soạn thảo kiểm tra bản khai bằng regex của JavaScript, còn Pydantic dùng regex của Rust. Do đó, mẫu regex không dùng lookahead, lookbehind hay `\d`. Viết `[0-9]` thay cho `\d`, vì `\d` của Rust nhận cả chữ số của các hệ chữ khác.
- Mỗi loại lỗi của Pydantic có thể gặp cần một câu tiếng Việt trong `MESSAGES` hoặc `RULES`. Lỗi chưa có câu riêng được in thành "Giá trị không hợp lệ."
- Khi lõi thêm schema, role của cơ sở dữ liệu, client của Keycloak hoặc route của API Gateway, thêm tên đó vào `RESERVED_NAMES`, với dấu gạch dưới đổi thành dấu gạch ngang. Kiểm thử `test_names_used_by_core_are_reserved` đọc các file SQL, file route và `setup-realm.lua` để kiểm tra quy tắc này. Danh sách trong README cũng phải khớp.
- Lệnh `check` không đi theo symlink và kiểm tra quyền đọc bằng tài khoản chạy service `apps`. Lệnh `saigonos apply --check` truyền tài khoản của người gọi qua tùy chọn `--user` của `docker compose run`. Không chạy service `apps` bằng root.

Khi sửa việc cài đặt ứng dụng, cần tuân theo các quy tắc sau:

- Chỉ service `apps` có mật khẩu superuser của PostgreSQL, mật khẩu của tài khoản `admin` trong realm master và khóa Admin API của APISIX. Không thêm `POSTGRES_PASSWORD`, `KEYCLOAK_ADMIN_PASSWORD` hay `APISIX_ADMIN_KEY` vào service `core` hay service chạy lâu dài khác. Kiểm thử `test_only_apps_service_gets_admin_secrets_for_installing_apps` kiểm tra quy tắc này với service `core`.
- File SQL của ứng dụng chạy bằng một kết nối đăng nhập bằng role sở hữu schema của ứng dụng. Không chạy file bằng `SET ROLE` hay `SET SESSION AUTHORIZATION` trong phiên của superuser, vì file có thể dùng `RESET ROLE` hoặc `RESET SESSION AUTHORIZATION` để quay về superuser.
- File SQL chạy qua hàm `core.run_app_sql(script)`, tức lệnh `EXECUTE` bên trong một hàm. Nhờ đó, `COMMIT`, `ROLLBACK` và `SAVEPOINT` trong file bị từ chối. Khi chạy file thẳng bằng giao thức simple query, các câu lệnh trước `COMMIT` được lưu dù file bị lỗi ở sau.
- Hàm `core.record_migration(name, checksum)` ghi file đã chạy vào `core.migrations` trong cùng transaction với file. Hàm lấy `scope` từ `session_user`, nên một ứng dụng chỉ ghi được cho chính nó.
- Lời gọi API vào schema của ứng dụng chạy bằng role `<schema>_user`. Hàm `core.pre_request()` đổi sang role này bằng `SET LOCAL ROLE` sau khi `core.check_token()` kiểm tra `azp`. Role `authenticator` có quyền SET trên role này nhưng không thừa hưởng quyền. Role sở hữu schema thừa hưởng quyền của role này để sửa hàm của nó nhưng không có quyền SET.
- PostgreSQL kiểm tra `SET ROLE` theo `session_user`. Do đó, mọi role mà `authenticator` SET được thì mã chạy trong lời gọi cũng SET được. Sau mỗi file, trong cùng transaction, hàm `core.secure_app()` đổi mọi hàm không khai `SECURITY DEFINER` của ứng dụng thành hàm `SECURITY DEFINER` của role `<schema>_user`, vì PostgreSQL không cho đổi role bên trong hàm như vậy. Chủ của hàm tự có quyền `EXECUTE`, nên hàm `core.secure_app()` thu lại quyền này rồi cấp lại đúng như file đã cấp. Hàm cũng từ chối file cấp quyền trên schema cho role khác `<schema>_user`, `anon` và `workflow`, vì role `<schema>_user` thừa hưởng quyền của `authenticated`.
- Không cấp `set_config` cho role mới. View, chính sách RLS và giá trị mặc định chạy ngoài hàm `SECURITY DEFINER`, nên `set_config('role', ...)` ở đó đổi được role. Service `core` gọi `set_config` bằng role `core_service` trước khi đổi role, rồi trả role về bằng `SET LOCAL ROLE NONE`.
- Event trigger `refuse_runtime_ddl` từ chối lệnh DDL khi `session_user` không phải superuser hay role sở hữu schema của một ứng dụng. Role sở hữu schema chỉ đăng nhập được trong lúc cài đặt. Thiếu event trigger này, mã của ứng dụng lúc phục vụ có thể dùng `ALTER FUNCTION` để đổi hàm về `SECURITY INVOKER`. Do đó, service mới cần tạo bảng hay hàm thì làm bằng migration.
- Chỉ superuser gọi được `core.prepare_app`, `core.open_app_login`, `core.close_app_login` và `core.finish_app`. Kiểm thử `test_functions_for_plugging_apps_are_closed_to_other_roles` kiểm tra quyền của các hàm này.
- Hàm `core.pre_config()` chỉ liệt kê schema còn tồn tại. Khi danh sách có một schema đã bị xóa, PostgREST không nạp được schema cache, và sau khi khởi động lại thì không phục vụ API nào.
- Hàm `core.finish_app` gửi cả `reload config` và `reload schema` tới kênh `pgrst`. PostgREST 16.5 chỉ phục vụ schema mới sau khi nạp lại schema cache, và đọc lại cấu hình mỗi lần nạp như vậy. Do đó, không bỏ `reload schema`.
- Lệnh `saigonos apply` chép ứng dụng vào thư mục `apps/.<tên>.new`, đổi tên bản đang dùng thành `apps/.<tên>.old` rồi mới đặt bản mới vào chỗ. Khi cài đặt lỗi hoặc bị ngắt, bản cũ được trả lại. Lần chạy sau còn thấy `apps/.<tên>.old` thì coi đó là bản đã cài đặt thành công gần nhất. File `.apps.lock` trong thư mục làm việc chặn hai lệnh cài đặt chạy cùng lúc. Khi đặt quyền cho file đã chép, bỏ qua symlink, vì `chmod` đổi quyền của file mà symlink trỏ tới.
- Phần Keycloak nằm trong `saigonos_core/app_keycloak.py`. Lệnh `apply` kiểm tra tên client và realm role trên Keycloak trước khi đụng tới cơ sở dữ liệu. Phần tạo và đặt lại client chạy sau các file SQL và trước `core.finish_app`. Nhờ đó, schema của ứng dụng chỉ được đưa vào API khi client đã đúng bản khai.
- Client và realm role do SaigonOS tạo mang thuộc tính `saigonos.app` có giá trị là tên ứng dụng. Không nhận một client hay realm role thiếu thuộc tính này, vì `core.pre_request()` cho access token của client trùng tên ứng dụng gọi vào schema của ứng dụng.
- Lệnh `apply` không xóa realm role. Role bị bỏ khỏi bản khai chỉ bị bỏ khỏi scope mapping của client, vì xóa role làm mất việc gán role cho người dùng.
- Phần APISIX nằm trong `saigonos_core/app_gateway.py`. Route của ứng dụng có mã `app-<tên>` và label `saigonos.app`. Do đó, tên file route của lõi không được bắt đầu bằng `app-`. Kiểm thử `test_route_ids_of_core_never_start_with_prefix_of_apps` kiểm tra quy tắc này. Lệnh `apply` luôn gửi lại toàn bộ route bằng `PUT`, rồi so route APISIX trả về với route đọc được trước đó để biết có thay đổi hay không. APISIX tự thêm giá trị mặc định vào cấu hình của plugin, nên không so route đã lưu với route gửi đi.
- Cấu hình `openid-connect` và `limit-count` của route ứng dụng phải giống route `api.json`. Kiểm thử `test_route_checks_token_and_limits_calls_like_api_route` báo lỗi khi hai bên khác nhau. Plugin `response-rewrite` sửa `basePath` trong tài liệu OpenAPI của ứng dụng, vì `PGRST_OPENAPI_SERVER_PROXY_URI` chỉ có một giá trị cho mọi schema.
- Thiết lập của client nằm trong hàm `wanted_client`. Khi phiên bản Keycloak mới có thêm một loại grant hoặc thiết lập bảo mật cho client, thêm thiết lập đó vào hàm này với giá trị an toàn. Keycloak tự đặt `adminUrl` bằng `rootUrl` cho client mới và gọi tới địa chỉ này khi người dùng đăng xuất, nên hàm đặt `adminUrl` rỗng.

Khi sửa phần quy trình của ứng dụng, cần tuân theo các quy tắc sau:

- Lệnh `check` soát file BPMN trong `saigonos_core/bpmn.py` theo danh sách thẻ và thuộc tính được phép, tức `ELEMENTS` và `EXTENSION_ELEMENTS`, không theo danh sách cấm. Lý do là Operaton chạy mã ở nhiều chỗ, ví dụ `formHandlerClass`, ràng buộc `validator` và listener. Khi service `core` hỗ trợ thêm một thẻ hoặc thuộc tính, thêm vào hai bảng này cùng một kiểm thử.
- Mọi giá trị thuộc tính và nội dung thẻ chứa `${` hoặc `#{` đều qua hàm `expression_problem`, kể cả tên của việc và phần documentation, vì Operaton tính expression ở cả hai chỗ này.
- File BPMN được đọc bằng `xml.parsers.expat` để có số dòng của từng thẻ. Khai báo DOCTYPE bị từ chối, nên file không khai báo được entity.
- Phần Operaton của lệnh `apply` nằm trong `saigonos_core/app_processes.py`. Mỗi file BPMN là một bản triển khai trong tenant trùng tên ứng dụng, với nguồn `app:<tên>`, bật `enable-duplicate-filtering` và `deploy-changed-only`. Operaton dựa vào tên, nguồn và tenant để bỏ qua file không thay đổi. Do đó, không đổi tên, nguồn hay tenant của bản triển khai.
- Tài khoản `core` thuộc nhóm quản trị của Operaton nên thấy mọi tenant. Service `core` tự lọc theo tenant: `tenantIdIn` hoặc `withoutTenantId` trong truy vấn việc, `GET /process-definition/key/{key}/tenant-id/{tenant}` khi bắt đầu quy trình của ứng dụng. Lời gọi `GET /process-definition/key/{key}` chỉ trả về quy trình không thuộc tenant nào. Service còn so `tenantId` của kết quả với phạm vi của access token, phòng khi Operaton bỏ qua điều kiện lọc.
- Phạm vi của access token nằm trong `saigonos_core/scopes.py`. Claim `azp` trùng tên một ứng dụng trong bảng `core.apps` thì token thuộc ứng dụng đó. Việc và quy trình nằm ngoài phạm vi nhận mã 404 như khi không tồn tại, để token của client khác không biết chúng có hay không.
- Service `core` kiểm tra schema của hàm trước khi chạy bước máy làm: quy trình trong tenant của ứng dụng chỉ gọi hàm trong schema của ứng dụng đó, quy trình không thuộc tenant nào không gọi được hàm của ứng dụng. Lệnh `check` đã kiểm tra quy tắc này, nhưng service có mật khẩu của tài khoản `core` vẫn triển khai được file BPMN mà không qua lệnh `check`.
- Hàm `core.prepare_app` cấp quyền `USAGE` trên schema của ứng dụng cho role `workflow`, để `core.run_step` gọi được hàm của bước máy làm. Hàm này cũng cấp `core.notify`, `core.publish` và `core.send_email` cho role sở hữu schema và role `<schema>_user`.
- Ba hàm trên lấy ứng dụng đang gọi từ hàm `core.calling_app()`. Hàm này xét `session_user` (file SQL lúc cài đặt), rồi `current_setting('role')` (lời gọi API, PostgREST đặt role này và mã của ứng dụng không đổi được), rồi `azp` trong claims đã niêm phong (service `core` và bước máy làm). Khi claims bị sửa, hàm báo lỗi thay vì coi lời gọi là của hệ thống. Do đó, service `core` đặt `azp` là tên ứng dụng vào claims của bước máy làm trong tenant của ứng dụng.
- Chính sách RLS `recipient_only` của bảng `core.notifications` so cột `app` với `core.calling_app()`. Lời gọi `GET /core/notifications` không tự lọc theo ứng dụng mà dựa vào chính sách này. Khóa chống trùng của `core.notifications` và `core.deliveries` có cả cột `app`.
- Mã của ứng dụng chỉ gửi tin vào kênh `role:<tên>.`, `public:<tên>.` và `user:<tên>.`. Kênh `user:#<sub>` không cần token kênh nên giao diện của mọi ứng dụng nghe được. Do đó, kênh này chỉ mang thông báo không thuộc ứng dụng nào.

Khi sửa việc gỡ ứng dụng, cần tuân theo các quy tắc sau:

- Lệnh `remove` của service `apps` gỡ theo thứ tự route, client, quy trình rồi cơ sở dữ liệu. Mỗi bước bỏ qua phần đã gỡ. Do đó, chạy lại lệnh sau một lần lỗi thì lệnh làm tiếp phần còn lại.
- Hàm `core.remove_app` đặt `applied_at` về `NULL` và ghi `removed_at`. Ở lần cài đặt sau, `apply_database` báo cho `configure_services` rằng ứng dụng vừa bị gỡ, và chỉ khi đó quy trình mới được chạy lại. Không chạy lại quy trình ở mọi lần cài đặt, vì quản trị viên có thể đã tạm dừng một quy trình trong Cockpit.
- Hàm `core.purge_app` xóa dòng của ứng dụng trong `core.deliveries`, `core.notifications`, `core.step_runs` và `core.migrations`, rồi xóa schema và hai role. Khi lõi thêm bảng lưu dữ liệu theo ứng dụng, thêm bảng đó vào hàm này. Không xóa `core.audit_log`.
- Lệnh `apply --all` lấy danh sách ứng dụng từ `core.apps`, không từ thư mục `apps`. Lệnh `saigonos up` chỉ gọi `apply --all` khi thư mục `apps` có ứng dụng, còn `saigonos doctor` kiểm tra từng ứng dụng trong thư mục này. Do đó, lệnh `saigonos remove` xóa cả bản chép của ứng dụng.

Service `core` phục vụ giao diện của ứng dụng bằng `saigonos_core/ui.py`. Khi sửa phần này, cần tuân theo các quy tắc sau:

- Ứng dụng đã cài đặt là ứng dụng có `applied_at` trong bảng `core.apps`. Role `core_service` chỉ đọc được các cột `name`, `schema_name`, `manifest` và `applied_at` của bảng này.
- Mỗi phần của đường dẫn phải khớp mẫu `SEGMENT`, nên `.`, `..`, tên bắt đầu bằng dấu chấm, dấu `\` và ký tự điều khiển bị từ chối. Hàm `open_file` mở từng thư mục rồi tới file bằng `O_NOFOLLOW`, mỗi lần mở tính từ thư mục vừa mở. Do đó, không có symlink nào được đi theo, kể cả symlink trỏ vào trong thư mục `ui`. Không thay hàm này bằng `os.path.realpath` hay `StaticFiles`.
- Loại nội dung lấy từ bảng `TYPES` theo phần mở rộng, không lấy từ file `mime.types` của image. Khi giao diện cần một loại file mới, thêm phần mở rộng vào bảng này.

Unit test nằm trong `tests/core/test_manifest.py`, `tests/core/test_bpmn.py`, `tests/core/test_apps_cli.py`, `tests/core/test_app_database.py`, `tests/core/test_app_keycloak.py`, `tests/core/test_app_gateway.py`, `tests/core/test_app_processes.py`, `tests/core/test_scopes.py`, `tests/core/test_ui.py` và `tests/test_apply.py`. Unit test của phần Keycloak dùng một Keycloak giả trong bộ nhớ, viết theo hành vi đã kiểm tra trên Keycloak 26.8.2. Integration test lấy access token của ứng dụng bằng hàm `Stack.app_token()`, hàm này đăng nhập qua luồng Authorization Code với PKCE như trình duyệt. Integration test `tests/integration/test_apps.py` chạy service `apps` thật, kể cả với symlink và file chỉ chủ sở hữu đọc được. Các kiểm thử cài đặt ứng dụng dùng một tên ứng dụng ngẫu nhiên cho mỗi kiểm thử. Kiểm thử `test_refused_file_is_rolled_back_and_last_good_version_kept` thử từng loại file bị từ chối, ví dụ file đọc schema của ứng dụng khác hoặc dùng `COMMIT`. Kiểm thử `test_function_of_app_cannot_read_another_app_even_rows_of_caller` thử các cách đổi sang role của ứng dụng khác: `SET LOCAL ROLE`, mệnh đề `SET role` của hàm, `set_config` trong view và `ALTER FUNCTION` lúc phục vụ. Kiểm thử `test_step_calling_function_of_another_app_becomes_incident` triển khai file BPMN thẳng qua REST API của Operaton, không qua lệnh `check`, để thử phần kiểm tra của service `core`. Khi stdout không phải terminal, Docker Compose in log build vào stdout trước kết quả của container, nên kiểm thử chỉ so phần cuối của stdout.

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
