<!-- SPDX-License-Identifier: Apache-2.0 -->
# Kiểm thử

SaigonOS có ba loại kiểm thử. Unit test và test luật OPA chạy bằng lệnh `make check`. Integration test chạy cả hệ thống bằng Docker Compose, qua lệnh `make integration`. CI chạy cả ba loại ở mỗi pull request.

## Integration test

Integration test cần Docker đang hoạt động. Ở lần chạy đầu tiên, Docker tải khoảng 1,5 GB image. Mỗi nhóm kiểm thử dựng một hệ thống riêng và cần khoảng 3 GB RAM. Một lượt chạy mất khoảng 40 phút. Với mỗi nhóm có khởi động hệ thống, lệnh thực hiện các bước sau:

1. Tạo một thư mục làm việc tạm bằng `saigonos init` với các cổng còn trống.
2. Khởi động hệ thống bằng `saigonos up`.
3. Chạy các kiểm thử của nhóm.
4. Xóa container và dữ liệu bằng `saigonos down --volumes`, rồi xóa image của service `core` vừa build.

Các nhóm kiểm thử nằm trong thư mục [`tests/integration`](https://github.com/tynnpdhsp/SaigonOS/tree/main/tests/integration):

| File | Nội dung |
|---|---|
| `test_stack.py` | Hệ thống với cấu hình mặc định, API Gateway và tường lửa ứng dụng web |
| `test_database.py` | Service `migrate`, Row-Level Security, role `anon`, audit log và bảng sự đồng ý |
| `test_storage.py` | SeaweedFS và ClamAV |
| `test_core.py` | Service `core`, access token giả, access token hết hạn và việc đổi khóa ký |
| `test_files.py` | Tải file lên, quét mã độc và tải file về |
| `test_workflow.py` | Operaton, đăng nhập Cockpit, quy trình, form, việc và hẹn giờ |
| `test_realtime.py` | Centrifugo, quyền nghe kênh, history, thông báo và Telegram |
| `test_caddy.py` | Caddy với chứng chỉ do Caddy tự cấp |
| `test_monitoring.py` | Prometheus, Loki, Grafana và việc tắt giám sát |
| `test_apps.py` | Soát và cài đặt ứng dụng, lưu trữ, chốt số liệu và hồ dữ liệu |
| `test_sample_app.py` | Ứng dụng mẫu `examples/phong-may` qua API, với từng role |
| `test_recovery.py` | Sao lưu rồi khôi phục tại chỗ và vào một thư mục làm việc mới |

Để chạy một nhóm, chạy `pytest -m integration` với tên file, ví dụ `pytest -m integration tests/integration/test_sample_app.py`.

## Lưu ý khi viết integration test

- SeaweedFS và ClamAV nằm trong mạng Docker riêng và không mở cổng ra máy cài đặt. Kiểm thử gọi hai service này từ một container tạm gắn vào mạng của chúng. Mẫu mã độc là file EICAR, một file thử vô hại mà mọi phần mềm diệt virus đều nhận ra.
- Sau khi một service được tạo lại hoặc khởi động lại, API Gateway cần khoảng 1 giây để nhận địa chỉ IP mới. Do đó, kiểm thử dùng hàm `Stack.up()` thay cho lệnh `saigonos up`, và gọi `Stack.wait_until_answers()` trước khi gọi API qua API Gateway.
- Kiểm thử cần nhiều lời gọi chạy chồng lên nhau thì tạm dừng service bằng `docker compose pause`, gửi các lời gọi, rồi chạy lại service.
- Nhóm kiểm thử Caddy tạo hai mạng Docker tạm, một cho IPv4 và một cho IPv6. Do đó, máy chạy kiểm thử cần hỗ trợ IPv6.
- Kiểm thử gọi API của Prometheus và Loki bằng `wget` bên trong chính container đó qua địa chỉ `127.0.0.1`, vì `wget` của busybox có thể không phân giải được tên service.
