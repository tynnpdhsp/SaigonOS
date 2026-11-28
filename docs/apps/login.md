<!-- SPDX-License-Identifier: Apache-2.0 -->
# Đăng nhập

Người dùng đăng nhập vào ứng dụng bằng Keycloak. Lệnh cài đặt tạo các mục sau trong realm `saigonos`:

- Mỗi role trong bản khai báo trở thành một realm role, với mô tả lấy từ bản khai báo.
- Một client trùng tên ứng dụng, ví dụ `phong-may`. Đây là public client, chỉ dùng luồng Authorization Code với PKCE `S256`. Password grant, luồng implicit, service account và device grant đều tắt. Địa chỉ chuyển hướng chỉ gồm `<địa chỉ truy cập>/apps/<tên ứng dụng>/` và các đường dẫn bên dưới.
- Client có client scope mặc định `acr`, `basic`, `email`, `profile`, `roles`, `web-origins` và không có client scope tùy chọn. Access token do client cấp chỉ mang realm role `authenticated` và các role của chính ứng dụng, kể cả khi người dùng có role của ứng dụng khác hoặc role `admin`.

Ứng dụng đăng nhập theo các địa chỉ trong tài liệu discovery `/auth/realms/saigonos/.well-known/openid-configuration`, với `client_id` là tên ứng dụng. Giao diện của ứng dụng mẫu đăng nhập bằng PKCE trong file [`ui/app.js`](https://github.com/tynnpdhsp/SaigonOS/blob/main/examples/phong-may/ui/app.js), không dùng thư viện ngoài.

Để gán role của ứng dụng cho người dùng, mở Admin Console của realm `saigonos`, chọn Users, chọn người dùng, mở thẻ Role mapping, bấm Assign role rồi chọn role của ứng dụng.

Mỗi lần cài đặt, client và mô tả của realm role được đặt lại theo bản khai báo. Thiết lập đã sửa trong Admin Console đều trở về như trên. Role bị bỏ khỏi bản khai báo vẫn được giữ cùng với việc gán role, nhưng access token của ứng dụng không mang role đó nữa. SaigonOS ghi tên ứng dụng vào thuộc tính `saigonos.app` của client và realm role. Client hoặc realm role trùng tên mà không mang thuộc tính này không bị lệnh cài đặt đụng tới.
