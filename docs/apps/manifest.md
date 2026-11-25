<!-- SPDX-License-Identifier: Apache-2.0 -->
# Bản khai và cài đặt ứng dụng

Mỗi ứng dụng là một thư mục có file bản khai `saigonos-app.json`. Bản khai cho biết tên, phiên bản, các realm role của ứng dụng và các thư mục chứa file SQL, file BPMN và giao diện.

## Bản khai

Ví dụ bản khai của một ứng dụng xin nghỉ phép:

```json
{
  "$schema": "https://raw.githubusercontent.com/tynnpdhsp/SaigonOS/main/schemas/saigonos-app.schema.json",
  "name": "nghi-phep",
  "title": "Nghỉ phép",
  "version": "0.1.0",
  "roles": [
    { "name": "nghi-phep.nhan-vien", "description": "Gửi đơn và xem đơn của mình" },
    { "name": "nghi-phep.quan-ly", "description": "Duyệt đơn của nhân viên" }
  ],
  "database": "database",
  "processes": "processes",
  "ui": "ui"
}
```

| Trường | Bắt buộc | Ý nghĩa |
|---|---|---|
| `$schema` | Không | Địa chỉ JSON Schema của bản khai. Trình soạn thảo như VS Code dùng địa chỉ này để kiểm tra và gợi ý khi viết bản khai |
| `name` | Có | Tên ứng dụng |
| `title` | Có | Tên hiển thị của ứng dụng |
| `version` | Có | Phiên bản của ứng dụng theo [Semantic Versioning](https://semver.org/lang/vi/), ví dụ `1.2.0` |
| `roles` | Có | Danh sách realm role của ứng dụng, có ít nhất một role. Mỗi role gồm tên `name` và mô tả `description` |
| `database` | Không | Thư mục chứa file SQL, có ít nhất một file `.sql` |
| `processes` | Không | Thư mục chứa file BPMN, có ít nhất một file `.bpmn` |
| `ui` | Không | Thư mục chứa giao diện, có file `index.html` |
| `access` | Không | Danh sách luật truy cập API của ứng dụng, tối đa 20 luật, như mục [Luật truy cập của ứng dụng](access-rules.md) |
| `search` | Không | Danh sách bảng cần tìm kiếm toàn văn, tối đa 20 bảng, như mục [Tìm kiếm trong ứng dụng](search.md) |
| `archive` | Không | Danh sách bảng có dòng cũ được chuyển xuống hồ dữ liệu, tối đa 20 bảng, như mục [Lưu trữ và chốt số liệu của ứng dụng](archive.md) |
| `snapshots` | Không | Danh sách view hoặc bảng được chốt số liệu theo tháng, tối đa 20 mục, như mục [Lưu trữ và chốt số liệu của ứng dụng](archive.md) |

Bản khai tuân theo các quy tắc sau:

- Tên ứng dụng gồm các cụm chữ thường không dấu và chữ số, nối với nhau bằng một dấu gạch ngang. Tên bắt đầu bằng chữ cái và dài tối đa 32 ký tự. Ví dụ: `nghi-phep`, `don-tu-2`.
- Tên ứng dụng không bắt đầu bằng `pg-` và không trùng các tên mà lõi đã dùng cho schema, role của cơ sở dữ liệu, client của Keycloak, đường dẫn của API Gateway và catalog, schema của DuckDB khi đọc hồ dữ liệu. Các tên đó gồm `account`, `account-console`, `admin-cli`, `anon`, `api`, `apps`, `auth`, `auth-admin`, `authenticated`, `authenticator`, `broker`, `centrifugo`, `core`, `core-service`, `grafana`, `information-schema`, `keycloak`, `lake`, `main`, `memory`, `operaton`, `postgres`, `public`, `realm-management`, `realtime`, `saigonos`, `security-admin-console`, `snapshots`, `system`, `temp` và `workflow`.
- Tên role có dạng `<tên ứng dụng>.<vai trò>`, ví dụ `nghi-phep.quan-ly`. Vai trò viết theo quy tắc của tên ứng dụng. Tên role dài tối đa 64 ký tự và không được khai báo hai lần.
- Tên hiển thị dài tối đa 100 ký tự, mô tả của role dài tối đa 255 ký tự. Hai giá trị này không được để trống, không có khoảng trắng ở đầu hoặc cuối và không chứa ký tự điều khiển.
- Đường dẫn của thư mục tính từ thư mục ứng dụng, ví dụ `ui` hoặc `web/dist`. Mỗi cấp gồm chữ cái không dấu, chữ số, dấu chấm, dấu gạch ngang, dấu gạch dưới và không bắt đầu bằng dấu chấm. Do đó, đường dẫn không trỏ ra ngoài thư mục ứng dụng được. Ba thư mục không trùng nhau và không nằm trong nhau.
- Bản khai và các thư mục đã khai không chứa symlink, pipe, socket hay file thiết bị. Mọi file và thư mục con đều phải đọc được.
- Bản khai chỉ có các trường trong bảng trên. Trường viết sai chính tả bị báo lỗi.

JSON Schema của bản khai nằm trong file [schemas/saigonos-app.schema.json](https://github.com/tynnpdhsp/SaigonOS/blob/main/schemas/saigonos-app.schema.json).

## Soát ứng dụng

Lệnh sau soát bản khai và các thư mục của ứng dụng trong thư mục `./nghi-phep`:

```bash
saigonos apply --check ./nghi-phep
```

Thư mục làm việc phải được tạo bằng lệnh `saigonos init` trước đó, nhưng hệ thống không cần đang chạy. Lệnh chạy service `apps` bằng Docker Compose. Service này dùng image của service `core` và chỉ chạy khi được gọi. Mỗi lần chạy, Docker Compose build lại image này. Nhờ cache của Docker, việc build chỉ mất vài giây. Lần build đầu tiên phải tải các thư viện của service `core` nên lâu hơn.

Khi không có lỗi, lệnh in một dòng như sau:

```text
Ứng dụng nghi-phep 0.1.0 không có lỗi.
```

Khi có lỗi, lệnh in mọi lỗi tìm thấy rồi kết thúc với mã thoát 1. Mỗi dòng bắt đầu bằng vị trí của lỗi trong bản khai, ví dụ:

```text
Ứng dụng có 3 lỗi:
- version: Phiên bản phải theo Semantic Versioning, ví dụ 1.0.0 hoặc 1.0.0-beta.1.
- roles[1].name: Tên role phải bắt đầu bằng "nghi-phep.".
- ui: Thư mục "ui" không có file index.html.
```

Lệnh soát cả các file BPMN trong thư mục `processes` theo mục [Quy trình của ứng dụng](workflow.md#quy-trình-của-ứng-dụng). Lỗi trong file BPMN có tên file và số dòng, ví dụ `- processes: "processes/duyet.bpmn", dòng 12: Thẻ scriptTask chạy script trong Operaton nên không được dùng.` Cảnh báo được in trước dòng kết quả và không làm lệnh kết thúc với mã thoát 1.

Lệnh soát ở trên chạy service `apps` bằng tài khoản đang dùng. Cũng có thể soát bằng Docker Compose sau khi chép thư mục ứng dụng vào thư mục `apps` của thư mục làm việc:

```bash
cp -r ./nghi-phep ~/saigonos/apps/
cd ~/saigonos
docker compose run --rm apps check nghi-phep
```

Khi gọi theo cách này, service `apps` chạy bằng tài khoản `nobody` của container. Do đó, mọi file của ứng dụng cần quyền đọc cho mọi tài khoản, ví dụ quyền `644`, và mọi thư mục cần quyền `755`.

## Cài đặt ứng dụng

Khi hệ thống đang chạy, lệnh sau cài đặt ứng dụng trong thư mục `./nghi-phep` vào hệ thống:

```bash
saigonos apply ./nghi-phep
```

Lệnh thực hiện các bước sau:

1. Soát ứng dụng như mục [Soát ứng dụng](#soát-ứng-dụng). Khi có lỗi, lệnh dừng và không thay đổi gì.
2. Chép bản khai và các thư mục đã khai vào thư mục `apps/<tên ứng dụng>` của thư mục làm việc. Các file khác trong thư mục ứng dụng, ví dụ thư mục `.git`, không được chép.
3. Chạy lệnh `apply` của service `apps`. Lệnh này soát lại bản đã chép rồi cài đặt ứng dụng vào cơ sở dữ liệu như mục [File SQL của ứng dụng](database.md#file-sql-của-ứng-dụng), vào Keycloak như mục [Đăng nhập vào ứng dụng](login.md), vào APISIX như mục [Gọi API của ứng dụng](database.md#gọi-api-của-ứng-dụng) và vào Operaton như mục [Quy trình của ứng dụng](workflow.md#quy-trình-của-ứng-dụng).

Ở lần cài đặt đầu tiên, lệnh in các dòng sau:

```text
Đã tạo schema nghi_phep, role nghi_phep và role nghi_phep_user của ứng dụng.
Đã chạy file 0001_don.sql.
Đã chạy file 0002_duyet.sql.
Đã tạo realm role nghi-phep.nhan-vien.
Đã tạo realm role nghi-phep.quan-ly.
Đã tạo client nghi-phep.
Đã tạo route app-nghi-phep.
Đã triển khai file duyet.bpmn: quy trình nghi_phep.duyet, phiên bản 1.
Đã cài đặt ứng dụng nghi-phep 0.1.0.
```

Khi cài đặt lỗi, lệnh kết thúc với mã thoát 1 và thư mục `apps/nghi-phep` được trả về bản đã cài đặt thành công gần nhất. Mỗi lần chạy, lệnh chỉ in những gì đã thay đổi. Chạy lại lệnh khi ứng dụng không đổi thì cơ sở dữ liệu, Keycloak, APISIX và Operaton không thay đổi, và lệnh chỉ in dòng `Không có gì thay đổi.`

Cũng có thể cài đặt bằng Docker Compose sau khi chép thư mục ứng dụng vào thư mục `apps` của thư mục làm việc. Tên thư mục phải trùng tên ứng dụng:

```bash
cp -r ./nghi-phep ~/saigonos/apps/
cd ~/saigonos
docker compose run --rm apps apply nghi-phep
```

Service `apps` giữ mật khẩu superuser của PostgreSQL, mật khẩu của tài khoản `admin` trong realm master của Keycloak và khóa Admin API của APISIX. Service này chỉ chạy khi được gọi. Service `core` không có ba giá trị này. Để triển khai file BPMN, service `apps` dùng tài khoản `core` của Operaton giống service `core`.

## Gỡ ứng dụng

Lệnh sau gỡ ứng dụng `nghi-phep` khỏi hệ thống:

```bash
saigonos remove nghi-phep
```

Lệnh gỡ route của ứng dụng trên APISIX và client trên Keycloak, tạm dừng các quy trình của ứng dụng cùng các quy trình đang chạy trên Operaton, rồi bỏ schema của ứng dụng khỏi API. Giao diện của ứng dụng không còn được phục vụ. Bản chép của ứng dụng trong thư mục `apps` bị xóa. Schema, dữ liệu, các role và việc gán role cho người dùng được giữ lại. Cài đặt lại ứng dụng thì dùng tiếp dữ liệu cũ, các file SQL đã chạy không chạy lại và các quy trình đã tạm dừng được chạy lại.

Để xóa hẳn ứng dụng cùng schema, dữ liệu, role, thông báo, hàng đợi gửi tin và các bản triển khai trên Operaton, thêm tùy chọn `--purge`:

```bash
saigonos remove nghi-phep --purge
```

Lệnh hỏi lại và chỉ xóa khi người dùng gõ đúng tên ứng dụng. Khi chạy trong script, thêm tùy chọn `--yes` để bỏ qua câu hỏi. Lịch sử của quy trình cũng bị xóa. Audit log của các bảng của ứng dụng được giữ lại.

Cũng có thể gỡ bằng Docker Compose. Khi đó, xóa bản chép trong thư mục `apps` bằng tay:

```bash
cd ~/saigonos
docker compose run --rm apps remove nghi-phep
rm -r apps/nghi-phep
```
