<!-- SPDX-License-Identifier: Apache-2.0 -->
# Thông báo

Thông báo cho người dùng được lưu trong bảng `core.notifications` của cơ sở dữ liệu `saigonos`. Mỗi thông báo gửi cho một người dùng. Người nhận đọc thông báo của mình qua service `core` và nhận thông báo mới tức thời qua kênh `user:#<sub>` của Centrifugo. Thông báo do mã của một ứng dụng gửi thuộc về ứng dụng đó, như mục [Thông báo và kênh của ứng dụng](#thông-báo-và-kênh-của-ứng-dụng).

## Gửi thông báo

Hàm `core.notify(recipient, dedup_key, title, body, link, telegram)` của cơ sở dữ liệu ghi một thông báo rồi gửi thông báo đó tới kênh `user:#<recipient>`. Hàm trả về mã của thông báo, có kiểu `uuid`. Các tham số của hàm như sau:

| Tham số | Ý nghĩa |
|---|---|
| `recipient` | Mã người nhận, tức claim `sub` trong access token của người nhận |
| `dedup_key` | Khóa chống trùng, dài từ 1 đến 255 ký tự |
| `title` | Tiêu đề, dài tối đa 200 ký tự. Tiêu đề không được để trống và không chứa ký tự điều khiển, ví dụ dấu xuống dòng |
| `body` | Nội dung, dài tối đa 2000 ký tự. Tham số này có thể bỏ qua |
| `link` | Đường dẫn tới một trang trong hệ thống, bắt đầu bằng một dấu `/` và dài tối đa 1000 ký tự. Ví dụ: `/yeu-cau/YC-001`. Tham số này có thể bỏ qua |
| `telegram` | Khi có giá trị `true`, thông báo còn được gửi tới nhóm Telegram như ở mục [Gửi thông báo qua Telegram](#gửi-thông-báo-qua-telegram). Mặc định là `false` |

Hàm báo lỗi khi một tham số không hợp lệ. Hàm từ chối đường dẫn tới web khác, ví dụ `https://...` hoặc `//...`, và đường dẫn `javascript:`. Do đó, ứng dụng hiển thị được đường dẫn của thông báo mà không cần kiểm tra lại.

Thông báo và tin gửi Centrifugo được ghi trong cùng transaction với dữ liệu, như với hàm `core.publish` ở mục [Gửi tin từ cơ sở dữ liệu](realtime.md#gửi-tin-từ-cơ-sở-dữ-liệu). Khi transaction bị hủy, thông báo và tin cũng bị hủy.

Mỗi người nhận chỉ có một thông báo cho mỗi khóa chống trùng của mỗi ứng dụng. Khi hàm được gọi lại với cùng người nhận và cùng khóa, hàm không ghi thêm thông báo, không gửi thêm tin và trả về mã của thông báo đã có. Nội dung của thông báo đã có được giữ nguyên. Quy tắc này vẫn đúng khi hai transaction gọi hàm cùng lúc. Do đó, khóa chống trùng nên nêu sự việc mà thông báo nói tới, ví dụ `yeu-cau:YC-001:da-xu-ly`. Khi một sự việc được báo cho nhiều người, mọi người nhận dùng chung một khóa.

Role `workflow` và các role của ứng dụng có quyền gọi hàm. Ví dụ, hàm sau của một [bước máy làm](workflow.md#bước-máy-làm) báo cho người đã bắt đầu quy trình rằng yêu cầu đã được xử lý:

```sql
CREATE FUNCTION ung_dung.bao_tin_da_xu_ly(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM core.notify(
        recipient => bien ->> 'initiator',
        dedup_key => 'yeu-cau:' || (bien ->> 'ma_yeu_cau') || ':da-xu-ly',
        title => 'Yêu cầu ' || (bien ->> 'ma_yeu_cau') || ' đã được xử lý',
        link => '/yeu-cau/' || (bien ->> 'ma_yeu_cau')
    );
    RETURN NULL;
END
$$;
GRANT EXECUTE ON FUNCTION ung_dung.bao_tin_da_xu_ly(jsonb) TO workflow;
```

## Đọc thông báo

Lời gọi `GET /core/notifications` trả về các thông báo gửi cho người gọi. Access token của một ứng dụng chỉ thấy thông báo của ứng dụng đó. Access token của client khác chỉ thấy thông báo không thuộc ứng dụng nào. Thông báo mới nhất đứng đầu. Tham số `limit` đặt số thông báo tối đa được trả về, mặc định là 50 và tối đa là 200. Tham số `offset` đặt số thông báo được bỏ qua ở đầu danh sách. Mỗi thông báo gồm các trường sau:

| Trường | Ý nghĩa |
|---|---|
| `id` | Mã của thông báo |
| `title`, `body`, `link` | Tiêu đề, nội dung và đường dẫn. Trường `body` và `link` có giá trị `null` khi hàm `core.notify` không nhận hai tham số này |
| `created_at` | Thời điểm tạo |
| `read_at` | Thời điểm người nhận đánh dấu đã đọc. Giá trị `null` nghĩa là chưa đọc |

Lời gọi `POST /core/notifications/{id}/read` đánh dấu một thông báo là đã đọc và trả về thông báo đó. Khi thông báo đã được đọc trước đó, thời điểm đọc không đổi. Người dùng chỉ thấy và chỉ đánh dấu được thông báo gửi cho chính mình. Với thông báo của người khác, lời gọi nhận mã 404 như khi thông báo không tồn tại.

## Nhận thông báo mới

Khi có thông báo mới, kênh `user:#<sub>` của người nhận nhận một tin có dạng `{"notification": {...}}`. Đối tượng `notification` có các trường như ở mục [Đọc thông báo](#đọc-thông-báo), với `read_at` là `null`. Kênh này có thể nhận cả tin khác của ứng dụng. Do đó, ứng dụng nhận ra thông báo nhờ khóa `notification`. Ví dụ, tiếp theo ví dụ ở mục [Kết nối](realtime.md#kết-nối):

```js
const sub = centrifuge.newSubscription("user:#" + keycloak.subject);
sub.on("publication", (ctx) => {
  if (ctx.data.notification) {
    showNotification(ctx.data.notification);
  }
});
sub.subscribe();
```

Trong ví dụ trên, `showNotification` là hàm của ứng dụng. Ứng dụng thường tải danh sách thông báo bằng lời gọi `GET /core/notifications` rồi nghe kênh. Một thông báo có thể vừa có trong danh sách vừa tới qua kênh. Do đó, ứng dụng bỏ thông báo trùng theo trường `id`.

## Gửi thông báo qua Telegram

Khi hàm `core.notify` nhận tham số `telegram => true`, thông báo còn được gửi tới một nhóm Telegram qua Bot API. Tin Telegram gồm tiêu đề in đậm, nội dung và địa chỉ đầy đủ của đường dẫn, ví dụ `https://dx.example.com/yeu-cau/YC-001`. Tin được gửi tới nhóm, không gửi riêng cho người nhận. Do đó, mỗi khóa chống trùng chỉ có một tin Telegram, kể cả khi sự việc được báo cho nhiều người. Ví dụ, trong hàm của một bước máy làm:

```sql
PERFORM core.notify(
    recipient => bien ->> 'nguoi_xu_ly',
    dedup_key => 'yeu-cau:' || (bien ->> 'ma_yeu_cau') || ':moi',
    title => 'Có yêu cầu mới ' || (bien ->> 'ma_yeu_cau'),
    link => '/yeu-cau/' || (bien ->> 'ma_yeu_cau'),
    telegram => true
);
```

Để bật Telegram:

1. Tạo bot bằng [BotFather](https://t.me/BotFather) với lệnh `/newbot`. BotFather trả về token của bot, có dạng `123456789:AA...`.
2. Thêm bot vào nhóm nhận thông báo. Sau đó, gửi lệnh `/start@<tên bot>` trong nhóm. Khi nhóm có chủ đề (topic), gửi lệnh này trong chủ đề cần nhận tin.
3. Mở địa chỉ `https://api.telegram.org/bot<token>/getUpdates` bằng trình duyệt. Mã nhóm là giá trị `chat.id`, ví dụ `-1001234567890`. Mã chủ đề là giá trị `message_thread_id`. Telegram chỉ giữ các giá trị này trong 24 giờ.
4. Thêm các dòng sau vào file `.env` trong thư mục làm việc, rồi chạy `saigonos up`.

```
TELEGRAM_BOT_TOKEN=123456789:AA...
TELEGRAM_CHAT_ID=-1001234567890
TELEGRAM_TOPIC_ID=2
```

Khi bật chủ đề cho nhóm, Telegram chuyển nhóm thành supergroup và mã nhóm thay đổi. Do đó, lấy mã nhóm sau khi bật chủ đề. Các giá trị Telegram trong file `.env` như sau:

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

Trạng thái của tin, cách xử lý lỗi và cách gửi lại được trình bày ở mục [Hàng đợi gửi tin](../admin/notifications.md#hàng-đợi-gửi-tin).

## Gửi email

Hàm `core.send_email(address, dedup_key, title, body, link)` của cơ sở dữ liệu ghi một email vào hàng đợi `core.deliveries`. Service `core` gửi email qua một máy chủ SMTP, ví dụ máy chủ của Gmail. Hàm trả về mã của email trong hàng đợi, có kiểu `bigint`. Các tham số của hàm như sau:

| Tham số | Ý nghĩa |
|---|---|
| `address` | Địa chỉ email của người nhận, dài tối đa 254 ký tự. Địa chỉ không chứa chữ có dấu |
| `dedup_key` | Khóa chống trùng, dài từ 1 đến 255 ký tự |
| `title` | Tiêu đề của email, theo quy tắc của tham số `title` ở hàm `core.notify` |
| `body` | Nội dung, dài tối đa 2000 ký tự. Tham số này có thể bỏ qua |
| `link` | Đường dẫn tới một trang trong hệ thống, theo quy tắc của tham số `link` ở hàm `core.notify`. Tham số này có thể bỏ qua |

Người nhận không cần có tài khoản trong hệ thống. Ví dụ, hàm sau của một bước máy làm gửi email xác nhận cho người gửi yêu cầu:

```sql
CREATE FUNCTION ung_dung.gui_email_da_nhan(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM core.send_email(
        address => bien ->> 'email',
        dedup_key => 'yeu-cau:' || (bien ->> 'ma_yeu_cau') || ':da-nhan',
        title => 'Đã nhận yêu cầu ' || (bien ->> 'ma_yeu_cau'),
        body => 'Cảm ơn bạn đã gửi yêu cầu. Bạn có thể tra cứu yêu cầu tại đường dẫn sau.',
        link => '/tra-cuu/' || (bien ->> 'ma_yeu_cau')
    );
    RETURN NULL;
END
$$;
GRANT EXECUTE ON FUNCTION ung_dung.gui_email_da_nhan(jsonb) TO workflow;
```

Email được ghi trong cùng transaction với dữ liệu. Khi transaction bị hủy, email cũng bị hủy. Mỗi địa chỉ chỉ nhận một email cho mỗi khóa chống trùng của mỗi ứng dụng. Khi hàm được gọi lại với cùng địa chỉ và cùng khóa, hàm không ghi thêm email và trả về mã của email đã có.

Email chỉ có phần văn bản thuần. Phần này gồm nội dung, hoặc tiêu đề khi không có nội dung, rồi tới địa chỉ đầy đủ của đường dẫn. Email có header `Auto-Submitted: auto-generated`, nên chức năng trả lời tự động của hộp thư người nhận không trả lời email này.

Để bật email, thêm các dòng sau vào file `.env` trong thư mục làm việc, rồi chạy `saigonos up`. Ví dụ với Gmail:

```
SMTP_HOST=smtp.gmail.com
SMTP_USERNAME=thong-bao@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
SMTP_FROM=thong-bao@gmail.com
SMTP_FROM_NAME=Phòng Kỹ thuật
```

Gmail không nhận mật khẩu đăng nhập thường của tài khoản. Tài khoản cần bật xác minh 2 bước, rồi tạo mật khẩu ứng dụng tại trang [Mật khẩu ứng dụng](https://myaccount.google.com/apppasswords). Mật khẩu ứng dụng gồm 16 chữ cái, được viết liền, không có khoảng trắng. Các giá trị SMTP trong file `.env` như sau:

| Giá trị | Ý nghĩa |
|---|---|
| `SMTP_HOST` | Tên hoặc địa chỉ IP của máy chủ SMTP |
| `SMTP_PORT` | Cổng của máy chủ SMTP. Mặc định là 587, hoặc 465 khi `SMTP_SECURITY` là `tls`, hoặc 25 khi `SMTP_SECURITY` là `none` |
| `SMTP_SECURITY` | Cách mã hóa kết nối. Giá trị `starttls` mã hóa kết nối bằng lệnh STARTTLS. Giá trị `tls` mã hóa ngay từ đầu kết nối. Giá trị `none` không mã hóa và không cho dùng mật khẩu, chỉ dùng với máy chủ SMTP trong mạng nội bộ. Mặc định là `tls` khi `SMTP_PORT` là 465, và `starttls` với các cổng khác |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Tài khoản đăng nhập máy chủ SMTP. Bỏ trống hai giá trị này khi máy chủ không yêu cầu đăng nhập |
| `SMTP_FROM` | Địa chỉ gửi. Với Gmail, đây là địa chỉ của tài khoản |
| `SMTP_FROM_NAME` | Tên người gửi hiện trong hộp thư của người nhận. Giá trị này có thể bỏ trống |

Service `core` luôn kiểm tra chứng chỉ của máy chủ SMTP. Khi `SMTP_SECURITY` là `starttls` mà máy chủ không hỗ trợ STARTTLS, email không được gửi. Do đó, mật khẩu không được gửi qua kết nối chưa mã hóa. Khi một giá trị trong file `.env` có dấu `$`, giá trị đó được đặt trong cặp dấu nháy đơn, ví dụ `SMTP_PASSWORD='ab$cd'`.

Để thử cấu hình, chạy lệnh sau trong thư mục làm việc, với `<địa chỉ>` là một địa chỉ email của bạn. Email tới sau vài giây. Mỗi lần thử cần một khóa chống trùng mới, ví dụ `kiem-tra-email-2`.

```bash
docker compose exec postgres psql -U postgres -d saigonos -c "SET ROLE workflow; SELECT core.send_email('<địa chỉ>', 'kiem-tra-email-1', 'Email thử của SaigonOS')"
```

## Thông báo và kênh của ứng dụng

Mã của ứng dụng gọi được các hàm `core.notify`, `core.publish` và `core.send_email`. Mã của ứng dụng gồm hàm, trigger và file SQL của ứng dụng, kể cả hàm của bước máy làm. Các hàm này nhận ra ứng dụng đang gọi theo các quy tắc sau:

- Lời gọi API vào schema của ứng dụng chạy bằng role `<schema>_user` của ứng dụng đó.
- Bước máy làm của quy trình trong tenant của ứng dụng mang tên ứng dụng trong claim `azp` của claims đã niêm phong.
- File SQL chạy bằng role sở hữu schema của ứng dụng.

Khi mã của bước máy làm sửa `request.jwt.claims`, ba hàm trên báo lỗi `Claims của lời gọi đã bị sửa`.

Thông báo do mã của ứng dụng gửi mang tên ứng dụng trong cột `app` của bảng `core.notifications`. Thông báo này được gửi tới kênh `user:<tên ứng dụng>.<recipient>`, không gửi tới kênh `user:#<recipient>`. Khóa chống trùng của thông báo và email chỉ có hiệu lực trong một ứng dụng. Do đó, hai ứng dụng dùng cùng một khóa vẫn gửi được hai thông báo riêng.

Lời gọi `GET /core/notifications` với access token của ứng dụng chỉ trả về thông báo của ứng dụng đó. Hàm SQL của ứng dụng đọc bảng `core.notifications` cũng chỉ thấy thông báo của chính ứng dụng gửi cho người gọi. Thông báo không thuộc ứng dụng nào chỉ hiện với access token của client khác.

Mã của ứng dụng chỉ gửi được tin vào các kênh sau:

- `role:<tên ứng dụng>.<vai trò>`, ví dụ `role:nghi-phep.quan-ly`.
- `public:<tên ứng dụng>.<tên>`, ví dụ `public:nghi-phep.bang-tin`.
- `user:<tên ứng dụng>.<sub>`, tức kênh cá nhân của người dùng trong ứng dụng.

Tin gửi vào kênh khác bị từ chối với mã lỗi `42501`. Ví dụ, mã của ứng dụng `nghi-phep` không gửi được tin vào kênh `role:admin` hay `user:#<sub>`.

Để nghe kênh `user:<tên ứng dụng>.<sub>`, giao diện của ứng dụng lấy token kênh như mục [Nghe kênh](realtime.md#nghe-kênh). Centrifugo chỉ nhận token kênh do service `core` cấp, và service `core` chỉ cấp cho access token của chính ứng dụng. Do đó, giao diện của ứng dụng khác không nghe được kênh này. Kênh `user:#<sub>` không cần token kênh nên giao diện của mọi ứng dụng đều nghe được. Vì vậy, kênh này chỉ mang thông báo không thuộc ứng dụng nào. Ví dụ, tiếp theo ví dụ ở mục [Nhận thông báo mới](#nhận-thông-báo-mới):

```js
const channel = `user:nghi-phep.${keycloak.subject}`;
const sub = centrifuge.newSubscription(channel, {
  getToken: async () => {
    await keycloak.updateToken(30);
    const res = await fetch("/core/realtime/token", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${keycloak.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ channel }),
    });
    return (await res.json()).token;
  },
});
sub.on("publication", (ctx) => ctx.data.notification && showNotification(ctx.data.notification));
sub.subscribe();
```
