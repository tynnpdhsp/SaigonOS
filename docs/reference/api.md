<!-- SPDX-License-Identifier: Apache-2.0 -->
# Tài liệu API

Các API của lõi đều nằm sau API Gateway. Lời gọi cần đăng nhập gửi access token do Keycloak cấp trong header `Authorization`, dạng `Bearer` kèm access token.

| Địa chỉ | API | Tài liệu |
|---|---|---|
| `/api/` | REST API của PostgREST cho schema `api` của lõi | OpenAPI 2.0 ở chính địa chỉ này |
| `/apps/<tên ứng dụng>/api/` | REST API của PostgREST cho schema của từng ứng dụng | OpenAPI 2.0 ở chính địa chỉ này, như ở trang [Dữ liệu và API](../apps/database.md) |
| `/core/` | API của service `core` cho [file](../apps/files.md), [quy trình](../apps/workflow.md), [thông báo](../apps/notifications.md) và token kênh của [cập nhật tức thời](../apps/realtime.md) | OpenAPI 3.1 ở địa chỉ `/core/openapi.json` |
| `/realtime/connection/websocket` | WebSocket của Centrifugo | Trang [Cập nhật tức thời](../apps/realtime.md) |

## REST API của dữ liệu

PostgREST tự sinh tài liệu OpenAPI 2.0 cho REST API. Tài liệu mở được bằng trình duyệt hoặc nạp được vào các công cụ hỗ trợ OpenAPI 2.0, ví dụ Swagger UI. Tài liệu chỉ liệt kê các bảng, view và hàm mà người gọi được dùng. Lời gọi không có access token nhận tài liệu theo quyền của role `anon`. Các địa chỉ trong tài liệu được lấy từ địa chỉ truy cập của hệ thống, ví dụ `https://dx.example.com/api`.

Mỗi lời gọi tới `/api/` và `/apps/<tên ứng dụng>/api/` chạy tối đa 15 giây. Khi quá thời gian này, PostgreSQL dừng truy vấn và lời gọi nhận mã 500 với mã lỗi `57014`.

## API của service core

Service `core` cung cấp các API mà PostgREST không đảm nhận, ví dụ tải file lên và bắt đầu quy trình. Tài liệu OpenAPI 3.1 ở địa chỉ `/core/openapi.json` không cần đăng nhập. Các API trong tài liệu cần access token, trừ `/core/health` và đường dẫn [tải file về](../apps/files.md#tải-file-về). Ví dụ, lời gọi `GET /core/me` trả về mã người dùng, đơn vị và role mà cơ sở dữ liệu nhận được từ access token của người gọi.

Service `core` tự kiểm tra lại chữ ký, issuer, thời hạn, loại token và realm role `authenticated` của access token. Service chỉ nhận access token, không nhận ID token. Mỗi truy vấn chạy với role và nội dung access token của người gọi, giống PostgREST. Do đó, chính sách Row-Level Security (RLS) của các bảng áp dụng như nhau ở cả hai nơi.

## Mã lỗi

Lỗi riêng của lõi có dạng lỗi của PostgREST, với mã bắt đầu bằng `SGN`:

| Mã | Mã HTTP | Ý nghĩa |
|---|---|---|
| `SGN01` | 401 | Token không phải access token, ví dụ ID token |
| `SGN02` | 403 | Access token không do client của ứng dụng cấp, như ở trang [Dữ liệu và API](../apps/database.md#gọi-api-của-ứng-dụng) |
| `SGN03` | 401, 403 | Lời gọi không đạt [luật truy cập của ứng dụng](../apps/access-rules.md) |
| `SGN04` | 403, 413 | [Tường lửa ứng dụng web](../admin/waf.md) chặn lời gọi |
