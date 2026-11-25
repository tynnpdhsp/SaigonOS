<!-- SPDX-License-Identifier: Apache-2.0 -->
# File

## Tải file lên

Service `core` nhận file của các ứng dụng và lưu file vào SeaweedFS. Mỗi file được tải lên bằng hai lời gọi. Cả hai lời gọi đều cần access token của người dùng đã đăng nhập.

1. Lời gọi `POST /core/files` khai báo tên, loại và dung lượng của file. Service kiểm tra ba giá trị này trước khi nhận nội dung. Khi hợp lệ, service trả về mã 201 kèm mã file và đường dẫn tải lên trong trường `upload_url`. File ở trạng thái `pending_upload`.
2. Lời gọi `PUT` tới đường dẫn tải lên gửi nội dung của file. Service tính dung lượng và mã băm SHA-256 của nội dung, rồi kiểm tra phần đầu của nội dung. Khi hợp lệ, nội dung được lưu vào bucket `quarantine` và file chuyển sang trạng thái `pending_scan`, tức chờ quét mã độc.

Ngay sau khi nhận nội dung, service `core` quét file bằng ClamAV. Việc quét chạy nền nên lời gọi `PUT` không phải chờ. Ứng dụng gọi `GET /core/files/{id}` để biết kết quả quét. Mục [Quét mã độc](../admin/malware-scan.md) mô tả cách quét. Khi file có trạng thái `clean`, ứng dụng tải file về theo mục [Tải file về](#tải-file-về).

Ba trường của lời gọi khai báo có cùng tên với các thuộc tính của đối tượng `File` trong trình duyệt. Ví dụ, một ứng dụng web tải file mà người dùng đã chọn như sau:

```js
const headers = { Authorization: `Bearer ${accessToken}` };
const declared = await fetch("/core/files", {
  method: "POST",
  headers: { ...headers, "Content-Type": "application/json" },
  body: JSON.stringify({ name: file.name, type: file.type, size: file.size }),
});
const { upload_url } = await declared.json();
await fetch(upload_url, { method: "PUT", headers, body: file });
```

Mỗi file chỉ nhận nội dung một lần. Khi lời gọi gửi nội dung bị từ chối, nội dung không được lưu và có thể được gửi lại. Lời gọi `GET /core/files/{id}` trả về thông tin và trạng thái của file. Bảng `core.files` có chính sách phân quyền từng dòng. Do đó, mỗi người dùng chỉ thấy file của chính mình.

Các trạng thái của file:

| Trạng thái | Ý nghĩa |
|---|---|
| `pending_upload` | Chờ gửi nội dung |
| `pending_scan` | Nội dung nằm trong bucket `quarantine` và chờ quét mã độc |
| `clean` | ClamAV không phát hiện mã độc. Nội dung đã được chuyển sang bucket `clean` và tải về được |
| `infected` | ClamAV phát hiện mã độc. Trường `malware` ghi tên mã độc. Nội dung được giữ trong bucket `quarantine` và không tải về được |

Các loại file được phép:

| Loại file | Phần mở rộng | Phần đầu của nội dung |
|---|---|---|
| `application/pdf` | `.pdf` | `%PDF-` |
| `image/jpeg` | `.jpg`, `.jpeg` | Các byte `FF D8 FF` |
| `image/png` | `.png` | Các byte `89 50 4E 47 0D 0A 1A 0A` |
| `image/webp` | `.webp` | `RIFF`, 4 byte bất kỳ, sau đó là `WEBP` |
| `text/plain` | `.txt` | 8.192 byte đầu không chứa byte 0 |
| `text/csv` | `.csv` | 8.192 byte đầu không chứa byte 0 |
| `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | `.docx` | `PK` và các byte `03 04` của file ZIP |
| `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | `.xlsx` | `PK` và các byte `03 04` của file ZIP |

Tên file phải có phần mở rộng ứng với loại file. Tên file dài tối đa 255 ký tự và không chứa ký tự điều khiển, dấu `/` hoặc dấu `\`. Văn bản mã hóa UTF-16 chứa byte 0 nên không được nhận là `text/plain` hoặc `text/csv`.

Mỗi file có dung lượng tối đa 10 MB, với 1 MB là 1.048.576 byte. Tùy chọn `--max-file-size` của lệnh `saigonos init` đổi giới hạn này. API Gateway cũng từ chối mọi lời gọi có nội dung lớn hơn giới hạn này.

Các mã lỗi của hai lời gọi:

| Mã | Lời gọi | Ý nghĩa |
|---|---|---|
| 401 | Khai báo và gửi nội dung | Thiếu access token hoặc access token không hợp lệ |
| 413 | Khai báo | Dung lượng khai báo vượt giới hạn |
| 413 | Gửi nội dung | Nội dung lớn hơn giới hạn nên API Gateway từ chối |
| 415 | Khai báo | Loại file không được phép |
| 422 | Khai báo | Tên file không hợp lệ hoặc phần mở rộng không ứng với loại file |
| 422 | Gửi nội dung | Dung lượng hoặc phần đầu của nội dung không khớp với thông tin đã khai báo |
| 404 | Gửi nội dung | Không có file với mã này hoặc file thuộc người dùng khác |
| 409 | Gửi nội dung | File đã nhận nội dung |
| 503 | Gửi nội dung | SeaweedFS chưa sẵn sàng. File vẫn ở trạng thái `pending_upload` và có thể gửi lại |

## Tải file về

Mỗi file được tải về bằng một đường dẫn có thời hạn. Ứng dụng xin đường dẫn bằng lời gọi `POST /core/files/{id}/download-url` kèm access token của người dùng đã đăng nhập. Service trả về đường dẫn trong trường `download_url` và thời điểm hết hạn trong trường `expires_at`.

Đường dẫn dùng được trong 60 giây và mở được trong trình duyệt mà không cần access token. Trong 60 giây này, đường dẫn mở được nhiều lần và bất kỳ ai có đường dẫn đều tải được file. Do đó, ứng dụng chỉ xin đường dẫn ngay trước khi tải và không lưu lại đường dẫn. Thời hạn chỉ áp dụng cho lúc mở đường dẫn. Một file lớn có thể tải xong sau thời điểm hết hạn.

Ví dụ, một ứng dụng web tải file về như sau:

```js
const reply = await fetch(`/core/files/${id}/download-url`, {
  method: "POST",
  headers: { Authorization: `Bearer ${accessToken}` },
});
const { download_url } = await reply.json();
window.location.assign(download_url);
```

Chỉ file có trạng thái `clean` mới tải về được. Người dùng chỉ xin được đường dẫn cho file mà chính sách phân quyền từng dòng của bảng `core.files` cho phép đọc. Trước khi gửi file, service đọc lại nội dung từ bucket `clean` và so với mã băm SHA-256 đã ghi.

File được gửi kèm các header `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff` và `Cache-Control: no-store`. Do đó, trình duyệt luôn lưu file về máy với tên đã khai báo, không tự đoán lại loại file và không giữ file trong bộ nhớ đệm.

Đường dẫn được ký bằng khóa `CORE_DOWNLOAD_KEY` trong file `.env`. Sau khi đổi khóa này và chạy `saigonos up`, các đường dẫn đã cấp không còn dùng được.

Các mã lỗi của hai lời gọi:

| Mã | Lời gọi | Ý nghĩa |
|---|---|---|
| 401 | Xin đường dẫn | Thiếu access token hoặc access token không hợp lệ |
| 404 | Xin đường dẫn | Không có file với mã này hoặc người gọi không được đọc file |
| 409 | Xin đường dẫn và tải về | File chưa có nội dung, đang chờ quét mã độc hoặc có mã độc |
| 403 | Tải về | Đường dẫn không hợp lệ hoặc đã hết hạn |
| 503 | Tải về | SeaweedFS chưa sẵn sàng |
| 500 | Tải về | Nội dung trong bucket `clean` không khớp mã băm đã ghi. File không được gửi |

## Tìm file

Lời gọi `GET /core/files?q=<chữ cần tìm>` kèm access token tìm file theo tên. Kết quả chỉ gồm các file mà chính sách phân quyền từng dòng của bảng `core.files` cho người gọi đọc. Tham số `limit` đặt số file trả về tối đa, mặc định là 20, tối đa là 100.

```js
const reply = await fetch(`/core/files?q=${encodeURIComponent("máy hỏng")}`, {
  headers: { Authorization: `Bearer ${accessToken}` },
});
const files = await reply.json();
```

Chữ cần tìm gõ có dấu hay không dấu đều được. Chữ hoa và chữ thường được coi như nhau. Ví dụ, `may hong` tìm thấy file `Ảnh máy hỏng.png`. Dấu gạch ngang, dấu gạch dưới và dấu chấm trong tên file được coi là khoảng trắng, nên `bien ban` tìm thấy file `bien-ban_sua-may.pdf`.

Khi chữ cần tìm có nhiều từ, file phải có đủ các từ. Cú pháp giống ô tìm kiếm của các trang web. Cụm từ đặt trong dấu nháy kép phải xuất hiện liền nhau và đúng thứ tự. Từ có dấu trừ ở trước thì file chứa từ đó bị loại. Kết quả xếp theo độ khớp, rồi tới file được khai báo sau.
