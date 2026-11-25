<!-- SPDX-License-Identifier: Apache-2.0 -->
# Tường lửa ứng dụng web

API Gateway chạy tường lửa ứng dụng web (WAF) [Coraza](https://coraza.io/) với bộ luật [OWASP Core Rule Set](https://coreruleset.org/) (CRS) 4.14.0. Tường lửa kiểm tra lời gọi tới `/api`, `/apps` và `/core` trước khi lời gọi được chuyển tới service phía sau. Lời gọi có dấu hiệu tấn công, ví dụ SQL injection, XSS hoặc path traversal, bị chặn ngay tại API Gateway.

Ở lần khởi động đầu tiên, service `waf` tải plugin `coraza-proxy-wasm` 0.6.0 và kiểm tra mã băm SHA-256 của plugin. Khi không tải được hoặc mã băm không khớp, lệnh `saigonos up` báo lỗi ở service `waf`.

## Phạm vi kiểm tra

- Tường lửa kiểm tra đường dẫn, query string, header và body của lời gọi. Body JSON, form và XML được tách thành từng tham số để kiểm tra.
- Bộ luật CRS chạy ở mức paranoia 1. Lời gọi bị chặn khi có một luật mức critical khớp.
- Luật 920350 bị tắt. Luật này chặn header `Host` là địa chỉ IP, trong khi hệ thống cho truy cập bằng địa chỉ IP trong mạng nội bộ.
- Sau khi đăng nhập, Keycloak gửi tham số `iss` về trang của ứng dụng. Tham số này được bỏ qua khi giá trị đúng bằng issuer của realm `saigonos`. Tham số `iss` có giá trị khác vẫn được kiểm tra.
- Chỉ các phương thức GET, HEAD, POST, OPTIONS, PUT, PATCH và DELETE được nhận.
- Body của lời gọi tối đa 1 MB. Lời gọi có body lớn hơn nhận mã 413.
- Nội dung file gửi tới `/core/files/{id}/content` không đi qua tường lửa mà được [quét mã độc](malware-scan.md).
- Keycloak, Operaton và `/realtime` không đi qua tường lửa.

## Lời gọi bị chặn

Lời gọi bị chặn nhận mã 403, hoặc mã 413 khi body quá lớn. Nội dung trả về theo dạng lỗi của PostgREST với mã `SGN04`:

```json
{"code":"SGN04","details":null,"hint":null,"message":"Tường lửa ứng dụng web đã chặn lời gọi này vì có dấu hiệu tấn công."}
```

Mỗi luật khớp được ghi vào log của APISIX, kèm mã luật và phần dữ liệu khớp. Mỗi lời gọi bị chặn có thêm một dòng log ghi địa chỉ IP của người gọi. Các dòng này được xem bằng lệnh sau trong thư mục làm việc:

```bash
docker compose logs apisix | grep -E "Coraza|Tường lửa"
```

## Chế độ chỉ ghi log

Để thử tường lửa trên hệ thống đang chạy mà không chặn lời gọi nào, thêm dòng sau vào file `.env` rồi chạy `saigonos up`:

```
SAIGONOS_WAF_MODE=detect
```

Ở chế độ này, các luật khớp chỉ được ghi vào log. Để chặn trở lại, xóa dòng trên hoặc đặt giá trị `block`, rồi chạy `saigonos up`. Lệnh `saigonos doctor` cho biết tường lửa đang chặn hay chỉ ghi log.
