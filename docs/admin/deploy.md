<!-- SPDX-License-Identifier: Apache-2.0 -->
# Triển khai lên máy chủ

## Máy chủ chưa có reverse proxy

Trên máy chủ chưa có reverse proxy, SaigonOS dùng Caddy để nhận kết nối HTTPS từ người dùng. Caddy tự lấy chứng chỉ từ Let's Encrypt và tự gia hạn chứng chỉ. Caddy cũng hỗ trợ HTTP/3 và chuyển các kết nối HTTP sang HTTPS.

Caddy dùng mạng của máy chủ (host network) để thấy đúng địa chỉ IP của người dùng qua IPv4 và IPv6. Do đó, cách triển khai này chỉ dùng được trên Linux. Cổng 80 và 443 của máy chủ phải còn trống. Nếu một web server khác đang dùng hai cổng này, hãy làm theo mục [Triển khai trên máy chủ đã có reverse proxy](#máy-chủ-đã-có-reverse-proxy).

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

### 4. Kiểm tra hệ thống qua HTTPS

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

Sau khi tắt Caddy, người dùng chỉ truy cập được hệ thống qua một reverse proxy khác. Cách cấu hình reverse proxy được trình bày ở mục [Triển khai trên máy chủ đã có reverse proxy](#máy-chủ-đã-có-reverse-proxy).

## Máy chủ đã có reverse proxy

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

Khối `map` và ba dòng `proxy_http_version`, `Upgrade`, `Connection` cho phép Nginx chuyển tiếp kết nối WebSocket tới [Centrifugo](../apps/realtime.md). Khối `map` đặt ở ngoài khối `server` và dùng tên biến riêng của SaigonOS để không trùng với cấu hình của các site khác. Centrifugo gửi ping 25 giây một lần. Do đó, thời gian chờ mặc định 60 giây của Nginx không đóng các kết nối WebSocket đang mở.

### 3. Kiểm tra hệ thống qua reverse proxy

```bash
saigonos doctor
```

Lệnh này gọi hệ thống qua địa chỉ `https://dx.example.com`. Do đó, lệnh cũng kiểm tra được kết nối qua reverse proxy và chứng chỉ. Nếu reverse proxy không gửi đủ các header ở bước 2, lệnh báo lỗi ở mục Đăng nhập và ghi địa chỉ mà Keycloak nhận được. Nếu reverse proxy không chuyển tiếp kết nối WebSocket, lệnh báo lỗi ở mục Centrifugo.
