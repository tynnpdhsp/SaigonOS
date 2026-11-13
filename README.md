<!-- SPDX-License-Identifier: Apache-2.0 -->
# SaigonOS

SaigonOS là một hệ điều hành chuyển đổi số (DX-OS) nguồn mở. Phần lõi được xây dựng từ các phần mềm nguồn mở và không có giao diện cho người dùng cuối. Mỗi ứng dụng chỉ cần phát triển phần giao diện và gọi các service của lõi.

Lõi cung cấp bốn service chính:

- Quản lý định danh và đăng nhập một lần (Identity/SSO)
- Cổng API (API Gateway)
- Quản lý dữ liệu có cấu trúc và phi cấu trúc
- Luồng công việc (Workflow)

Phiên bản hiện tại cung cấp đăng nhập một lần, API Gateway và REST API cho dữ liệu có cấu trúc. Phần quản lý dữ liệu phi cấu trúc và luồng công việc đang được phát triển. Các thay đổi được ghi lại trong [CHANGELOG.md](CHANGELOG.md).

## Yêu cầu hệ thống

- Hệ điều hành Linux. SaigonOS được kiểm thử trên Ubuntu 24.04.
- Python 3.11 trở lên và pip.
- Docker Engine 25.0 trở lên và Docker Compose 2.20.2 trở lên. Tài khoản cài đặt chạy được lệnh `docker` mà không cần `sudo`.
- Git.
- Khoảng 2 GB dung lượng đĩa cho các image Docker và 1 GB RAM cho các service.

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

Hệ thống dùng hai cổng 9080 và 9180. Nếu một trong hai cổng đang được chương trình khác sử dụng, hãy chọn cổng khác theo mục [Cấu hình](#cấu-hình).

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
ĐẠT  apisix     đang chạy
ĐẠT  etcd       đang chạy
ĐẠT  jwks       đã chạy xong
ĐẠT  keycloak   đang chạy
ĐẠT  postgres   đang chạy
ĐẠT  postgrest  đang chạy
ĐẠT  routes     đã chạy xong
ĐẠT  Đăng nhập  Keycloak trả lời tại http://localhost:9080/auth
ĐẠT  API        lời gọi không có access token bị từ chối
Hệ thống hoạt động bình thường.
```

## Truy cập hệ thống

Với cấu hình mặc định, hệ thống chỉ truy cập được từ chính máy cài đặt và có các địa chỉ sau:

| Địa chỉ | Nội dung | Thông tin đăng nhập |
|---|---|---|
| http://localhost:9080/auth/admin/ | Admin Console của Keycloak | Tài khoản `admin`, mật khẩu là giá trị `KEYCLOAK_ADMIN_PASSWORD` |
| http://127.0.0.1:9180/ui/ | Dashboard của APISIX, chỉ truy cập được từ chính máy cài đặt | Khóa quản trị (Admin Key) là giá trị `APISIX_ADMIN_KEY` |
| http://localhost:9080/api/ | REST API của PostgREST | Access token do Keycloak cấp |

Các giá trị trên nằm trong file `~/saigonos/.env`. Ví dụ, để xem mật khẩu quản trị của Keycloak:

```bash
grep KEYCLOAK_ADMIN_PASSWORD ~/saigonos/.env
```

## Cấu hình

Mọi giá trị cấu hình được đặt bằng tùy chọn của lệnh `saigonos init`. Lệnh này có thể chạy lại nhiều lần. Các mật khẩu đã tạo được giữ nguyên.

| Tùy chọn | Mặc định | Ý nghĩa |
|---|---|---|
| `--home` | `~/saigonos` | Thư mục làm việc. Có thể đặt bằng biến môi trường `SAIGONOS_HOME` |
| `--http-host` | `127.0.0.1` | Địa chỉ IP mà cổng HTTP của API Gateway lắng nghe. Với giá trị mặc định, hệ thống chỉ truy cập được từ chính máy cài đặt |
| `--http-port` | `9080` | Cổng HTTP của API Gateway |
| `--admin-port` | `9180` | Cổng quản trị của APISIX, chỉ truy cập được từ chính máy cài đặt |
| `--url` | `http://localhost:9080` | Địa chỉ mà người dùng truy cập hệ thống |

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

Keycloak chỉ chấp nhận kết nối HTTP từ các địa chỉ IP trong mạng nội bộ. Để phục vụ người dùng qua Internet, hãy làm theo mục [Triển khai sau reverse proxy HTTPS](#triển-khai-sau-reverse-proxy-https).

## Khởi động và dừng

Hai lệnh `saigonos up` và `saigonos down` gọi Docker Compose trong thư mục làm việc. Có thể dùng trực tiếp các lệnh Docker Compose tương ứng.

| Thao tác | Lệnh `saigonos` | Lệnh Docker Compose trong `~/saigonos` |
|---|---|---|
| Khởi động | `saigonos up` | `docker compose up -d --wait` |
| Dừng và giữ dữ liệu | `saigonos down` | `docker compose down` |
| Dừng và xóa dữ liệu | `saigonos down --volumes` | `docker compose down --volumes` |

## Triển khai sau reverse proxy HTTPS

Để phục vụ người dùng qua Internet, SaigonOS cần chạy sau một reverse proxy có HTTPS, ví dụ Nginx. Reverse proxy nhận kết nối HTTPS từ người dùng và chuyển tiếp tới cổng HTTP của API Gateway trên cùng máy.

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

### 3. Kiểm tra hệ thống

```bash
saigonos doctor
```

Lệnh này gọi hệ thống qua địa chỉ `https://dx.example.com`. Do đó, lệnh cũng kiểm tra được reverse proxy và chứng chỉ.

## Cập nhật phiên bản

Các thay đổi của từng phiên bản được ghi trong [CHANGELOG.md](CHANGELOG.md). Khi cập nhật, dữ liệu và các mật khẩu trong file `.env` được giữ nguyên.

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

Lệnh `saigonos init` cập nhật file `compose.yaml` và thư mục `config` theo phiên bản mới. Lệnh `saigonos up` tạo lại các container với cấu hình mới.

## Tham gia phát triển

- Báo lỗi hoặc đề xuất tính năng: mở một [issue](https://github.com/tynnpdhsp/SaigonOS/issues/new/choose).
- Đóng góp mã nguồn: xem [CONTRIBUTING.md](CONTRIBUTING.md).
- Báo cáo lỗ hổng bảo mật: xem [SECURITY.md](SECURITY.md).

## Giấy phép

SaigonOS được phát hành theo giấy phép [Apache-2.0](LICENSE). Mỗi file trong repo có một dòng `SPDX-License-Identifier` ở đầu. Công cụ [REUSE](https://reuse.software/) được dùng để kiểm tra các dòng này.

Các thư viện, phần mềm chạy trong container và công cụ mà SaigonOS sử dụng được liệt kê trong [DEPENDENCIES.md](DEPENDENCIES.md). Mỗi dòng ghi rõ phiên bản, giấy phép, mô tả và nguồn.
