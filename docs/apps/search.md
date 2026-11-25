<!-- SPDX-License-Identifier: Apache-2.0 -->
# Tìm kiếm

Mục `search` của bản khai khai các bảng cần tìm kiếm toàn văn. Mỗi phần tử gồm tên bảng `table` trong schema của ứng dụng và danh sách cột `columns` cần tìm:

```json
"search": [
  { "table": "don", "columns": ["ly_do", "ghi_chu"] }
]
```

Khi cài đặt, lõi tạo cho mỗi bảng một index GIN tên `saigonos_search_<bảng>` và một hàm `search_<bảng>(q text)`. Index được tạo trên biểu thức, nên bảng không có thêm cột nào. Ứng dụng gọi hàm qua API của ứng dụng:

```js
const query = new URLSearchParams({ q: "ly do gia dinh" });
const reply = await fetch(`/apps/nghi-phep/api/rpc/search_don?${query}`, { headers });
const found = await reply.json();
```

Hàm trả về các dòng của bảng như lời gọi `GET /apps/nghi-phep/api/don`, nên dùng được các tham số `select`, `limit` và bộ lọc của PostgREST. Chữ cần tìm gõ có dấu hay không dấu đều được. Chữ hoa và chữ thường được coi như nhau. Khi có nhiều từ, dòng phải có đủ các từ. Cụm từ đặt trong dấu nháy kép phải xuất hiện liền nhau và đúng thứ tự. Từ có dấu trừ ở trước thì dòng chứa từ đó bị loại. Kết quả xếp theo độ khớp, dòng có từ cần tìm xuất hiện nhiều lần đứng trước.

Hàm chạy với role `<schema>_user` của ứng dụng, như các hàm do file SQL của ứng dụng tạo. Do đó, chính sách phân quyền từng dòng của bảng vẫn áp dụng, và người dùng chỉ tìm thấy các dòng mình được đọc. Role `anon` không gọi được hàm này. Với bảng có phân quyền từng dòng, PostgreSQL không dùng được index cho phép tìm, vì toán tử `@@` của PostgreSQL chưa được đánh dấu leakproof. Khi đó, PostgreSQL đọc lần lượt các dòng mà người gọi được xem. Trên bảng 10.000 dòng, việc này mất khoảng 35 ms trong cơ sở dữ liệu. Index được dùng khi bảng không có phân quyền từng dòng.

Mục `search` tuân theo các quy tắc sau:

- Tên bảng và tên cột gồm chữ thường không dấu, chữ số và dấu gạch dưới, bắt đầu bằng chữ cái hoặc dấu gạch dưới. Tên bảng dài tối đa 47 ký tự. Mỗi bảng có từ 1 tới 10 cột, không cột nào được khai báo hai lần.
- Bảng phải có trong schema của ứng dụng. Cột phải có kiểu `text`, `varchar` hoặc `char`, hay một domain dựa trên các kiểu này. Lệnh cài đặt kiểm tra điều này sau khi chạy các file SQL và dừng khi có sai.
- Tên hàm `search_<bảng>` không được trùng hàm do file SQL của ứng dụng tạo. Khi trùng, lệnh cài đặt dừng và không đụng tới hàm đó.

Mỗi lần cài đặt, lõi tạo lại index và hàm khi danh sách cột thay đổi hoặc khi index đã mất, ví dụ vì file SQL đã xóa một cột được tìm. Bỏ một bảng khỏi mục `search` thì lõi gỡ index và hàm của bảng đó.

Lõi có sẵn cấu hình tìm kiếm `core.vietnamese` của PostgreSQL. Cấu hình này bỏ dấu bằng extension `unaccent` và đổi chữ hoa thành chữ thường. Hàm `core.search_vector(VARIADIC text[])` tạo vector tìm kiếm từ các chuỗi, còn hàm `core.search_query(text)` đọc chữ cần tìm theo cú pháp trên. File SQL của ứng dụng dùng được hai hàm này để tự viết câu tìm kiếm, ví dụ `WHERE core.search_vector(ly_do) @@ core.search_query('gia dinh')`.
