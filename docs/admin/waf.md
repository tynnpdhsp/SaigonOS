<!-- SPDX-License-Identifier: Apache-2.0 -->
# Tường lửa ứng dụng web

API Gateway chạy tường lửa ứng dụng web (WAF) [Coraza](https://coraza.io/) với bộ luật [OWASP Core Rule Set](https://coreruleset.org/) (CRS) 4.14.0. Coraza kiểm tra lời gọi tới `/api`, `/apps` và `/core` trước khi lời gọi được chuyển tới service phía sau. Lời gọi có dấu hiệu tấn công, ví dụ SQL injection, XSS hoặc path traversal, bị chặn ngay tại API Gateway.

Coraza chạy trong APISIX dưới dạng plugin wasm. Ở lần khởi động đầu tiên, service `waf` tải file `coraza-proxy-wasm` 0.6.0 từ trang Releases của dự án. Service này kiểm tra mã băm SHA-256 của file zip và của file `.wasm`, rồi lưu file vào volume `wasm`. Ở các lần khởi động sau, file đã lưu được dùng lại. Khi không tải được file hoặc mã băm không khớp, lệnh `saigonos up` báo lỗi ở service `waf`.

## Phạm vi kiểm tra

- Coraza kiểm tra đường dẫn, query string, header và body của lời gọi. Body JSON, form và XML được tách thành từng tham số để kiểm tra.
- Bộ luật CRS chạy ở mức paranoia 1. Lời gọi bị chặn khi tổng điểm bất thường đạt 5, tức là chỉ cần một luật mức critical khớp.
- Bộ luật CRS chạy đầy đủ, chỉ tắt luật 920350. Luật này chặn lời gọi có header `Host` là địa chỉ IP, trong khi SaigonOS cho phép truy cập bằng địa chỉ IP trong mạng nội bộ như mục [Cấu hình](configuration.md). Toàn bộ integration test của SaigonOS, gồm các luồng của ứng dụng thử, chạy qua tường lửa mà không bị chặn nhầm.
- Các luật của CRS bỏ qua tham số `iss` trong query string khi giá trị của tham số đúng bằng issuer của realm `saigonos`, tức `<SAIGONOS_URL>/auth/realms/saigonos`. Keycloak gửi tham số này khi chuyển người dùng về trang của ứng dụng sau khi đăng nhập. Khi địa chỉ truy cập là địa chỉ IP, luật 931100 coi giá trị này là tấn công nạp file từ xa (RFI). Với địa chỉ `127.0.0.1`, luật 934110 coi giá trị này là tấn công SSRF. Tham số `iss` có giá trị khác vẫn được kiểm tra như mọi tham số.
- Các phương thức được dùng là GET, HEAD, POST, OPTIONS, PUT, PATCH và DELETE.
- Body của lời gọi tối đa 1 MB. Lời gọi có body lớn hơn nhận mã 413, vì tường lửa không kiểm tra được.
- Body JSON không đúng định dạng không tách được thành tham số. PostgREST và service `core` từ chối body này với mã 400 hoặc 422.
- Lời gọi gửi nội dung file tới `/core/files/{id}/content` không đi qua tường lửa. Nội dung file được ClamAV quét như mục [Quét mã độc](malware-scan.md).
- Keycloak, Operaton và `/realtime` không đi qua tường lửa.

## Lời gọi bị chặn

Lời gọi bị chặn nhận mã 403, hoặc mã 413 khi body quá lớn. Nội dung trả về theo dạng lỗi của PostgREST với mã `SGN04`. Ví dụ:

```json
{"code":"SGN04","details":null,"hint":null,"message":"Tường lửa ứng dụng web đã chặn lời gọi này vì có dấu hiệu tấn công."}
```

Mỗi luật khớp được ghi vào log của APISIX, kèm mã luật và phần dữ liệu khớp. Plugin `saigonos-waf` ghi thêm một dòng cho mỗi lời gọi bị chặn, kèm địa chỉ IP của người gọi. Trong thư mục làm việc, xem các dòng này bằng lệnh sau:

```bash
docker compose logs apisix | grep -E "Coraza|Tường lửa"
```

## Chế độ chỉ ghi log

Để thử tường lửa trên hệ thống đang chạy mà không chặn lời gọi nào, thêm dòng sau vào file `.env` trong thư mục làm việc, rồi chạy `saigonos up`:

```
SAIGONOS_WAF_MODE=detect
```

Ở chế độ này, các luật khớp vẫn được ghi vào log nhưng lời gọi không bị chặn. Để chặn trở lại, xóa dòng trên hoặc đặt giá trị `block`, rồi chạy `saigonos up`. Khi giá trị không hợp lệ, lệnh `saigonos up` báo lỗi ở service `routes` và tường lửa giữ chế độ đang chạy. Lệnh `saigonos doctor` cho biết tường lửa đang chặn hay chỉ ghi log.
