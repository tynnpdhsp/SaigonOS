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
- Đối chiếu [DEPENDENCIES.md](DEPENDENCIES.md) với lock file và file `compose.yaml`.
- Chạy kiểm thử bằng `pytest` và đo coverage.

Để tự động sửa định dạng mã, chạy `make format`.

## Kiểm thử tích hợp

Kiểm thử tích hợp chạy cả bộ Docker Compose trên máy, do đó cần Docker đang hoạt động. Ở lần chạy đầu tiên, Docker tải các image với tổng dung lượng khoảng 2 GB.

```bash
make integration
```

Lệnh này chạy ba nhóm kiểm thử trong thư mục `tests/integration`. File `test_stack.py` dùng cấu hình mặc định. File `test_database.py` kiểm tra cơ sở dữ liệu, ví dụ service `migrate`, phân quyền từng dòng, role `anon` và audit log, với cấu hình mặc định. File `test_caddy.py` bật Caddy với chứng chỉ do Caddy tự cấp. Với mỗi nhóm, lệnh thực hiện các bước sau:

- Tạo một thư mục làm việc tạm bằng `saigonos init` với các cổng còn trống.
- Khởi động hệ thống bằng `saigonos up`.
- Chạy các kiểm thử của nhóm.
- Xóa container và dữ liệu bằng `saigonos down --volumes`.

Nhóm kiểm thử Caddy tạo thêm hai mạng Docker tạm với dải địa chỉ `192.0.2.0/28` và `2001:db8:5a1:9::/64`. Lời gọi từ hai mạng này giả lập máy gọi từ Internet qua IPv4 và IPv6. Do đó, máy chạy kiểm thử cần hỗ trợ IPv6.

Một lượt chạy mất khoảng 7 phút. Lệnh `make check` không chạy các kiểm thử này. CI chạy chúng ở job `integration` của mỗi pull request.

## Quy ước

- Mỗi file mới phải bắt đầu bằng một dòng `SPDX-License-Identifier` với giá trị `Apache-2.0`. Dòng này được viết dưới dạng comment theo cú pháp của loại file đó.
- Tính năng mới phải có kiểm thử đi kèm.
- Mỗi commit message chỉ gồm một dòng theo quy ước [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/). Ví dụ: `feat(cli): thêm lệnh doctor`.
- Mỗi thay đổi được thực hiện trên một branch riêng, sau đó mở pull request vào `main`. Pull request chỉ được merge khi CI chạy thành công.
- Những thay đổi ảnh hưởng đến người dùng được ghi vào mục "Chưa phát hành" của [CHANGELOG.md](CHANGELOG.md).

## Thêm thư viện

Chỉ sử dụng thư viện có giấy phép nguồn mở được OSI công nhận. Không sao chép mã nguồn của dự án khác vào repo.

1. Khai báo thư viện trong `pyproject.toml`.
2. Thêm một mô tả ngắn cho thư viện vào `DESCRIPTIONS` trong `scripts/dependencies.py`.
3. Chạy `make lock` để tạo lại lock file.
4. Chạy `pip install -r requirements-dev.txt` để cài đặt đúng các phiên bản trong lock file.
5. Chạy `make dependencies` để tạo lại [DEPENDENCIES.md](DEPENDENCIES.md).

Ở bước 5, lệnh sẽ báo lỗi "Giấy phép ngoài danh sách cho phép" nếu giấy phép của thư viện chưa có trong danh sách cho phép ở `scripts/dependencies.py`. Khi đó, hãy mở một issue để thảo luận trước khi thêm thư viện.

## Thêm hoặc đổi phiên bản image Docker

Chỉ sử dụng phần mềm có giấy phép nguồn mở được OSI công nhận. Mỗi image phải ghi rõ phiên bản và không dùng tag `latest`.

1. Sửa dòng `image` trong `src/saigonos/stack/compose.yaml`.
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

## Thay đổi realm của Keycloak

Keycloak chỉ đọc file `src/saigonos/stack/config/keycloak/realm.json` một lần khi tạo realm `saigonos`. Do đó, không thêm thiết lập mới vào file này.

Thiết lập mới của realm được thêm vào script `setup-realm.lua` trong cùng thư mục. Mỗi lần hệ thống khởi động, service `realm` chạy script này và gọi Admin REST API của Keycloak. Script tuân theo các quy tắc sau:

- Chỉ thêm thiết lập còn thiếu. Khi thiết lập đã có, script không ghi đè, vì quản trị viên có thể đã sửa thiết lập đó.
- Chạy lại nhiều lần vẫn cho cùng một kết quả.
- In một dòng cho mỗi thiết lập vừa thêm.

Mỗi thiết lập mới cần một kiểm thử tích hợp. Kiểm thử xóa thiết lập khỏi realm, chạy `saigonos up` rồi kiểm tra thiết lập đã được thêm lại. Cách này giả lập một realm được tạo từ phiên bản cũ.

## Phát hành phiên bản mới

Phần này dành cho maintainer của repo.

1. Cập nhật `version` trong `pyproject.toml` thành số phiên bản mới, sau đó chạy lại `pip install --no-deps -e .`.
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
