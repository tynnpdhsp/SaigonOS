<!-- SPDX-License-Identifier: Apache-2.0 -->
# Luật truy cập

API Gateway hỏi Open Policy Agent (OPA) trước khi cho lời gọi tới các route cần bảo vệ đi qua. OPA trả lời theo các luật viết bằng Rego trong thư mục [`config/opa`](https://github.com/tynnpdhsp/SaigonOS/tree/main/src/saigonos/stack/config/opa) của thư mục làm việc. Quyền trên từng dòng dữ liệu vẫn do PostgreSQL kiểm tra. Luật riêng của từng ứng dụng được khai trong bản khai, như trang [Luật truy cập của ứng dụng](../apps/access-rules.md).

## Trang quản trị

Luật trong file [`config/opa/admin.rego`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/config/opa/admin.rego) áp dụng cho Admin Console của realm `saigonos` tại `/auth/admin/`, Operaton tại `/operaton/` và Grafana tại `/grafana/`. Lời gọi chỉ được cho qua khi đạt cả hai điều kiện sau:

- Địa chỉ IP của người gọi thuộc một dải mạng trong `SAIGONOS_ADMIN_NETWORKS` của file `.env`. Khi giá trị này trống hoặc không có, mọi địa chỉ IP đều đạt.
- Lời gọi tới Admin REST API mang access token của một lần đăng nhập có mã OTP. Lần đăng nhập này dùng được tới hết SSO Session Max của realm, mặc định là 10 giờ.

Lời gọi không đạt nhận mã 403 kèm lý do. Khi OPA dừng, các route quản trị bị từ chối, còn trang đăng nhập và các route khác vẫn hoạt động.

Ví dụ, để chỉ mở trang quản trị cho mạng `192.168.1.0/24` và địa chỉ IP `203.0.113.7`, thêm dòng sau vào file `.env` rồi chạy `saigonos up`:

```
SAIGONOS_ADMIN_NETWORKS=192.168.1.0/24,203.0.113.7/32
```

Mỗi dải mạng viết theo dạng CIDR, cho cả IPv4 và IPv6. Các dải cách nhau bằng dấu phẩy. Một địa chỉ IP riêng lẻ có thêm `/32`, hoặc `/128` với IPv6. Khi có dải không hợp lệ, lệnh `saigonos up` báo lỗi ở service `policies`, và các route quản trị bị từ chối cho tới khi sửa xong.

Giới hạn theo dải mạng có hiệu lực chắc chắn với người gọi từ Internet và người gọi qua reverse proxy. Một máy trong mạng nội bộ gọi thẳng vào cổng của API Gateway có thể khai báo địa chỉ IP khác, như trang [Cấu hình](configuration.md).

## Thêm luật

OPA nạp lại luật ngay khi một file trong thư mục `config/opa` thay đổi. Khi file có lỗi, OPA giữ nguyên luật đang chạy, và lệnh `saigonos up` báo lỗi ở service `policies`. Vị trí lỗi được xem bằng lệnh sau trong thư mục làm việc:

```bash
docker compose logs policies
```

Khi cập nhật phiên bản, lệnh `saigonos init` ghi đè các file luật có sẵn. Do đó, luật riêng của hệ thống được viết trong file mới, ví dụ `config/opa/local.rego`. Mỗi lý do trong tập `deny` của package `saigonos.admin` làm lời gọi bị từ chối. Ví dụ, file sau không cho xóa tài khoản qua Admin Console:

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
