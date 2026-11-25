<!-- SPDX-License-Identifier: Apache-2.0 -->
# Thông báo

Thông báo cho người dùng được lưu trong bảng `core.notifications`. Mỗi thông báo gửi cho một người dùng. Người nhận đọc thông báo qua service `core` và nhận thông báo mới tức thời qua Centrifugo. Thông báo cũng có thể được gửi thêm tới nhóm Telegram. Email được gửi tới mọi địa chỉ, kể cả người không có tài khoản trong hệ thống. Cách cấu hình Telegram và email được trình bày ở trang [Telegram và email](../admin/notifications.md).

## Gửi thông báo

Hàm `core.notify(recipient, dedup_key, title, body, link, telegram)` ghi một thông báo rồi gửi thông báo đó tới kênh của người nhận. Hàm trả về mã của thông báo, kiểu `uuid`. Các tham số của hàm như sau:

| Tham số | Ý nghĩa |
|---|---|
| `recipient` | Mã người nhận, tức claim `sub` trong access token của người nhận |
| `dedup_key` | Khóa chống trùng, dài từ 1 đến 255 ký tự |
| `title` | Tiêu đề, dài tối đa 200 ký tự. Tiêu đề không được để trống và không chứa ký tự điều khiển, ví dụ dấu xuống dòng |
| `body` | Nội dung, dài tối đa 2000 ký tự. Tham số này có thể bỏ qua |
| `link` | Đường dẫn tới một trang trong hệ thống, bắt đầu bằng một dấu `/` và dài tối đa 1000 ký tự, ví dụ `/apps/phong-may/?don=12`. Tham số này có thể bỏ qua |
| `telegram` | Khi có giá trị `true`, thông báo còn được gửi tới nhóm Telegram. Mặc định là `false` |

Hàm báo lỗi khi một tham số không hợp lệ. Hàm từ chối đường dẫn tới web khác, ví dụ `https://...` hoặc `//...`, và đường dẫn `javascript:`. Do đó, ứng dụng hiển thị được đường dẫn của thông báo mà không cần kiểm tra lại.

Thông báo được ghi trong cùng transaction với dữ liệu. Khi transaction bị hủy, thông báo cũng bị hủy. Mỗi người nhận chỉ có một thông báo cho mỗi khóa chống trùng của mỗi ứng dụng. Khi hàm được gọi lại với cùng người nhận và cùng khóa, hàm không ghi thêm thông báo và trả về mã của thông báo đã có. Do đó, khóa chống trùng nên nêu sự việc mà thông báo nói tới, ví dụ `don:12:ket-qua`.

Ví dụ, hàm `ghi_ket_qua` trong file [`database/0004_quy_trinh.sql`](https://github.com/tynnpdhsp/SaigonOS/blob/main/examples/phong-may/database/0004_quy_trinh.sql) của ứng dụng mẫu báo kết quả duyệt cho giáo viên đã gửi đơn:

```sql
PERFORM core.notify(
    recipient => ban_ghi.nguoi_gui,
    dedup_key => 'don:' || ban_ghi.id || ':ket-qua',
    title => format(
        'Đơn đặt phòng số %s %s',
        ban_ghi.id,
        CASE WHEN duoc_duyet THEN 'đã được duyệt' ELSE 'bị từ chối' END
    ),
    body => format('%s, %s.', ten_phong, phong_may.mo_ta_gio(ban_ghi.bat_dau, ban_ghi.ket_thuc))
        || coalesce(' Ý kiến: ' || ban_ghi.y_kien, ''),
    link => '/apps/phong-may/?don=' || ban_ghi.id
);
```

## Đọc thông báo

Lời gọi `GET /core/notifications` trả về các thông báo gửi cho người gọi. Access token của một ứng dụng chỉ thấy thông báo của ứng dụng đó. Thông báo mới nhất đứng đầu. Tham số `limit` đặt số thông báo tối đa được trả về, mặc định là 50 và tối đa là 200. Tham số `offset` đặt số thông báo được bỏ qua ở đầu danh sách. Mỗi thông báo gồm các trường sau:

| Trường | Ý nghĩa |
|---|---|
| `id` | Mã của thông báo |
| `title`, `body`, `link` | Tiêu đề, nội dung và đường dẫn. Trường `body` và `link` có giá trị `null` khi hàm `core.notify` không nhận hai tham số này |
| `created_at` | Thời điểm tạo |
| `read_at` | Thời điểm người nhận đánh dấu đã đọc. Giá trị `null` nghĩa là chưa đọc |

Lời gọi `POST /core/notifications/{id}/read` đánh dấu một thông báo là đã đọc và trả về thông báo đó. Người dùng chỉ thấy và chỉ đánh dấu được thông báo gửi cho chính mình. Với thông báo của người khác, lời gọi nhận mã 404 như khi thông báo không tồn tại.

## Nhận thông báo mới

Thông báo do mã của ứng dụng gửi được đưa tới kênh `user:<tên ứng dụng>.<sub>` của người nhận, ví dụ `user:phong-may.<sub>`. Tin của kênh có dạng `{"notification": {...}}`, với các trường như mục [Đọc thông báo](#đọc-thông-báo). Kênh này cần token kênh như ở trang [Cập nhật tức thời](realtime.md#nghe-kênh), và chỉ giao diện của chính ứng dụng lấy được token này. Ví dụ, với `showNotification` là hàm của ứng dụng:

```js
const channel = `user:phong-may.${keycloak.subject}`;
const sub = centrifuge.newSubscription(channel, {
  getToken: async () => {
    await keycloak.updateToken(30);
    const res = await fetch("/core/realtime/token", {
      method: "POST",
      headers: { Authorization: `Bearer ${keycloak.token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ channel }),
    });
    return (await res.json()).token;
  },
});
sub.on("publication", (ctx) => ctx.data.notification && showNotification(ctx.data.notification));
sub.subscribe();
```

Ứng dụng thường tải danh sách thông báo bằng lời gọi `GET /core/notifications` rồi mới nghe kênh. Một thông báo có thể vừa có trong danh sách vừa tới qua kênh. Do đó, ứng dụng bỏ thông báo trùng theo trường `id`. Thông báo không thuộc ứng dụng nào được gửi tới kênh `user:#<sub>`.

## Gửi thông báo qua Telegram

Khi hàm `core.notify` nhận tham số `telegram => true`, thông báo còn được gửi tới nhóm Telegram đã cấu hình. Tin Telegram gồm tiêu đề in đậm, nội dung và địa chỉ đầy đủ của đường dẫn. Tin được gửi tới nhóm, không gửi riêng cho người nhận. Do đó, mỗi khóa chống trùng chỉ có một tin Telegram, kể cả khi sự việc được báo cho nhiều người. Ví dụ, hàm `nhac_duyet` trong file `database/0004_quy_trinh.sql` nhắc mọi phụ trách phòng khi đơn tới hạn duyệt. Hàm `bao_vai` của ứng dụng mẫu gọi `core.notify` cho từng người có role đã nêu, với tham số cuối cùng là `telegram`:

```sql
PERFORM phong_may.bao_vai(
    'phong-may.phu-trach',
    'don:' || ban_ghi.id || ':nhac-duyet',
    format('Đơn đặt phòng số %s đã tới hạn duyệt', ban_ghi.id),
    format(
        '%s, %s. Lớp hoặc học phần: %s.',
        ban_ghi.ten_phong, phong_may.mo_ta_gio(ban_ghi.bat_dau, ban_ghi.ket_thuc), ban_ghi.lop
    ),
    '/apps/phong-may/?don=' || ban_ghi.id,
    true
);
```

## Gửi email

Hàm `core.send_email(address, dedup_key, title, body, link)` ghi một email vào hàng đợi gửi tin. Hàm trả về mã của email trong hàng đợi, kiểu `bigint`. Các tham số `dedup_key`, `title`, `body` và `link` theo quy tắc của hàm `core.notify`. Tham số `address` là địa chỉ email của người nhận, dài tối đa 254 ký tự và không chứa chữ có dấu. Ví dụ, một bước máy làm gửi email xác nhận tới địa chỉ trong biến `email` của quy trình:

```sql
PERFORM core.send_email(
    address => bien ->> 'email',
    dedup_key => 'don:' || (bien ->> 'ma_don') || ':da-nhan',
    title => 'Đã nhận đơn đặt phòng số ' || (bien ->> 'ma_don'),
    link => '/apps/phong-may/?don=' || (bien ->> 'ma_don')
);
```

Email được ghi trong cùng transaction với dữ liệu. Mỗi địa chỉ chỉ nhận một email cho mỗi khóa chống trùng của mỗi ứng dụng. Email chỉ có phần văn bản thuần, gồm nội dung hoặc tiêu đề, rồi tới địa chỉ đầy đủ của đường dẫn.

## Thông báo của ứng dụng

Mã của ứng dụng gồm hàm, trigger, file SQL và hàm của bước máy làm. Thông báo, email và tin do mã của ứng dụng gửi đều thuộc về ứng dụng đó. Khóa chống trùng chỉ có hiệu lực trong một ứng dụng, nên hai ứng dụng dùng cùng một khóa vẫn gửi được hai thông báo riêng. Hàm của ứng dụng đọc bảng `core.notifications` cũng chỉ thấy thông báo của chính ứng dụng. Khi mã của bước máy làm sửa `request.jwt.claims`, ba hàm `core.notify`, `core.send_email` và `core.publish` báo lỗi `Claims của lời gọi đã bị sửa`.
