<!-- SPDX-License-Identifier: Apache-2.0 -->
# Tài liệu API

## REST API của dữ liệu

PostgREST tự sinh tài liệu OpenAPI 2.0 cho REST API. Tài liệu nằm ở địa chỉ gốc của REST API, mặc định là http://localhost:9080/api/. Tài liệu có thể được mở bằng trình duyệt hoặc nạp vào các công cụ hỗ trợ OpenAPI 2.0, ví dụ Swagger UI.

Tài liệu chỉ liệt kê các bảng, view và hàm mà người gọi được dùng. Lời gọi không có access token nhận tài liệu theo quyền của role `anon`. Lời gọi có access token trong header `Authorization` nhận tài liệu theo quyền của role `authenticated`. Quyền được kiểm tra ở mỗi lời gọi. Do đó, sau khi một quyền được cấp hoặc thu hồi, tài liệu thay đổi ngay ở lời gọi tiếp theo.

Các địa chỉ trong tài liệu được lấy từ địa chỉ truy cập của hệ thống, tức giá trị của tùy chọn `--url`. Ví dụ, với địa chỉ truy cập `https://dx.example.com`, các lời gọi trong tài liệu bắt đầu bằng `https://dx.example.com/api`.

## API của service core

Service `core` cung cấp các API của lõi mà PostgREST không đảm nhận, ví dụ tải lên và quét mã độc file, bắt đầu quy trình và xử lý việc. Service được viết bằng FastAPI. API nằm ở địa chỉ `/core/` của API Gateway. Tài liệu OpenAPI 3.1 nằm ở địa chỉ http://localhost:9080/core/openapi.json. Ví dụ, lời gọi `GET /core/me` trả về mã người dùng, đơn vị và role mà cơ sở dữ liệu nhận được từ access token của người gọi.

API Gateway kiểm tra access token của lời gọi tới `/core` như với `/api`. Service `core` kiểm tra lại chữ ký, issuer (`iss`), thời hạn, loại token và realm role `authenticated`. Do đó, lời gọi tới thẳng service từ bên trong mạng Docker vẫn bị từ chối khi access token không hợp lệ. Service chỉ chấp nhận access token, không chấp nhận ID token. Khi Keycloak đổi khóa ký, service tự lấy khóa mới.

Service kết nối PostgreSQL bằng role `core_service`. Mỗi truy vấn chạy với role và nội dung access token của người gọi, giống PostgREST. Do đó, các hàm `core.uid()`, `core.has_role()`, `core.unit()` và chính sách phân quyền từng dòng dùng chung cho cả hai.

Image của service được Docker Compose build trên máy cài đặt từ image `python` chính thức. Các thư viện được cài từ lock file có mã băm. Ở lần khởi động đầu tiên, việc build mất khoảng một phút. Mỗi lần chạy `saigonos up`, Docker Compose build lại image. Khi mã nguồn không đổi, việc build dùng lại kết quả cũ nên chỉ mất vài giây. Với Docker Compose 2.x, container của service `core` cũng được tạo lại ở mỗi lần chạy, kể cả khi mã nguồn không đổi.
