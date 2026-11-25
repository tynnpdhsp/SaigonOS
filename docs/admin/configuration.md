<!-- SPDX-License-Identifier: Apache-2.0 -->
# Cấu hình

Các giá trị cấu hình được đặt bằng tùy chọn của lệnh `saigonos init`. Lệnh này có thể chạy lại nhiều lần. Các mật khẩu đã tạo và các dòng được thêm bằng tay vào file `.env` được giữ nguyên. Riêng cấu hình Telegram, SMTP, dải mạng của trang quản trị và múi giờ của hồ dữ liệu được ghi trực tiếp vào file `.env`, như ở mục [Gửi thông báo qua Telegram](../apps/notifications.md#gửi-thông-báo-qua-telegram), mục [Gửi email](../apps/notifications.md#gửi-email), mục [Trang quản trị](access-rules.md#trang-quản-trị) và mục [Hồ dữ liệu](data-lake.md).

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
| `--monitoring`, `--no-monitoring` | Tắt | Bật hoặc tắt [giám sát](monitoring.md) bằng Prometheus, Loki và Grafana |

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

- Máy chủ chưa có reverse proxy: làm theo mục [Triển khai trên máy chủ chưa có reverse proxy](deploy.md#máy-chủ-chưa-có-reverse-proxy).
- Máy chủ đã có reverse proxy, ví dụ Nginx: làm theo mục [Triển khai trên máy chủ đã có reverse proxy](deploy.md#máy-chủ-đã-có-reverse-proxy).

## Khởi động và dừng

Hai lệnh `saigonos up` và `saigonos down` gọi Docker Compose trong thư mục làm việc. Có thể dùng trực tiếp các lệnh Docker Compose tương ứng.

| Thao tác | Lệnh `saigonos` | Lệnh Docker Compose trong `~/saigonos` |
|---|---|---|
| Khởi động | `saigonos up` | `docker compose up -d --wait` rồi `docker compose run --rm apps apply --all` |
| Dừng và giữ dữ liệu | `saigonos down` | `docker compose down` |
| Dừng và xóa dữ liệu | `saigonos down --volumes` | `docker compose down --volumes` |

Sau khi các service sẵn sàng, lệnh `saigonos up` cài đặt lại mọi ứng dụng đã cài đặt, như mục [Cài đặt ứng dụng](../apps/manifest.md#cài-đặt-ứng-dụng). Do đó, phần của ứng dụng bị sửa tay trên Keycloak, APISIX hay Operaton được đặt lại theo bản khai. Mỗi dòng kết quả bắt đầu bằng tên ứng dụng. Khi chưa có ứng dụng nào trong thư mục `apps`, lệnh bỏ qua bước này.
