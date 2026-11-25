<!-- SPDX-License-Identifier: Apache-2.0 -->
# Đăng nhập

Lệnh cài đặt tạo các mục sau trong realm `saigonos` của Keycloak:

- Mỗi role trong bản khai trở thành một realm role, với mô tả lấy từ bản khai.
- Một client trùng tên ứng dụng, ví dụ `nghi-phep`. Đây là public client, chỉ dùng luồng Authorization Code với PKCE `S256`. Password grant, luồng implicit, service account và device grant đều tắt. Địa chỉ chuyển hướng chỉ gồm `<địa chỉ truy cập>/apps/<tên ứng dụng>/` và các đường dẫn bên dưới.
- Thiết lập Full scope allowed của client bị tắt. Scope mapping của client chỉ gồm realm role `authenticated` và các role của ứng dụng. Client có các client scope mặc định `acr`, `basic`, `email`, `profile`, `roles`, `web-origins` và không có client scope tùy chọn.

Nhờ đó, access token do client cấp chỉ mang realm role `authenticated` và các role của chính ứng dụng, kể cả khi người dùng có role của ứng dụng khác hoặc role `admin`. Ứng dụng cũng không xin được scope `offline_access`.

Ứng dụng đăng nhập theo các địa chỉ trong tài liệu discovery `/auth/realms/saigonos/.well-known/openid-configuration`, với `client_id` là tên ứng dụng.

Để gán role của ứng dụng cho người dùng, mở Admin Console của realm `saigonos`, chọn **Users**, chọn người dùng, mở tab **Role mapping**, bấm **Assign role** rồi chọn role của ứng dụng.

Mỗi lần cài đặt, client được đặt lại theo bản khai. Thiết lập, mapper, scope mapping và client scope đã sửa trong Admin Console đều trở về như trên. Mô tả của realm role cũng được đặt lại, composite role thêm vào role của ứng dụng bị gỡ. Role bị bỏ khỏi bản khai vẫn được giữ cùng với việc gán role, nhưng không còn trong scope mapping. Do đó, access token của ứng dụng không mang role đó nữa.

SaigonOS ghi tên ứng dụng vào thuộc tính `saigonos.app` của client và realm role. Khi Keycloak đã có client hoặc realm role trùng tên mà không mang thuộc tính này, lệnh cài đặt dừng trước khi thay đổi cơ sở dữ liệu và không đụng tới client hoặc role đó.

Địa chỉ chuyển hướng lấy từ giá trị `SAIGONOS_URL` trong file `.env`. Sau khi đổi địa chỉ truy cập, hãy chạy lại lệnh cài đặt cho từng ứng dụng, ví dụ `saigonos apply ./nghi-phep`.
