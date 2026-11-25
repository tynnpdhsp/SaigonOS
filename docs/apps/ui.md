<!-- SPDX-License-Identifier: Apache-2.0 -->
# Giao diện

Service `core` phục vụ các file trong thư mục `ui` của ứng dụng đã cài đặt tại địa chỉ `/apps/<tên ứng dụng>/`. Ví dụ, file [`ui/app.js`](https://github.com/tynnpdhsp/SaigonOS/blob/main/examples/phong-may/ui/app.js) của ứng dụng mẫu nằm ở địa chỉ `/apps/phong-may/app.js`. Địa chỉ `/apps/phong-may` chuyển hướng về `/apps/phong-may/`.

Các quy tắc sau áp dụng cho giao diện:

- Địa chỉ không khớp file nào và không có phần mở rộng trả về file `index.html`. Nhờ đó, ứng dụng một trang (single-page application) tự xử lý các địa chỉ như `/apps/phong-may/don/12`. Địa chỉ có phần mở rộng mà không khớp file nào nhận mã 404.
- File `index.html` không được cache. Các file khác được cache nhưng trình duyệt phải hỏi lại service `core` trước mỗi lần dùng.
- Mỗi trả lời có các header `Content-Security-Policy`, `X-Content-Type-Options: nosniff` và `Referrer-Policy: same-origin`. Chính sách `Content-Security-Policy` chỉ cho trang tải script, ảnh, font và gọi API từ chính địa chỉ của hệ thống. Script viết trực tiếp trong file HTML không chạy, nên mọi script phải nằm trong file `.js` riêng.
- File và thư mục có tên bắt đầu bằng dấu chấm, symlink và địa chỉ có `..` không được phục vụ.
- Ứng dụng chưa cài đặt nhận mã 404, kể cả khi thư mục đã được chép vào thư mục `apps`.

Giao diện không cần đăng nhập để tải về. Dữ liệu được lấy qua API của ứng dụng bằng access token, như trang [Đăng nhập](login.md) và [Dữ liệu và API](database.md).
