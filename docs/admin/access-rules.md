<!-- SPDX-License-Identifier: Apache-2.0 -->
# Luật truy cập

Service `opa` chạy [Open Policy Agent](https://www.openpolicyagent.org/) (OPA). Trước khi chuyển lời gọi tới một route cần bảo vệ, API Gateway hỏi OPA. OPA trả lời cho phép hay từ chối theo các luật viết bằng Rego trong thư mục `config/opa` của thư mục làm việc. OPA chỉ giữ các luật chung ở API Gateway. Quyền trên từng dòng dữ liệu vẫn do PostgreSQL kiểm tra.

OPA chỉ nằm trong mạng nội bộ `policy` cùng APISIX và không mở cổng nào trên máy cài đặt. Luật trong file `config/opa/system.rego` chỉ cho API của OPA trả về quyết định. Lời gọi đọc dữ liệu, sửa luật hay sửa dữ liệu qua API của OPA đều bị từ chối. OPA được chạy với việc kiểm tra phiên bản mới đã tắt, nên không gửi thông tin tới máy chủ của dự án OPA.

## Trang quản trị

Hai route quản trị đi qua OPA:

- Route `auth-admin`: Admin Console và Admin REST API của realm `saigonos` tại `/auth/admin/`.
- Route `operaton`: Cockpit, Tasklist và Admin của Operaton tại `/operaton/`.

Luật trong file `config/opa/admin.rego` chỉ cho qua lời gọi đạt cả hai điều kiện sau:

- Địa chỉ IP của người gọi thuộc một dải mạng trong `SAIGONOS_ADMIN_NETWORKS` của file `.env`. Khi giá trị này trống hoặc không có, mọi địa chỉ IP đều đạt.
- Lời gọi tới Admin REST API mang access token của một lần đăng nhập có mã OTP. Keycloak ghi các bước đăng nhập vào claim `amr` của access token, gồm `pwd` cho mật khẩu và `otp` cho mã OTP. Luật kiểm tra claim này có `otp`. Các giá trị trong claim `amr` có hiệu lực suốt phiên đăng nhập, kể cả trong access token được làm mới. Thời gian này bằng SSO Session Max của realm, mặc định là 10 giờ.

Lời gọi không đạt nhận mã 403 kèm lý do. Khi OPA dừng hoặc trả lời sai định dạng, API Gateway từ chối các route quản trị với mã 403 hoặc 503. Trang đăng nhập và các route khác vẫn hoạt động. Quyền trên từng chức năng của Admin Console vẫn do Keycloak kiểm tra theo các role của client `realm-management`. Operaton chỉ cho tài khoản có realm role `admin` đăng nhập và luôn hỏi mã OTP.

Ví dụ, để chỉ mở trang quản trị cho mạng `192.168.1.0/24` và địa chỉ IP `203.0.113.7`, thêm dòng sau vào file `.env` trong thư mục làm việc, rồi chạy `saigonos up`:

```
SAIGONOS_ADMIN_NETWORKS=192.168.1.0/24,203.0.113.7/32
```

Mỗi dải mạng viết theo dạng CIDR, cho cả IPv4 và IPv6, các dải cách nhau bằng dấu phẩy. Một địa chỉ IP riêng lẻ có thêm `/32`, hoặc `/128` với IPv6. Khi có dải không hợp lệ, lệnh `saigonos up` báo lỗi ở service `policies`. Lúc đó OPA chưa khởi động lại, nên các route quản trị bị từ chối cho tới khi sửa xong.

API Gateway tin header `X-Forwarded-For` do máy trong mạng nội bộ gửi tới, như mục [Cấu hình](configuration.md). Do đó, giới hạn theo dải mạng có hiệu lực chắc chắn với người gọi từ Internet và người gọi qua reverse proxy trên máy chủ. Một máy trong mạng nội bộ gọi thẳng vào cổng của API Gateway có thể khai báo một địa chỉ IP khác.

Ở lần đăng nhập đầu tiên, tài khoản quản trị cài đặt OTP. Keycloak không ghi mã OTP của lần cài đặt vào claim `amr`. Do đó, sau khi cài đặt OTP, hãy đăng xuất rồi đăng nhập lại bằng mật khẩu và mã OTP.

## Sửa luật

OPA theo dõi thư mục `config/opa` và nạp lại luật ngay khi một file thay đổi. Khi file có lỗi, OPA giữ nguyên luật đang chạy. Lệnh `saigonos up` soát mọi file luật bằng service `policies`. Khi có file lỗi, lệnh báo service `policies` kết thúc với mã lỗi. Trong thư mục làm việc, xem vị trí lỗi bằng lệnh sau:

```bash
docker compose logs policies
```

Khi cập nhật phiên bản, lệnh `saigonos init` ghi đè các file luật có sẵn và giữ nguyên các file khác. Do đó, luật riêng của hệ thống nên được viết trong file mới, ví dụ `config/opa/local.rego`.

Mỗi lý do trong tập `deny` của package `saigonos.admin` làm lời gọi bị từ chối. Luật mới thêm lý do vào tập này. Ví dụ, file sau không cho xóa tài khoản qua Admin Console, để người quản trị chỉ tắt tài khoản:

```rego
package saigonos.admin

deny contains "Không xóa tài khoản qua API Gateway. Hãy tắt tài khoản thay cho việc xóa." if {
	input.request.method == "DELETE"
	regex.match(`^/auth/admin/realms/saigonos/users/[^/]+$`, input.request.path)
}
```

Luật đọc được các giá trị sau của lời gọi:

| Giá trị | Ý nghĩa |
|---|---|
| `input.request.method` | Phương thức HTTP |
| `input.request.path` | Đường dẫn, không gồm query string |
| `input.request.query` | Các tham số của query string |
| `input.request.headers` | Các header, tên viết thường |
| `input.var.remote_addr` | Địa chỉ IP của người gọi |
