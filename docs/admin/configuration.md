<!-- SPDX-License-Identifier: Apache-2.0 -->
# Cấu hình

Cấu hình được đặt bằng các tùy chọn của lệnh `saigonos init`. Lệnh này chạy lại được nhiều lần. Các mật khẩu đã tạo và các dòng được thêm bằng tay vào file `.env` được giữ nguyên. Sau khi đổi cấu hình, chạy `saigonos up` để áp dụng.

| Tùy chọn | Mặc định | Ý nghĩa |
|---|---|---|
| `--home` | `~/saigonos` | Thư mục làm việc. Có thể đặt bằng biến môi trường `SAIGONOS_HOME` |
| `--http-host` | `127.0.0.1` | Địa chỉ IP mà cổng HTTP của API Gateway lắng nghe. Giá trị mặc định chỉ cho truy cập từ chính máy cài đặt |
| `--http-port` | `9080` | Cổng HTTP của API Gateway |
| `--admin-port` | `9180` | Cổng quản trị của APISIX |
| `--keycloak-port` | `9280` | Cổng của Keycloak, dùng cho Admin Console của realm master |
| `--seaweedfs-port` | `9380` | Cổng Admin UI của SeaweedFS |
| `--centrifugo-port` | `9480` | Cổng API của server và Admin web của Centrifugo |
| `--url` | `http://localhost:9080` | Địa chỉ mà người dùng truy cập hệ thống |
| `--max-file-size` | `10` | Dung lượng tối đa của một file tải lên, tính bằng MB, từ 1 đến 100. API Gateway từ chối lời gọi có nội dung lớn hơn |
| `--caddy`, `--no-caddy` | Tắt | Bật hoặc tắt Caddy, như ở trang [Triển khai lên máy chủ](deploy.md) |
| `--monitoring`, `--no-monitoring` | Tắt | Bật hoặc tắt [giám sát](monitoring.md) |

Bốn cổng quản trị của APISIX, Keycloak, SeaweedFS và Centrifugo chỉ mở trên địa chỉ `127.0.0.1`. Cổng HTTP không được trùng các cổng 7085, 9090, 9091, 9180 và 9443. APISIX dùng các cổng này bên trong container.

Một số giá trị không có tùy chọn riêng mà được ghi thẳng vào file `.env`. Các giá trị này gồm:

- Cấu hình [Telegram và email](notifications.md).
- Dải mạng được mở [trang quản trị](access-rules.md#trang-quản-trị).
- Chế độ của [tường lửa ứng dụng web](waf.md#chế-độ-chỉ-ghi-log).
- Múi giờ của [hồ dữ liệu](data-lake.md).

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

Cách này chỉ nên dùng trong mạng nội bộ đáng tin cậy, vì kết nối HTTP không được mã hóa. API Gateway cũng tin header `X-Forwarded-For` do máy trong mạng nội bộ gửi tới. Do đó, một máy trong mạng nội bộ có thể khai báo địa chỉ IP khác với địa chỉ thật. Keycloak chỉ nhận kết nối HTTP từ địa chỉ IP trong mạng nội bộ. Để phục vụ người dùng qua Internet, làm theo trang [Triển khai lên máy chủ](deploy.md).

Khi đổi địa chỉ truy cập, chạy lại lệnh `saigonos init` với tùy chọn `--url` rồi chạy `saigonos up`. Lệnh `saigonos init` cập nhật cả cấu hình của Centrifugo theo địa chỉ mới. Do đó, sau khi sửa tay dòng `SAIGONOS_URL` của file `.env`, cũng cần chạy lại lệnh `saigonos init`.

## Khởi động và dừng

Hai lệnh `saigonos up` và `saigonos down` gọi Docker Compose trong thư mục làm việc. Có thể dùng trực tiếp các lệnh Docker Compose tương ứng:

| Thao tác | Lệnh `saigonos` | Lệnh Docker Compose trong `~/saigonos` |
|---|---|---|
| Khởi động | `saigonos up` | `docker compose up -d --wait` rồi `docker compose run --rm apps apply --all` |
| Dừng và giữ dữ liệu | `saigonos down` | `docker compose down` |
| Dừng và xóa dữ liệu | `saigonos down --volumes` | `docker compose down --volumes` |

Sau khi các service sẵn sàng, lệnh `saigonos up` cài đặt lại mọi ứng dụng đã cài đặt. Do đó, phần của ứng dụng bị sửa tay trên Keycloak, APISIX hay Operaton được đặt lại theo bản khai báo.
