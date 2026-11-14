<!-- SPDX-License-Identifier: Apache-2.0 -->
# Nhật ký thay đổi

File này ghi lại các thay đổi đáng chú ý của SaigonOS. Cách ghi tuân theo [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Số phiên bản tuân theo [Semantic Versioning](https://semver.org/lang/vi/).

Mục "Chưa phát hành" ghi các thay đổi đã có trên `main` nhưng chưa có trong release nào.

## [Chưa phát hành]

## [0.2.0] - 2026-11-14

### Thêm

- Service `caddy` nhận kết nối HTTPS trên máy chủ chưa có reverse proxy. Caddy tự lấy chứng chỉ từ Let's Encrypt và bật HSTS. Caddy cũng hỗ trợ HTTP/3 và chuyển các kết nối HTTP sang HTTPS. Caddy dùng mạng của máy chủ nên thấy đúng địa chỉ IP của người dùng qua IPv4 và IPv6. Các header `X-Forwarded-*` do người dùng tự gửi bị bỏ qua.
- Tùy chọn `--caddy` và `--no-caddy` của lệnh `saigonos init` bật và tắt Caddy. Caddy mặc định tắt. Khi Caddy bật, địa chỉ truy cập phải bắt đầu bằng `https://`.
- Lệnh `saigonos doctor` tin chứng chỉ do Caddy tự cấp, ví dụ chứng chỉ cho `localhost`.
- Lệnh `saigonos doctor` báo lỗi khi Keycloak nhận lời gọi qua một địa chỉ khác với `SAIGONOS_URL`. Lỗi này xảy ra khi reverse proxy không gửi đủ các header `X-Forwarded-Proto`, `X-Forwarded-Host` và `X-Forwarded-Port`.
- Hướng dẫn triển khai trên máy chủ chưa có reverse proxy trong README.

### Thay đổi

- Lệnh `saigonos doctor` ghi `BÌNH THƯỜNG` thay cho `ĐẠT` và ghi `healthcheck báo lỗi` thay cho `không đạt healthcheck`. Các cột cách nhau 4 dấu cách.
- Lệnh `saigonos init` từ chối cổng HTTP trùng các cổng 7085, 9090, 9091, 9180 và 9443. APISIX dùng các cổng này bên trong container. Ở phiên bản 0.1.1, các cổng này vẫn được chấp nhận.
- Lệnh `saigonos up` và `saigonos down` xóa container của Caddy sau khi Caddy bị tắt bằng lệnh `saigonos init --no-caddy`.
- Mục "Triển khai sau reverse proxy HTTPS" của README đổi tên thành "Triển khai trên máy chủ đã có reverse proxy".

### Sửa

- Khi người dùng truy cập thẳng API Gateway qua cổng 80, `token_endpoint` của Keycloak không còn kèm cổng 9080. Lỗi này có từ phiên bản 0.1.0. Để sửa lỗi, APISIX lắng nghe trong container đúng cổng HTTP được mở ra máy chủ.

## [0.1.1] - 2026-11-13

### Thêm

- Tùy chọn `--http-host` của lệnh `saigonos init` đặt địa chỉ IP mà cổng HTTP của API Gateway lắng nghe. Giá trị `0.0.0.0` cho phép truy cập từ máy khác.
- Hướng dẫn triển khai sau reverse proxy HTTPS và hướng dẫn cập nhật phiên bản trong README.

### Thay đổi

- Cổng HTTP của API Gateway mặc định chỉ lắng nghe trên địa chỉ `127.0.0.1`. Ở phiên bản 0.1.0, cổng này lắng nghe trên mọi địa chỉ của máy cài đặt. Để các máy khác vẫn truy cập được sau khi cập nhật, chạy lệnh `saigonos init --http-host 0.0.0.0`.

### Sửa

- Khi SaigonOS chạy sau reverse proxy, APISIX giữ nguyên các header `X-Forwarded-Proto`, `X-Forwarded-Host` và `X-Forwarded-Port` do proxy trong mạng nội bộ gửi tới. Địa chỉ IP của người dùng được lấy từ header `X-Forwarded-For`. Ở phiên bản 0.1.0, Keycloak trả về địa chỉ `http` kèm cổng 9080 và giới hạn tần suất gọi tính mọi người dùng vào cùng một địa chỉ IP.

### Bảo mật

- APISIX bỏ header `X-Forwarded-For` do máy ngoài mạng nội bộ gửi tới. Ở phiên bản 0.1.0, một máy bên ngoài có thể dùng header này để khai báo với Keycloak một địa chỉ IP trong mạng nội bộ.

## [0.1.0] - 2026-11-12

### Thêm

- Package Python `saigonos` có lệnh `saigonos --version`.
- Giấy phép Apache-2.0 với dòng SPDX ở đầu mọi file, được kiểm tra bằng REUSE.
- Lock file `requirements.txt` và `requirements-dev.txt` cố định phiên bản thư viện.
- Bộ tài liệu khung gồm README, hướng dẫn đóng góp, chính sách bảo mật và mẫu issue.
- `DEPENDENCIES.md` liệt kê thư viện, phần mềm chạy trong container và công cụ phát triển kèm giấy phép, được tạo bằng lệnh `make dependencies`.
- File nén mã nguồn `.tar.gz` kèm `SHA256SUMS`, được tạo tự động khi push tag phiên bản.
- Bộ Docker Compose gồm PostgreSQL, Keycloak, etcd, APISIX và PostgREST. Mỗi service được cố định phiên bản, có healthcheck và tự khởi động lại.
- Realm `saigonos` của Keycloak được nạp từ file. Tài khoản có vai trò `admin` phải nhập OTP khi đăng nhập. Access token có thời hạn 60 giây.
- Route `/auth` tới Keycloak và route `/api` tới PostgREST trên API Gateway. Route `/api` kiểm tra access token và giới hạn tần suất gọi.
- Lệnh `saigonos init` tạo thư mục làm việc gồm file `compose.yaml`, thư mục `config` và file `.env` chứa mật khẩu ngẫu nhiên. Khi chạy lại, các giá trị đã có trong file `.env` được giữ nguyên.
- Lệnh `saigonos up` và `saigonos down` khởi động và dừng các service bằng Docker Compose.
- Lệnh `saigonos doctor` kiểm tra trạng thái từng service và API Gateway.
- Hướng dẫn cài đặt bằng pip và Docker Compose trong README.

[Chưa phát hành]: https://github.com/tynnpdhsp/SaigonOS/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.2.0
[0.1.1]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.1.1
[0.1.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.1.0
