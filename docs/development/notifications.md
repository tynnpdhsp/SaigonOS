<!-- SPDX-License-Identifier: Apache-2.0 -->
# Thông báo, Telegram và email

Bảng `core.notifications` và hàm `core.notify` được tạo trong file [`0015_notifications.sql`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/config/postgres/migrations/0015_notifications.sql). Hai lời gọi đọc thông báo và đánh dấu đã đọc nằm trong [`saigonos_core/notifications.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/core/saigonos_core/notifications.py). Khi sửa phần thông báo, cần tuân theo các quy tắc sau:

- Bảng `core.notifications` chỉ được thêm dòng qua hàm `core.notify`. Không cấp quyền `INSERT` trên bảng cho role nào. Role `authenticated` chỉ có quyền `SELECT`. Role `core_service` chỉ có quyền `SELECT` và quyền `UPDATE` trên cột `read_at`.
- Chính sách `recipient_only` chỉ cho hai role trên thấy thông báo có người nhận trùng claim `sub` của người gọi. Các câu truy vấn của service `core` cũng lọc theo `core.uid()`. Nhờ đó, mỗi lớp tự chặn được thông báo của người khác. Lời gọi đánh dấu đã đọc chạy trong `Database.service_session(caller)`, nên audit log ghi đúng người gọi.
- Tin gửi tới kênh `user:#<sub>` có dạng `{"notification": {...}}` với đúng các trường của model `Notification`. Khi thêm hoặc đổi trường, cần sửa cả hàm `core.notify` và bảng trường ở trang [Thông báo](../apps/notifications.md#đọc-thông-báo). Kiểm thử `test_notification_reaches_recipient_within_one_second_as_listed` so tin này với kết quả của `GET /core/notifications`. Kiểm thử `test_docs_lists_every_notification_field` so bảng này với model.
- Người nhận dài tối đa 249 ký tự, vì tên kênh `user:#<sub>` dài tối đa 255 ký tự.
- Không bỏ kiểm tra đường dẫn của hàm `core.notify`. Ứng dụng dựa vào kiểm tra này để hiển thị đường dẫn mà không kiểm tra lại. Trình duyệt bỏ dấu tab và dấu xuống dòng trong địa chỉ. Ví dụ, đường dẫn gồm dấu `/`, một dấu tab và `/web-khac.example` trở thành `//web-khac.example`, tức một địa chỉ của web khác. Do đó, hàm từ chối mọi ký tự điều khiển trong đường dẫn.

## Gửi tin Telegram

Bảng `core.deliveries` và phiên bản mới của hàm `core.notify` được tạo trong file [`0016_deliveries.sql`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/config/postgres/migrations/0016_deliveries.sql). Vòng lặp gửi tin nằm trong [`saigonos_core/deliveries.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/core/saigonos_core/deliveries.py). Client của Bot API nằm trong [`saigonos_core/telegram.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/core/saigonos_core/telegram.py) và dùng `http.client`, không thêm thư viện. Khi sửa phần này, cần tuân theo các quy tắc sau:

- Bảng `core.deliveries` chỉ được thêm dòng qua hàm `core.notify` và hàm `core.send_email`. Role `core_service` chỉ có quyền `SELECT` và quyền `UPDATE` trên các cột trạng thái. Không cấp thêm quyền cho role nào.
- Tiêu đề, nội dung và đường dẫn được chép vào bảng `core.deliveries`. Vòng lặp gửi tin không có người gọi, nên chính sách `recipient_only` của bảng `core.notifications` không cho vòng lặp đọc thông báo.
- Dòng được chuyển sang `sending` và commit trước khi gọi Telegram. Không giữ khóa dòng trong lúc gọi Telegram. Nếu giữ khóa, transaction bị hủy khi service `core` chết, dòng trở về `pending` và tin được gửi lại dù Telegram có thể đã nhận tin.
- Khi service `core` khởi động, các dòng còn ở `sending` chuyển sang `unknown`. Do đó, chỉ chạy một container của service `core`.
- Lỗi xảy ra trước khi gửi xong lời gọi, ví dụ không kết nối được hoặc lỗi TLS, được gửi lại. Lỗi xảy ra sau khi đã gửi xong lời gọi cho kết quả `unknown`. Không gửi lại tin `unknown`.
- Khi service `core` dừng trong lúc gửi, vòng lặp chờ Telegram trả lời rồi ghi kết quả, nhờ `asyncio.shield`. Khi lời gọi `run_in_threadpool` bị hủy thẳng, thread vẫn gửi tin nhưng kết quả bị mất.
- Token của bot nằm trong đường dẫn của lời gọi. Không ghi đường dẫn hoặc token vào log. Token được kiểm tra dạng `<số>:<chuỗi>` lúc khởi động, nên `http.client` không báo lỗi `InvalidURL` chứa đường dẫn.
- Cấu hình Telegram sai không làm service `core` dừng. Service ghi lý do vào log và chuyển tin sang `skipped`.
- Trigger `notify` của bảng gửi NOTIFY tới kênh `core_deliveries` khi có dòng mới. Service `core` nghe kênh này bằng một kết nối riêng, mở bằng `Database.listen`. Khi không có NOTIFY, service đọc bảng 10 giây một lần.

Bot API giả nằm trong file [`tests/integration/fake_telegram.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/tests/integration/fake_telegram.py). Fixture `bot_api` chạy file này trong một container, rồi ghi cấu hình Telegram trỏ tới container này vào file `.env`. Bot API giả trả lời theo kế hoạch mà kiểm thử gửi tới `/plan`, ví dụ mã 500, mã 429 kèm `retry_after` hoặc ngắt kết nối. Kiểm thử `test_telegram_message_is_skipped_while_telegram_is_not_configured` phải đứng trước các kiểm thử dùng fixture `bot_api`, vì fixture này bật Telegram cho cả bộ thử.

## Gửi email

Hàm `core.send_email` và hàm `core.check_message` được tạo trong file [`0017_email.sql`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/config/postgres/migrations/0017_email.sql). Client SMTP nằm trong [`saigonos_core/smtp.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/core/saigonos_core/smtp.py) và dùng `smtplib`, không thêm thư viện. Khi sửa phần này, cần tuân theo các quy tắc sau:

- Hàm `core.check_message` kiểm tra khóa chống trùng, tiêu đề, nội dung và đường dẫn cho cả `core.notify` và `core.send_email`. Quy tắc của các giá trị này chỉ được sửa ở hàm này.
- Hàm `core.send_email` và `saigonos_core/smtp.py` kiểm tra địa chỉ email theo cùng một mẫu. Mẫu này là định nghĩa địa chỉ email hợp lệ của HTML và chỉ nhận ký tự ASCII. Do đó, máy chủ SMTP không cần hỗ trợ SMTPUTF8.
- Nội dung email được mã hóa bằng quoted-printable hoặc base64 nhờ policy `cte_type="7bit"`, nên chỉ gồm ký tự ASCII. Do đó, máy chủ SMTP không cần hỗ trợ 8BITMIME.
- Mỗi kênh có một vòng gửi `Deliveries` riêng, với cấu hình `Channel` trong `saigonos_core/deliveries.py`. Mọi câu truy vấn của vòng gửi lọc theo cột `channel`. Nhờ đó, lệnh chờ `retry_after` của Telegram không làm chậm email.
- Luôn truyền `ssl.create_default_context()` cho `starttls()` và `SMTP_SSL`. Khi không nhận context, `smtplib` vẫn mã hóa kết nối nhưng không kiểm tra chứng chỉ.
- Không bỏ qua STARTTLS khi máy chủ không hỗ trợ. Cấu hình có mật khẩu mà `SMTP_SECURITY` là `none` bị từ chối lúc khởi động.
- Nội dung email được gửi bằng `docmd("DATA")`, `send()` và `getreply()`, không dùng `sendmail()`. Nhờ đó, client phân biệt được nội dung chưa gửi xong, được gửi lại, với câu trả lời bị mất sau khi đã gửi xong nội dung, cho kết quả `unknown`.

Máy chủ SMTP giả nằm trong file [`tests/integration/fake_smtp.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/tests/integration/fake_smtp.py) và chỉ dùng thư viện chuẩn của Python. Fixture `mail_server` chạy file này trong một container, tạo một CA thử, rồi ghi file `compose.override.yaml` để service `core` tin CA này qua biến `SSL_CERT_FILE`. Chứng chỉ của máy chủ giả có đủ các extension mà Python 3.13 trở lên đòi hỏi. Kiểm thử `test_email_is_skipped_while_smtp_is_not_configured` phải đứng trước các kiểm thử dùng fixture `mail_server`.