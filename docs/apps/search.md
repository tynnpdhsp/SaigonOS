<!-- SPDX-License-Identifier: Apache-2.0 -->
# Tìm kiếm

Mục `search` của bản khai báo liệt kê các bảng cần tìm kiếm toàn văn. Mỗi phần tử gồm tên bảng `table` trong schema của ứng dụng và danh sách cột `columns` cần tìm. Ví dụ, để ứng dụng mẫu tìm đơn đặt phòng theo lớp, phần mềm và ghi chú, thêm vào bản khai báo:

```json
"search": [
  { "table": "don", "columns": ["lop", "phan_mem", "ghi_chu"] }
]
```

Khi cài đặt, lõi tạo cho mỗi bảng một index GIN tên `saigonos_search_<bảng>` và một hàm `search_<bảng>(q text)`. Bảng không có thêm cột nào. Ứng dụng gọi hàm qua API của ứng dụng:

```js
const query = new URLSearchParams({ q: "lap trinh python" });
const reply = await fetch(`/apps/phong-may/api/rpc/search_don?${query}`, { headers });
const found = await reply.json();
```

Hàm trả về các dòng của bảng như lời gọi `GET /apps/phong-may/api/don`, nên dùng được các tham số `select`, `limit` và bộ lọc của PostgREST. Chữ cần tìm gõ có dấu hay không dấu đều được, chữ hoa và chữ thường được coi như nhau. Khi có nhiều từ, dòng phải có đủ các từ. Cụm từ đặt trong dấu nháy kép phải xuất hiện liền nhau và đúng thứ tự. Từ có dấu trừ ở trước thì dòng chứa từ đó bị loại. Kết quả xếp theo độ khớp.

Hàm chạy bằng role `<schema>_user` của ứng dụng. Do đó, chính sách Row-Level Security (RLS) của bảng vẫn áp dụng, và người dùng chỉ tìm thấy các dòng mình được đọc. Role `anon` không gọi được hàm này. Với bảng có RLS, PostgreSQL đọc lần lượt các dòng mà người gọi được xem thay cho việc dùng index. Trên bảng 10.000 dòng, việc này mất khoảng 35 ms.

Mục `search` tuân theo các quy tắc sau:

- Mục có tối đa 20 bảng. Tên bảng và tên cột gồm chữ thường không dấu, chữ số và dấu gạch dưới, bắt đầu bằng chữ cái hoặc dấu gạch dưới. Tên bảng dài tối đa 47 ký tự. Mỗi bảng có từ 1 tới 10 cột, không cột nào được khai báo hai lần.
- Bảng phải có trong schema của ứng dụng. Cột phải có kiểu `text`, `varchar` hoặc `char`, hay một domain dựa trên các kiểu này. Lệnh cài đặt kiểm tra điều này sau khi chạy các file SQL và dừng khi có sai.
- Tên hàm `search_<bảng>` không được trùng hàm do file SQL của ứng dụng tạo.

Mỗi lần cài đặt, lõi tạo lại index và hàm khi danh sách cột thay đổi. Bỏ một bảng khỏi mục `search` thì lõi gỡ index và hàm của bảng đó.

File SQL của ứng dụng cũng tự viết được câu tìm kiếm bằng hai hàm của lõi. Hàm `core.search_vector(VARIADIC text[])` tạo vector tìm kiếm từ các chuỗi, còn hàm `core.search_query(text)` đọc chữ cần tìm theo cú pháp trên. Ví dụ, `WHERE core.search_vector(lop, phan_mem) @@ core.search_query('lap trinh')`.
