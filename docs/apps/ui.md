<!-- SPDX-License-Identifier: Apache-2.0 -->
# Giao diện

Service `core` phục vụ các file trong thư mục `ui` của ứng dụng đã cài đặt tại địa chỉ `/apps/<tên ứng dụng>/`. Ví dụ, file `ui/app.js` của ứng dụng `nghi-phep` nằm ở địa chỉ `/apps/nghi-phep/app.js`. Địa chỉ `/apps/nghi-phep` chuyển hướng về `/apps/nghi-phep/`. Service `core` đọc thư mục `apps` của thư mục làm việc ở chế độ chỉ đọc.

Các quy tắc sau áp dụng cho giao diện:

- Địa chỉ không khớp file nào và không có phần mở rộng trả về file `index.html`. Nhờ đó, ứng dụng một trang (single-page application) tự xử lý các địa chỉ như `/apps/nghi-phep/don/12`. Địa chỉ có phần mở rộng mà không khớp file nào nhận mã 404.
- File `index.html` không được cache. Các file khác được cache nhưng trình duyệt phải hỏi lại service `core` trước mỗi lần dùng. File không đổi thì service trả mã 304 và trình duyệt dùng bản đã cache.
- Mỗi trả lời có các header `Content-Security-Policy`, `X-Content-Type-Options: nosniff` và `Referrer-Policy: same-origin`. Chính sách `Content-Security-Policy` chỉ cho trang tải script, ảnh, font và gọi API từ chính địa chỉ của hệ thống. Script viết trực tiếp trong file HTML không chạy, nên mọi script phải nằm trong file `.js` riêng.
- Địa chỉ có `..`, kể cả ở dạng mã hóa như `%2e%2e`, nhận mã 404. File và thư mục có tên bắt đầu bằng dấu chấm, symlink và địa chỉ bắt đầu bằng `/apps/<tên ứng dụng>/api` không được phục vụ như file của giao diện.
- Ứng dụng chưa cài đặt, kể cả khi thư mục đã được chép vào thư mục `apps`, nhận mã 404.
