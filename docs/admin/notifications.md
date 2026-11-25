<!-- SPDX-License-Identifier: Apache-2.0 -->
# Telegram và email

Thông báo cho người dùng có thể được gửi thêm tới một nhóm Telegram hoặc qua email. Cách gửi từ mã của ứng dụng được trình bày ở trang [Thông báo](../apps/notifications.md). Trang này trình bày cách cấu hình hai kênh gửi và cách xử lý tin gửi lỗi.

## Telegram

Để bật Telegram, thực hiện các bước sau:

1. Tạo bot bằng [BotFather](https://t.me/BotFather) với lệnh `/newbot`. BotFather trả về token của bot, có dạng `123456789:AA...`.
2. Thêm bot vào nhóm nhận thông báo, rồi gửi lệnh `/start@<tên bot>` trong nhóm. Khi nhóm có chủ đề (topic), gửi lệnh này trong chủ đề cần nhận tin.
3. Mở địa chỉ `https://api.telegram.org/bot<token>/getUpdates` bằng trình duyệt. Mã nhóm là giá trị `chat.id`, ví dụ `-1001234567890`. Mã chủ đề là giá trị `message_thread_id`. Telegram chỉ giữ các giá trị này trong 24 giờ.
4. Thêm các dòng sau vào file `.env` trong thư mục làm việc, rồi chạy `saigonos up`.

```
TELEGRAM_BOT_TOKEN=123456789:AA...
TELEGRAM_CHAT_ID=-1001234567890
TELEGRAM_TOPIC_ID=2
```

Khi bật chủ đề cho nhóm, Telegram đổi mã nhóm. Do đó, cần lấy mã nhóm sau khi bật chủ đề. Các giá trị Telegram trong file `.env` như sau:

| Giá trị | Ý nghĩa |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token của bot |
| `TELEGRAM_CHAT_ID` | Mã nhóm, hoặc tên công khai của nhóm dạng `@ten_nhom` |
| `TELEGRAM_TOPIC_ID` | Mã chủ đề. Khi bỏ trống, tin được gửi vào nhóm, hoặc vào chủ đề General khi nhóm có chủ đề |
| `TELEGRAM_API_URL` | Địa chỉ của Bot API, mặc định là `https://api.telegram.org`. Chỉ đổi giá trị này khi dùng Bot API server riêng |

Để thử cấu hình, chạy lệnh sau trong thư mục làm việc. Nhóm nhận tin sau vài giây. Mỗi lần thử cần một khóa chống trùng mới, ví dụ `kiem-tra-telegram-2`.

```bash
docker compose exec postgres psql -U postgres -d saigonos -c "SET ROLE workflow; SELECT core.notify('kiem-tra', 'kiem-tra-telegram-1', 'Tin thử của SaigonOS', telegram => true)"
```

## Email

Email được gửi qua một máy chủ SMTP, ví dụ máy chủ của Gmail. Để bật email, thêm các dòng sau vào file `.env` trong thư mục làm việc, rồi chạy `saigonos up`. Ví dụ với Gmail:

```
SMTP_HOST=smtp.gmail.com
SMTP_USERNAME=thong-bao@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
SMTP_FROM=thong-bao@gmail.com
SMTP_FROM_NAME=Phòng Kỹ thuật
```

Gmail không nhận mật khẩu đăng nhập thường của tài khoản. Tài khoản cần bật xác minh 2 bước, rồi tạo mật khẩu ứng dụng tại trang [Mật khẩu ứng dụng](https://myaccount.google.com/apppasswords). Mật khẩu ứng dụng gồm 16 chữ cái, viết liền, không có khoảng trắng. Các giá trị SMTP trong file `.env` như sau:

| Giá trị | Ý nghĩa |
|---|---|
| `SMTP_HOST` | Tên hoặc địa chỉ IP của máy chủ SMTP |
| `SMTP_PORT` | Cổng của máy chủ SMTP. Mặc định là 587, hoặc 465 khi `SMTP_SECURITY` là `tls`, hoặc 25 khi `SMTP_SECURITY` là `none` |
| `SMTP_SECURITY` | Cách mã hóa kết nối. Giá trị `starttls` mã hóa kết nối bằng lệnh STARTTLS. Giá trị `tls` mã hóa ngay từ đầu kết nối. Giá trị `none` không mã hóa và không cho dùng mật khẩu, chỉ dùng với máy chủ SMTP trong mạng nội bộ. Mặc định là `tls` khi `SMTP_PORT` là 465, và `starttls` với các cổng khác |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Tài khoản đăng nhập máy chủ SMTP. Bỏ trống hai giá trị này khi máy chủ không yêu cầu đăng nhập |
| `SMTP_FROM` | Địa chỉ gửi. Với Gmail, đây là địa chỉ của tài khoản |
| `SMTP_FROM_NAME` | Tên người gửi hiện trong hộp thư của người nhận. Giá trị này có thể bỏ trống |

Service `core` luôn kiểm tra chứng chỉ của máy chủ SMTP và không gửi mật khẩu qua kết nối chưa mã hóa. Khi một giá trị trong file `.env` có dấu `$`, giá trị đó được đặt trong cặp dấu nháy đơn, ví dụ `SMTP_PASSWORD='ab$cd'`.

Để thử cấu hình, chạy lệnh sau trong thư mục làm việc, với `<địa chỉ>` là một địa chỉ email nhận thử. Email tới sau vài giây. Mỗi lần thử cần một khóa chống trùng mới, ví dụ `kiem-tra-email-2`.

```bash
docker compose exec postgres psql -U postgres -d saigonos -c "SET ROLE workflow; SELECT core.send_email('<địa chỉ>', 'kiem-tra-email-1', 'Email thử của SaigonOS')"
```

## Hàng đợi gửi tin

Mỗi tin Telegram và mỗi email là một dòng của bảng `core.deliveries`. Service `core` gửi tin ngay khi transaction ghi tin được commit. Cột `channel` có giá trị `telegram` hoặc `email`. Cột `status` cho biết trạng thái của tin:

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

- Không kết nối được, Telegram trả về mã 5xx hoặc máy chủ SMTP trả về mã 4xx: tin được gửi lại sau 5 giây, 30 giây, 2 phút và 10 phút. Sau 5 lần gửi lỗi, tin chuyển sang `failed`.
- Telegram trả về mã 429: service `core` chờ đúng số giây trong `retry_after` rồi mới gửi tiếp. Lần chờ này không tính là một lần gửi lỗi.
- Telegram trả về mã 4xx khác, ví dụ token sai hoặc bot không ở trong nhóm: tin chuyển sang `failed` ngay.
- Máy chủ SMTP trả về mã 5xx, ví dụ sai mật khẩu hoặc địa chỉ người nhận không tồn tại: email chuyển sang `failed` ngay.

Lý do của mỗi lần gửi lỗi được ghi vào log của service `core`, xem bằng `docker compose logs core` trong thư mục làm việc.

Tin chuyển sang `unknown` khi mất kết nối sau khi đã gửi đi, hoặc khi service `core` bị dừng đột ngột trong lúc gửi. Tin này không được gửi lại, để người nhận không nhận hai tin giống nhau. Người quản trị kiểm tra nhóm Telegram hoặc hỏi người nhận email. Nếu tin chưa tới, lệnh sau đưa tin về `pending`, với `<id>` là giá trị cột `id` của tin. Tin được gửi lại trong vòng 10 giây.

```bash
docker compose exec postgres psql -U postgres -d saigonos -c "UPDATE core.deliveries SET status = 'pending' WHERE id = <id> AND status = 'unknown'"
```

Khi file `.env` chưa có cấu hình của một kênh hoặc cấu hình chưa đúng, tin của kênh đó chuyển sang `skipped` và hệ thống vẫn chạy bình thường. Lý do được ghi vào log của service `core` lúc khởi động. Tin đã `skipped` không được gửi khi kênh được cấu hình sau đó.
