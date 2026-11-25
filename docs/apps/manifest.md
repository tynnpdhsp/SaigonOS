<!-- SPDX-License-Identifier: Apache-2.0 -->
# Bản khai và cài đặt ứng dụng

Mỗi ứng dụng là một thư mục có file bản khai `saigonos-app.json`. Bản khai cho biết tên, phiên bản, các role của ứng dụng và các thư mục chứa file SQL, file BPMN và giao diện. Ứng dụng được cài đặt vào hệ thống đang chạy bằng một lệnh, không cần sửa mã của lõi. Ví dụ trên trang này dùng ứng dụng mẫu trong thư mục [`examples/phong-may`](https://github.com/tynnpdhsp/SaigonOS/tree/main/examples/phong-may).

## Bản khai

Ví dụ bản khai của một ứng dụng đặt phòng máy có hai role:

```json
{
  "$schema": "https://raw.githubusercontent.com/tynnpdhsp/SaigonOS/main/schemas/saigonos-app.schema.json",
  "name": "phong-may",
  "title": "Đặt phòng máy",
  "version": "0.1.0",
  "roles": [
    { "name": "phong-may.giao-vien", "description": "Gửi đơn đặt phòng và xem đơn của mình" },
    { "name": "phong-may.phu-trach", "description": "Duyệt đơn và xem mọi đơn" }
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
| `database` | Không | Thư mục chứa file SQL, có ít nhất một file `.sql`, như ở trang [Dữ liệu và API](database.md) |
| `processes` | Không | Thư mục chứa file BPMN, có ít nhất một file `.bpmn`, như ở trang [Quy trình](workflow.md) |
| `ui` | Không | Thư mục chứa giao diện, có file `index.html`, như ở trang [Giao diện](ui.md) |
| `access` | Không | Danh sách luật truy cập API của ứng dụng, tối đa 20 luật, như ở trang [Luật truy cập của ứng dụng](access-rules.md) |
| `search` | Không | Danh sách bảng cần tìm kiếm toàn văn, tối đa 20 bảng, như ở trang [Tìm kiếm](search.md) |
| `archive` | Không | Danh sách bảng có dòng cũ được chuyển xuống hồ dữ liệu, tối đa 20 bảng, như ở trang [Lưu trữ và chốt số liệu](archive.md) |
| `snapshots` | Không | Danh sách view hoặc bảng được chốt số liệu theo tháng, tối đa 20 mục, như ở trang [Lưu trữ và chốt số liệu](archive.md) |

Bản khai tuân theo các quy tắc sau:

- Tên ứng dụng gồm các cụm chữ thường không dấu và chữ số, nối với nhau bằng một dấu gạch ngang. Tên bắt đầu bằng chữ cái và dài tối đa 32 ký tự. Ví dụ: `phong-may`, `don-tu-2`.
- Tên ứng dụng không bắt đầu bằng `pg-` và không trùng các tên mà lõi đã dùng cho schema, role của cơ sở dữ liệu, client của Keycloak, đường dẫn của API Gateway và catalog, schema của DuckDB khi đọc hồ dữ liệu. Các tên đó gồm `account`, `account-console`, `admin-cli`, `anon`, `api`, `apps`, `auth`, `auth-admin`, `authenticated`, `authenticator`, `broker`, `centrifugo`, `core`, `core-service`, `grafana`, `information-schema`, `keycloak`, `lake`, `main`, `memory`, `operaton`, `postgres`, `public`, `realm-management`, `realtime`, `saigonos`, `security-admin-console`, `snapshots`, `system`, `temp` và `workflow`.
- Tên role có dạng `<tên ứng dụng>.<vai trò>`, ví dụ `phong-may.phu-trach`. Vai trò viết theo quy tắc của tên ứng dụng. Tên role dài tối đa 64 ký tự và không được khai báo hai lần.
- Tên hiển thị dài tối đa 100 ký tự, mô tả của role dài tối đa 255 ký tự. Hai giá trị này không được để trống, không có khoảng trắng ở đầu hoặc cuối và không chứa ký tự điều khiển.
- Đường dẫn của thư mục tính từ thư mục ứng dụng, ví dụ `ui` hoặc `web/dist`, và không trỏ ra ngoài thư mục ứng dụng. Ba thư mục không trùng nhau và không nằm trong nhau.
- Bản khai và các thư mục đã khai không chứa symlink, pipe, socket hay file thiết bị. Mọi file và thư mục con đều phải đọc được.
- Bản khai chỉ có các trường trong bảng trên. Trường viết sai chính tả bị báo lỗi.

JSON Schema của bản khai nằm trong file [schemas/saigonos-app.schema.json](https://github.com/tynnpdhsp/SaigonOS/blob/main/schemas/saigonos-app.schema.json).

## Soát ứng dụng

Lệnh sau soát bản khai và các thư mục của ứng dụng mẫu. Lệnh được chạy trong thư mục `SaigonOS` đã tạo bằng `git clone`:

```bash
saigonos apply --check examples/phong-may
```

Hệ thống không cần đang chạy, chỉ cần thư mục làm việc đã được tạo bằng lệnh `saigonos init`. Khi không có lỗi, lệnh in một dòng như sau:

```text
Ứng dụng phong-may 0.1.0 không có lỗi.
```

Khi có lỗi, lệnh in mọi lỗi tìm thấy rồi kết thúc với mã thoát 1. Mỗi dòng bắt đầu bằng vị trí của lỗi trong bản khai. Ví dụ, bản khai có phiên bản `1.0`, có thêm role `don-tu.quan-ly` và thư mục `ui` thiếu file `index.html`:

```text
Ứng dụng có 3 lỗi:
- version: Phiên bản phải theo Semantic Versioning, ví dụ 1.0.0 hoặc 1.0.0-beta.1.
- roles[4].name: Tên role phải bắt đầu bằng "phong-may.".
- ui: Thư mục "ui" không có file index.html.
```

Lệnh soát cả các file BPMN theo các quy tắc ở trang [Quy trình](workflow.md#file-bpmn-của-ứng-dụng). Lỗi trong file BPMN có tên file và số dòng. Cảnh báo được in trước dòng kết quả và không làm lệnh kết thúc với mã thoát 1.

Cũng có thể soát bằng Docker Compose sau khi chép thư mục ứng dụng vào thư mục `apps` của thư mục làm việc. Khi đó, mọi file của ứng dụng cần quyền đọc cho mọi tài khoản, ví dụ quyền `644`, và mọi thư mục cần quyền `755`.

```bash
cp -r examples/phong-may ~/saigonos/apps/
cd ~/saigonos
docker compose run --rm apps check phong-may
```

## Cài đặt ứng dụng

Khi hệ thống đang chạy, lệnh sau cài đặt ứng dụng mẫu vào hệ thống:

```bash
saigonos apply examples/phong-may
```

Lệnh thực hiện các bước sau:

1. Soát ứng dụng như mục trên. Khi có lỗi, lệnh dừng và không thay đổi gì.
2. Chép bản khai và các thư mục đã khai vào thư mục `apps/phong-may` của thư mục làm việc. Các file khác, ví dụ thư mục `.git`, không được chép.
3. Tạo schema, chạy các file SQL, tạo realm role và client trên Keycloak, tạo route trên APISIX, rồi triển khai các file BPMN vào Operaton.

Ở lần cài đặt đầu tiên, lệnh in các dòng sau:

```text
Đã tạo schema phong_may, role phong_may và role phong_may_user của ứng dụng.
Đã chạy file 0001_phong.sql.
Đã chạy file 0002_nguoi_dung.sql.
Đã chạy file 0003_don.sql.
Đã chạy file 0004_quy_trinh.sql.
Đã tạo realm role phong-may.giao-vien.
Đã tạo realm role phong-may.phu-trach.
Đã tạo realm role phong-may.chuyen-vien.
Đã tạo realm role phong-may.hoc-sinh.
Đã tạo client phong-may.
Đã tạo route app-phong-may.
Đã triển khai file dat-phong.bpmn: quy trình phong_may.dat_phong, phiên bản 1.
Đã cài đặt ứng dụng phong-may 0.1.0.
```

Mỗi lần chạy, lệnh chỉ in những gì đã thay đổi. Khi ứng dụng không đổi, lệnh chỉ in dòng `Không có gì thay đổi.` Khi cài đặt lỗi, lệnh kết thúc với mã thoát 1 và thư mục `apps/phong-may` được trả về bản đã cài đặt thành công gần nhất. Khi Keycloak, APISIX hay cơ sở dữ liệu đã có client, route, role hoặc schema trùng tên mà không do SaigonOS tạo cho ứng dụng, lệnh dừng và không đụng tới chúng.

Cũng có thể cài đặt bằng Docker Compose sau khi chép thư mục ứng dụng vào thư mục `apps`. Tên thư mục phải trùng tên ứng dụng:

```bash
cp -r examples/phong-may ~/saigonos/apps/
cd ~/saigonos
docker compose run --rm apps apply phong-may
```

## Gỡ ứng dụng

```bash
saigonos remove phong-may
```

Lệnh gỡ route, client và giao diện của ứng dụng, tạm dừng các quy trình của ứng dụng, rồi xóa bản chép trong thư mục `apps`. Schema, dữ liệu, các role và việc gán role cho người dùng được giữ lại. Khi cài đặt lại, ứng dụng dùng tiếp dữ liệu cũ, các file SQL đã chạy không chạy lại và các quy trình đã tạm dừng được chạy lại.

Để xóa hẳn ứng dụng cùng schema, dữ liệu, role, thông báo, hàng đợi gửi tin, các bản triển khai và lịch sử quy trình trên Operaton, thêm tùy chọn `--purge`:

```bash
saigonos remove phong-may --purge
```

Lệnh hỏi lại và chỉ xóa khi người dùng gõ đúng tên ứng dụng. Tùy chọn `--yes` bỏ qua câu hỏi này. Audit log của các bảng của ứng dụng được giữ lại.

Khi gỡ bằng Docker Compose, bản chép trong thư mục `apps` được xóa bằng tay:

```bash
cd ~/saigonos
docker compose run --rm apps remove phong-may
rm -r apps/phong-may
```
