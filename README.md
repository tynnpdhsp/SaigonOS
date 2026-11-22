<!-- SPDX-License-Identifier: Apache-2.0 -->
# SaigonOS

SaigonOS là một hệ điều hành chuyển đổi số (DX-OS) nguồn mở. Phần lõi được xây dựng từ các phần mềm nguồn mở và không có giao diện cho người dùng cuối. Mỗi ứng dụng chỉ cần phát triển phần giao diện và gọi các service của lõi.

Lõi cung cấp bốn service chính:

- Quản lý định danh và đăng nhập một lần (Identity/SSO)
- Cổng API (API Gateway)
- Quản lý dữ liệu có cấu trúc và phi cấu trúc
- Luồng công việc (Workflow)

Phiên bản hiện tại cung cấp đăng nhập một lần, API Gateway và REST API cho dữ liệu có cấu trúc. Dữ liệu phi cấu trúc được lưu trong kho file có quét mã độc. Luồng công việc chạy các quy trình BPMN bằng Operaton, gồm việc của người, bước máy làm, form và hẹn giờ. Ứng dụng nhận cập nhật tức thời qua WebSocket bằng Centrifugo. Thông báo cho người dùng được lưu trong hệ thống và có thể được gửi thêm qua Telegram hoặc email. Các thay đổi được ghi lại trong [CHANGELOG.md](CHANGELOG.md).

## Mục lục

- [Yêu cầu hệ thống](#yêu-cầu-hệ-thống)
- [Cài đặt](#cài-đặt)
- [Truy cập hệ thống](#truy-cập-hệ-thống)
- [Tài khoản quản trị](#tài-khoản-quản-trị)
- [Tài liệu API](#tài-liệu-api)
- [API của service core](#api-của-service-core)
- [Tải file lên](#tải-file-lên)
- [Tải file về](#tải-file-về)
- [Cấu hình](#cấu-hình)
- [Khởi động và dừng](#khởi-động-và-dừng)
- [Triển khai trên máy chủ chưa có reverse proxy](#triển-khai-trên-máy-chủ-chưa-có-reverse-proxy)
- [Triển khai trên máy chủ đã có reverse proxy](#triển-khai-trên-máy-chủ-đã-có-reverse-proxy)
- [Kiểm tra audit log](#kiểm-tra-audit-log)
- [Quét mã độc](#quét-mã-độc)
- [Quy trình](#quy-trình)
- [Cập nhật tức thời](#cập-nhật-tức-thời)
- [Thông báo cho người dùng](#thông-báo-cho-người-dùng)
- [Ứng dụng](#ứng-dụng)
- [Cập nhật phiên bản](#cập-nhật-phiên-bản)
- [Tham gia phát triển](#tham-gia-phát-triển)
- [Giấy phép](#giấy-phép)

## Yêu cầu hệ thống

- Hệ điều hành Linux. SaigonOS được kiểm thử trên Ubuntu 24.04.
- Python 3.11 trở lên và pip.
- Docker Engine 25.0 trở lên, Docker Compose 2.20.2 trở lên và Docker Buildx. Ba thành phần này có sẵn khi cài Docker theo hướng dẫn của Docker. Tài khoản cài đặt chạy được lệnh `docker` mà không cần `sudo`.
- Git.
- Kết nối Internet để tải các image Docker, các thư viện của service `core` và bản cập nhật của cơ sở dữ liệu mã độc.
- Khoảng 6 GB dung lượng đĩa cho các image Docker và dữ liệu ban đầu, chưa tính các file được tải lên.
- Khoảng 3 GB RAM cho các service.

## Cài đặt

Việc cài đặt chỉ cần pip và Docker Compose. Mọi cấu hình đều có giá trị mặc định. Do đó, không cần chỉnh sửa file cấu hình nào.

### 1. Cài đặt package `saigonos`

Nên cài đặt trong một môi trường riêng, ví dụ môi trường conda:

```bash
conda create -n saigonos python=3.12
conda activate saigonos
git clone https://github.com/tynnpdhsp/SaigonOS.git
cd SaigonOS
pip install .
```

Mã nguồn của từng phiên bản cũng có ở trang [Releases](https://github.com/tynnpdhsp/SaigonOS/releases). Tải file `saigonos-X.Y.Z.tar.gz`, giải nén rồi chạy `pip install .` trong thư mục vừa giải nén.

### 2. Tạo thư mục làm việc

```bash
saigonos init
```

Lệnh này tạo thư mục làm việc `~/saigonos`. Thư mục bao gồm file `compose.yaml`, thư mục `config`, thư mục `apps` chứa các ứng dụng và file `.env`. File `.env` chứa các mật khẩu được tạo ngẫu nhiên.

Hệ thống dùng các cổng 9080, 9180, 9280, 9380 và 9480. Nếu một trong các cổng này đang được chương trình khác sử dụng, hãy chọn cổng khác theo mục [Cấu hình](#cấu-hình).

### 3. Khởi động các service

```bash
cd ~/saigonos
docker compose up -d --wait
```

Ở lần chạy đầu tiên, Docker tải các image nên lệnh mất vài phút. Ở những lần sau, lệnh mất khoảng một phút.

### 4. Kiểm tra hệ thống

```bash
saigonos doctor
```

Khi mọi service hoạt động bình thường, lệnh in ra kết quả sau:

```text
BÌNH THƯỜNG    apisix        đang chạy
BÌNH THƯỜNG    centrifugo    đang chạy
BÌNH THƯỜNG    clamav        đang chạy
BÌNH THƯỜNG    core          đang chạy
BÌNH THƯỜNG    databases     đã chạy xong
BÌNH THƯỜNG    etcd          đang chạy
BÌNH THƯỜNG    freshclam     đang chạy
BÌNH THƯỜNG    jwks          đã chạy xong
BÌNH THƯỜNG    keycloak      đang chạy
BÌNH THƯỜNG    migrate       đã chạy xong
BÌNH THƯỜNG    operaton      đang chạy
BÌNH THƯỜNG    postgres      đang chạy
BÌNH THƯỜNG    postgrest     đang chạy
BÌNH THƯỜNG    processes     đã chạy xong
BÌNH THƯỜNG    realm         đã chạy xong
BÌNH THƯỜNG    routes        đã chạy xong
BÌNH THƯỜNG    seaweedfs     đang chạy
BÌNH THƯỜNG    Đăng nhập     Keycloak trả lời tại http://localhost:9080/auth
BÌNH THƯỜNG    API           PostgREST trả lời, access token không hợp lệ bị từ chối
BÌNH THƯỜNG    Core API      service core trả lời, access token không hợp lệ bị từ chối
BÌNH THƯỜNG    Operaton      Operaton chuyển tới trang đăng nhập, REST của Operaton bị chặn
BÌNH THƯỜNG    Centrifugo    Centrifugo nhận kết nối WebSocket, API của Centrifugo bị chặn
Hệ thống hoạt động bình thường.
```

## Truy cập hệ thống

Với cấu hình mặc định, hệ thống chỉ truy cập được từ chính máy cài đặt và có các địa chỉ sau:

| Địa chỉ | Nội dung | Thông tin đăng nhập |
|---|---|---|
| http://localhost:9080/auth/admin/saigonos/console/ | Admin Console của realm `saigonos`, dùng để quản lý người dùng | Tài khoản quản trị của realm `saigonos`, đăng nhập bằng mật khẩu và OTP. Cách tạo tài khoản được trình bày ở mục [Tài khoản quản trị](#tài-khoản-quản-trị) |
| http://localhost:9080/operaton/ | Cockpit, Tasklist và Admin của [Operaton](#quy-trình), dùng để theo dõi và quản lý các quy trình | Tài khoản quản trị của realm `saigonos`, đăng nhập bằng mật khẩu và OTP |
| http://localhost:9280/auth/admin/master/console/ | Admin Console của realm master, chỉ truy cập được từ chính máy cài đặt | Tài khoản `admin`, mật khẩu là giá trị `KEYCLOAK_ADMIN_PASSWORD` |
| http://127.0.0.1:9180/ui/ | Dashboard của APISIX, chỉ truy cập được từ chính máy cài đặt | Khóa quản trị (Admin Key) là giá trị `APISIX_ADMIN_KEY` |
| http://127.0.0.1:9380/ | Admin UI của SeaweedFS, dùng để xem các bucket và file, chỉ truy cập được từ chính máy cài đặt | Tài khoản `admin`, mật khẩu là giá trị `SEAWEEDFS_ADMIN_PASSWORD` |
| http://127.0.0.1:9480/ | Admin web của Centrifugo, dùng để xem số kết nối và gọi thử API của server, chỉ truy cập được từ chính máy cài đặt | Mật khẩu là giá trị `CENTRIFUGO_ADMIN_PASSWORD` |
| http://localhost:9080/api/ | REST API của PostgREST và [tài liệu API](#tài-liệu-api) | Access token do Keycloak cấp. Lời gọi không có access token chỉ dùng được các bảng và hàm đã cấp cho role `anon` |
| http://localhost:9080/core/openapi.json | Tài liệu OpenAPI của [service core](#api-của-service-core) | Không cần đăng nhập. Các API trong tài liệu cần access token do Keycloak cấp, trừ `/core/health` và [đường dẫn tải về](#tải-file-về) |
| ws://localhost:9080/realtime/connection/websocket | Kết nối WebSocket của Centrifugo, dùng để nhận [cập nhật tức thời](#cập-nhật-tức-thời) | Access token do Keycloak cấp, gửi trong lệnh connect |

Các giá trị trên nằm trong file `~/saigonos/.env`. Ví dụ, để xem mật khẩu quản trị của Keycloak:

```bash
grep KEYCLOAK_ADMIN_PASSWORD ~/saigonos/.env
```

Mỗi khi hệ thống khởi động, service `realm` đăng nhập Keycloak bằng tài khoản `admin` này để cập nhật realm master và realm `saigonos`. Service này chỉ đăng nhập bằng mật khẩu. Do đó, không xóa tài khoản này và không bật OTP cho tài khoản này. Sau khi đổi mật khẩu của tài khoản trong Admin Console, cần ghi mật khẩu mới vào dòng `KEYCLOAK_ADMIN_PASSWORD` của file `.env`.

## Tài khoản quản trị

Keycloak có hai loại tài khoản quản trị:

- Tài khoản `admin` của realm master có toàn quyền trên Keycloak. Tài khoản này đăng nhập bằng mật khẩu và chỉ dùng được trên chính máy cài đặt.
- Tài khoản quản trị của realm `saigonos` chỉ quản lý được realm `saigonos`, ví dụ người dùng, role và client. Tài khoản này đăng nhập bằng mật khẩu và OTP, dùng được từ mọi máy. Nên dùng loại tài khoản này cho công việc hằng ngày.

### Realm master

API Gateway trả về mã 404 cho mọi địa chỉ của realm master. Realm master chỉ mở qua cổng 9280 của Keycloak trên chính máy cài đặt. Realm master khóa tạm một tài khoản sau nhiều lần đăng nhập sai. Mỗi khi hệ thống khởi động, service `realm` bật lại tính năng này nếu tính năng đã bị tắt.

Để mở Admin Console của realm master từ một máy khác, tạo SSH tunnel tới máy cài đặt. Thay `ubuntu@dx.example.com` bằng tài khoản SSH và địa chỉ của máy cài đặt.

```bash
ssh -L 9280:127.0.0.1:9280 ubuntu@dx.example.com
```

Sau đó, mở địa chỉ http://localhost:9280/auth/admin/master/console/ trên máy đang dùng. Cổng trên máy đang dùng cũng phải là 9280, vì Keycloak tạo các địa chỉ của realm master theo cổng này.

Trên máy chủ có tên miền, có thể kiểm tra realm master từ một máy khác bằng lệnh sau. Kết quả đúng là `404`.

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://dx.example.com/auth/realms/master
```

### Tạo tài khoản quản trị của realm saigonos

Tài khoản quản trị của realm `saigonos` có realm role `admin`. Các lệnh sau dùng công cụ `kcadm.sh` có sẵn trong container của Keycloak. Thay `quantri` và các thông tin đi kèm bằng giá trị thật.

```bash
cd ~/saigonos
docker compose exec keycloak /opt/keycloak/bin/kcadm.sh config credentials --server http://localhost:8080/auth --realm master --user admin
docker compose exec keycloak /opt/keycloak/bin/kcadm.sh create users -r saigonos -s username=quantri -s email=quantri@example.com -s firstName=Quản -s lastName=Trị -s enabled=true -s 'requiredActions=["CONFIGURE_TOTP"]'
docker compose exec keycloak /opt/keycloak/bin/kcadm.sh set-password -r saigonos --username quantri
docker compose exec keycloak /opt/keycloak/bin/kcadm.sh add-roles -r saigonos --uusername quantri --rolename admin
```

Lệnh thứ hai hỏi mật khẩu của tài khoản `admin`, tức giá trị `KEYCLOAK_ADMIN_PASSWORD`. Lệnh thứ tư hỏi mật khẩu cho tài khoản mới.

Sau đó, mở địa chỉ http://localhost:9080/auth/admin/saigonos/console/ và đăng nhập bằng tài khoản mới. Trên máy chủ có tên miền, địa chỉ này có dạng `https://dx.example.com/auth/admin/saigonos/console/`. Ở lần đăng nhập đầu tiên, Keycloak yêu cầu cài đặt OTP. Hãy quét mã QR bằng một ứng dụng xác thực, ví dụ FreeOTP hoặc Google Authenticator, rồi nhập mã gồm 6 chữ số. Từ lần sau, tài khoản đăng nhập bằng mật khẩu và mã OTP.

Trước khi cài đặt OTP, tài khoản chưa lấy được access token. Tuy vậy, người nào biết mật khẩu cũng có thể đăng nhập lần đầu và cài đặt OTP cho tài khoản. Do đó, hãy đăng nhập lần đầu ngay sau khi tạo tài khoản.

## Tài liệu API

PostgREST tự sinh tài liệu OpenAPI 2.0 cho REST API. Tài liệu nằm ở địa chỉ gốc của REST API, mặc định là http://localhost:9080/api/. Tài liệu có thể được mở bằng trình duyệt hoặc nạp vào các công cụ hỗ trợ OpenAPI 2.0, ví dụ Swagger UI.

Tài liệu chỉ liệt kê các bảng, view và hàm mà người gọi được dùng. Lời gọi không có access token nhận tài liệu theo quyền của role `anon`. Lời gọi có access token trong header `Authorization` nhận tài liệu theo quyền của role `authenticated`. Quyền được kiểm tra ở mỗi lời gọi. Do đó, sau khi một quyền được cấp hoặc thu hồi, tài liệu thay đổi ngay ở lời gọi tiếp theo.

Các địa chỉ trong tài liệu được lấy từ địa chỉ truy cập của hệ thống, tức giá trị của tùy chọn `--url`. Ví dụ, với địa chỉ truy cập `https://dx.example.com`, các lời gọi trong tài liệu bắt đầu bằng `https://dx.example.com/api`.

## API của service core

Service `core` cung cấp các API của lõi mà PostgREST không đảm nhận, ví dụ tải lên và quét mã độc file, bắt đầu quy trình và xử lý việc. Service được viết bằng FastAPI. API nằm ở địa chỉ `/core/` của API Gateway. Tài liệu OpenAPI 3.1 nằm ở địa chỉ http://localhost:9080/core/openapi.json. Ví dụ, lời gọi `GET /core/me` trả về mã người dùng, đơn vị và role mà cơ sở dữ liệu nhận được từ access token của người gọi.

API Gateway kiểm tra access token của lời gọi tới `/core` như với `/api`. Service `core` kiểm tra lại chữ ký, issuer (`iss`), thời hạn, loại token và realm role `authenticated`. Do đó, lời gọi tới thẳng service từ bên trong mạng Docker vẫn bị từ chối khi access token không hợp lệ. Service chỉ chấp nhận access token, không chấp nhận ID token. Khi Keycloak đổi khóa ký, service tự lấy khóa mới.

Service kết nối PostgreSQL bằng role `core_service`. Mỗi truy vấn chạy với role và nội dung access token của người gọi, giống PostgREST. Do đó, các hàm `core.uid()`, `core.has_role()`, `core.unit()` và chính sách phân quyền từng dòng dùng chung cho cả hai.

Image của service được Docker Compose build trên máy cài đặt từ image `python` chính thức. Các thư viện được cài từ lock file có mã băm. Ở lần khởi động đầu tiên, việc build mất khoảng một phút. Mỗi lần chạy `saigonos up`, Docker Compose build lại image. Khi mã nguồn không đổi, việc build dùng lại kết quả cũ nên chỉ mất vài giây. Với Docker Compose 2.x, container của service `core` cũng được tạo lại ở mỗi lần chạy, kể cả khi mã nguồn không đổi.

## Tải file lên

Service `core` nhận file của các ứng dụng và lưu file vào SeaweedFS. Mỗi file được tải lên bằng hai lời gọi. Cả hai lời gọi đều cần access token của người dùng đã đăng nhập.

1. Lời gọi `POST /core/files` khai báo tên, loại và dung lượng của file. Service kiểm tra ba giá trị này trước khi nhận nội dung. Khi hợp lệ, service trả về mã 201 kèm mã file và đường dẫn tải lên trong trường `upload_url`. File ở trạng thái `pending_upload`.
2. Lời gọi `PUT` tới đường dẫn tải lên gửi nội dung của file. Service tính dung lượng và mã băm SHA-256 của nội dung, rồi kiểm tra phần đầu của nội dung. Khi hợp lệ, nội dung được lưu vào bucket `quarantine` và file chuyển sang trạng thái `pending_scan`, tức chờ quét mã độc.

Ngay sau khi nhận nội dung, service `core` quét file bằng ClamAV. Việc quét chạy nền nên lời gọi `PUT` không phải chờ. Ứng dụng gọi `GET /core/files/{id}` để biết kết quả quét. Mục [Quét mã độc](#quét-mã-độc) mô tả cách quét. Khi file có trạng thái `clean`, ứng dụng tải file về theo mục [Tải file về](#tải-file-về).

Ba trường của lời gọi khai báo có cùng tên với các thuộc tính của đối tượng `File` trong trình duyệt. Ví dụ, một ứng dụng web tải file mà người dùng đã chọn như sau:

```js
const headers = { Authorization: `Bearer ${accessToken}` };
const declared = await fetch("/core/files", {
  method: "POST",
  headers: { ...headers, "Content-Type": "application/json" },
  body: JSON.stringify({ name: file.name, type: file.type, size: file.size }),
});
const { upload_url } = await declared.json();
await fetch(upload_url, { method: "PUT", headers, body: file });
```

Mỗi file chỉ nhận nội dung một lần. Khi lời gọi gửi nội dung bị từ chối, nội dung không được lưu và có thể được gửi lại. Lời gọi `GET /core/files/{id}` trả về thông tin và trạng thái của file. Bảng `core.files` có chính sách phân quyền từng dòng. Do đó, mỗi người dùng chỉ thấy file của chính mình.

Các trạng thái của file:

| Trạng thái | Ý nghĩa |
|---|---|
| `pending_upload` | Chờ gửi nội dung |
| `pending_scan` | Nội dung nằm trong bucket `quarantine` và chờ quét mã độc |
| `clean` | ClamAV không phát hiện mã độc. Nội dung đã được chuyển sang bucket `clean` và tải về được |
| `infected` | ClamAV phát hiện mã độc. Trường `malware` ghi tên mã độc. Nội dung được giữ trong bucket `quarantine` và không tải về được |

Các loại file được phép:

| Loại file | Phần mở rộng | Phần đầu của nội dung |
|---|---|---|
| `application/pdf` | `.pdf` | `%PDF-` |
| `image/jpeg` | `.jpg`, `.jpeg` | Các byte `FF D8 FF` |
| `image/png` | `.png` | Các byte `89 50 4E 47 0D 0A 1A 0A` |
| `image/webp` | `.webp` | `RIFF`, 4 byte bất kỳ, sau đó là `WEBP` |
| `text/plain` | `.txt` | 8.192 byte đầu không chứa byte 0 |
| `text/csv` | `.csv` | 8.192 byte đầu không chứa byte 0 |
| `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | `.docx` | `PK` và các byte `03 04` của file ZIP |
| `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | `.xlsx` | `PK` và các byte `03 04` của file ZIP |

Tên file phải có phần mở rộng ứng với loại file. Tên file dài tối đa 255 ký tự và không chứa ký tự điều khiển, dấu `/` hoặc dấu `\`. Văn bản mã hóa UTF-16 chứa byte 0 nên không được nhận là `text/plain` hoặc `text/csv`.

Mỗi file có dung lượng tối đa 10 MB, với 1 MB là 1.048.576 byte. Tùy chọn `--max-file-size` của lệnh `saigonos init` đổi giới hạn này. API Gateway cũng từ chối mọi lời gọi có nội dung lớn hơn giới hạn này.

Các mã lỗi của hai lời gọi:

| Mã | Lời gọi | Ý nghĩa |
|---|---|---|
| 401 | Khai báo và gửi nội dung | Thiếu access token hoặc access token không hợp lệ |
| 413 | Khai báo | Dung lượng khai báo vượt giới hạn |
| 413 | Gửi nội dung | Nội dung lớn hơn giới hạn nên API Gateway từ chối |
| 415 | Khai báo | Loại file không được phép |
| 422 | Khai báo | Tên file không hợp lệ hoặc phần mở rộng không ứng với loại file |
| 422 | Gửi nội dung | Dung lượng hoặc phần đầu của nội dung không khớp với thông tin đã khai báo |
| 404 | Gửi nội dung | Không có file với mã này hoặc file thuộc người dùng khác |
| 409 | Gửi nội dung | File đã nhận nội dung |
| 503 | Gửi nội dung | SeaweedFS chưa sẵn sàng. File vẫn ở trạng thái `pending_upload` và có thể gửi lại |

## Tải file về

Mỗi file được tải về bằng một đường dẫn có thời hạn. Ứng dụng xin đường dẫn bằng lời gọi `POST /core/files/{id}/download-url` kèm access token của người dùng đã đăng nhập. Service trả về đường dẫn trong trường `download_url` và thời điểm hết hạn trong trường `expires_at`.

Đường dẫn dùng được trong 60 giây và mở được trong trình duyệt mà không cần access token. Trong 60 giây này, đường dẫn mở được nhiều lần và bất kỳ ai có đường dẫn đều tải được file. Do đó, ứng dụng chỉ xin đường dẫn ngay trước khi tải và không lưu lại đường dẫn. Thời hạn chỉ áp dụng cho lúc mở đường dẫn. Một file lớn có thể tải xong sau thời điểm hết hạn.

Ví dụ, một ứng dụng web tải file về như sau:

```js
const reply = await fetch(`/core/files/${id}/download-url`, {
  method: "POST",
  headers: { Authorization: `Bearer ${accessToken}` },
});
const { download_url } = await reply.json();
window.location.assign(download_url);
```

Chỉ file có trạng thái `clean` mới tải về được. Người dùng chỉ xin được đường dẫn cho file mà chính sách phân quyền từng dòng của bảng `core.files` cho phép đọc. Trước khi gửi file, service đọc lại nội dung từ bucket `clean` và so với mã băm SHA-256 đã ghi.

File được gửi kèm các header `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff` và `Cache-Control: no-store`. Do đó, trình duyệt luôn lưu file về máy với tên đã khai báo, không tự đoán lại loại file và không giữ file trong bộ nhớ đệm.

Đường dẫn được ký bằng khóa `CORE_DOWNLOAD_KEY` trong file `.env`. Sau khi đổi khóa này và chạy `saigonos up`, các đường dẫn đã cấp không còn dùng được.

Các mã lỗi của hai lời gọi:

| Mã | Lời gọi | Ý nghĩa |
|---|---|---|
| 401 | Xin đường dẫn | Thiếu access token hoặc access token không hợp lệ |
| 404 | Xin đường dẫn | Không có file với mã này hoặc người gọi không được đọc file |
| 409 | Xin đường dẫn và tải về | File chưa có nội dung, đang chờ quét mã độc hoặc có mã độc |
| 403 | Tải về | Đường dẫn không hợp lệ hoặc đã hết hạn |
| 503 | Tải về | SeaweedFS chưa sẵn sàng |
| 500 | Tải về | Nội dung trong bucket `clean` không khớp mã băm đã ghi. File không được gửi |

## Cấu hình

Các giá trị cấu hình được đặt bằng tùy chọn của lệnh `saigonos init`. Lệnh này có thể chạy lại nhiều lần. Các mật khẩu đã tạo và các dòng được thêm bằng tay vào file `.env` được giữ nguyên. Riêng cấu hình Telegram và SMTP được ghi trực tiếp vào file `.env`, như ở mục [Gửi thông báo qua Telegram](#gửi-thông-báo-qua-telegram) và mục [Gửi email](#gửi-email).

| Tùy chọn | Mặc định | Ý nghĩa |
|---|---|---|
| `--home` | `~/saigonos` | Thư mục làm việc. Có thể đặt bằng biến môi trường `SAIGONOS_HOME` |
| `--http-host` | `127.0.0.1` | Địa chỉ IP mà cổng HTTP của API Gateway lắng nghe. Với giá trị mặc định, hệ thống chỉ truy cập được từ chính máy cài đặt |
| `--http-port` | `9080` | Cổng HTTP của API Gateway |
| `--admin-port` | `9180` | Cổng quản trị của APISIX, chỉ truy cập được từ chính máy cài đặt |
| `--keycloak-port` | `9280` | Cổng của Keycloak, chỉ truy cập được từ chính máy cài đặt. Admin Console của realm master dùng cổng này |
| `--seaweedfs-port` | `9380` | Cổng Admin UI của SeaweedFS, chỉ truy cập được từ chính máy cài đặt |
| `--centrifugo-port` | `9480` | Cổng API của server và Admin web của Centrifugo, chỉ truy cập được từ chính máy cài đặt |
| `--url` | `http://localhost:9080` | Địa chỉ mà người dùng truy cập hệ thống |
| `--max-file-size` | `10` | Dung lượng tối đa của một file tải lên, tính bằng MB, từ 1 đến 100. API Gateway cũng từ chối các lời gọi có nội dung lớn hơn giá trị này |
| `--caddy`, `--no-caddy` | Tắt | Bật hoặc tắt Caddy để nhận kết nối HTTPS trên máy chủ chưa có reverse proxy |

Cổng HTTP không được trùng các cổng 7085, 9090, 9091, 9180 và 9443. APISIX dùng các cổng này bên trong container.

Ví dụ, để đổi cổng HTTP thành 8080:

```bash
saigonos init --http-port 8080
saigonos up
```

Ví dụ, để các máy khác trong mạng nội bộ truy cập được hệ thống qua địa chỉ `192.168.1.10` của máy cài đặt:

```bash
saigonos init --http-host 0.0.0.0 --url http://192.168.1.10:9080
saigonos up
```

Chỉ nên dùng cách này trong một mạng nội bộ đáng tin cậy. Kết nối HTTP không được mã hóa. API Gateway cũng tin header `X-Forwarded-For` do máy trong mạng nội bộ gửi tới. Do đó, một máy trong mạng nội bộ có thể khai báo một địa chỉ IP khác với địa chỉ thật.

Keycloak chỉ chấp nhận kết nối HTTP từ các địa chỉ IP trong mạng nội bộ. Để phục vụ người dùng qua Internet, hệ thống cần HTTPS. Cách triển khai tùy theo máy chủ:

- Máy chủ chưa có reverse proxy: làm theo mục [Triển khai trên máy chủ chưa có reverse proxy](#triển-khai-trên-máy-chủ-chưa-có-reverse-proxy).
- Máy chủ đã có reverse proxy, ví dụ Nginx: làm theo mục [Triển khai trên máy chủ đã có reverse proxy](#triển-khai-trên-máy-chủ-đã-có-reverse-proxy).

## Khởi động và dừng

Hai lệnh `saigonos up` và `saigonos down` gọi Docker Compose trong thư mục làm việc. Có thể dùng trực tiếp các lệnh Docker Compose tương ứng.

| Thao tác | Lệnh `saigonos` | Lệnh Docker Compose trong `~/saigonos` |
|---|---|---|
| Khởi động | `saigonos up` | `docker compose up -d --wait` |
| Dừng và giữ dữ liệu | `saigonos down` | `docker compose down` |
| Dừng và xóa dữ liệu | `saigonos down --volumes` | `docker compose down --volumes` |

## Triển khai trên máy chủ chưa có reverse proxy

Trên máy chủ chưa có reverse proxy, SaigonOS dùng Caddy để nhận kết nối HTTPS từ người dùng. Caddy tự lấy chứng chỉ từ Let's Encrypt và tự gia hạn chứng chỉ. Caddy cũng hỗ trợ HTTP/3 và chuyển các kết nối HTTP sang HTTPS.

Caddy dùng mạng của máy chủ (host network) để thấy đúng địa chỉ IP của người dùng qua IPv4 và IPv6. Do đó, cách triển khai này chỉ dùng được trên Linux. Cổng 80 và 443 của máy chủ phải còn trống. Nếu một web server khác đang dùng hai cổng này, hãy làm theo mục [Triển khai trên máy chủ đã có reverse proxy](#triển-khai-trên-máy-chủ-đã-có-reverse-proxy).

### 1. Trỏ tên miền về máy chủ

Tạo bản ghi A trỏ tên miền về địa chỉ IPv4 của máy chủ. Nếu máy chủ có địa chỉ IPv6, tạo thêm bản ghi AAAA. Việc này cần làm trước khi bật Caddy, vì Caddy chỉ lấy được chứng chỉ khi tên miền đã trỏ đúng về máy chủ.

### 2. Mở cổng

Tường lửa của nhà cung cấp máy chủ phải mở các cổng sau:

| Cổng | Giao thức | Mục đích |
|---|---|---|
| 80 | TCP | Lấy chứng chỉ và chuyển kết nối HTTP sang HTTPS |
| 443 | TCP | Kết nối HTTPS |
| 443 | UDP | Kết nối HTTP/3 |

Caddy dùng mạng của máy chủ. Do đó, tường lửa trên máy chủ cũng phải mở các cổng này. Ví dụ, với UFW trên Ubuntu:

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
```

### 3. Bật Caddy

```bash
saigonos init --caddy --url https://dx.example.com
saigonos up
```

Trong đó `dx.example.com` là tên miền của hệ thống. Khi Caddy bật, địa chỉ truy cập phải bắt đầu bằng `https://`. Cổng HTTP của API Gateway vẫn chỉ lắng nghe trên địa chỉ `127.0.0.1`. Caddy chuyển tiếp kết nối của người dùng tới cổng này.

Lệnh `saigonos init` ghi giá trị `COMPOSE_PROFILES=caddy` vào file `.env`. Do đó, lệnh `docker compose up -d --wait` cũng khởi động Caddy. Khi chạy lại lệnh `saigonos init` không kèm tùy chọn `--caddy`, Caddy vẫn được bật.

Caddy bỏ qua các header `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host` và `X-Forwarded-Port` do người dùng tự gửi. Do đó, người dùng không thể tự khai báo một địa chỉ IP khác.

### 4. Kiểm tra hệ thống

```bash
saigonos doctor
```

Kết quả có thêm dòng của service `caddy`. Lệnh này gọi hệ thống qua địa chỉ `https://dx.example.com`. Do đó, lệnh cũng kiểm tra được chứng chỉ. Ở lần khởi động đầu tiên, Caddy cần thêm vài giây để lấy chứng chỉ. Nếu lệnh báo lỗi chứng chỉ, hãy chờ một lúc rồi chạy lại.

Sau khi triển khai, Admin Console của realm `saigonos` có địa chỉ `https://dx.example.com/auth/admin/saigonos/console/`. REST API có địa chỉ `https://dx.example.com/api/`. Admin Console của realm master và Dashboard của APISIX vẫn chỉ truy cập được từ chính máy cài đặt.

### Chứng chỉ

Chứng chỉ được lưu trong thư mục `data/caddy` của thư mục làm việc, mặc định là `~/saigonos/data/caddy`. Lệnh `saigonos down --volumes` không xóa thư mục này. Theo [giới hạn của Let's Encrypt](https://letsencrypt.org/docs/rate-limits/), một tên miền chỉ được cấp tối đa 5 chứng chỉ trong 7 ngày. Do đó, cần giữ thư mục này khi cài đặt lại hệ thống.

Thư mục `data/caddy` do Docker tạo ra nên thuộc quyền root. Để xóa thư mục này, dừng hệ thống bằng lệnh `saigonos down` rồi chạy lệnh:

```bash
sudo rm -rf ~/saigonos/data/caddy
```

Caddy gửi header `Strict-Transport-Security` (HSTS) trong các phản hồi HTTPS. Sau lần truy cập đầu tiên, trình duyệt chỉ kết nối tới tên miền này bằng HTTPS trong một năm.

### Tắt Caddy

```bash
saigonos init --no-caddy
saigonos up
```

Lệnh `saigonos up` xóa container của Caddy rồi khởi động các service còn lại. Nếu dùng trực tiếp Docker Compose, chạy lệnh `docker compose rm --stop --force caddy` trước lệnh `docker compose up -d --wait`.

Sau khi tắt Caddy, người dùng chỉ truy cập được hệ thống qua một reverse proxy khác. Cách cấu hình reverse proxy được trình bày ở mục [Triển khai trên máy chủ đã có reverse proxy](#triển-khai-trên-máy-chủ-đã-có-reverse-proxy).

## Triển khai trên máy chủ đã có reverse proxy

Trên máy chủ đã có reverse proxy, ví dụ Nginx, SaigonOS chạy sau reverse proxy đó. Reverse proxy nhận kết nối HTTPS từ người dùng và chuyển tiếp tới cổng HTTP của API Gateway trên cùng máy. Cách triển khai này không dùng Caddy.

### 1. Đặt địa chỉ truy cập

```bash
saigonos init --url https://dx.example.com
saigonos up
```

Trong đó `dx.example.com` là tên miền của hệ thống. Cổng HTTP vẫn chỉ lắng nghe trên địa chỉ `127.0.0.1`. Do đó, người dùng chỉ truy cập được hệ thống qua reverse proxy.

### 2. Cấu hình reverse proxy

Ví dụ, với Nginx và chứng chỉ do Certbot lấy từ Let's Encrypt:

```nginx
map $http_upgrade $saigonos_connection {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl;
    server_name dx.example.com;

    ssl_certificate /etc/letsencrypt/live/dx.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dx.example.com/privkey.pem;

    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:9080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $saigonos_connection;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
    }
}
```

Reverse proxy phải gửi đủ các header trong ví dụ trên. API Gateway dùng các header này để xác định địa chỉ mà người dùng truy cập và địa chỉ IP của người dùng. API Gateway chỉ tin các header này khi kết nối đến từ một địa chỉ IP trong mạng nội bộ, gồm các dải `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12` và `192.168.0.0/16`.

Header `X-Forwarded-For` được đặt bằng `$remote_addr` để người dùng không thể tự khai báo một địa chỉ IP khác.

Dòng `client_max_body_size` cho phép Nginx nhận nội dung lớn tới 10 MB, bằng giới hạn dung lượng file mặc định của SaigonOS. Nginx mặc định chỉ nhận nội dung tới 1 MB. Khi đổi giới hạn bằng tùy chọn `--max-file-size`, cần đổi cả giá trị này.

Khối `map` và ba dòng `proxy_http_version`, `Upgrade`, `Connection` cho phép Nginx chuyển tiếp kết nối WebSocket tới [Centrifugo](#cập-nhật-tức-thời). Khối `map` đặt ở ngoài khối `server` và dùng tên biến riêng của SaigonOS để không trùng với cấu hình của các site khác. Centrifugo gửi ping 25 giây một lần. Do đó, thời gian chờ mặc định 60 giây của Nginx không đóng các kết nối WebSocket đang mở.

### 3. Kiểm tra hệ thống

```bash
saigonos doctor
```

Lệnh này gọi hệ thống qua địa chỉ `https://dx.example.com`. Do đó, lệnh cũng kiểm tra được kết nối qua reverse proxy và chứng chỉ. Nếu reverse proxy không gửi đủ các header ở bước 2, lệnh báo lỗi ở mục Đăng nhập và ghi địa chỉ mà Keycloak nhận được. Nếu reverse proxy không chuyển tiếp kết nối WebSocket, lệnh báo lỗi ở mục Centrifugo.

## Kiểm tra audit log

Bảng `core.audit_log` của cơ sở dữ liệu lưu audit log. Với những bảng đã gắn hàm `core.audit()`, mỗi lần một dòng được thêm, sửa hoặc xóa đều được ghi lại. Cách gắn hàm này cho một bảng được trình bày trong [CONTRIBUTING.md](CONTRIBUTING.md#ghi-audit-log-cho-bảng).

Bảng `core.audit_log` chỉ cho phép thêm dòng. Các lệnh `UPDATE`, `DELETE` và `TRUNCATE` trên bảng này bị từ chối, kể cả với role sở hữu bảng. Mỗi dòng audit log mang một mã băm được tính từ nội dung của dòng và mã băm của dòng trước. Do đó, các dòng nối thành một chuỗi.

Để kiểm tra audit log có bị sửa hoặc bị xóa bớt hay không:

```bash
saigonos audit verify
```

Lệnh này tính lại mã băm của từng dòng và so sánh với mã băm đã lưu. Khi mọi dòng đều khớp, lệnh in ra kết quả sau:

```text
Audit log có 1250 dòng. Chuỗi mã băm khớp.
Mã băm của dòng cuối: 1df5c68192da0b9f077c8e6dd77ad3196de0d1d42fae945e2e31f4ad1c5710f9
```

Khi một dòng đã bị sửa hoặc bị xóa, lệnh chỉ ra dòng sai đầu tiên và kết thúc với mã thoát 1. Ví dụ:

```text
Dòng 57 của audit log không khớp mã băm. Nội dung hoặc mã băm của dòng này đã bị sửa.
```

Tài khoản superuser của PostgreSQL vẫn tắt được trigger chặn sửa và xóa. Lệnh `saigonos audit verify` phát hiện các dòng đã bị sửa hoặc bị xóa theo cách này. Lệnh tự tính mã băm và không dùng hàm lưu trong cơ sở dữ liệu.

Lệnh không phát hiện được hai trường hợp. Trường hợp thứ nhất là các dòng cuối cùng bị xóa. Trường hợp thứ hai là một dòng bị sửa và mã băm của mọi dòng từ đó về sau được tính lại. Trong cả hai trường hợp, các dòng còn lại vẫn nối đúng với nhau. Do đó, nên lưu kết quả của lệnh ở một nơi ngoài máy chủ sau mỗi lần kiểm tra. Số dòng của audit log chỉ tăng. Với cùng một số dòng, mã băm của dòng cuối không đổi.

## Quét mã độc

SaigonOS dùng ClamAV để quét mã độc. ClamAV chạy trong hai service:

- Service `clamav` quét nội dung được gửi tới. Service này nằm trong mạng Docker `scan` riêng. Mạng này không có kết nối Internet. Chỉ service `core` kết nối được tới ClamAV.
- Service `freshclam` kiểm tra bản cập nhật của cơ sở dữ liệu mã độc 12 lần mỗi ngày. Bản cập nhật được tải từ `database.clamav.net`.

Service `core` quét mọi file ngay sau khi nhận nội dung. Trước khi quét, nội dung được đọc lại từ bucket `quarantine` và được so với mã băm SHA-256 đã ghi. File sạch được chuyển sang bucket `clean`. File có mã độc được giữ trong bucket `quarantine`. Kết quả quét được ghi vào bảng `core.files` và audit log.

Nội dung mà ClamAV không quét hết được cũng bị coi là mã độc. Khi đó, tên mã độc bắt đầu bằng `Heuristics.Limits.Exceeded`. Các trường hợp này gồm:

- Tổng nội dung sau khi giải nén lớn hơn 400 MB.
- File nén chứa hơn 10.000 file.
- File nén lồng nhau quá 17 lớp.
- Việc quét kéo dài quá 2 phút.

Khi ClamAV chưa sẵn sàng, file chờ ở trạng thái `pending_scan`. Service `core` thử quét lại sau mỗi 10 giây. Trạng thái chờ được lưu trong cơ sở dữ liệu. Do đó, file vẫn được quét sau khi service `core` khởi động lại. Khi việc quét một file bị lỗi, file đó được hoãn và các file khác được quét trước. Thời gian hoãn bắt đầu từ 20 giây, tăng gấp đôi sau mỗi lần lỗi và tối đa là 1 giờ.

Cơ sở dữ liệu mã độc được lưu trong volume `clamav-data`. Do đó, các bản cập nhật được giữ lại khi khởi động lại hệ thống. Service `clamav` kiểm tra cơ sở dữ liệu 10 phút một lần và tự nạp bản mới. Trong lúc nạp, ClamAV chỉ giữ một bản cơ sở dữ liệu trong RAM để dùng khoảng 1 GB RAM thay vì 2 GB. Do đó, các yêu cầu quét phải chờ khoảng 15 giây cho tới khi nạp xong.

Để xem kết quả của các lần cập nhật gần nhất:

```bash
cd ~/saigonos
docker compose logs --tail 20 freshclam
```

Service `core` ghi vào log mỗi khi phát hiện mã độc hoặc chưa quét được một file. Để xem các dòng log gần nhất:

```bash
cd ~/saigonos
docker compose logs --tail 20 core
```

## Quy trình

SaigonOS dùng Operaton để chạy các quy trình BPMN 2.0. Operaton lưu dữ liệu trong cơ sở dữ liệu `operaton` riêng. Role `operaton` của cơ sở dữ liệu không kết nối được tới các cơ sở dữ liệu khác.

Ba trang Cockpit, Tasklist và Admin của Operaton nằm ở địa chỉ `/operaton/` của API Gateway, ví dụ http://localhost:9080/operaton/. Cockpit dùng để theo dõi các quy trình đang chạy. Tasklist dùng để xem và xử lý các việc. Admin dùng để quản lý quyền trong Operaton.

Chỉ tài khoản có realm role `admin` đăng nhập được vào ba trang này. Cách tạo tài khoản được trình bày ở mục [Tạo tài khoản quản trị của realm saigonos](#tạo-tài-khoản-quản-trị-của-realm-saigonos). Mỗi lần đăng nhập, tài khoản phải nhập mật khẩu và mã OTP, kể cả khi đã đăng nhập vào một trang khác của hệ thống. Tài khoản không có realm role `admin` bị từ chối ngay sau khi nhập mật khẩu. Khi đó, trang đăng nhập báo rằng chỉ tài khoản quản trị mới vào được trang này. Nội dung thông báo có khóa `saigonos-operaton-admin-only` và sửa được trong Admin Console của realm `saigonos`, ở mục Realm settings, thẻ Localization, phần Realm overrides. Keycloak tính mỗi lần bị từ chối là một lần đăng nhập sai. Do đó, hai lần bị từ chối trong vòng 1 giây làm tài khoản tạm bị khóa 60 giây. Trang đăng nhập khóa nút đăng nhập ngay sau lần bấm đầu tiên, nên trường hợp này chỉ xảy ra khi một chương trình gửi form đăng nhập liên tục.

Operaton làm mới access token ở mỗi lời gọi của ba trang. Do đó, khi một tài khoản bị khóa trong Keycloak, phiên đăng nhập của tài khoản trong Operaton kết thúc ngay ở lời gọi tiếp theo. Nút đăng xuất của ba trang mở địa chỉ `/operaton/logout` để kết thúc phiên đăng nhập của Operaton. Sau khi đăng xuất, lần mở tiếp theo phải nhập lại mật khẩu và mã OTP. Phiên đăng nhập của Keycloak vẫn còn, nên các ứng dụng khác của hệ thống không bị đăng xuất.

Mỗi khi hệ thống khởi động, service `realm` kiểm tra client `operaton` của realm `saigonos` và luồng đăng nhập riêng của client này. Khi luồng đăng nhập bị thay đổi, service tạo lại luồng này. Các thiết lập bảo mật của client cũng được đặt lại, ví dụ địa chỉ chuyển hướng sau khi đăng nhập.

REST API của Operaton không mở qua API Gateway. Chỉ hai service `core` và `processes` gọi REST API này, bằng tài khoản `core` của Operaton. Mật khẩu của tài khoản là giá trị `CORE_OPERATON_PASSWORD` trong file `.env`. Operaton tạo tài khoản này ở lần khởi động đầu tiên. Do đó, đổi giá trị này trong file `.env` sau đó không đổi mật khẩu của tài khoản. Sau mỗi lần đăng nhập sai, Operaton tạm khóa tài khoản trong 3 giây. Thời gian khóa tăng gấp đôi sau mỗi lần sai tiếp theo, tối đa là 60 giây. Sau 10 lần sai liên tiếp, tài khoản bị khóa hẳn.

Để tài khoản không bị khóa hẳn, service `core` ngừng gọi Operaton trong 60 giây sau mỗi lần Operaton từ chối tài khoản `core`. Trong thời gian này, các lời gọi cần Operaton nhận mã 503 và các bước máy làm chưa được chạy. Sau 5 lần bị từ chối liên tiếp, service ngừng gọi Operaton cho tới khi được khởi động lại, và log của service ghi cách khắc phục. Sau khi khôi phục giá trị đúng của `CORE_OPERATON_PASSWORD` trong file `.env`, chạy lại lệnh `saigonos up`. Nếu giá trị này vốn đúng, khởi động lại service `core` bằng lệnh sau:

```bash
cd ~/saigonos
docker compose restart core
```

### Triển khai quy trình

Mỗi quy trình nằm trong một file BPMN 2.0 ở thư mục `~/saigonos/config/operaton/processes`. Lệnh `saigonos init` tạo sẵn thư mục này. Mỗi khi hệ thống khởi động, service `processes` triển khai các file trong thư mục vào Operaton. Do đó, sau khi thêm hoặc sửa một file, cần chạy lại lệnh sau:

```bash
saigonos up
```

Service `processes` tuân theo các quy tắc sau:

- File không thay đổi thì không tạo phiên bản mới của quy trình. File đã sửa tạo một phiên bản mới. Các quy trình đang chạy vẫn dùng phiên bản cũ.
- Mỗi quy trình phải có thuộc tính `operaton:historyTimeToLive`, tức thời gian giữ lịch sử của quy trình. Ví dụ, giá trị `P30D` là 30 ngày. Mỗi ngày từ 01:00 đến 05:00 giờ Việt Nam, Operaton xóa lịch sử của các quy trình đã kết thúc quá thời gian này.
- Tên file chỉ gồm chữ cái không dấu, chữ số, dấu chấm, dấu gạch ngang, dấu gạch dưới và kết thúc bằng `.bpmn`.
- Mỗi mã quy trình, tức thuộc tính `id` của thẻ `process`, chỉ được khai báo trong một file. Khi một file khai báo lại mã quy trình của file khác, service gỡ bản triển khai vừa tạo và báo lỗi. Nhờ đó, một file không thay được quy trình của file khác.
- Xóa một file khỏi thư mục không gỡ quy trình khỏi Operaton.

Khi một file bị lỗi, lệnh `saigonos up` kết thúc với mã lỗi. Service `core` chờ service `processes` chạy xong, nên có thể chưa khởi động cho tới khi file được sửa. Để xem kết quả triển khai và lỗi của từng file:

```bash
cd ~/saigonos
docker compose logs --tail 20 processes
```

File BPMN có thể chứa mã chạy bên trong Operaton, ví dụ script task. Do đó, chỉ đặt vào thư mục này các file từ nguồn đáng tin cậy.

Ví dụ sau là một quy trình đơn giản gồm điểm bắt đầu và điểm kết thúc. Nội dung được lưu trong file `thu-nghiem.bpmn`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:operaton="http://operaton.org/schema/1.0/bpmn"
                  id="thu_nghiem_dinh_nghia" targetNamespace="https://dx.example.com/bpmn">
  <bpmn:process id="thu_nghiem" name="Quy trình thử nghiệm" isExecutable="true"
                operaton:historyTimeToLive="P30D">
    <bpmn:startEvent id="bat_dau" />
    <bpmn:sequenceFlow id="luong_1" sourceRef="bat_dau" targetRef="ket_thuc" />
    <bpmn:endEvent id="ket_thuc" />
  </bpmn:process>
</bpmn:definitions>
```

### Form

Form khai báo các giá trị mà người dùng nhập khi bắt đầu quy trình hoặc khi hoàn thành việc. Form bắt đầu nằm trong thẻ `startEvent` của quy trình. Form của việc nằm trong thẻ `userTask`. Mỗi trường của form là một thẻ `operaton:formField` trong phần `operaton:formData`. Thuộc tính `id` là tên biến của trường, `label` là tên hiển thị và `type` là kiểu của trường. Form viết với tiền tố `camunda:` của Camunda 7 cũng được đọc như Operaton đọc.

Ví dụ sau khai báo trường `ket_qua` của một việc. Trường này bắt buộc nhập và phải có ít nhất 10 ký tự:

```xml
<bpmn:userTask id="xu_ly" name="Xử lý yêu cầu" operaton:candidateGroups="nhan-vien">
  <bpmn:extensionElements>
    <operaton:formData>
      <operaton:formField id="ket_qua" label="Kết quả" type="string">
        <operaton:validation>
          <operaton:constraint name="required" />
          <operaton:constraint name="minlength" config="10" />
        </operaton:validation>
      </operaton:formField>
    </operaton:formData>
  </bpmn:extensionElements>
</bpmn:userTask>
```

Service `core` chỉ nhận các trường được khai báo trong form. Lời gọi gửi biến không có trong form nhận mã 422. Nhờ đó, người dùng không ghi đè được các biến khác của quy trình. Ví dụ, form của việc không khai báo trường `noi_dung` thì người hoàn thành việc không sửa được biến `noi_dung`. Quy trình hoặc việc không có form chỉ nhận nội dung không có biến nào.

Thuộc tính `id` của trường bắt đầu bằng chữ cái không dấu hoặc dấu gạch dưới. Các ký tự tiếp theo là chữ cái không dấu, chữ số hoặc dấu gạch dưới. Tên dài tối đa 64 ký tự. Kiểu của trường quy định giá trị được nhận:

| Kiểu | Giá trị trong JSON | Kiểu biến trong Operaton |
|---|---|---|
| `string` | Chuỗi tối đa 4.000 ký tự | `String` |
| `long` | Số nguyên từ -2^63 tới 2^63 - 1 | `Long` |
| `boolean` | `true` hoặc `false` | `Boolean` |
| `date` | Chuỗi ngày giờ theo ISO 8601 có múi giờ, ví dụ `2026-11-20T09:00:00+07:00` | `Date`, lưu theo giờ UTC |
| `enum` | Chuỗi bằng thuộc tính `id` của một thẻ `operaton:value` trong trường | `String` |

Trường không bắt buộc nhận thêm giá trị `null`. Các ràng buộc của trường nằm trong phần `operaton:validation`:

| Ràng buộc | Ý nghĩa |
|---|---|
| `required` | Bắt buộc nhập. Giá trị `null`, chuỗi rỗng và chuỗi chỉ có khoảng trắng được coi là chưa nhập |
| `minlength` | Số ký tự tối thiểu của chuỗi, không tính khoảng trắng ở đầu và cuối |
| `maxlength` | Số ký tự tối đa của chuỗi |
| `min`, `max` | Giá trị nhỏ nhất và lớn nhất của trường kiểu `long` |
| `readonly` | Trường chỉ để xem. Service `core` không nhận giá trị của trường này |

Service `core` kiểm tra form trước khi gửi các giá trị tới Operaton. Khi một giá trị không đạt, lời gọi nhận mã 422 với nội dung bắt đầu bằng `LỖI TUÂN THỦ`. Nội dung lỗi nêu tên hiển thị và tên biến của từng trường không đạt. Khi đó, quy trình chưa được bắt đầu, hoặc việc vẫn thuộc người nhận và quy trình không đi tiếp. Ví dụ, lời gọi hoàn thành việc `xu_ly` ở trên mà thiếu trường `ket_qua` nhận nội dung sau:

```json
{"detail": "LỖI TUÂN THỦ: Phải nhập Kết quả (ket_qua)"}
```

### Bắt đầu quy trình

Lời gọi `POST /core/processes/{key}/start` bắt đầu phiên bản mới nhất của quy trình có mã `key`. Mã quy trình là thuộc tính `id` của thẻ `process`. Lời gọi cần access token của người dùng đã đăng nhập.

Người gọi phải có một realm role nằm trong thuộc tính `operaton:candidateStarterGroups` của thẻ `process`. Giá trị của thuộc tính là danh sách tên realm role, cách nhau bởi dấu phẩy, không dùng biểu thức `${...}`. Quy trình không có thuộc tính này thì không ai bắt đầu được qua API. File BPMN viết cho Camunda 7 với tiền tố `camunda:` cũng được đọc như Operaton đọc.

Nội dung của lời gọi chứa giá trị của các trường trong form bắt đầu, đặt trong trường `variables`. Quy tắc của form được trình bày ở mục [Form](#form).

Service `core` ghi mã người gọi, tức claim `sub` của access token, vào biến `initiator`. Khi điểm bắt đầu của quy trình có thuộc tính `operaton:initiator`, biến mang tên ghi trong thuộc tính này cũng nhận mã người gọi. Người gọi không gửi được các biến này, kể cả khi form khai báo trường cùng tên.

Ví dụ, một ứng dụng web bắt đầu quy trình `yeu_cau` như sau:

```js
const reply = await fetch("/core/processes/yeu_cau/start", {
  method: "POST",
  headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
  body: JSON.stringify({ variables: { noi_dung: "Máy 12 không lên màn hình" } }),
});
const { id, version } = await reply.json();
```

Lời gọi trả về mã 201 kèm mã của quy trình vừa bắt đầu trong trường `id` và phiên bản của quy trình trong trường `version`.

Quy trình `yeu_cau` trong ví dụ được lưu trong file `yeu-cau.bpmn`. Người có realm role `nguoi-gui` bắt đầu được quy trình. Form bắt đầu có trường `noi_dung` bắt buộc nhập. Việc `xu_ly` chờ một người có realm role `nhan-vien` nhận. Form của việc này có trường `ket_qua` bắt buộc nhập và phải có ít nhất 10 ký tự:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:operaton="http://operaton.org/schema/1.0/bpmn"
                  id="yeu_cau_dinh_nghia" targetNamespace="https://dx.example.com/bpmn">
  <bpmn:process id="yeu_cau" name="Tiếp nhận yêu cầu" isExecutable="true"
                operaton:historyTimeToLive="P30D" operaton:candidateStarterGroups="nguoi-gui">
    <bpmn:startEvent id="bat_dau">
      <bpmn:extensionElements>
        <operaton:formData>
          <operaton:formField id="noi_dung" label="Nội dung" type="string">
            <operaton:validation>
              <operaton:constraint name="required" />
            </operaton:validation>
          </operaton:formField>
        </operaton:formData>
      </bpmn:extensionElements>
    </bpmn:startEvent>
    <bpmn:sequenceFlow id="luong_1" sourceRef="bat_dau" targetRef="xu_ly" />
    <bpmn:userTask id="xu_ly" name="Xử lý yêu cầu" operaton:candidateGroups="nhan-vien">
      <bpmn:extensionElements>
        <operaton:formData>
          <operaton:formField id="ket_qua" label="Kết quả" type="string">
            <operaton:validation>
              <operaton:constraint name="required" />
              <operaton:constraint name="minlength" config="10" />
            </operaton:validation>
          </operaton:formField>
        </operaton:formData>
      </bpmn:extensionElements>
    </bpmn:userTask>
    <bpmn:sequenceFlow id="luong_2" sourceRef="xu_ly" targetRef="ket_thuc" />
    <bpmn:endEvent id="ket_thuc" />
  </bpmn:process>
</bpmn:definitions>
```

### Danh sách việc

Lời gọi `GET /core/tasks` trả về các việc mà người gọi xử lý được. Danh sách gồm hai loại việc:

- Việc mà người gọi đã nhận.
- Việc chưa ai nhận và có nhóm ứng viên là một realm role của người gọi. Nhóm ứng viên được khai báo trong thuộc tính `operaton:candidateGroups` của thẻ `userTask`.

Việc mà người khác đã nhận không có trong danh sách. Các việc được xếp theo thời điểm tạo, việc cũ nhất đứng đầu. Tham số `limit` đặt số việc tối đa được trả về, mặc định là 50 và tối đa là 200. Tham số `offset` đặt số việc được bỏ qua ở đầu danh sách. Ví dụ, lời gọi `GET /core/tasks?offset=50&limit=50` trả về trang thứ hai.

Mỗi việc gồm các trường sau:

| Trường | Ý nghĩa |
|---|---|
| `id` | Mã của việc |
| `name`, `description` | Tên và mô tả của việc trong file BPMN |
| `assignee` | Mã người nhận việc. Giá trị `null` nghĩa là việc đang chờ nhận |
| `created`, `due` | Thời điểm tạo và hạn xử lý |
| `priority` | Độ ưu tiên |
| `task_key` | Mã của việc trong file BPMN, tức thuộc tính `id` của thẻ `userTask` |
| `process_instance_id` | Mã của quy trình chứa việc, bằng trường `id` khi bắt đầu quy trình |
| `process_definition_id` | Mã phiên bản của quy trình |
| `suspended` | Việc đang tạm ngưng |

### Nhận việc và hoàn thành việc

Lời gọi `POST /core/tasks/{id}/claim` nhận việc có mã `id` cho người gọi. Mã việc là trường `id` trong danh sách việc. Người gọi phải có một realm role nằm trong nhóm ứng viên của việc. Việc đã có người khác nhận thì không nhận được. Khi nhiều người cùng nhận một việc, chỉ một người nhận được. Những người còn lại nhận mã 409. Gọi lại lời gọi này với việc mà người gọi đã nhận thì không có gì thay đổi.

Lời gọi `POST /core/tasks/{id}/complete` hoàn thành việc mà người gọi đã nhận. Chỉ người nhận việc mới hoàn thành được việc. Nội dung của lời gọi chứa giá trị của các trường trong form của việc, đặt trong trường `variables`. Service `core` kiểm tra các giá trị theo mục [Form](#form) rồi gửi qua form của việc trong Operaton. Sau đó, quy trình đi tiếp sang bước sau. Người hoàn thành việc cũng không gửi được biến `initiator` và biến ghi trong thuộc tính `operaton:initiator`.

Cả hai lời gọi cần access token của người dùng đã đăng nhập. Khi thành công, lời gọi trả về mã 204 và không có nội dung.

Ví dụ, một ứng dụng web nhận và hoàn thành việc `task` lấy từ danh sách việc như sau:

```js
const headers = { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" };
await fetch(`/core/tasks/${task.id}/claim`, { method: "POST", headers });
await fetch(`/core/tasks/${task.id}/complete`, {
  method: "POST",
  headers,
  body: JSON.stringify({ variables: { ket_qua: "Đã thay cáp màn hình" } }),
});
```

Các mã lỗi của các lời gọi về quy trình và việc:

| Mã | Lời gọi | Ý nghĩa |
|---|---|---|
| 401 | Tất cả | Thiếu access token hoặc access token không hợp lệ |
| 403 | Bắt đầu quy trình | Người gọi không có realm role nằm trong `candidateStarterGroups`, hoặc quy trình không khai báo thuộc tính này |
| 403 | Nhận việc | Người gọi không có realm role nằm trong nhóm ứng viên của việc |
| 403 | Hoàn thành việc | Người gọi không phải là người nhận việc |
| 404 | Bắt đầu quy trình | Không có quy trình với mã này |
| 404 | Nhận việc, hoàn thành việc | Không có việc với mã này, ví dụ việc đã được hoàn thành |
| 409 | Bắt đầu quy trình | Quy trình đang tạm ngưng trong Cockpit |
| 409 | Nhận việc | Việc đã có người khác nhận |
| 409 | Nhận việc, hoàn thành việc | Việc đang tạm ngưng vì quy trình chứa việc bị tạm ngưng trong Cockpit |
| 422 | Bắt đầu quy trình, hoàn thành việc | Giá trị không theo form trong file BPMN, ví dụ thiếu trường bắt buộc hoặc gửi biến không có trong form |
| 422 | Tất cả | Nội dung hoặc tham số không hợp lệ, ví dụ người gọi gửi biến `initiator` |
| 502 | Tất cả | Operaton báo lỗi. Nội dung lỗi được ghi vào log của service `core` |
| 503 | Tất cả | Operaton chưa sẵn sàng hoặc đang từ chối tài khoản `core` |

### Bước máy làm

Bước máy làm là một service task trong file BPMN. Bước này gọi một hàm trong cơ sở dữ liệu `saigonos`. Service `core` lấy các bước này từ Operaton, gọi hàm rồi ghi kết quả của hàm thành biến của quy trình.

Để khai báo bước máy làm, thẻ `serviceTask` cần có thuộc tính `operaton:type="external"` và `operaton:topic="saigonos-function"`. Tên hàm nằm trong thuộc tính `function` của phần `operaton:properties`, có dạng `schema.ten_ham`. Tên chỉ gồm chữ thường không dấu, chữ số và dấu gạch dưới. Ví dụ, bước sau gọi hàm `ung_dung.ghi_ket_qua`:

```xml
<bpmn:serviceTask id="ghi_ket_qua" name="Ghi kết quả" operaton:type="external"
                  operaton:topic="saigonos-function">
  <bpmn:extensionElements>
    <operaton:properties>
      <operaton:property name="function" value="ung_dung.ghi_ket_qua" />
    </operaton:properties>
  </bpmn:extensionElements>
</bpmn:serviceTask>
```

Hàm nhận đúng một tham số kiểu `jsonb` và trả về kiểu `jsonb`. Tham số là một object chứa mọi biến của quy trình, ví dụ `{"ma_yeu_cau": "YC-01", "ket_qua": "Đã thay cáp màn hình"}`. Biến kiểu ngày giờ được truyền dưới dạng chuỗi theo giờ UTC, ví dụ `2026-11-20T02:00:00.000+0000`. Quy trình có biến thuộc kiểu khác chuỗi, số, ngày giờ, `true`, `false` và `null` thì bước máy làm không chạy được. Hàm trả về một object hoặc `null`. Mỗi khóa của object trở thành một biến của quy trình. Tên biến theo quy tắc của thuộc tính `id` ở mục [Form](#form). Giá trị là chuỗi tối đa 4.000 ký tự, số nguyên, số thực, `true`, `false` hoặc `null`. Hàm không ghi được biến `initiator` và biến ghi trong thuộc tính `operaton:initiator`.

Hàm phải được khai báo cho quy trình bằng lệnh `GRANT EXECUTE` cho role `workflow` của cơ sở dữ liệu. Quyền cấp cho `PUBLIC` không được tính. Hàm chạy với quyền của role `workflow`, nên role này cần quyền trên schema và các bảng mà hàm dùng. Ví dụ, ứng dụng khai báo hàm `ung_dung.ghi_ket_qua` bằng các lệnh SQL sau:

```sql
GRANT USAGE ON SCHEMA ung_dung TO workflow;
GRANT SELECT, UPDATE ON ung_dung.yeu_cau TO workflow;

CREATE FUNCTION ung_dung.ghi_ket_qua(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE ung_dung.yeu_cau SET trang_thai = 'da_xu_ly', ket_qua = bien ->> 'ket_qua'
    WHERE ma = bien ->> 'ma_yeu_cau';
    RETURN jsonb_build_object('da_cap_nhat', FOUND);
END
$$;
GRANT EXECUTE ON FUNCTION ung_dung.ghi_ket_qua(jsonb) TO workflow;
```

Service `core` chạy bước máy làm theo các quy tắc sau:

- Hàm chạy trong một transaction và tối đa 20 giây. Audit log ghi role `workflow` trong cột `db_role`. Cột `actor` để trống vì bước này không có người gọi.
- Hàm được gọi qua một hàm `SECURITY DEFINER` của role `workflow`. Do đó, hàm không đổi được role của phiên làm việc, ví dụ bằng lệnh `RESET ROLE`.
- Mỗi bước máy làm chỉ chạy hàm một lần. Kết quả của hàm được ghi vào bảng `core.step_runs` trong cùng transaction với hàm. Khi service `core` dừng đột ngột sau khi hàm chạy xong, bước này được chạy tiếp sau tối đa 1 phút bằng kết quả đã ghi, không gọi lại hàm.
- Khi hàm báo lỗi, mọi thay đổi của hàm bị hủy. Service `core` thử lại sau 5 giây, 30 giây rồi 2 phút. Sau lần lỗi thứ tư, bước máy làm trở thành incident trong Cockpit.
- Khi hàm không tồn tại, chưa được khai báo, sai kiểu tham số hoặc kiểu trả về, hoặc kết quả không ghi được thành biến, bước máy làm trở thành incident ngay mà không thử lại.

Nội dung lỗi của incident nằm trong Cockpit, ở thẻ Incidents của quy trình. Bấm vào nội dung lỗi để xem chi tiết, gồm mã SQLSTATE và vị trí lỗi trong hàm. Sau khi sửa lỗi, bước máy làm được chạy lại bằng thao tác Increment Number of Retries của incident.

### Hẹn giờ và leo thang

Hẹn giờ (timer) gắn trên biên của một việc cho phép quy trình rẽ sang nhánh khác khi việc quá hạn. Ví dụ sau chuyển việc `xu_ly` cho nhóm quản lý khi tới thời điểm ghi trong biến `han_xu_ly`:

```xml
<bpmn:userTask id="xu_ly" name="Xử lý yêu cầu" operaton:candidateGroups="nhan-vien"
               operaton:dueDate="${han_xu_ly}" />
<bpmn:boundaryEvent id="qua_han" name="Quá hạn" attachedToRef="xu_ly">
  <bpmn:timerEventDefinition>
    <bpmn:timeDate>${han_xu_ly}</bpmn:timeDate>
  </bpmn:timerEventDefinition>
</bpmn:boundaryEvent>
<bpmn:sequenceFlow id="luong_qua_han" sourceRef="qua_han" targetRef="xu_ly_qua_han" />
<bpmn:userTask id="xu_ly_qua_han" name="Xử lý yêu cầu quá hạn" operaton:candidateGroups="quan-ly" />
```

Thẻ `boundaryEvent` chứa hẹn giờ. Thuộc tính `attachedToRef` nêu việc được gắn hẹn giờ. Thuộc tính `operaton:dueDate` ghi hạn vào trường `due` của việc trong [Danh sách việc](#danh-sách-việc).

Biến `han_xu_ly` cần là một trường kiểu `date` bắt buộc nhập trong form bắt đầu. Khi quy trình thiếu biến này, Operaton báo lỗi và quy trình không được bắt đầu.

Khi tới hạn mà việc `xu_ly` chưa hoàn thành, Operaton hủy việc này, kể cả khi việc đã có người nhận. Lời gọi hoàn thành việc đã bị hủy nhận mã 404. Sau đó, quy trình tạo việc `xu_ly_qua_han` chờ một người có realm role `quan-ly` nhận. Khi việc `xu_ly` được hoàn thành trước hạn, hẹn giờ cũng bị hủy.

Job executor của Operaton tìm các hẹn giờ đã tới hạn 2 giây một lần. Do đó, hẹn giờ chạy chậm nhất khoảng 2 giây sau hạn. Việc tìm này thêm khoảng 120 câu lệnh mỗi phút vào cơ sở dữ liệu `operaton`.

Các hẹn giờ được lưu trong cơ sở dữ liệu `operaton`. Khi Operaton dừng rồi chạy lại, các hẹn giờ vẫn còn. Hẹn giờ tới hạn trong lúc Operaton dừng sẽ chạy ngay khi Operaton chạy lại.

Operaton chạy theo giờ UTC. Do đó, ngày giờ không ghi múi giờ và biểu thức cron trong file BPMN được tính theo giờ UTC. Ví dụ, `2026-12-01T08:00:00` là 15:00 giờ Việt Nam. Để đặt hẹn giờ theo giờ Việt Nam, ghi ngày giờ kèm múi giờ, ví dụ `2026-12-01T08:00:00+07:00`.

## Cập nhật tức thời

SaigonOS dùng Centrifugo để gửi cập nhật tức thời tới ứng dụng qua WebSocket. Ứng dụng kết nối tới địa chỉ `/realtime/connection/websocket` của API Gateway, ví dụ `ws://localhost:9080/realtime/connection/websocket`. Trên máy chủ có HTTPS, địa chỉ này có dạng `wss://dx.example.com/realtime/connection/websocket`. API Gateway chỉ mở địa chỉ này của Centrifugo.

### Kết nối

Sau khi mở WebSocket, ứng dụng gửi access token do Keycloak cấp trong lệnh connect. Trình duyệt không gửi được header `Authorization` khi mở WebSocket. Do đó, API Gateway không kiểm tra access token ở địa chỉ này. Centrifugo tự kiểm tra chữ ký, issuer (`iss`), thời hạn và audience (`aud`) của access token. Kết nối không có access token hoặc có access token không mang mã người dùng (`sub`) đều bị từ chối. Khi Keycloak đổi khóa ký, Centrifugo tự lấy khóa mới.

Centrifugo chỉ nhận access token có audience `saigonos`. Mỗi khi hệ thống khởi động, service `realm` thêm audience này vào access token của mọi client dùng client scope `roles`. ID token không có audience này nên bị từ chối. Khi mapper `audience saigonos` của client scope `roles` bị sửa hoặc bị xóa, service `realm` đặt lại mapper này.

Khi mở WebSocket, trình duyệt gửi địa chỉ của trang trong header `Origin`. Centrifugo chỉ nhận kết nối từ trang có địa chỉ trùng với địa chỉ truy cập của hệ thống, tức giá trị của tùy chọn `--url`. Do đó, trang của một web khác không mở được kết nối bằng phiên đăng nhập của người dùng.

Lệnh `saigonos init` ghi địa chỉ truy cập vào dòng `CENTRIFUGO_ALLOWED_ORIGIN` của file `.env`. Centrifugo đọc giá trị này như một mẫu glob, nên mỗi ký tự đặc biệt của mẫu glob được thêm dấu `\` ở trước. Ví dụ, địa chỉ `http://[2001:db8::1]:9080` được ghi thành `http://\[2001:db8::1\]:9080`. Lệnh `saigonos init` ghi lại dòng này mỗi lần chạy. Do đó, sau khi sửa dòng `SAIGONOS_URL` trong file `.env`, cần chạy lại lệnh `saigonos init` rồi `saigonos up`.

Ví dụ, với thư viện [centrifuge-js](https://github.com/centrifugal/centrifuge-js) và [keycloak-js](https://www.npmjs.com/package/keycloak-js):

```js
import { Centrifuge } from "centrifuge";

const centrifuge = new Centrifuge("wss://dx.example.com/realtime/connection/websocket", {
  getToken: async () => {
    await keycloak.updateToken(30);
    return keycloak.token;
  },
});
centrifuge.connect();
```

Access token chỉ có hiệu lực 60 giây. Khi access token hết hạn, thư viện gọi hàm `getToken` để lấy access token mới và gửi cho Centrifugo. Access token mới phải thuộc cùng người dùng. Nếu không nhận được access token mới, Centrifugo đóng kết nối khoảng 25 giây sau khi access token hết hạn.

Khi từ chối hoặc đóng kết nối, Centrifugo trả về một trong các mã sau:

| Mã | Ý nghĩa |
|---|---|
| `109` | Access token đã hết hạn. Thư viện tự lấy access token mới rồi kết nối lại |
| `3001` | Centrifugo đang dừng. Thư viện tự kết nối lại |
| `3005` | Kết nối hết hạn vì không nhận được access token mới. Thư viện tự kết nối lại |
| `3500` | Access token không hợp lệ, ví dụ sai chữ ký, sai issuer, là ID token hoặc thuộc người dùng khác |
| `3501` | Lệnh connect không có access token |
| `3507` | Access token không mang mã người dùng |

### Nghe kênh

Sau khi kết nối, ứng dụng nghe một kênh bằng lệnh subscribe. Tên kênh có một trong ba dạng sau:

| Kênh | Người nghe được | Token kênh |
|---|---|---|
| `public:<tên>` | Mọi người dùng đã đăng nhập | Không cần |
| `user:#<sub>` | Chỉ người dùng có mã `<sub>`, tức claim `sub` trong access token | Không cần |
| `role:<realm role>` | Những người dùng có realm role `<realm role>` | Cần |

Tên, `sub` và realm role chỉ gồm chữ cái không dấu, chữ số và các dấu `_`, `.`, `-`. Tên kênh dài tối đa 255 ký tự. Kênh không có namespace hoặc thuộc namespace khác bị từ chối.

Để nghe kênh `role:<realm role>`, ứng dụng lấy token kênh (subscription token) bằng lời gọi `POST /core/realtime/token`, với nội dung `{"channel": "role:<realm role>"}`. Service `core` trả về `{"token": "..."}` khi access token của người gọi có realm role này. Người gọi không có realm role nhận mã 403. Kênh không có dạng `role:<realm role>` nhận mã 422. Token kênh được ký bằng khóa `CENTRIFUGO_SUBSCRIPTION_KEY` trong file `.env` và chỉ dùng được cho đúng kênh, đúng người dùng đã lấy token.

Token kênh có hiệu lực 60 giây và hết hạn không muộn hơn access token dùng để lấy token kênh. Khi token kênh hết hạn, thư viện gọi hàm `getToken` của kênh để lấy token mới. Nếu không nhận được token mới, Centrifugo ngừng gửi tin của kênh trong khoảng 25 đến 52 giây sau khi token kênh hết hạn. Do đó, người dùng bị gỡ realm role ngừng nhận tin của kênh chậm nhất khoảng 2 phút sau khi bị gỡ.

Ví dụ, tiếp theo ví dụ ở mục [Kết nối](#kết-nối):

```js
import { UnauthorizedError } from "centrifuge";

const sub = centrifuge.newSubscription("role:quan-ly", {
  getToken: async (ctx) => {
    await keycloak.updateToken(30);
    const res = await fetch("https://dx.example.com/core/realtime/token", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${keycloak.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ channel: ctx.channel }),
    });
    if (res.status === 403) {
      throw new UnauthorizedError();
    }
    if (!res.ok) {
      throw new Error(`Không lấy được token kênh, mã ${res.status}`);
    }
    return (await res.json()).token;
  },
});
sub.on("publication", (ctx) => console.log(ctx.data));
sub.subscribe();
```

Khi `getToken` ném `UnauthorizedError`, thư viện ngừng nghe kênh. Với lỗi khác, thư viện thử lại sau ít giây. Kênh `public:<tên>` và `user:#<sub>` không cần `getToken`, ví dụ `centrifuge.newSubscription("user:#" + keycloak.subject).subscribe()`.

Khi từ chối hoặc ngừng gửi tin của kênh, Centrifugo trả về một trong các mã sau:

| Mã | Ý nghĩa |
|---|---|
| `102` | Kênh thuộc namespace khác ba namespace trên |
| `103` | Không có quyền nghe kênh, ví dụ kênh không có namespace, kênh `user:#<sub>` của người khác, kênh `role:` không kèm token kênh hoặc kèm token kênh giả |
| `109` | Token kênh đã hết hạn. Thư viện tự lấy token kênh mới rồi nghe lại |
| `2501` | Kênh hết hạn vì không nhận được token kênh mới. Thư viện tự nghe lại |
| `3500` | Token kênh của kênh khác hoặc của người dùng khác. Centrifugo đóng kết nối và thư viện không kết nối lại |

### Gửi tin từ cơ sở dữ liệu

Hàm `core.publish(channel, data)` của cơ sở dữ liệu `saigonos` gửi một tin tới một kênh của Centrifugo. Tham số `channel` là tên kênh, có một trong ba dạng ở mục [Nghe kênh](#nghe-kênh). Tham số `data` là nội dung của tin, có kiểu `jsonb`. Hàm trả về mã của tin, có kiểu `uuid`. Hàm báo lỗi khi kênh sai dạng hoặc nội dung là `NULL`.

Hàm ghi tin vào bảng `core.outbox` trong cùng transaction với dữ liệu. Ngay khi transaction được commit, Centrifugo đọc tin, gửi tới các client đang nghe kênh rồi xóa tin khỏi bảng. Khi transaction bị hủy, tin cũng bị hủy. Do đó, client chỉ nhận tin về dữ liệu đã được lưu. Các tin của cùng một transaction tới client theo đúng thứ tự gọi hàm.

Chỉ role được cấp quyền `EXECUTE` mới gọi được hàm. Hiện tại, chỉ role `workflow` có quyền này. Do đó, hàm được gọi trong [bước máy làm](#bước-máy-làm) của quy trình. Ví dụ, hàm sau cập nhật một yêu cầu rồi báo cho người đã bắt đầu quy trình, tức người có mã trong biến `initiator`:

```sql
CREATE FUNCTION ung_dung.bao_da_xu_ly(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE ung_dung.yeu_cau SET trang_thai = 'da_xu_ly' WHERE ma = bien ->> 'ma_yeu_cau';
    PERFORM core.publish(
        'user:#' || (bien ->> 'initiator'),
        jsonb_build_object('ma_yeu_cau', bien ->> 'ma_yeu_cau', 'trang_thai', 'da_xu_ly')
    );
    RETURN NULL;
END
$$;
GRANT EXECUTE ON FUNCTION ung_dung.bao_da_xu_ly(jsonb) TO workflow;
```

Centrifugo gửi mã của tin trong trường `tags` của tin, với khóa `id`. Ví dụ: `{"id": "1276d3b3-fd8f-43e0-9649-b5ef7743accf"}`. Trong một số trường hợp hiếm, client nhận một tin hai lần. Ví dụ, Centrifugo dừng đột ngột sau khi gửi tin và trước khi xóa tin khỏi bảng. Khi chạy lại, Centrifugo gửi lại tin này. Do đó, client dùng mã của tin để bỏ tin trùng.

### Tin bị lỡ khi mất kết nối

Mỗi kênh có history giữ tối đa 100 tin gần nhất trong 5 phút. Mỗi tin trong history có một số thứ tự (offset). History của kênh có một mã (epoch). Mã này đổi khi history được tạo lại.

Khi client mất kết nối rồi kết nối lại, thư viện tự gửi epoch và offset của tin cuối cùng đã nhận. Nếu các tin bị lỡ còn đủ trong history, Centrifugo gửi lại các tin này theo đúng thứ tự, trước các tin mới. Khi đó, sự kiện `subscribed` có `recovered` là true và ứng dụng không cần làm gì thêm.

Centrifugo trả `recovered` là false khi client lỡ quá 100 tin, kết nối lại sau quá 5 phút hoặc Centrifugo đã khởi động lại. Centrifugo giữ history trong bộ nhớ. Do đó, mỗi lần Centrifugo khởi động lại, history mất và mọi kênh có epoch mới. Khi `recovered` là false, client có thể đã lỡ tin, nên ứng dụng tải lại dữ liệu qua API. Ví dụ, `reloadData` dưới đây là hàm của ứng dụng, đọc lại dữ liệu qua API:

```js
sub.on("subscribed", async (ctx) => {
  if (ctx.wasRecovering && !ctx.recovered) {
    await reloadData();
  }
});
```

Tin ghi bằng hàm `core.publish` trong lúc Centrifugo dừng không bị mất. Các tin này nằm lại trong bảng `core.outbox` và được gửi ngay khi Centrifugo chạy lại, theo đúng thứ tự ghi. Client thường kết nối lại sau lúc đó, nên không nhận các tin này như tin mới. Các tin này nằm trong history của kênh. Ứng dụng chỉ hiện các tin gần đây, ví dụ danh sách thông báo, có thể đọc history thay cho việc tải lại dữ liệu:

```js
const { publications } = await sub.history({ limit: 100 });
```

Sau khi Centrifugo khởi động lại, history chỉ gồm các tin được gửi từ lúc đó. Lời gọi `history` phải có `limit`. Khi không có `limit`, Centrifugo chỉ trả epoch và offset của kênh, không trả tin nào. Tin trong history mang cùng mã `id` với tin đã nhận, nên ứng dụng bỏ tin trùng theo mã này. Chỉ client đang nghe kênh mới đọc được history của kênh đó.

### API của server và Admin web

API của server và Admin web của Centrifugo nằm ở cổng 9480, chỉ truy cập được từ chính máy cài đặt. API Gateway không mở cổng này. Lời gọi API của server cần header `X-API-Key` với giá trị `CENTRIFUGO_API_KEY` trong file `.env`. Ví dụ, lệnh sau xem thông tin các node của Centrifugo:

```bash
curl -X POST -H "X-API-Key: $(grep CENTRIFUGO_API_KEY ~/saigonos/.env | cut -d= -f2)" -d '{}' http://127.0.0.1:9480/api/info
```

Admin web ở địa chỉ http://127.0.0.1:9480/ dùng để xem số kết nối và gọi thử API của server. Mật khẩu đăng nhập là giá trị `CENTRIFUGO_ADMIN_PASSWORD` trong file `.env`.

## Thông báo cho người dùng

Thông báo cho người dùng được lưu trong bảng `core.notifications` của cơ sở dữ liệu `saigonos`. Mỗi thông báo gửi cho một người dùng. Người nhận đọc thông báo của mình qua service `core` và nhận thông báo mới tức thời qua kênh `user:#<sub>` của Centrifugo.

### Gửi thông báo

Hàm `core.notify(recipient, dedup_key, title, body, link, telegram)` của cơ sở dữ liệu ghi một thông báo rồi gửi thông báo đó tới kênh `user:#<recipient>`. Hàm trả về mã của thông báo, có kiểu `uuid`. Các tham số của hàm như sau:

| Tham số | Ý nghĩa |
|---|---|
| `recipient` | Mã người nhận, tức claim `sub` trong access token của người nhận |
| `dedup_key` | Khóa chống trùng, dài từ 1 đến 255 ký tự |
| `title` | Tiêu đề, dài tối đa 200 ký tự. Tiêu đề không được để trống và không chứa ký tự điều khiển, ví dụ dấu xuống dòng |
| `body` | Nội dung, dài tối đa 2000 ký tự. Tham số này có thể bỏ qua |
| `link` | Đường dẫn tới một trang trong hệ thống, bắt đầu bằng một dấu `/` và dài tối đa 1000 ký tự. Ví dụ: `/yeu-cau/YC-001`. Tham số này có thể bỏ qua |
| `telegram` | Khi có giá trị `true`, thông báo còn được gửi tới nhóm Telegram như ở mục [Gửi thông báo qua Telegram](#gửi-thông-báo-qua-telegram). Mặc định là `false` |

Hàm báo lỗi khi một tham số không hợp lệ. Hàm từ chối đường dẫn tới web khác, ví dụ `https://...` hoặc `//...`, và đường dẫn `javascript:`. Do đó, ứng dụng hiển thị được đường dẫn của thông báo mà không cần kiểm tra lại.

Thông báo và tin gửi Centrifugo được ghi trong cùng transaction với dữ liệu, như với hàm `core.publish` ở mục [Gửi tin từ cơ sở dữ liệu](#gửi-tin-từ-cơ-sở-dữ-liệu). Khi transaction bị hủy, thông báo và tin cũng bị hủy.

Mỗi người nhận chỉ có một thông báo cho mỗi khóa chống trùng. Khi hàm được gọi lại với cùng người nhận và cùng khóa, hàm không ghi thêm thông báo, không gửi thêm tin và trả về mã của thông báo đã có. Nội dung của thông báo đã có được giữ nguyên. Quy tắc này vẫn đúng khi hai transaction gọi hàm cùng lúc. Do đó, khóa chống trùng nên nêu sự việc mà thông báo nói tới, ví dụ `yeu-cau:YC-001:da-xu-ly`. Khi một sự việc được báo cho nhiều người, mọi người nhận dùng chung một khóa.

Hiện tại, chỉ role `workflow` có quyền gọi hàm. Ví dụ, hàm sau của một [bước máy làm](#bước-máy-làm) báo cho người đã bắt đầu quy trình rằng yêu cầu đã được xử lý:

```sql
CREATE FUNCTION ung_dung.bao_tin_da_xu_ly(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM core.notify(
        recipient => bien ->> 'initiator',
        dedup_key => 'yeu-cau:' || (bien ->> 'ma_yeu_cau') || ':da-xu-ly',
        title => 'Yêu cầu ' || (bien ->> 'ma_yeu_cau') || ' đã được xử lý',
        link => '/yeu-cau/' || (bien ->> 'ma_yeu_cau')
    );
    RETURN NULL;
END
$$;
GRANT EXECUTE ON FUNCTION ung_dung.bao_tin_da_xu_ly(jsonb) TO workflow;
```

### Đọc thông báo

Lời gọi `GET /core/notifications` trả về các thông báo gửi cho người gọi. Thông báo mới nhất đứng đầu. Tham số `limit` đặt số thông báo tối đa được trả về, mặc định là 50 và tối đa là 200. Tham số `offset` đặt số thông báo được bỏ qua ở đầu danh sách. Mỗi thông báo gồm các trường sau:

| Trường | Ý nghĩa |
|---|---|
| `id` | Mã của thông báo |
| `title`, `body`, `link` | Tiêu đề, nội dung và đường dẫn. Trường `body` và `link` có giá trị `null` khi hàm `core.notify` không nhận hai tham số này |
| `created_at` | Thời điểm tạo |
| `read_at` | Thời điểm người nhận đánh dấu đã đọc. Giá trị `null` nghĩa là chưa đọc |

Lời gọi `POST /core/notifications/{id}/read` đánh dấu một thông báo là đã đọc và trả về thông báo đó. Khi thông báo đã được đọc trước đó, thời điểm đọc không đổi. Người dùng chỉ thấy và chỉ đánh dấu được thông báo gửi cho chính mình. Với thông báo của người khác, lời gọi nhận mã 404 như khi thông báo không tồn tại.

### Nhận thông báo mới

Khi có thông báo mới, kênh `user:#<sub>` của người nhận nhận một tin có dạng `{"notification": {...}}`. Đối tượng `notification` có các trường như ở mục [Đọc thông báo](#đọc-thông-báo), với `read_at` là `null`. Kênh này có thể nhận cả tin khác của ứng dụng. Do đó, ứng dụng nhận ra thông báo nhờ khóa `notification`. Ví dụ, tiếp theo ví dụ ở mục [Kết nối](#kết-nối):

```js
const sub = centrifuge.newSubscription("user:#" + keycloak.subject);
sub.on("publication", (ctx) => {
  if (ctx.data.notification) {
    showNotification(ctx.data.notification);
  }
});
sub.subscribe();
```

Trong ví dụ trên, `showNotification` là hàm của ứng dụng. Ứng dụng thường tải danh sách thông báo bằng lời gọi `GET /core/notifications` rồi nghe kênh. Một thông báo có thể vừa có trong danh sách vừa tới qua kênh. Do đó, ứng dụng bỏ thông báo trùng theo trường `id`.

### Gửi thông báo qua Telegram

Khi hàm `core.notify` nhận tham số `telegram => true`, thông báo còn được gửi tới một nhóm Telegram qua Bot API. Tin Telegram gồm tiêu đề in đậm, nội dung và địa chỉ đầy đủ của đường dẫn, ví dụ `https://dx.example.com/yeu-cau/YC-001`. Tin được gửi tới nhóm, không gửi riêng cho người nhận. Do đó, mỗi khóa chống trùng chỉ có một tin Telegram, kể cả khi sự việc được báo cho nhiều người. Ví dụ, trong hàm của một bước máy làm:

```sql
PERFORM core.notify(
    recipient => bien ->> 'nguoi_xu_ly',
    dedup_key => 'yeu-cau:' || (bien ->> 'ma_yeu_cau') || ':moi',
    title => 'Có yêu cầu mới ' || (bien ->> 'ma_yeu_cau'),
    link => '/yeu-cau/' || (bien ->> 'ma_yeu_cau'),
    telegram => true
);
```

Để bật Telegram:

1. Tạo bot bằng [BotFather](https://t.me/BotFather) với lệnh `/newbot`. BotFather trả về token của bot, có dạng `123456789:AA...`.
2. Thêm bot vào nhóm nhận thông báo. Sau đó, gửi lệnh `/start@<tên bot>` trong nhóm. Khi nhóm có chủ đề (topic), gửi lệnh này trong chủ đề cần nhận tin.
3. Mở địa chỉ `https://api.telegram.org/bot<token>/getUpdates` bằng trình duyệt. Mã nhóm là giá trị `chat.id`, ví dụ `-1001234567890`. Mã chủ đề là giá trị `message_thread_id`. Telegram chỉ giữ các giá trị này trong 24 giờ.
4. Thêm các dòng sau vào file `.env` trong thư mục làm việc, rồi chạy `saigonos up`.

```
TELEGRAM_BOT_TOKEN=123456789:AA...
TELEGRAM_CHAT_ID=-1001234567890
TELEGRAM_TOPIC_ID=2
```

Khi bật chủ đề cho nhóm, Telegram chuyển nhóm thành supergroup và mã nhóm thay đổi. Do đó, lấy mã nhóm sau khi bật chủ đề. Các giá trị Telegram trong file `.env` như sau:

| Giá trị | Ý nghĩa |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token của bot |
| `TELEGRAM_CHAT_ID` | Mã nhóm, hoặc tên công khai của nhóm dạng `@ten_nhom` |
| `TELEGRAM_TOPIC_ID` | Mã chủ đề. Khi bỏ trống, tin được gửi vào nhóm, hoặc vào chủ đề General khi nhóm có chủ đề |
| `TELEGRAM_API_URL` | Địa chỉ của Bot API, mặc định là `https://api.telegram.org`. Chỉ đổi giá trị này khi dùng Bot API server riêng |

Để thử cấu hình, chạy lệnh sau trong thư mục làm việc. Nhóm nhận tin sau vài giây. Mỗi lần thử cần một khóa chống trùng mới, ví dụ `kiem-tra-telegram-2`.

```bash
docker compose exec postgres psql -U postgres -d saigonos -c "SET ROLE workflow; SELECT core.notify('kiem-tra', 'kiem-tra-telegram-1', 'Tin thử của SaigonOS', telegram => true)"
```

Trạng thái của tin, cách xử lý lỗi và cách gửi lại được trình bày ở mục [Hàng đợi gửi tin](#hàng-đợi-gửi-tin).

### Gửi email

Hàm `core.send_email(address, dedup_key, title, body, link)` của cơ sở dữ liệu ghi một email vào hàng đợi `core.deliveries`. Service `core` gửi email qua một máy chủ SMTP, ví dụ máy chủ của Gmail. Hàm trả về mã của email trong hàng đợi, có kiểu `bigint`. Các tham số của hàm như sau:

| Tham số | Ý nghĩa |
|---|---|
| `address` | Địa chỉ email của người nhận, dài tối đa 254 ký tự. Địa chỉ không chứa chữ có dấu |
| `dedup_key` | Khóa chống trùng, dài từ 1 đến 255 ký tự |
| `title` | Tiêu đề của email, theo quy tắc của tham số `title` ở hàm `core.notify` |
| `body` | Nội dung, dài tối đa 2000 ký tự. Tham số này có thể bỏ qua |
| `link` | Đường dẫn tới một trang trong hệ thống, theo quy tắc của tham số `link` ở hàm `core.notify`. Tham số này có thể bỏ qua |

Người nhận không cần có tài khoản trong hệ thống. Ví dụ, hàm sau của một bước máy làm gửi email xác nhận cho người gửi yêu cầu:

```sql
CREATE FUNCTION ung_dung.gui_email_da_nhan(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM core.send_email(
        address => bien ->> 'email',
        dedup_key => 'yeu-cau:' || (bien ->> 'ma_yeu_cau') || ':da-nhan',
        title => 'Đã nhận yêu cầu ' || (bien ->> 'ma_yeu_cau'),
        body => 'Cảm ơn bạn đã gửi yêu cầu. Bạn có thể tra cứu yêu cầu tại đường dẫn sau.',
        link => '/tra-cuu/' || (bien ->> 'ma_yeu_cau')
    );
    RETURN NULL;
END
$$;
GRANT EXECUTE ON FUNCTION ung_dung.gui_email_da_nhan(jsonb) TO workflow;
```

Email được ghi trong cùng transaction với dữ liệu. Khi transaction bị hủy, email cũng bị hủy. Mỗi địa chỉ chỉ nhận một email cho mỗi khóa chống trùng. Khi hàm được gọi lại với cùng địa chỉ và cùng khóa, hàm không ghi thêm email và trả về mã của email đã có.

Email chỉ có phần văn bản thuần. Phần này gồm nội dung, hoặc tiêu đề khi không có nội dung, rồi tới địa chỉ đầy đủ của đường dẫn. Email có header `Auto-Submitted: auto-generated`, nên chức năng trả lời tự động của hộp thư người nhận không trả lời email này.

Để bật email, thêm các dòng sau vào file `.env` trong thư mục làm việc, rồi chạy `saigonos up`. Ví dụ với Gmail:

```
SMTP_HOST=smtp.gmail.com
SMTP_USERNAME=thong-bao@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
SMTP_FROM=thong-bao@gmail.com
SMTP_FROM_NAME=Phòng Kỹ thuật
```

Gmail không nhận mật khẩu đăng nhập thường của tài khoản. Tài khoản cần bật xác minh 2 bước, rồi tạo mật khẩu ứng dụng tại trang [Mật khẩu ứng dụng](https://myaccount.google.com/apppasswords). Mật khẩu ứng dụng gồm 16 chữ cái, được viết liền, không có khoảng trắng. Các giá trị SMTP trong file `.env` như sau:

| Giá trị | Ý nghĩa |
|---|---|
| `SMTP_HOST` | Tên hoặc địa chỉ IP của máy chủ SMTP |
| `SMTP_PORT` | Cổng của máy chủ SMTP. Mặc định là 587, hoặc 465 khi `SMTP_SECURITY` là `tls`, hoặc 25 khi `SMTP_SECURITY` là `none` |
| `SMTP_SECURITY` | Cách mã hóa kết nối. Giá trị `starttls` mã hóa kết nối bằng lệnh STARTTLS. Giá trị `tls` mã hóa ngay từ đầu kết nối. Giá trị `none` không mã hóa và không cho dùng mật khẩu, chỉ dùng với máy chủ SMTP trong mạng nội bộ. Mặc định là `tls` khi `SMTP_PORT` là 465, và `starttls` với các cổng khác |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Tài khoản đăng nhập máy chủ SMTP. Bỏ trống hai giá trị này khi máy chủ không yêu cầu đăng nhập |
| `SMTP_FROM` | Địa chỉ gửi. Với Gmail, đây là địa chỉ của tài khoản |
| `SMTP_FROM_NAME` | Tên người gửi hiện trong hộp thư của người nhận. Giá trị này có thể bỏ trống |

Service `core` luôn kiểm tra chứng chỉ của máy chủ SMTP. Khi `SMTP_SECURITY` là `starttls` mà máy chủ không hỗ trợ STARTTLS, email không được gửi. Do đó, mật khẩu không được gửi qua kết nối chưa mã hóa. Khi một giá trị trong file `.env` có dấu `$`, giá trị đó được đặt trong cặp dấu nháy đơn, ví dụ `SMTP_PASSWORD='ab$cd'`.

Để thử cấu hình, chạy lệnh sau trong thư mục làm việc, với `<địa chỉ>` là một địa chỉ email của bạn. Email tới sau vài giây. Mỗi lần thử cần một khóa chống trùng mới, ví dụ `kiem-tra-email-2`.

```bash
docker compose exec postgres psql -U postgres -d saigonos -c "SET ROLE workflow; SELECT core.send_email('<địa chỉ>', 'kiem-tra-email-1', 'Email thử của SaigonOS')"
```

### Hàng đợi gửi tin

Mỗi tin Telegram và mỗi email là một dòng của bảng `core.deliveries`. Dòng này được ghi trong cùng transaction với dữ liệu. Khi transaction được commit, service `core` gửi tin ngay. Telegram và email có vòng gửi riêng, nên lỗi của kênh này không làm chậm kênh kia. Cột `channel` cho biết kênh gửi, có giá trị `telegram` hoặc `email`. Cột `status` cho biết trạng thái của tin:

| Trạng thái | Ý nghĩa |
|---|---|
| `pending` | Tin đang chờ gửi hoặc chờ gửi lại |
| `sending` | Service `core` đang gửi tin |
| `sent` | Telegram hoặc máy chủ SMTP đã nhận tin. Cột `sent_id` ghi mã của tin trong nhóm Telegram, hoặc `Message-ID` của email |
| `failed` | Không gửi được tin. Cột `error` ghi lý do |
| `unknown` | Không biết Telegram hoặc máy chủ SMTP đã nhận tin hay chưa |
| `skipped` | Tin không được gửi vì kênh gửi chưa được cấu hình hoặc cấu hình chưa đúng |

Ví dụ, lệnh sau xem 10 tin gần nhất:

```bash
docker compose exec postgres psql -U postgres -d saigonos -c "SELECT id, channel, status, failures, error FROM core.deliveries ORDER BY id DESC LIMIT 10"
```

Khi gửi lỗi, service `core` xử lý như sau:

- Không kết nối được Telegram hoặc máy chủ SMTP, Telegram trả về mã 5xx, hoặc máy chủ SMTP trả về mã 4xx: tin được gửi lại sau 5 giây, 30 giây, 2 phút và 10 phút. Sau 5 lần gửi lỗi, tin chuyển sang `failed`.
- Telegram trả về mã 429: service `core` chờ đúng số giây trong `retry_after` rồi mới gửi tiếp. Các tin Telegram khác cũng chờ trong thời gian này. Lần chờ này không tính là một lần gửi lỗi.
- Telegram trả về mã 4xx khác, ví dụ token sai hoặc bot không ở trong nhóm: tin chuyển sang `failed` ngay.
- Máy chủ SMTP trả về mã 5xx, ví dụ sai mật khẩu hoặc địa chỉ người nhận không tồn tại: email chuyển sang `failed` ngay. Máy chủ không hỗ trợ STARTTLS cũng cho kết quả này.

Mỗi lần gửi lỗi được ghi vào log của service `core`, kèm lý do mà Telegram hoặc máy chủ SMTP trả về. Lệnh `docker compose logs core` trong thư mục làm việc dùng để xem log này.

Bot API của Telegram và giao thức SMTP không có cách chống gửi trùng. Do đó, service `core` chuyển tin sang `sending` trước khi gửi, và tin đã `sent` không được gửi lại. Có hai trường hợp không biết tin đã tới nơi hay chưa. Trường hợp thứ nhất là lời gọi tới Telegram hoặc nội dung email đã được gửi đi, nhưng mất kết nối trước khi có câu trả lời. Trường hợp thứ hai là service `core` bị dừng đột ngột trong lúc gửi. Khi đó, tin chuyển sang `unknown` và không được gửi lại, để người nhận không nhận hai tin giống nhau. Thông báo trong ứng dụng không bị ảnh hưởng. Quản trị viên kiểm tra nhóm Telegram hoặc hỏi người nhận email. Nếu tin chưa tới, lệnh sau đưa tin về `pending`, với `<id>` là giá trị cột `id` của tin. Tin được gửi lại trong vòng 10 giây.

```bash
docker compose exec postgres psql -U postgres -d saigonos -c "UPDATE core.deliveries SET status = 'pending' WHERE id = <id> AND status = 'unknown'"
```

Khi file `.env` chưa có cấu hình Telegram hoặc SMTP, tin của kênh đó chuyển sang `skipped` và hệ thống vẫn chạy bình thường. Khi cấu hình chưa đúng, ví dụ thiếu `TELEGRAM_CHAT_ID` hoặc thiếu `SMTP_FROM`, service `core` ghi lý do vào log lúc khởi động và tin cũng chuyển sang `skipped`. Tin đã `skipped` không được gửi khi kênh được cấu hình sau đó.

Bảng `core.deliveries` giữ địa chỉ email, tiêu đề và nội dung của tin sau khi gửi.

## Ứng dụng

Mỗi ứng dụng là một thư mục có file bản khai `saigonos-app.json`. Bản khai cho biết tên, phiên bản, các realm role của ứng dụng và các thư mục chứa file SQL, file BPMN và giao diện.

### Bản khai

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

Bản khai tuân theo các quy tắc sau:

- Tên ứng dụng gồm các cụm chữ thường không dấu và chữ số, nối với nhau bằng một dấu gạch ngang. Tên bắt đầu bằng chữ cái và dài tối đa 32 ký tự. Ví dụ: `nghi-phep`, `don-tu-2`.
- Tên ứng dụng không bắt đầu bằng `pg-` và không trùng các tên mà lõi đã dùng cho schema, role của cơ sở dữ liệu, client của Keycloak và đường dẫn của API Gateway. Các tên đó gồm `account`, `account-console`, `admin-cli`, `anon`, `api`, `apps`, `auth`, `authenticated`, `authenticator`, `broker`, `centrifugo`, `core`, `core-service`, `information-schema`, `keycloak`, `operaton`, `postgres`, `public`, `realm-management`, `realtime`, `saigonos`, `security-admin-console` và `workflow`.
- Tên role có dạng `<tên ứng dụng>.<vai trò>`, ví dụ `nghi-phep.quan-ly`. Vai trò viết theo quy tắc của tên ứng dụng. Tên role dài tối đa 64 ký tự và không được khai báo hai lần.
- Tên hiển thị dài tối đa 100 ký tự, mô tả của role dài tối đa 255 ký tự. Hai giá trị này không được để trống, không có khoảng trắng ở đầu hoặc cuối và không chứa ký tự điều khiển.
- Đường dẫn của thư mục tính từ thư mục ứng dụng, ví dụ `ui` hoặc `web/dist`. Mỗi cấp gồm chữ cái không dấu, chữ số, dấu chấm, dấu gạch ngang, dấu gạch dưới và không bắt đầu bằng dấu chấm. Do đó, đường dẫn không trỏ ra ngoài thư mục ứng dụng được. Ba thư mục không trùng nhau và không nằm trong nhau.
- Bản khai và các thư mục đã khai không chứa symlink, pipe, socket hay file thiết bị. Mọi file và thư mục con đều phải đọc được.
- Bản khai chỉ có các trường trong bảng trên. Trường viết sai chính tả bị báo lỗi.

JSON Schema của bản khai nằm trong file [schemas/saigonos-app.schema.json](schemas/saigonos-app.schema.json).

### Soát ứng dụng

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

Lệnh soát ở trên chạy service `apps` bằng tài khoản đang dùng. Cũng có thể soát bằng Docker Compose sau khi chép thư mục ứng dụng vào thư mục `apps` của thư mục làm việc:

```bash
cp -r ./nghi-phep ~/saigonos/apps/
cd ~/saigonos
docker compose run --rm apps check nghi-phep
```

Khi gọi theo cách này, service `apps` chạy bằng tài khoản `nobody` của container. Do đó, mọi file của ứng dụng cần quyền đọc cho mọi tài khoản, ví dụ quyền `644`, và mọi thư mục cần quyền `755`.

### Cài đặt ứng dụng

Khi hệ thống đang chạy, lệnh sau cài đặt ứng dụng trong thư mục `./nghi-phep` vào hệ thống:

```bash
saigonos apply ./nghi-phep
```

Lệnh thực hiện các bước sau:

1. Soát ứng dụng như mục [Soát ứng dụng](#soát-ứng-dụng). Khi có lỗi, lệnh dừng và không thay đổi gì.
2. Chép bản khai và các thư mục đã khai vào thư mục `apps/<tên ứng dụng>` của thư mục làm việc. Các file khác trong thư mục ứng dụng, ví dụ thư mục `.git`, không được chép.
3. Chạy lệnh `apply` của service `apps`. Lệnh này soát lại bản đã chép rồi cài đặt ứng dụng vào cơ sở dữ liệu như mục [File SQL của ứng dụng](#file-sql-của-ứng-dụng) và vào Keycloak như mục [Đăng nhập vào ứng dụng](#đăng-nhập-vào-ứng-dụng).

Ở lần cài đặt đầu tiên, lệnh in các dòng sau:

```text
Đã tạo schema nghi_phep và role nghi_phep của ứng dụng.
Đã chạy file 0001_don.sql.
Đã tạo realm role nghi-phep.nhan-vien.
Đã tạo realm role nghi-phep.quan-ly.
Đã tạo client nghi-phep.
Đã cài đặt ứng dụng nghi-phep 0.1.0.
```

Khi cài đặt lỗi, lệnh kết thúc với mã thoát 1 và thư mục `apps/nghi-phep` được trả về bản đã cài đặt thành công gần nhất. Chạy lại lệnh khi ứng dụng không đổi thì cơ sở dữ liệu và Keycloak không thay đổi.

Cũng có thể cài đặt bằng Docker Compose sau khi chép thư mục ứng dụng vào thư mục `apps` của thư mục làm việc. Tên thư mục phải trùng tên ứng dụng:

```bash
cp -r ./nghi-phep ~/saigonos/apps/
cd ~/saigonos
docker compose run --rm apps apply nghi-phep
```

Service `apps` giữ mật khẩu superuser của PostgreSQL và mật khẩu của tài khoản `admin` trong realm master của Keycloak. Service này chỉ chạy khi được gọi. Service `core` không có hai mật khẩu này.

### File SQL của ứng dụng

Mỗi ứng dụng có một schema và một role riêng trong cơ sở dữ liệu. Tên của cả hai là tên ứng dụng với dấu gạch ngang đổi thành dấu gạch dưới, ví dụ `nghi_phep`. Role sở hữu schema. Lệnh cài đặt chạy các file `.sql` trong thư mục `database` của ứng dụng theo các quy tắc sau:

- File chạy theo thứ tự tên, bằng role của ứng dụng, không bằng superuser. Role này chỉ đăng nhập được trong lúc lệnh cài đặt chạy, với mật khẩu sinh mới mỗi lần.
- Schema của ứng dụng là `search_path` của file. Do đó, lệnh `CREATE TABLE don (...)` tạo bảng `nghi_phep.don`.
- Mỗi file chạy trong một transaction. Khi một câu lệnh bị lỗi, mọi thay đổi của file bị hủy. File không được dùng `BEGIN`, `COMMIT`, `ROLLBACK` hay `SAVEPOINT`.
- Bảng `core.migrations` ghi tên và mã băm của từng file đã chạy, với cột `scope` là tên ứng dụng. File đã chạy thì không chạy lại. File đã chạy mà bị sửa thì lệnh cài đặt dừng và báo lỗi. Để thay đổi cơ sở dữ liệu, hãy thêm một file mới.
- Role của ứng dụng không đọc được schema của ứng dụng khác và các bảng của lõi, ví dụ `core.audit_log`. Role này cũng không đổi được sang role khác bằng `SET ROLE`.
- Bảng, view và hàm mới chưa được cấp cho role nào, kể cả `PUBLIC`. File SQL cấp quyền cho role `authenticated` và `anon` bằng `GRANT`, gồm cả quyền `USAGE` trên schema của ứng dụng.
- Role của ứng dụng dùng được hàm `core.audit()` để ghi audit log cho bảng và hàm `core.append_only()` để chặn sửa, xóa dòng của bảng.
- Các hàm `core.claims()`, `core.uid()`, `core.has_role()` và `core.unit()` chỉ đọc claims do PostgREST hoặc service `core` đặt cho lời gọi. Khi một hàm của ứng dụng đổi `request.jwt.claims` bằng `set_config` hay `SET LOCAL`, các hàm này trả về `NULL`. Do đó, mã của một ứng dụng không mạo danh được người dùng khác.
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
GRANT USAGE ON SCHEMA nghi_phep TO authenticated;
GRANT SELECT, INSERT ON don TO authenticated;
```

### Đăng nhập vào ứng dụng

Lệnh cài đặt tạo các mục sau trong realm `saigonos` của Keycloak:

- Mỗi role trong bản khai trở thành một realm role, với mô tả lấy từ bản khai.
- Một client trùng tên ứng dụng, ví dụ `nghi-phep`. Đây là public client, chỉ dùng luồng Authorization Code với PKCE `S256`. Password grant, luồng implicit, service account và device grant đều tắt. Địa chỉ chuyển hướng chỉ gồm `<địa chỉ truy cập>/apps/<tên ứng dụng>/` và các đường dẫn bên dưới.
- Thiết lập Full scope allowed của client bị tắt. Scope mapping của client chỉ gồm realm role `authenticated` và các role của ứng dụng. Client có các client scope mặc định `acr`, `basic`, `email`, `profile`, `roles`, `web-origins` và không có client scope tùy chọn.

Nhờ đó, access token do client cấp chỉ mang realm role `authenticated` và các role của chính ứng dụng, kể cả khi người dùng có role của ứng dụng khác hoặc role `admin`. Ứng dụng cũng không xin được scope `offline_access`.

Ứng dụng đăng nhập theo các địa chỉ trong tài liệu discovery `/auth/realms/saigonos/.well-known/openid-configuration`, với `client_id` là tên ứng dụng.

Để gán role của ứng dụng cho người dùng, mở Admin Console của realm `saigonos`, chọn **Users**, chọn người dùng, mở tab **Role mapping**, bấm **Assign role** rồi chọn role của ứng dụng.

Mỗi lần cài đặt, client được đặt lại theo bản khai. Thiết lập, mapper, scope mapping và client scope đã sửa trong Admin Console đều trở về như trên. Mô tả của realm role cũng được đặt lại, composite role thêm vào role của ứng dụng bị gỡ. Role bị bỏ khỏi bản khai vẫn được giữ cùng với việc gán role, nhưng không còn trong scope mapping. Do đó, access token của ứng dụng không mang role đó nữa.

SaigonOS ghi tên ứng dụng vào thuộc tính `saigonos.app` của client và realm role. Khi Keycloak đã có client hoặc realm role trùng tên mà không mang thuộc tính này, lệnh cài đặt dừng trước khi thay đổi cơ sở dữ liệu và không đụng tới client hoặc role đó.

Địa chỉ chuyển hướng lấy từ giá trị `SAIGONOS_URL` trong file `.env`. Sau khi đổi địa chỉ truy cập, hãy chạy lại lệnh cài đặt cho từng ứng dụng, ví dụ `saigonos apply ./nghi-phep`.

### Gọi API của ứng dụng

PostgREST phục vụ schema của mọi ứng dụng đã cài đặt tại địa chỉ `/api/` của API Gateway. Lời gọi chọn schema bằng header `Accept-Profile` khi đọc và `Content-Profile` khi ghi. Lời gọi không có hai header này dùng schema `api`.

Lời gọi vào schema của một ứng dụng phải kèm access token được cấp cho client của ứng dụng đó, tức claim `azp` của access token là tên ứng dụng. Access token của client khác, kể cả của ứng dụng khác, nhận mã 403 với mã lỗi `SGN02`. Lời gọi không có access token vẫn chạy với role `anon`. Schema `api` nhận access token của mọi client. Ví dụ:

```js
const headers = {
  Authorization: `Bearer ${accessToken}`,
  "Accept-Profile": "nghi_phep",
  "Content-Profile": "nghi_phep",
  "Content-Type": "application/json",
};
await fetch("/api/don", { method: "POST", headers, body: JSON.stringify({ ly_do: "Việc gia đình" }) });
const don = await (await fetch("/api/don", { headers })).json();
```

Tài liệu OpenAPI của ứng dụng nằm ở địa chỉ `/api/` khi lời gọi có header `Accept-Profile`. Sau khi cài đặt, PostgREST nạp lại cấu hình và schema cache mà không khởi động lại. Việc này mất khoảng 1 giây.

## Cập nhật phiên bản

Các thay đổi của từng phiên bản được ghi trong [CHANGELOG.md](CHANGELOG.md). Khi cập nhật, dữ liệu, các mật khẩu trong file `.env` và chứng chỉ của Caddy được giữ nguyên.

### 1. Dừng các service

```bash
saigonos down
```

### 2. Cài đặt phiên bản mới của package `saigonos`

Trong thư mục `SaigonOS` đã tạo bằng lệnh `git clone`:

```bash
git pull
pip install .
```

Nếu cài đặt từ file release, tải file `saigonos-X.Y.Z.tar.gz` của phiên bản mới, giải nén rồi chạy `pip install .` trong thư mục vừa giải nén.

### 3. Cập nhật thư mục làm việc và khởi động lại

```bash
saigonos init
saigonos up
saigonos doctor
```

Lệnh `saigonos init` cập nhật file `compose.yaml` và thư mục `config` theo phiên bản mới. Lệnh này cũng thêm vào file `.env` các giá trị mà phiên bản mới cần, ví dụ mật khẩu của service mới. Lệnh `saigonos up` build lại image của service `core` và tạo lại các container với cấu hình mới. Service `migrate` chạy các file SQL mới của phiên bản để cập nhật cơ sở dữ liệu. Service `realm` thêm các thiết lập mới của phiên bản vào realm `saigonos` của Keycloak.

## Tham gia phát triển

- Báo lỗi hoặc đề xuất tính năng: mở một [issue](https://github.com/tynnpdhsp/SaigonOS/issues/new/choose).
- Đóng góp mã nguồn: xem [CONTRIBUTING.md](CONTRIBUTING.md).
- Báo cáo lỗ hổng bảo mật: xem [SECURITY.md](SECURITY.md).

## Giấy phép

SaigonOS được phát hành theo giấy phép [Apache-2.0](LICENSE). Mỗi file trong repo có một dòng `SPDX-License-Identifier` ở đầu. Công cụ [REUSE](https://reuse.software/) được dùng để kiểm tra các dòng này.

Các thư viện, phần mềm chạy trong container và công cụ mà SaigonOS sử dụng được liệt kê trong [DEPENDENCIES.md](DEPENDENCIES.md). Mỗi dòng ghi rõ phiên bản, giấy phép, mô tả và nguồn.
