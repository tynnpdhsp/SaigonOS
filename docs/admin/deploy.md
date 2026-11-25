<!-- SPDX-License-Identifier: Apache-2.0 -->
# Triển khai lên máy chủ

Để phục vụ người dùng qua Internet, hệ thống cần một tên miền và HTTPS. Cách triển khai tùy theo máy chủ đã có reverse proxy hay chưa.

## Máy chủ chưa có reverse proxy

Trên máy chủ chưa có reverse proxy, SaigonOS dùng Caddy để nhận kết nối HTTPS. Caddy tự lấy và tự gia hạn chứng chỉ của Let's Encrypt. Caddy cũng hỗ trợ HTTP/3 và chuyển kết nối HTTP sang HTTPS. Caddy dùng mạng của máy chủ (host network) để thấy đúng địa chỉ IP của người dùng. Do đó, cách này chỉ dùng được trên Linux, và cổng 80, 443 của máy chủ phải còn trống.

### 1. Trỏ tên miền về máy chủ

Tạo bản ghi A trỏ tên miền về địa chỉ IPv4 của máy chủ. Nếu máy chủ có địa chỉ IPv6, tạo thêm bản ghi AAAA. Caddy chỉ lấy được chứng chỉ khi tên miền đã trỏ đúng về máy chủ.

### 2. Mở cổng

Tường lửa của nhà cung cấp máy chủ và tường lửa trên máy chủ phải mở cổng 80 TCP, 443 TCP và 443 UDP. Ví dụ, với UFW trên Ubuntu:

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

Trong đó `dx.example.com` là tên miền của hệ thống. Cổng HTTP của API Gateway vẫn chỉ lắng nghe trên địa chỉ `127.0.0.1`, và Caddy chuyển tiếp kết nối của người dùng tới cổng này. Caddy bỏ qua các header `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host` và `X-Forwarded-Port` do người dùng tự gửi. Khi chạy lại lệnh `saigonos init` không kèm tùy chọn `--caddy`, Caddy vẫn được bật.

### 4. Kiểm tra hệ thống qua HTTPS

```bash
saigonos doctor
```

Kết quả có thêm dòng của service `caddy`. Lệnh gọi hệ thống qua địa chỉ `https://dx.example.com`, nên kiểm tra được cả chứng chỉ. Ở lần khởi động đầu tiên, Caddy cần thêm vài giây để lấy chứng chỉ. Khi lệnh báo lỗi chứng chỉ, chờ một lúc rồi chạy lại.

### Chứng chỉ

Chứng chỉ được lưu trong thư mục `~/saigonos/data/caddy`. Lệnh `saigonos down --volumes` không xóa thư mục này. Let's Encrypt chỉ cấp tối đa 5 chứng chỉ cho một tên miền trong 7 ngày. Do đó, cần giữ thư mục này khi cài đặt lại hệ thống. Thư mục thuộc quyền root. Để xóa thư mục, dừng hệ thống bằng `saigonos down` rồi chạy lệnh:

```bash
sudo rm -rf ~/saigonos/data/caddy
```

Caddy gửi header `Strict-Transport-Security` (HSTS). Sau lần truy cập đầu tiên, trình duyệt chỉ kết nối tới tên miền này bằng HTTPS trong một năm.

### Tắt Caddy

```bash
saigonos init --no-caddy
saigonos up
```

Khi dùng trực tiếp Docker Compose, chạy `docker compose rm --stop --force caddy` trước lệnh `docker compose up -d --wait`. Sau khi tắt Caddy, người dùng chỉ truy cập được hệ thống qua một reverse proxy khác, như mục sau.

## Máy chủ đã có reverse proxy

Trên máy chủ đã có reverse proxy, ví dụ Nginx, reverse proxy nhận kết nối HTTPS từ người dùng rồi chuyển tiếp tới cổng HTTP của API Gateway trên cùng máy.

### 1. Đặt địa chỉ truy cập

```bash
saigonos init --url https://dx.example.com
saigonos up
```

Cổng HTTP vẫn chỉ lắng nghe trên địa chỉ `127.0.0.1`. Do đó, người dùng chỉ truy cập được hệ thống qua reverse proxy.

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

Reverse proxy phải gửi đủ các header trong ví dụ trên. API Gateway dùng các header này để biết địa chỉ mà người dùng truy cập và địa chỉ IP của người dùng. API Gateway chỉ tin các header này khi kết nối đến từ một địa chỉ IP trong các dải `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12` và `192.168.0.0/16`. Header `X-Forwarded-For` được đặt bằng `$remote_addr` để người dùng không tự khai báo được địa chỉ IP khác.

Dòng `client_max_body_size` cho Nginx nhận nội dung tới 10 MB, bằng giới hạn dung lượng file mặc định. Khi đổi giới hạn bằng tùy chọn `--max-file-size`, cần đổi cả giá trị này. Khối `map` và ba dòng `proxy_http_version`, `Upgrade`, `Connection` chuyển tiếp kết nối WebSocket của [cập nhật tức thời](../apps/realtime.md).

### 3. Kiểm tra hệ thống qua reverse proxy

```bash
saigonos doctor
```

Lệnh gọi hệ thống qua địa chỉ `https://dx.example.com`. Khi reverse proxy không gửi đủ các header, lệnh báo lỗi ở dòng Đăng nhập. Khi reverse proxy không chuyển tiếp kết nối WebSocket, lệnh báo lỗi ở dòng Centrifugo.
