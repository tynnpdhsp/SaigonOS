<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lưu trữ và chốt số liệu

Mục `archive` của bản khai khai các bảng có dòng cũ được chuyển xuống [hồ dữ liệu](../admin/data-lake.md). Mục `snapshots` khai các view hoặc bảng được chốt số liệu theo tháng. Ví dụ, để ứng dụng mẫu chuyển các đơn cũ hơn một năm xuống hồ và chốt lịch dùng phòng mỗi tháng, thêm vào bản khai:

```json
"archive": [
  {
    "table": "don",
    "column": "bat_dau",
    "keep_days": 365,
    "rules": [
      { "rule": "not_null", "columns": ["phong_id", "nguoi_gui"] },
      { "rule": "unique", "columns": ["id"] },
      { "rule": "range", "column": "so_may_san_sang", "min": 1, "max": 500 }
    ]
  }
],
"snapshots": [
  { "view": "lich", "column": "bat_dau", "rules": [{ "rule": "not_null", "columns": ["ma_phong"] }] }
]
```

| Trường | Ý nghĩa |
|---|---|
| `table` | Bảng trong schema của ứng dụng, có dòng cũ được chuyển xuống hồ |
| `view` | View hoặc bảng trong schema của ứng dụng, được chốt số liệu theo tháng |
| `column` | Cột thời gian của dòng, có kiểu `timestamptz`, `timestamp` hoặc `date` |
| `keep_days` | Số ngày dòng được giữ ở bảng, từ 1 đến 36500 |
| `rules` | Luật chất lượng, tối đa 20 luật. Mỗi luật có tối đa 10 cột |

Mỗi giờ, service `core` làm hai việc theo thứ tự sau:

1. Chốt số liệu. Với mỗi mục trong `snapshots`, lõi chốt từng tháng đã hết mà chưa được chốt. File của một tháng gồm mọi dòng có cột thời gian thuộc tháng đó. File đã chốt không bị ghi đè, kể cả khi dữ liệu của tháng thay đổi sau đó.
2. Lưu trữ. Với mỗi bảng trong `archive`, lõi chuyển các dòng cũ hơn `keep_days` ngày sang file Parquet, mỗi tháng một file. Lõi ghi file, đọc lại để so mã băm và số dòng, rồi mới xóa các dòng này khỏi bảng. Khi có sai lệch hay lỗi, bảng giữ nguyên.

Khi ứng dụng có mục `snapshots`, dòng của các tháng chưa chốt được giữ lại ở bảng, kể cả khi cũ hơn `keep_days` ngày. Dòng có cột thời gian rỗng luôn được giữ ở bảng.

Luật chất lượng được kiểm trên các dòng sắp chuyển xuống hồ, hoặc trên các dòng của tháng sắp chốt:

| Luật | Ý nghĩa |
|---|---|
| `not_null` | Các cột trong `columns` không được rỗng |
| `unique` | Không có hai dòng trùng giá trị ở mọi cột trong `columns`. Dòng có cột rỗng không được tính |
| `range` | Giá trị của cột `column` nằm trong khoảng từ `min` đến `max`, tính cả hai đầu. Luật cần ít nhất một trong hai giá trị. Dòng có cột rỗng không bị tính là vi phạm |

Khi một luật không đạt, tháng đó không được chốt hoặc dòng cũ không được chuyển xuống hồ. Lõi gửi tin cho admin qua kênh `role:admin` và qua nhóm Telegram. Tin chỉ ra luật bị vi phạm, số dòng vi phạm và tối đa 3 dòng ví dụ. Ví dụ:

```text
Chưa chuyển dòng cũ của bảng don trong ứng dụng phong-may xuống hồ dữ liệu vì dữ liệu không đạt luật chất lượng. Luật range của cột so_may_san_sang (từ 1 đến 500) không đạt ở 1 dòng, ví dụ {"id": 42, "so_may_san_sang": 0}.
```

Lõi kiểm lại ở mỗi lần chạy. Do đó, sau khi dữ liệu được sửa, tháng được chốt và dòng cũ được chuyển xuống hồ ở lần chạy kế tiếp. Kết quả của mỗi lần kiểm được ghi vào bảng `core.lineage`.

Lệnh cài đặt kiểm tra các mục này sau khi chạy các file SQL và dừng khi có sai:

- Bảng, view và các cột đã khai phải có trong schema của ứng dụng. Cột của luật `range` phải có kiểu số.
- Bảng trong mục `archive` không được bảng khác tham chiếu bằng khóa ngoại `ON DELETE CASCADE`, `SET NULL` hay `SET DEFAULT`, vì dòng của bảng kia sẽ bị đổi theo mà không được lưu vào hồ.

Lõi đọc và xóa dòng bằng role `lake` của cơ sở dữ liệu. Role này bỏ qua chính sách phân quyền từng dòng để đọc đủ mọi dòng. Lệnh cài đặt chỉ cấp cho role `lake` quyền đọc các bảng, view đã khai và quyền xóa trên các bảng trong mục `archive`. File của hai việc này nằm trong bucket `lake` của SeaweedFS và được đọc bằng các lệnh ở trang [Hồ dữ liệu](../admin/data-lake.md).
