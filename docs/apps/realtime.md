<!-- SPDX-License-Identifier: Apache-2.0 -->
# Cập nhật tức thời

SaigonOS dùng Centrifugo để gửi cập nhật tức thời tới ứng dụng qua WebSocket. Ứng dụng kết nối tới địa chỉ `/realtime/connection/websocket` của API Gateway, ví dụ `wss://dx.example.com/realtime/connection/websocket` trên máy chủ có HTTPS.

## Kết nối

Sau khi mở WebSocket, ứng dụng gửi access token do Keycloak cấp trong lệnh connect. Centrifugo tự kiểm tra chữ ký, issuer, thời hạn và audience `saigonos` của access token. ID token và access token không mang mã người dùng (`sub`) đều bị từ chối. Centrifugo chỉ nhận kết nối từ trang có địa chỉ trùng với địa chỉ truy cập của hệ thống. Lệnh `saigonos init` ghi địa chỉ này vào cấu hình của Centrifugo dưới dạng mẫu glob. Ví dụ, địa chỉ `http://[2001:db8::1]:9080` được ghi thành `http://\[2001:db8::1\]:9080`.

Ví dụ, với thư viện [centrifuge-js](https://github.com/centrifugal/centrifuge-js) và [keycloak-js](https://www.npmjs.com/package/keycloak-js):

```js
import { Centrifuge } from "centrifuge";

const centrifuge = new Centrifuge("wss://dx.example.com/realtime/connection/websocket", {
  getToken: async () => {
    await keycloak.updateToken(30);
    return keycloak.token;
  },
});
centrifuge.connect();
```

Access token chỉ có hiệu lực 60 giây. Khi access token hết hạn, thư viện gọi hàm `getToken` để lấy access token mới của cùng người dùng. Nếu không nhận được access token mới, Centrifugo đóng kết nối khoảng 25 giây sau khi access token hết hạn. Khi từ chối hoặc đóng kết nối, Centrifugo trả về một trong các mã sau:

| Mã | Ý nghĩa |
|---|---|
| `109` | Access token đã hết hạn. Thư viện tự lấy access token mới rồi kết nối lại |
| `3001` | Centrifugo đang dừng. Thư viện tự kết nối lại |
| `3005` | Kết nối hết hạn vì không nhận được access token mới. Thư viện tự kết nối lại |
| `3500` | Access token không hợp lệ, ví dụ sai chữ ký, sai issuer, là ID token hoặc thuộc người dùng khác |
| `3501` | Lệnh connect không có access token |
| `3507` | Access token không mang mã người dùng |

## Nghe kênh

Sau khi kết nối, ứng dụng nghe một kênh bằng lệnh subscribe. Tên kênh có một trong bốn dạng sau:

| Kênh | Người nghe được | Token kênh |
|---|---|---|
| `public:<tên>` | Mọi người dùng đã đăng nhập | Không cần |
| `user:#<sub>` | Chỉ người dùng có mã `<sub>`, tức claim `sub` trong access token | Không cần |
| `role:<realm role>` | Những người dùng có realm role `<realm role>` | Cần |
| `user:<tên ứng dụng>.<sub>` | Chỉ người dùng có mã `<sub>`, qua access token của ứng dụng `<tên ứng dụng>` | Cần |

Tên, `sub` và realm role chỉ gồm chữ cái không dấu, chữ số và các dấu `_`, `.`, `-`. Tên kênh dài tối đa 255 ký tự.

Để nghe kênh cần token kênh (subscription token), ứng dụng gọi `POST /core/realtime/token` với nội dung `{"channel": "<tên kênh>"}`. Với kênh `role:<realm role>`, service `core` chỉ cấp token khi người gọi có realm role này. Với kênh `user:<tên ứng dụng>.<sub>`, service `core` chỉ cấp token cho access token của chính ứng dụng đó, với `<sub>` là mã của người gọi. Trường hợp khác nhận mã 403. Token kênh có hiệu lực 60 giây. Người dùng bị gỡ realm role ngừng nhận tin của kênh chậm nhất khoảng 2 phút sau khi bị gỡ.

Ví dụ, tiếp theo ví dụ ở mục [Kết nối](#kết-nối), giao diện của phụ trách phòng nghe kênh `role:phong-may.phu-trach`:

```js
import { UnauthorizedError } from "centrifuge";

const sub = centrifuge.newSubscription("role:phong-may.phu-trach", {
  getToken: async (ctx) => {
    await keycloak.updateToken(30);
    const res = await fetch("/core/realtime/token", {
      method: "POST",
      headers: { Authorization: `Bearer ${keycloak.token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ channel: ctx.channel }),
    });
    if (res.status === 403) {
      throw new UnauthorizedError();
    }
    return (await res.json()).token;
  },
});
sub.on("publication", (ctx) => console.log(ctx.data));
sub.subscribe();
```

Khi `getToken` ném `UnauthorizedError`, thư viện ngừng nghe kênh. Với lỗi khác, thư viện thử lại sau ít giây. Khi từ chối hoặc ngừng gửi tin của kênh, Centrifugo trả về một trong các mã sau:

| Mã | Ý nghĩa |
|---|---|
| `102` | Kênh thuộc namespace khác ba namespace `public`, `user` và `role` |
| `103` | Không có quyền nghe kênh, ví dụ kênh `user:#<sub>` của người khác, hoặc kênh cần token kênh mà không có token |
| `109` | Token kênh đã hết hạn. Thư viện tự lấy token kênh mới rồi nghe lại |
| `2501` | Kênh hết hạn vì không nhận được token kênh mới. Thư viện tự nghe lại |
| `3500` | Token kênh của kênh khác hoặc của người dùng khác. Centrifugo đóng kết nối |

## Gửi tin từ cơ sở dữ liệu

Hàm `core.publish(channel, data)` gửi một tin tới một kênh. Tham số `channel` là tên kênh, tham số `data` là nội dung của tin, kiểu `jsonb`. Hàm trả về mã của tin, kiểu `uuid`. Hàm ghi tin vào bảng `core.outbox` trong cùng transaction với dữ liệu. Khi transaction được commit, Centrifugo gửi tin tới các client đang nghe kênh. Khi transaction bị hủy, tin cũng bị hủy. Do đó, client chỉ nhận tin về dữ liệu đã được lưu.

Mã của ứng dụng chỉ gửi được tin vào các kênh `role:<tên ứng dụng>.<vai trò>`, `public:<tên ứng dụng>.<tên>` và `user:<tên ứng dụng>.<sub>`. Tin gửi vào kênh khác bị từ chối với mã lỗi `42501`. Ví dụ, một hàm của ứng dụng mẫu báo cho phụ trách phòng có đơn mới, với `ban_ghi` là dòng vừa thêm vào bảng `don`:

```sql
PERFORM core.publish('role:phong-may.phu-trach', jsonb_build_object('don', ban_ghi.id));
```

Centrifugo gửi mã của tin trong trường `tags` của tin, với khóa `id`. Trong một số trường hợp hiếm, client nhận một tin hai lần, ví dụ khi Centrifugo dừng đột ngột ngay sau khi gửi tin. Do đó, client dùng mã của tin để bỏ tin trùng.

## Tin bị lỡ khi mất kết nối

Mỗi kênh có history giữ tối đa 100 tin gần nhất trong 5 phút. Khi client kết nối lại, thư viện tự gửi vị trí của tin cuối cùng đã nhận. Nếu các tin bị lỡ còn đủ trong history, Centrifugo gửi lại các tin này theo đúng thứ tự. Khi đó, sự kiện `subscribed` có `recovered` là true.

Centrifugo trả `recovered` là false khi client lỡ quá 100 tin, kết nối lại sau quá 5 phút hoặc Centrifugo đã khởi động lại. Khi đó, ứng dụng tải lại dữ liệu qua API. Ví dụ, với `reloadData` là hàm của ứng dụng đọc lại dữ liệu:

```js
sub.on("subscribed", async (ctx) => {
  if (ctx.wasRecovering && !ctx.recovered) {
    await reloadData();
  }
});
```

Tin được ghi bằng hàm `core.publish` trong lúc Centrifugo dừng không bị mất. Các tin này được gửi ngay khi Centrifugo chạy lại và nằm trong history của kênh. Ứng dụng chỉ hiện các tin gần đây, ví dụ danh sách thông báo, có thể đọc history thay cho việc tải lại dữ liệu:

```js
const { publications } = await sub.history({ limit: 100 });
```

Lời gọi `history` phải có `limit`. Chỉ client đang nghe kênh mới đọc được history của kênh đó.

## API của server và Admin web

API của server và Admin web của Centrifugo nằm ở cổng 9480, chỉ truy cập được từ chính máy cài đặt. Lời gọi API của server cần header `X-API-Key` với giá trị `CENTRIFUGO_API_KEY` trong file `.env`. Ví dụ, lệnh sau xem thông tin các node của Centrifugo:

```bash
curl -X POST -H "X-API-Key: $(grep CENTRIFUGO_API_KEY ~/saigonos/.env | cut -d= -f2)" -d '{}' http://127.0.0.1:9480/api/info
```

Admin web ở địa chỉ http://127.0.0.1:9480/ dùng để xem số kết nối và gọi thử API của server, với mật khẩu là giá trị `CENTRIFUGO_ADMIN_PASSWORD`.
