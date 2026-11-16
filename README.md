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

Hệ thống dùng ba cổng 9080, 9180 và 9280. Nếu một trong ba cổng đang được chương trình khác sử dụng, hãy chọn cổng khác theo mục [Cấu hình](#cấu-hình).

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
BÌNH THƯỜNG    etcd         đang chạy
BÌNH THƯỜNG    jwks         đã chạy xong
BÌNH THƯỜNG    keycloak     đang chạy
BÌNH THƯỜNG    migrate      đã chạy xong
BÌNH THƯỜNG    postgres     đang chạy
BÌNH THƯỜNG    postgrest    đang chạy
BÌNH THƯỜNG    realm        đã chạy xong
BÌNH THƯỜNG    routes       đã chạy xong
BÌNH THƯỜNG    Đăng nhập    Keycloak trả lời tại http://localhost:9080/auth
BÌNH THƯỜNG    API          PostgREST trả lời, access token không hợp lệ bị từ chối
Hệ thống hoạt động bình thường.
```

## Truy cập hệ thống

Với cấu hình mặc định, hệ thống chỉ truy cập được từ chính máy cài đặt và có các địa chỉ sau:

| Địa chỉ | Nội dung | Thông tin đăng nhập |
|---|---|---|
| http://localhost:9080/auth/admin/saigonos/console/ | Admin Console của realm `saigonos`, dùng để quản lý người dùng | Tài khoản quản trị của realm `saigonos`, đăng nhập bằng mật khẩu và OTP. Cách tạo tài khoản được trình bày ở mục [Tài khoản quản trị](#tài-khoản-quản-trị) |
| http://localhost:9280/auth/admin/master/console/ | Admin Console của realm master, chỉ truy cập được từ chính máy cài đặt | Tài khoản `admin`, mật khẩu là giá trị `KEYCLOAK_ADMIN_PASSWORD` |
| http://127.0.0.1:9180/ui/ | Dashboard của APISIX, chỉ truy cập được từ chính máy cài đặt | Khóa quản trị (Admin Key) là giá trị `APISIX_ADMIN_KEY` |
| http://localhost:9080/api/ | REST API của PostgREST và [tài liệu API](#tài-liệu-api) | Access token do Keycloak cấp. Lời gọi không có access token chỉ dùng được các bảng và hàm đã cấp cho role `anon` |

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

## Cấu hình

Mọi giá trị cấu hình được đặt bằng tùy chọn của lệnh `saigonos init`. Lệnh này có thể chạy lại nhiều lần. Các mật khẩu đã tạo được giữ nguyên.

| Tùy chọn | Mặc định | Ý nghĩa |
|---|---|---|
| `--home` | `~/saigonos` | Thư mục làm việc. Có thể đặt bằng biến môi trường `SAIGONOS_HOME` |
| `--http-host` | `127.0.0.1` | Địa chỉ IP mà cổng HTTP của API Gateway lắng nghe. Với giá trị mặc định, hệ thống chỉ truy cập được từ chính máy cài đặt |
| `--http-port` | `9080` | Cổng HTTP của API Gateway |
| `--admin-port` | `9180` | Cổng quản trị của APISIX, chỉ truy cập được từ chính máy cài đặt |
| `--keycloak-port` | `9280` | Cổng của Keycloak, chỉ truy cập được từ chính máy cài đặt. Admin Console của realm master dùng cổng này |
| `--url` | `http://localhost:9080` | Địa chỉ mà người dùng truy cập hệ thống |
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

Lệnh `saigonos init` cập nhật file `compose.yaml` và thư mục `config` theo phiên bản mới. Lệnh `saigonos up` tạo lại các container với cấu hình mới. Service `migrate` chạy các file SQL mới của phiên bản để cập nhật cơ sở dữ liệu. Service `realm` thêm các thiết lập mới của phiên bản vào realm `saigonos` của Keycloak.

## Tham gia phát triển

- Báo lỗi hoặc đề xuất tính năng: mở một [issue](https://github.com/tynnpdhsp/SaigonOS/issues/new/choose).
- Đóng góp mã nguồn: xem [CONTRIBUTING.md](CONTRIBUTING.md).
- Báo cáo lỗ hổng bảo mật: xem [SECURITY.md](SECURITY.md).

## Giấy phép

SaigonOS được phát hành theo giấy phép [Apache-2.0](LICENSE). Mỗi file trong repo có một dòng `SPDX-License-Identifier` ở đầu. Công cụ [REUSE](https://reuse.software/) được dùng để kiểm tra các dòng này.

Các thư viện, phần mềm chạy trong container và công cụ mà SaigonOS sử dụng được liệt kê trong [DEPENDENCIES.md](DEPENDENCIES.md). Mỗi dòng ghi rõ phiên bản, giấy phép, mô tả và nguồn.
