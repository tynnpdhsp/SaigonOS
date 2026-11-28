<!-- SPDX-License-Identifier: Apache-2.0 -->
# Centrifugo

Cấu hình của Centrifugo nằm trong file [`src/saigonos/stack/config/centrifugo/config.yaml`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/config/centrifugo/config.yaml). Các mật khẩu và các giá trị phụ thuộc file `.env` được đặt bằng biến môi trường `CENTRIFUGO_*` trong file [`compose.yaml`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/compose.yaml). Biến môi trường được ưu tiên hơn file cấu hình.

Khi sửa cấu hình hoặc route của Centrifugo, cần tuân theo các quy tắc sau:

- Route `realtime` của API Gateway chỉ khớp đúng đường dẫn `/realtime/connection/websocket` và luôn gửi tới đường dẫn `/connection/websocket` của Centrifugo. Không thêm route tới cổng nội bộ 9000. Cổng này phục vụ API của server, Admin web và `/health`.
- Giữ thiết lập `client.token.audience`. Nếu bỏ thiết lập này, Centrifugo nhận cả ID token.
- Giữ thiết lập `client.disallow_anonymous_connection_tokens`. Access token của client không dùng client scope `basic` không có claim `sub`. Nếu bỏ thiết lập này, Centrifugo coi kết nối bằng access token đó là kết nối ẩn danh.
- Biến `CENTRIFUGO_CLIENT_ALLOWED_ORIGINS` lấy giá trị `CENTRIFUGO_ALLOWED_ORIGIN` mà lệnh `saigonos init` ghi vào file `.env`. Centrifugo so header `Origin` với giá trị này như một mẫu glob, nên hàm `origin_pattern` trong [`src/saigonos/home.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/home.py) thêm dấu `\` trước mỗi ký tự trong `GLOB_SPECIALS`. Ví dụ, địa chỉ `http://[2001:db8::1]:9080` được ghi thành `http://\[2001:db8::1\]:9080`. Nếu thiếu bước này, địa chỉ IPv6 như `http://[2001:db8::1]:9080` trở thành một lớp ký tự. Khi đó, trang ở đúng địa chỉ này bị từ chối, còn Origin `http://1:9080` lại được nhận. Khi danh sách này rỗng, Centrifugo từ chối mọi kết nối có header `Origin`, kể cả từ chính địa chỉ của hệ thống. Không dùng giá trị `*`.
- Khi đổi phiên bản Centrifugo, kiểm tra thư viện glob mà Centrifugo dùng để so header `Origin`. Phiên bản 6.10.3 dùng `github.com/gobwas/glob` v1.1.0. `GLOB_SPECIALS` phải gồm đủ các ký tự mà hàm `QuoteMeta` của thư viện này thêm dấu `\` ở trước.
- Giữ thiết lập `usage_stats.disabled`. Nếu bỏ thiết lập này, Centrifugo gửi thống kê ẩn danh tới nhà phát triển lần đầu sau 24 đến 48 giờ mà không ghi log.

Integration test nằm trong file [`tests/integration/test_realtime.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/tests/integration/test_realtime.py). Client WebSocket của kiểm thử là lớp `Realtime` trong [`tests/integration/conftest.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/tests/integration/conftest.py), viết bằng thư viện chuẩn của Python.

## Quyền nghe kênh

Quyền nghe kênh được khai báo theo namespace trong `channel.namespaces`. Khi sửa namespace hoặc token kênh, cần tuân theo các quy tắc sau:

- Namespace `public` có `allow_subscribe_for_client`. Namespace `user` chỉ có `allow_user_limited_channels`. Namespace `role` không có thiết lập nào, nên chỉ nghe được bằng token kênh. Không thêm `allow_subscribe_for_client` vào namespace `user` hoặc `role`.
- Token kênh hợp lệ mở được đúng kênh ghi trong token ở mọi namespace đã khai báo, kể cả kênh `user:#<sub>` của người khác và kênh không có namespace. Do đó, lời gọi `POST /core/realtime/token` chỉ cấp token cho kênh `role:<realm role>` sau khi kiểm tra realm role của người gọi, và cho kênh `user:<tên ứng dụng>.<sub>` sau khi kiểm tra `azp` và `sub` của người gọi. Khóa `CENTRIFUGO_SUBSCRIPTION_KEY` không được dùng vào việc khác.
- Giữ thiết lập `client.subscription_token.enabled`. Thiết lập này cho Centrifugo kiểm tra token kênh bằng khóa trong biến `CENTRIFUGO_CLIENT_SUBSCRIPTION_TOKEN_HMAC_SECRET_KEY`. Biến này và biến `SUBSCRIPTION_KEY` của service `core` cùng lấy giá trị `CENTRIFUGO_SUBSCRIPTION_KEY`. Nếu bỏ thiết lập này, Centrifugo kiểm token kênh bằng JWKS của Keycloak nên mọi token kênh bị từ chối.
- Token kênh hết hạn không muộn hơn access token dùng để lấy token. Nhờ đó, người bị gỡ realm role không giữ được token kênh lâu hơn access token cũ. Centrifugo cho client thêm 25 giây để gửi token mới (`client.expired_sub_close_delay`) và kiểm tra hạn của kênh 27 giây một lần (`client.presence_update_interval`). Do đó, kênh không có token mới bị ngừng từ 25 đến 52 giây sau khi token hết hạn.

## Gửi tin qua bảng outbox

Bảng `core.outbox` theo mẫu của Centrifugo. Consumer `outbox` của Centrifugo khóa partition bằng advisory lock của PostgreSQL, đọc các dòng theo thứ tự `id`, gửi từng tin rồi xóa các dòng đã gửi. Khi cập nhật bảng hoặc consumer, cần tuân theo các quy tắc sau:

- Role `centrifugo` chỉ có quyền `SELECT` và `DELETE` trên bảng `core.outbox`. Centrifugo không cần quyền nào khác. Không cấp thêm quyền cho role này.
- Trigger `notify` của bảng gửi NOTIFY tới kênh `core_outbox` khi có dòng mới. Giá trị `partition_notification_channel` trong file cấu hình phải trùng tên kênh này. Nếu hai tên lệch nhau, Centrifugo chỉ đọc bảng 5 giây một lần theo `partition_poll_interval`.
- Chuỗi kết nối của consumer chứa mật khẩu, nên được đặt bằng biến `CENTRIFUGO_CONSUMERS_OUTBOX_POSTGRESQL_DSN` trong file `compose.yaml`. Tên biến chứa tên consumer viết hoa. Khi đổi tên consumer, cần đổi cả tên biến.
- Centrifugo dừng ngay khi không kết nối được cơ sở dữ liệu lúc khởi động. Do đó, service `centrifugo` chờ service `migrate` chạy xong. Service `migrate` chờ service `databases` tạo role `centrifugo`.
- Với lỗi không thể thử lại, ví dụ kênh thuộc namespace chưa khai báo, Centrifugo ghi log rồi bỏ tin. Do đó, khi thêm namespace, cần khai báo namespace trong `channel.namespaces` và thêm vào biểu thức kiểm tra kênh của hàm `core.publish`.
- Với lỗi tạm thời, Centrifugo thử lại tin bị lỗi sau tối đa 5 giây. Các tin sau phải chờ tin này.

## History

Mỗi namespace có bốn thiết lập `history_size`, `history_ttl`, `force_recovery` và `allow_history_for_subscriber`. Khi sửa history, cần tuân theo các quy tắc sau:

- Ba namespace dùng cùng `history_size` và `history_ttl`. Trang [Cập nhật tức thời](../apps/realtime.md#tin-bị-lỡ-khi-mất-kết-nối) ghi hai giá trị này. Kiểm thử `test_docs_states_history_of_centrifugo` báo lỗi khi trang này và file cấu hình lệch nhau.
- Không dùng `allow_history_for_client`. Thiết lập này cho mọi client đọc history mà không cần nghe kênh, nên lộ tin của kênh `user:#<sub>` và `role:`. Thiết lập `allow_history_for_subscriber` chỉ cho client đang nghe kênh đọc history, nên quyền đọc history đi theo quyền nghe kênh.
- History nằm trong bộ nhớ của Centrifugo và mất khi Centrifugo khởi động lại. Khi 1.000 kênh đều đầy 100 tin khoảng 200 byte, Centrifugo dùng thêm khoảng 130 MiB RAM. Phần này được trả lại sau `history_ttl`.

JSON của Centrifugo bỏ các trường có giá trị false, ví dụ `recovered`. Do đó, kiểm thử đọc các trường này với giá trị mặc định là false.