<!-- SPDX-License-Identifier: Apache-2.0 -->
# SaigonOS

SaigonOS là một hệ điều hành chuyển đổi số (DX-OS) nguồn mở. Phần lõi được xây dựng từ các phần mềm nguồn mở và không có giao diện cho người dùng cuối. Mỗi ứng dụng chỉ cần phát triển phần giao diện và gọi các service của lõi.

Lõi cung cấp bốn service chính:

- Quản lý định danh và đăng nhập một lần (Identity/SSO)
- Cổng API (API Gateway)
- Quản lý dữ liệu có cấu trúc và phi cấu trúc
- Luồng công việc (Workflow)

Phiên bản hiện tại cung cấp đăng nhập một lần, API Gateway và REST API cho dữ liệu có cấu trúc. Dữ liệu phi cấu trúc được lưu trong kho file có quét mã độc. Phần luồng công việc đang được phát triển. Các thay đổi được ghi lại trong [CHANGELOG.md](CHANGELOG.md).

## Yêu cầu hệ thống

- Hệ điều hành Linux. SaigonOS được kiểm thử trên Ubuntu 24.04.
- Python 3.11 trở lên và pip.
- Docker Engine 25.0 trở lên, Docker Compose 2.20.2 trở lên và Docker Buildx. Ba thành phần này có sẵn khi cài Docker theo hướng dẫn của Docker. Tài khoản cài đặt chạy được lệnh `docker` mà không cần `sudo`.
- Git.
- Kết nối Internet để tải các image Docker, các thư viện của service `core` và bản cập nhật của cơ sở dữ liệu mã độc.
- Khoảng 5 GB dung lượng đĩa cho các image Docker và dữ liệu ban đầu, chưa tính các file được tải lên.
- Khoảng 2,5 GB RAM cho các service.

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

Lệnh này tạo thư mục làm việc `~/saigonos`. Thư mục bao gồm file `compose.yaml`, thư mục `config` và file `.env`. File `.env` chứa các mật khẩu được tạo ngẫu nhiên.

Hệ thống dùng các cổng 9080, 9180, 9280 và 9380. Nếu một trong các cổng này đang được chương trình khác sử dụng, hãy chọn cổng khác theo mục [Cấu hình](#cấu-hình).

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
BÌNH THƯỜNG    apisix       đang chạy
BÌNH THƯỜNG    clamav       đang chạy
BÌNH THƯỜNG    core         đang chạy
BÌNH THƯỜNG    databases    đã chạy xong
BÌNH THƯỜNG    etcd         đang chạy
BÌNH THƯỜNG    freshclam    đang chạy
BÌNH THƯỜNG    jwks         đã chạy xong
BÌNH THƯỜNG    keycloak     đang chạy
BÌNH THƯỜNG    migrate      đã chạy xong
BÌNH THƯỜNG    operaton     đang chạy
BÌNH THƯỜNG    postgres     đang chạy
BÌNH THƯỜNG    postgrest    đang chạy
BÌNH THƯỜNG    processes    đã chạy xong
BÌNH THƯỜNG    realm        đã chạy xong
BÌNH THƯỜNG    routes       đã chạy xong
BÌNH THƯỜNG    seaweedfs    đang chạy
BÌNH THƯỜNG    Đăng nhập    Keycloak trả lời tại http://localhost:9080/auth
BÌNH THƯỜNG    API          PostgREST trả lời, access token không hợp lệ bị từ chối
BÌNH THƯỜNG    Core API     service core trả lời, access token không hợp lệ bị từ chối
BÌNH THƯỜNG    Operaton     Operaton chuyển tới trang đăng nhập, REST của Operaton bị chặn
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
| http://localhost:9080/api/ | REST API của PostgREST và [tài liệu API](#tài-liệu-api) | Access token do Keycloak cấp. Lời gọi không có access token chỉ dùng được các bảng và hàm đã cấp cho role `anon` |
| http://localhost:9080/core/openapi.json | Tài liệu OpenAPI của [service core](#api-của-service-core) | Không cần đăng nhập. Các API trong tài liệu cần access token do Keycloak cấp, trừ `/core/health` và [đường dẫn tải về](#tải-file-về) |

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

Mọi giá trị cấu hình được đặt bằng tùy chọn của lệnh `saigonos init`. Lệnh này có thể chạy lại nhiều lần. Các mật khẩu đã tạo được giữ nguyên.

| Tùy chọn | Mặc định | Ý nghĩa |
|---|---|---|
| `--home` | `~/saigonos` | Thư mục làm việc. Có thể đặt bằng biến môi trường `SAIGONOS_HOME` |
| `--http-host` | `127.0.0.1` | Địa chỉ IP mà cổng HTTP của API Gateway lắng nghe. Với giá trị mặc định, hệ thống chỉ truy cập được từ chính máy cài đặt |
| `--http-port` | `9080` | Cổng HTTP của API Gateway |
| `--admin-port` | `9180` | Cổng quản trị của APISIX, chỉ truy cập được từ chính máy cài đặt |
| `--keycloak-port` | `9280` | Cổng của Keycloak, chỉ truy cập được từ chính máy cài đặt. Admin Console của realm master dùng cổng này |
| `--seaweedfs-port` | `9380` | Cổng Admin UI của SeaweedFS, chỉ truy cập được từ chính máy cài đặt |
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
server {
    listen 443 ssl;
    server_name dx.example.com;

    ssl_certificate /etc/letsencrypt/live/dx.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dx.example.com/privkey.pem;

    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:9080;
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

### 3. Kiểm tra hệ thống

```bash
saigonos doctor
```

Lệnh này gọi hệ thống qua địa chỉ `https://dx.example.com`. Do đó, lệnh cũng kiểm tra được kết nối qua reverse proxy và chứng chỉ. Nếu reverse proxy không gửi đủ các header ở bước 2, lệnh báo lỗi ở mục Đăng nhập và ghi địa chỉ mà Keycloak nhận được.

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

Chỉ tài khoản có realm role `admin` đăng nhập được vào ba trang này. Cách tạo tài khoản được trình bày ở mục [Tạo tài khoản quản trị của realm saigonos](#tạo-tài-khoản-quản-trị-của-realm-saigonos). Mỗi lần đăng nhập, tài khoản phải nhập mật khẩu và mã OTP, kể cả khi đã đăng nhập vào một trang khác của hệ thống. Tài khoản không có realm role `admin` bị từ chối ngay sau khi nhập mật khẩu. Khi đó, trang đăng nhập báo rằng chỉ tài khoản quản trị mới vào được trang này. Nội dung thông báo có khóa `saigonos-operaton-admin-only` và sửa được trong Admin Console của realm `saigonos`, ở mục Realm settings, thẻ Localization, phần Realm overrides. Keycloak tính mỗi lần bị từ chối là một lần đăng nhập sai. Do đó, hai lần bị từ chối trong vòng 1 giây làm tài khoản tạm bị khóa 60 giây.

Operaton làm mới access token ở mỗi lời gọi của ba trang. Do đó, khi một tài khoản bị khóa trong Keycloak, phiên đăng nhập của tài khoản trong Operaton kết thúc ngay ở lời gọi tiếp theo. Nút đăng xuất của Operaton dùng địa chỉ `/logout` của API Gateway.

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
- Mỗi quy trình phải có thuộc tính `operaton:historyTimeToLive`, tức thời gian giữ lịch sử của quy trình. Ví dụ, giá trị `P30D` là 30 ngày.
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

### Bắt đầu quy trình

Lời gọi `POST /core/processes/{key}/start` bắt đầu phiên bản mới nhất của quy trình có mã `key`. Mã quy trình là thuộc tính `id` của thẻ `process`. Lời gọi cần access token của người dùng đã đăng nhập.

Người gọi phải có một realm role nằm trong thuộc tính `operaton:candidateStarterGroups` của thẻ `process`. Giá trị của thuộc tính là danh sách tên realm role, cách nhau bởi dấu phẩy, không dùng biểu thức `${...}`. Quy trình không có thuộc tính này thì không ai bắt đầu được qua API. File BPMN viết cho Camunda 7 với tiền tố `camunda:` cũng được đọc như Operaton đọc.

Nội dung của lời gọi có thể chứa các biến của quy trình trong trường `variables`. Tên biến bắt đầu bằng chữ cái không dấu hoặc dấu gạch dưới, tiếp theo là chữ cái không dấu, chữ số hoặc dấu gạch dưới, dài tối đa 64 ký tự. Giá trị của biến được đổi sang kiểu của Operaton như sau:

| Giá trị trong JSON | Kiểu biến trong Operaton |
|---|---|
| Chuỗi tối đa 4.000 ký tự | `String` |
| Số nguyên từ -2^63 tới 2^63 - 1 | `Long` |
| Số thực | `Double` |
| `true` hoặc `false` | `Boolean` |
| `null` | `Null` |

Service `core` ghi mã người gọi, tức claim `sub` của access token, vào biến `initiator`. Khi điểm bắt đầu của quy trình có thuộc tính `operaton:initiator`, biến mang tên ghi trong thuộc tính này cũng nhận mã người gọi. Người gọi không gửi được các biến này.

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

Quy trình `yeu_cau` trong ví dụ được lưu trong file `yeu-cau.bpmn`. Người có realm role `nguoi-gui` bắt đầu được quy trình. Việc `xu_ly` chờ một người có realm role `nhan-vien` nhận:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:operaton="http://operaton.org/schema/1.0/bpmn"
                  id="yeu_cau_dinh_nghia" targetNamespace="https://dx.example.com/bpmn">
  <bpmn:process id="yeu_cau" name="Tiếp nhận yêu cầu" isExecutable="true"
                operaton:historyTimeToLive="P30D" operaton:candidateStarterGroups="nguoi-gui">
    <bpmn:startEvent id="bat_dau" />
    <bpmn:sequenceFlow id="luong_1" sourceRef="bat_dau" targetRef="xu_ly" />
    <bpmn:userTask id="xu_ly" name="Xử lý yêu cầu" operaton:candidateGroups="nhan-vien" />
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

Lời gọi `POST /core/tasks/{id}/complete` hoàn thành việc mà người gọi đã nhận. Chỉ người nhận việc mới hoàn thành được việc. Nội dung của lời gọi có thể chứa các biến trong trường `variables`, theo cùng quy tắc với lời gọi bắt đầu quy trình. Service `core` gửi các biến này qua form của việc trong Operaton. Sau đó, quy trình đi tiếp sang bước sau. Người hoàn thành việc cũng không gửi được biến `initiator` và biến ghi trong thuộc tính `operaton:initiator`.

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

Hàm nhận đúng một tham số kiểu `jsonb` và trả về kiểu `jsonb`. Tham số là một object chứa mọi biến của quy trình, ví dụ `{"ma_yeu_cau": "YC-01", "ket_qua": "Đã thay cáp màn hình"}`. Biến kiểu ngày giờ được truyền dưới dạng chuỗi. Quy trình có biến thuộc kiểu khác chuỗi, số, ngày giờ, `true`, `false` và `null` thì bước máy làm không chạy được. Hàm trả về một object hoặc `null`. Mỗi khóa của object trở thành một biến của quy trình, theo quy tắc ở mục [Bắt đầu quy trình](#bắt-đầu-quy-trình). Hàm không ghi được biến `initiator` và biến ghi trong thuộc tính `operaton:initiator`.

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
