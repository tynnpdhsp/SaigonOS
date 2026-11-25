<!-- SPDX-License-Identifier: Apache-2.0 -->
# File

Service `core` nhận file của các ứng dụng, quét mã độc rồi lưu file vào SeaweedFS. Mọi lời gọi trên trang này cần access token của người dùng đã đăng nhập, trừ lời gọi tải về bằng đường dẫn có thời hạn.

## Tải file lên

Mỗi file được tải lên bằng hai lời gọi:

1. Lời gọi `POST /core/files` khai báo tên, loại và dung lượng của file. Khi ba giá trị này hợp lệ, service trả về mã 201 kèm mã file và đường dẫn tải lên trong trường `upload_url`. File ở trạng thái `pending_upload`.
2. Lời gọi `PUT` tới đường dẫn tải lên gửi nội dung của file. Service kiểm tra dung lượng và phần đầu của nội dung, rồi lưu nội dung vào bucket `quarantine`. File chuyển sang trạng thái `pending_scan`.

Ba trường của lời gọi khai báo có cùng tên với các thuộc tính của đối tượng `File` trong trình duyệt. Ví dụ, một trang web tải lên file mà người dùng đã chọn như sau:

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

Ngay sau khi nhận nội dung, service `core` [quét mã độc](../admin/malware-scan.md) trong nền. Ứng dụng gọi `GET /core/files/{id}` để biết trạng thái của file. Mỗi file chỉ nhận nội dung một lần. Khi lời gọi gửi nội dung bị từ chối, nội dung có thể được gửi lại. Bảng `core.files` có chính sách phân quyền từng dòng, nên mỗi người dùng chỉ thấy file của chính mình.

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

Tên file phải có phần mở rộng ứng với loại file. Tên file dài tối đa 255 ký tự và không chứa ký tự điều khiển, dấu `/` hoặc dấu `\`. Mỗi file có dung lượng tối đa 10 MB, với 1 MB là 1.048.576 byte. Giới hạn này đổi được bằng tùy chọn `--max-file-size` của lệnh `saigonos init`.

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

Mỗi file được tải về bằng một đường dẫn có thời hạn. Ứng dụng xin đường dẫn bằng lời gọi `POST /core/files/{id}/download-url`. Service trả về đường dẫn trong trường `download_url` và thời điểm hết hạn trong trường `expires_at`. Ví dụ:

```js
const reply = await fetch(`/core/files/${id}/download-url`, {
  method: "POST",
  headers: { Authorization: `Bearer ${accessToken}` },
});
const { download_url } = await reply.json();
window.location.assign(download_url);
```

Đường dẫn dùng được trong 60 giây và mở được trong trình duyệt mà không cần access token. Trong 60 giây này, bất kỳ ai có đường dẫn đều tải được file. Do đó, ứng dụng chỉ xin đường dẫn ngay trước khi tải và không lưu lại đường dẫn. Chỉ file có trạng thái `clean` mới tải về được. Người dùng chỉ xin được đường dẫn cho file mà mình được đọc.

File được gửi kèm các header `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff` và `Cache-Control: no-store`. Do đó, trình duyệt luôn lưu file về máy với tên đã khai báo và không giữ file trong bộ nhớ đệm. Đường dẫn được ký bằng khóa `CORE_DOWNLOAD_KEY` trong file `.env`. Sau khi đổi khóa này và chạy `saigonos up`, các đường dẫn đã cấp không còn dùng được.

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

Lời gọi `GET /core/files?q=<chữ cần tìm>` tìm file theo tên trong các file mà người gọi được đọc. Tham số `limit` đặt số file trả về tối đa, mặc định là 20, tối đa là 100. Ví dụ:

```js
const reply = await fetch(`/core/files?q=${encodeURIComponent("máy hỏng")}`, {
  headers: { Authorization: `Bearer ${accessToken}` },
});
const files = await reply.json();
```

Chữ cần tìm gõ có dấu hay không dấu đều được, chữ hoa và chữ thường được coi như nhau. Ví dụ, `may hong` tìm thấy file `Ảnh máy hỏng.png`. Dấu gạch ngang, dấu gạch dưới và dấu chấm trong tên file được coi là khoảng trắng. Khi có nhiều từ, file phải có đủ các từ. Cụm từ đặt trong dấu nháy kép phải xuất hiện liền nhau và đúng thứ tự. Từ có dấu trừ ở trước thì file chứa từ đó bị loại. Kết quả xếp theo độ khớp, rồi tới file được khai báo sau.
