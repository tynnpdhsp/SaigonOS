<!-- SPDX-License-Identifier: Apache-2.0 -->
# Thư viện và image

## Thêm thư viện

Chỉ sử dụng thư viện có giấy phép nguồn mở được OSI công nhận. Không sao chép mã nguồn của dự án khác vào repo.

1. Khai báo thư viện trong [`pyproject.toml`](https://github.com/tynnpdhsp/SaigonOS/blob/main/pyproject.toml). Thư viện của lệnh `saigonos` nằm trong `dependencies`. Thư viện của service `core` nằm trong nhóm `core` của `[dependency-groups]`.
2. Thêm một mô tả ngắn cho thư viện vào `DESCRIPTIONS` trong [`scripts/dependencies.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/scripts/dependencies.py).
3. Chạy `make lock` để tạo lại các lock file.
4. Chạy `pip install -r requirements-dev.txt` để cài đặt đúng các phiên bản trong lock file.
5. Chạy `make dependencies` để tạo lại [DEPENDENCIES.md](https://github.com/tynnpdhsp/SaigonOS/blob/main/DEPENDENCIES.md).

Ở bước 5, lệnh sẽ báo lỗi "Giấy phép ngoài danh sách cho phép" nếu giấy phép của thư viện chưa có trong danh sách cho phép ở `scripts/dependencies.py`. Khi đó, hãy mở một issue để thảo luận trước khi thêm thư viện.

## Thêm hoặc đổi phiên bản image

Chỉ sử dụng phần mềm có giấy phép nguồn mở được OSI công nhận. Mỗi image phải ghi rõ phiên bản và không dùng tag `latest`.

1. Sửa dòng `image` trong [`src/saigonos/stack/compose.yaml`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/compose.yaml). Với base image của service `core`, sửa dòng `FROM` trong [`src/saigonos/stack/core/Dockerfile`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/core/Dockerfile), gồm cả tag và digest.
2. Đọc file giấy phép trong mã nguồn của đúng phiên bản đó.
3. Khai báo image trong `IMAGES` ở `scripts/dependencies.py`. Mỗi image cần giấy phép, mô tả và địa chỉ mã nguồn của phiên bản đó.
4. Chạy `make dependencies` để tạo lại [DEPENDENCIES.md](https://github.com/tynnpdhsp/SaigonOS/blob/main/DEPENDENCIES.md).

Lệnh `make lint` báo lỗi khi một image trong [`compose.yaml`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/compose.yaml) chưa được khai báo. Giấy phép chưa có trong danh sách cho phép cũng bị báo lỗi. Khi đó, hãy mở một issue để thảo luận trước khi thêm image.

Khi đổi phiên bản Operaton, kiểm tra lại file [`src/saigonos/stack/config/operaton/sso-logout.js`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/config/operaton/sso-logout.js). File này thay plugin đăng xuất của Operaton, vì plugin gốc của bản 2.2.1 không tìm thấy nút đăng xuất trong menu tài khoản. Kiểm thử `test_logout_button_ends_session_of_operaton` báo lỗi khi menu tài khoản không còn thẻ `a` có class `logout`.

Khi đổi phiên bản APISIX, kiểm tra lại file [`src/saigonos/stack/config/apisix/saigonos-dns.lua`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/config/apisix/saigonos-dns.lua). APISIX nạp file này qua thiết lập `lua_module_hook` trong `config.yaml`. File bọc hàm `new` của module `apisix.core.dns.client` để đặt `emptyTtl` 1 giây, vì thư viện DNS của APISIX mặc định giữ lỗi `name error` 30 giây. Không sửa thẳng module `resty.dns.client`, vì APISIX nạp lại module này mỗi lần tạo client DNS. Kiểm thử `test_gateway_answers_within_seconds_after_stopped_core_starts_again` trong [`test_core.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/tests/integration/test_core.py) cho APISIX dùng DNS giả trong [`tests/integration/fake_dns.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/tests/integration/fake_dns.py), dừng `core` 3 giây rồi chạy lại. Kiểm thử báo lỗi khi API Gateway còn trả lỗi sau khi `core` đã `healthy` 3 giây.

Mỗi service chạy lâu dài trong `compose.yaml` cần một healthcheck thật. Không tắt healthcheck bằng `disable: true`. Với service như vậy, lệnh `docker compose up --wait` của Docker Compose 2.x báo lỗi "has no healthcheck configured", dù Docker Compose 5 vẫn chạy được. Kiểm thử trong [`tests/test_compose_file.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/tests/test_compose_file.py) kiểm tra quy tắc này.