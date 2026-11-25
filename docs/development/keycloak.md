<!-- SPDX-License-Identifier: Apache-2.0 -->
# Realm của Keycloak

Keycloak chỉ đọc file [`src/saigonos/stack/config/keycloak/realm.json`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/config/keycloak/realm.json) một lần khi tạo realm `saigonos`. Do đó, không thêm thiết lập mới vào file này.

Thiết lập mới của realm được thêm vào script [`setup-realm.lua`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/config/keycloak/setup-realm.lua) trong cùng thư mục. Mỗi lần hệ thống khởi động, service `realm` chạy script này và gọi Admin REST API của Keycloak. Script tuân theo các quy tắc sau:

- Chỉ thêm thiết lập còn thiếu. Khi thiết lập đã có, script không ghi đè, vì quản trị viên có thể đã sửa thiết lập đó.
- Chạy lại nhiều lần vẫn cho cùng một kết quả.
- In một dòng cho mỗi thiết lập vừa thêm.

Mỗi thiết lập mới cần một integration test. Kiểm thử xóa thiết lập khỏi realm, chạy `saigonos up` rồi kiểm tra thiết lập đã được thêm lại. Cách này giả lập một realm được tạo từ phiên bản cũ.

Script cũng cập nhật realm master. Keycloak tự tạo realm này khi khởi động lần đầu, nên mọi thiết lập của realm master đều nằm trong script. Riêng Frontend URL của realm master luôn được đặt theo giá trị `SAIGONOS_KEYCLOAK_PORT` trong file `.env`, kể cả khi quản trị viên đã sửa giá trị này. Sau khi đổi Frontend URL, script đăng nhập lại. Access token cũ mang địa chỉ cũ trong claim `iss` nên bị Keycloak từ chối.

API Gateway chặn mọi địa chỉ của realm master. Do đó, integration test gọi Admin REST API của Keycloak qua cổng `SAIGONOS_KEYCLOAK_PORT`, ví dụ bằng hàm `Stack.admin()` trong [`tests/integration/conftest.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/tests/integration/conftest.py).

Client `operaton` và luồng đăng nhập riêng của client này cũng là ngoại lệ. Script kiểm tra từng bước của luồng đăng nhập ở mỗi lần chạy. Khi luồng khác với thiết kế, script tắt client, xóa luồng, tạo lại luồng rồi bật lại client. Do đó, không có lúc nào client dùng luồng đăng nhập chung của realm. Các thiết lập bảo mật của client cũng được đặt lại ở mỗi lần chạy.

Bước từ chối trong luồng này dùng thông báo có khóa `saigonos-operaton-admin-only`, khai báo trong thiết lập `denyErrorMessage` của bước. Nội dung tiếng Việt và tiếng Anh của thông báo nằm trong Realm overrides của realm `saigonos`. Script chỉ thêm nội dung còn thiếu, nên nội dung mà quản trị viên đã sửa được giữ nguyên.

Mapper `audience saigonos` của client scope `roles` cũng là ngoại lệ. Mapper này thêm audience `saigonos` vào access token, không thêm vào ID token. Centrifugo chỉ nhận access token có audience này. Khi mapper bị sửa hoặc bị xóa, script đặt lại mapper ở lần chạy sau.

Mapper `amr` của client scope `basic` và giá trị `default.reference.value` của các bước đăng nhập cũng là ngoại lệ. Luật OPA của trang quản trị dựa vào claim `amr`, nên script đặt lại các thiết lập này khi bị sửa. Mapper phải bật `lightweight.claim`, vì client `security-admin-console` dùng lightweight access token. Keycloak chỉ ghi vào claim `amr` các bước có giá trị `default.reference.value`. Do đó, bước mật khẩu có giá trị `pwd` và bước OTP có giá trị `otp`, ở cả các luồng `saigonos browser*` và luồng `saigonos operaton`. Khi không tìm thấy bước mật khẩu hay bước OTP trong luồng `saigonos browser*`, service `realm` báo lỗi. Keycloak không ghi bước OTP khi người dùng cài đặt OTP bằng required action `CONFIGURE_TOTP`, nên lần đăng nhập đó chỉ có `pwd`.