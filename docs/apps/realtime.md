<!-- SPDX-License-Identifier: Apache-2.0 -->
# Cập nhật tức thời

SaigonOS dùng Centrifugo để gửi cập nhật tức thời tới ứng dụng qua WebSocket. Ứng dụng kết nối tới địa chỉ `/realtime/connection/websocket` của API Gateway, ví dụ `ws://localhost:9080/realtime/connection/websocket`. Trên máy chủ có HTTPS, địa chỉ này có dạng `wss://dx.example.com/realtime/connection/websocket`. API Gateway chỉ mở địa chỉ này của Centrifugo.

## Kết nối

Sau khi mở WebSocket, ứng dụng gửi access token do Keycloak cấp trong lệnh connect. Trình duyệt không gửi được header `Authorization` khi mở WebSocket. Do đó, API Gateway không kiểm tra access token ở địa chỉ này. Centrifugo tự kiểm tra chữ ký, issuer (`iss`), thời hạn và audience (`aud`) của access token. Kết nối không có access token hoặc có access token không mang mã người dùng (`sub`) đều bị từ chối. Khi Keycloak đổi khóa ký, Centrifugo tự lấy khóa mới.

Centrifugo chỉ nhận access token có audience `saigonos`. Mỗi khi hệ thống khởi động, service `realm` thêm audience này vào access token của mọi client dùng client scope `roles`. ID token không có audience này nên bị từ chối. Khi mapper `audience saigonos` của client scope `roles` bị sửa hoặc bị xóa, service `realm` đặt lại mapper này.

Khi mở WebSocket, trình duyệt gửi địa chỉ của trang trong header `Origin`. Centrifugo chỉ nhận kết nối từ trang có địa chỉ trùng với địa chỉ truy cập của hệ thống, tức giá trị của tùy chọn `--url`. Do đó, trang của một web khác không mở được kết nối bằng phiên đăng nhập của người dùng.

Lệnh `saigonos init` ghi địa chỉ truy cập vào dòng `CENTRIFUGO_ALLOWED_ORIGIN` của file `.env`. Centrifugo đọc giá trị này như một mẫu glob, nên mỗi ký tự đặc biệt của mẫu glob được thêm dấu `\` ở trước. Ví dụ, địa chỉ `http://[2001:db8::1]:9080` được ghi thành `http://\[2001:db8::1\]:9080`. Lệnh `saigonos init` ghi lại dòng này mỗi lần chạy. Do đó, sau khi sửa dòng `SAIGONOS_URL` trong file `.env`, cần chạy lại lệnh `saigonos init` rồi `saigonos up`.

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

Access token chỉ có hiệu lực 60 giây. Khi access token hết hạn, thư viện gọi hàm `getToken` để lấy access token mới và gửi cho Centrifugo. Access token mới phải thuộc cùng người dùng. Nếu không nhận được access token mới, Centrifugo đóng kết nối khoảng 25 giây sau khi access token hết hạn.

Khi từ chối hoặc đóng kết nối, Centrifugo trả về một trong các mã sau:

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

Tên, `sub` và realm role chỉ gồm chữ cái không dấu, chữ số và các dấu `_`, `.`, `-`. Tên kênh dài tối đa 255 ký tự. Kênh không có namespace hoặc thuộc namespace khác bị từ chối.

Để nghe kênh `role:<realm role>`, ứng dụng lấy token kênh (subscription token) bằng lời gọi `POST /core/realtime/token`, với nội dung `{"channel": "role:<realm role>"}`. Service `core` trả về `{"token": "..."}` khi access token của người gọi có realm role này. Người gọi không có realm role nhận mã 403. Với kênh `user:<tên ứng dụng>.<sub>`, service `core` chỉ cấp token kênh khi access token được cấp cho client của ứng dụng đó và `<sub>` là mã của người gọi. Trường hợp khác nhận mã 403. Kênh khác hai dạng này nhận mã 422. Token kênh được ký bằng khóa `CENTRIFUGO_SUBSCRIPTION_KEY` trong file `.env` và chỉ dùng được cho đúng kênh, đúng người dùng đã lấy token.

Token kênh có hiệu lực 60 giây và hết hạn không muộn hơn access token dùng để lấy token kênh. Khi token kênh hết hạn, thư viện gọi hàm `getToken` của kênh để lấy token mới. Nếu không nhận được token mới, Centrifugo ngừng gửi tin của kênh trong khoảng 25 đến 52 giây sau khi token kênh hết hạn. Do đó, người dùng bị gỡ realm role ngừng nhận tin của kênh chậm nhất khoảng 2 phút sau khi bị gỡ.

Ví dụ, tiếp theo ví dụ ở mục [Kết nối](#kết-nối):

```js
import { UnauthorizedError } from "centrifuge";

const sub = centrifuge.newSubscription("role:quan-ly", {
  getToken: async (ctx) => {
    await keycloak.updateToken(30);
    const res = await fetch("https://dx.example.com/core/realtime/token", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${keycloak.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ channel: ctx.channel }),
    });
    if (res.status === 403) {
      throw new UnauthorizedError();
    }
    if (!res.ok) {
      throw new Error(`Không lấy được token kênh, mã ${res.status}`);
    }
    return (await res.json()).token;
  },
});
sub.on("publication", (ctx) => console.log(ctx.data));
sub.subscribe();
```

Khi `getToken` ném `UnauthorizedError`, thư viện ngừng nghe kênh. Với lỗi khác, thư viện thử lại sau ít giây. Kênh `public:<tên>` và `user:#<sub>` không cần `getToken`, ví dụ `centrifuge.newSubscription("user:#" + keycloak.subject).subscribe()`.

Khi từ chối hoặc ngừng gửi tin của kênh, Centrifugo trả về một trong các mã sau:

| Mã | Ý nghĩa |
|---|---|
| `102` | Kênh thuộc namespace khác ba namespace `public`, `user` và `role` |
| `103` | Không có quyền nghe kênh, ví dụ kênh không có namespace, kênh `user:#<sub>` của người khác, kênh `role:` hoặc `user:<tên ứng dụng>.<sub>` không kèm token kênh hoặc kèm token kênh giả |
| `109` | Token kênh đã hết hạn. Thư viện tự lấy token kênh mới rồi nghe lại |
| `2501` | Kênh hết hạn vì không nhận được token kênh mới. Thư viện tự nghe lại |
| `3500` | Token kênh của kênh khác hoặc của người dùng khác. Centrifugo đóng kết nối và thư viện không kết nối lại |

## Gửi tin từ cơ sở dữ liệu

Hàm `core.publish(channel, data)` của cơ sở dữ liệu `saigonos` gửi một tin tới một kênh của Centrifugo. Tham số `channel` là tên kênh, có một trong bốn dạng ở mục [Nghe kênh](#nghe-kênh). Tham số `data` là nội dung của tin, có kiểu `jsonb`. Hàm trả về mã của tin, có kiểu `uuid`. Hàm báo lỗi khi kênh sai dạng hoặc nội dung là `NULL`.

Hàm ghi tin vào bảng `core.outbox` trong cùng transaction với dữ liệu. Ngay khi transaction được commit, Centrifugo đọc tin, gửi tới các client đang nghe kênh rồi xóa tin khỏi bảng. Khi transaction bị hủy, tin cũng bị hủy. Do đó, client chỉ nhận tin về dữ liệu đã được lưu. Các tin của cùng một transaction tới client theo đúng thứ tự gọi hàm.

Chỉ role được cấp quyền `EXECUTE` mới gọi được hàm. Role `workflow` và các role của ứng dụng có quyền này. Do đó, hàm được gọi trong [bước máy làm](workflow.md#bước-máy-làm) của quy trình hoặc trong mã của ứng dụng. Mã của ứng dụng chỉ gửi được tin vào kênh của chính ứng dụng, như mục [Thông báo và kênh của ứng dụng](notifications.md#thông-báo-và-kênh-của-ứng-dụng). Ví dụ, hàm sau cập nhật một yêu cầu rồi báo cho người đã bắt đầu quy trình, tức người có mã trong biến `initiator`:

```sql
CREATE FUNCTION ung_dung.bao_da_xu_ly(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE ung_dung.yeu_cau SET trang_thai = 'da_xu_ly' WHERE ma = bien ->> 'ma_yeu_cau';
    PERFORM core.publish(
        'user:#' || (bien ->> 'initiator'),
        jsonb_build_object('ma_yeu_cau', bien ->> 'ma_yeu_cau', 'trang_thai', 'da_xu_ly')
    );
    RETURN NULL;
END
$$;
GRANT EXECUTE ON FUNCTION ung_dung.bao_da_xu_ly(jsonb) TO workflow;
```

Centrifugo gửi mã của tin trong trường `tags` của tin, với khóa `id`. Ví dụ: `{"id": "1276d3b3-fd8f-43e0-9649-b5ef7743accf"}`. Trong một số trường hợp hiếm, client nhận một tin hai lần. Ví dụ, Centrifugo dừng đột ngột sau khi gửi tin và trước khi xóa tin khỏi bảng. Khi chạy lại, Centrifugo gửi lại tin này. Do đó, client dùng mã của tin để bỏ tin trùng.

## Tin bị lỡ khi mất kết nối

Mỗi kênh có history giữ tối đa 100 tin gần nhất trong 5 phút. Mỗi tin trong history có một số thứ tự (offset). History của kênh có một mã (epoch). Mã này đổi khi history được tạo lại.

Khi client mất kết nối rồi kết nối lại, thư viện tự gửi epoch và offset của tin cuối cùng đã nhận. Nếu các tin bị lỡ còn đủ trong history, Centrifugo gửi lại các tin này theo đúng thứ tự, trước các tin mới. Khi đó, sự kiện `subscribed` có `recovered` là true và ứng dụng không cần làm gì thêm.

Centrifugo trả `recovered` là false khi client lỡ quá 100 tin, kết nối lại sau quá 5 phút hoặc Centrifugo đã khởi động lại. Centrifugo giữ history trong bộ nhớ. Do đó, mỗi lần Centrifugo khởi động lại, history mất và mọi kênh có epoch mới. Khi `recovered` là false, client có thể đã lỡ tin, nên ứng dụng tải lại dữ liệu qua API. Ví dụ, `reloadData` dưới đây là hàm của ứng dụng, đọc lại dữ liệu qua API:

```js
sub.on("subscribed", async (ctx) => {
  if (ctx.wasRecovering && !ctx.recovered) {
    await reloadData();
  }
});
```

Tin ghi bằng hàm `core.publish` trong lúc Centrifugo dừng không bị mất. Các tin này nằm lại trong bảng `core.outbox` và được gửi ngay khi Centrifugo chạy lại, theo đúng thứ tự ghi. Client thường kết nối lại sau lúc đó, nên không nhận các tin này như tin mới. Các tin này nằm trong history của kênh. Ứng dụng chỉ hiện các tin gần đây, ví dụ danh sách thông báo, có thể đọc history thay cho việc tải lại dữ liệu:

```js
const { publications } = await sub.history({ limit: 100 });
```

Sau khi Centrifugo khởi động lại, history chỉ gồm các tin được gửi từ lúc đó. Lời gọi `history` phải có `limit`. Khi không có `limit`, Centrifugo chỉ trả epoch và offset của kênh, không trả tin nào. Tin trong history mang cùng mã `id` với tin đã nhận, nên ứng dụng bỏ tin trùng theo mã này. Chỉ client đang nghe kênh mới đọc được history của kênh đó.

## API của server và Admin web

API của server và Admin web của Centrifugo nằm ở cổng 9480, chỉ truy cập được từ chính máy cài đặt. API Gateway không mở cổng này. Lời gọi API của server cần header `X-API-Key` với giá trị `CENTRIFUGO_API_KEY` trong file `.env`. Ví dụ, lệnh sau xem thông tin các node của Centrifugo:

```bash
curl -X POST -H "X-API-Key: $(grep CENTRIFUGO_API_KEY ~/saigonos/.env | cut -d= -f2)" -d '{}' http://127.0.0.1:9480/api/info
```

Admin web ở địa chỉ http://127.0.0.1:9480/ dùng để xem số kết nối và gọi thử API của server. Mật khẩu đăng nhập là giá trị `CENTRIFUGO_ADMIN_PASSWORD` trong file `.env`.
