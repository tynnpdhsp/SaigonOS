<!-- SPDX-License-Identifier: Apache-2.0 -->
# Telegram và email

## Hàng đợi gửi tin

Mỗi tin Telegram và mỗi email là một dòng của bảng `core.deliveries`. Dòng này được ghi trong cùng transaction với dữ liệu. Khi transaction được commit, service `core` gửi tin ngay. Telegram và email có vòng gửi riêng, nên lỗi của kênh này không làm chậm kênh kia. Cột `channel` cho biết kênh gửi, có giá trị `telegram` hoặc `email`. Cột `status` cho biết trạng thái của tin:

| Trạng thái | Ý nghĩa |
|---|---|
| `pending` | Tin đang chờ gửi hoặc chờ gửi lại |
| `sending` | Service `core` đang gửi tin |
| `sent` | Telegram hoặc máy chủ SMTP đã nhận tin. Cột `sent_id` ghi mã của tin trong nhóm Telegram, hoặc `Message-ID` của email |
| `failed` | Không gửi được tin. Cột `error` ghi lý do |
| `unknown` | Không biết Telegram hoặc máy chủ SMTP đã nhận tin hay chưa |
| `skipped` | Tin không được gửi vì kênh gửi chưa được cấu hình hoặc cấu hình chưa đúng |

Ví dụ, lệnh sau xem 10 tin gần nhất:

```bash
docker compose exec postgres psql -U postgres -d saigonos -c "SELECT id, channel, status, failures, error FROM core.deliveries ORDER BY id DESC LIMIT 10"
```

Khi gửi lỗi, service `core` xử lý như sau:

- Không kết nối được Telegram hoặc máy chủ SMTP, Telegram trả về mã 5xx, hoặc máy chủ SMTP trả về mã 4xx: tin được gửi lại sau 5 giây, 30 giây, 2 phút và 10 phút. Sau 5 lần gửi lỗi, tin chuyển sang `failed`.
- Telegram trả về mã 429: service `core` chờ đúng số giây trong `retry_after` rồi mới gửi tiếp. Các tin Telegram khác cũng chờ trong thời gian này. Lần chờ này không tính là một lần gửi lỗi.
- Telegram trả về mã 4xx khác, ví dụ token sai hoặc bot không ở trong nhóm: tin chuyển sang `failed` ngay.
- Máy chủ SMTP trả về mã 5xx, ví dụ sai mật khẩu hoặc địa chỉ người nhận không tồn tại: email chuyển sang `failed` ngay. Máy chủ không hỗ trợ STARTTLS cũng cho kết quả này.

Mỗi lần gửi lỗi được ghi vào log của service `core`, kèm lý do mà Telegram hoặc máy chủ SMTP trả về. Lệnh `docker compose logs core` trong thư mục làm việc dùng để xem log này.

Bot API của Telegram và giao thức SMTP không có cách chống gửi trùng. Do đó, service `core` chuyển tin sang `sending` trước khi gửi, và tin đã `sent` không được gửi lại. Có hai trường hợp không biết tin đã tới nơi hay chưa. Trường hợp thứ nhất là lời gọi tới Telegram hoặc nội dung email đã được gửi đi, nhưng mất kết nối trước khi có câu trả lời. Trường hợp thứ hai là service `core` bị dừng đột ngột trong lúc gửi. Khi đó, tin chuyển sang `unknown` và không được gửi lại, để người nhận không nhận hai tin giống nhau. Thông báo trong ứng dụng không bị ảnh hưởng. Quản trị viên kiểm tra nhóm Telegram hoặc hỏi người nhận email. Nếu tin chưa tới, lệnh sau đưa tin về `pending`, với `<id>` là giá trị cột `id` của tin. Tin được gửi lại trong vòng 10 giây.

```bash
docker compose exec postgres psql -U postgres -d saigonos -c "UPDATE core.deliveries SET status = 'pending' WHERE id = <id> AND status = 'unknown'"
```

Khi file `.env` chưa có cấu hình Telegram hoặc SMTP, tin của kênh đó chuyển sang `skipped` và hệ thống vẫn chạy bình thường. Khi cấu hình chưa đúng, ví dụ thiếu `TELEGRAM_CHAT_ID` hoặc thiếu `SMTP_FROM`, service `core` ghi lý do vào log lúc khởi động và tin cũng chuyển sang `skipped`. Tin đã `skipped` không được gửi khi kênh được cấu hình sau đó.

Bảng `core.deliveries` giữ địa chỉ email, tiêu đề và nội dung của tin sau khi gửi.
