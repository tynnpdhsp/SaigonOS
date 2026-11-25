<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lưu trữ và chốt số liệu

Mục `archive` của bản khai khai các bảng có dòng cũ được chuyển xuống hồ dữ liệu. Mục `snapshots` khai các view hoặc bảng được chốt số liệu theo tháng. File của hai việc này nằm trong hồ dữ liệu như mục [Hồ dữ liệu](../admin/data-lake.md). Ví dụ:

```json
"archive": [
  {
    "table": "don",
    "column": "tao_luc",
    "keep_days": 365,
    "rules": [
      { "rule": "not_null", "columns": ["ma", "nguoi_gui"] },
      { "rule": "unique", "columns": ["ma"] },
      { "rule": "range", "column": "so_ngay", "min": 0.5, "max": 30 }
    ]
  }
],
"snapshots": [
  { "view": "chot_don", "column": "tao_luc", "rules": [{ "rule": "not_null", "columns": ["ma"] }] }
]
```

| Trường | Ý nghĩa |
|---|---|
| `table` | Bảng trong schema của ứng dụng, có dòng cũ được chuyển xuống hồ |
| `view` | View hoặc bảng trong schema của ứng dụng, được chốt số liệu theo tháng |
| `column` | Cột thời gian của dòng, có kiểu `timestamptz`, `timestamp` hoặc `date` |
| `keep_days` | Số ngày dòng được giữ ở bảng, từ 1 đến 36500 |
| `rules` | Luật chất lượng, tối đa 20 luật. Mỗi luật có tối đa 10 cột |

Mỗi giờ, service `core` làm hai việc theo thứ tự sau. Lệnh `saigonos lake run` làm ngay hai việc này.

1. Chốt số liệu. Với mỗi mục trong `snapshots`, lõi chốt từng tháng đã hết mà chưa được chốt, bắt đầu từ tháng của dòng cũ nhất. File của một tháng gồm mọi dòng có cột thời gian thuộc tháng đó. File đã chốt không bị ghi đè, kể cả khi dữ liệu của tháng thay đổi sau đó.
2. Lưu trữ. Với mỗi bảng trong `archive`, lõi chuyển các dòng cũ hơn `keep_days` ngày sang file Parquet, mỗi tháng một file. Lõi ghi file, đọc lại để so mã băm SHA-256 và đếm số dòng trong file, rồi mới xóa các dòng này khỏi bảng. Việc đọc, ghi phả hệ và xóa nằm trong cùng một transaction. Số dòng trong file, số dòng đã chọn và số dòng đã xóa phải bằng nhau. Khi có sai lệch hay lỗi, transaction bị hủy và bảng giữ nguyên.

Khi ứng dụng có mục `snapshots`, dòng từ tháng chưa chốt sớm nhất trở đi được giữ lại ở bảng, kể cả khi cũ hơn `keep_days` ngày. Nhờ đó, dòng không bị chuyển xuống hồ trước khi tháng của nó được chốt. Dòng có cột thời gian rỗng luôn được giữ ở bảng.

Luật chất lượng được kiểm bằng câu SQL trên các dòng sắp chuyển xuống hồ, hoặc trên các dòng của tháng sắp chốt:

| Luật | Ý nghĩa |
|---|---|
| `not_null` | Các cột trong `columns` không được rỗng |
| `unique` | Không có hai dòng trùng giá trị ở mọi cột trong `columns`. Dòng có cột rỗng không được tính |
| `range` | Giá trị của cột `column` nằm trong khoảng từ `min` đến `max`, tính cả hai đầu. Luật cần ít nhất một trong hai giá trị. Dòng có cột rỗng không bị tính là vi phạm |

Khi một luật không đạt, tháng đó không được chốt hoặc dòng cũ không được chuyển xuống hồ. Lõi gửi tin cho admin qua kênh `role:admin` như mục [Nghe kênh](realtime.md#nghe-kênh) và qua nhóm Telegram như mục [Gửi thông báo qua Telegram](notifications.md#gửi-thông-báo-qua-telegram). Tin chỉ ra luật bị vi phạm, số dòng vi phạm và tối đa 3 dòng ví dụ. Mỗi dòng ví dụ gồm khóa chính và cột vi phạm. Với view không có khóa chính, dòng ví dụ gồm cột thời gian và cột vi phạm. Ví dụ:

```text
Chưa chốt số liệu của chot_don tháng 10/2026 trong ứng dụng nghi-phep vì dữ liệu không đạt luật chất lượng. Luật not_null của cột ma không đạt ở 1 dòng, ví dụ {"ma": null, "tao_luc": "2026-10-18T09:00:00+07:00"}.
```

Tin giống nhau chỉ được gửi một lần. Lõi kiểm lại ở mỗi lần chạy, nên tháng được chốt và dòng cũ được chuyển xuống hồ ngay lần chạy sau khi dữ liệu đã được sửa. Kết quả của mỗi lần kiểm được ghi vào bảng `core.lineage`.

Lệnh cài đặt kiểm tra các mục này sau khi chạy các file SQL và dừng khi có sai:

- Bảng, view và các cột đã khai phải có trong schema của ứng dụng. Cột của luật `range` phải có kiểu số.
- Bảng trong mục `archive` không được bảng khác tham chiếu bằng khóa ngoại `ON DELETE CASCADE`, `SET NULL` hay `SET DEFAULT`. Khi đó, dòng của bảng kia bị đổi theo mà không được lưu vào hồ.

Lõi đọc và xóa dòng bằng role `lake` của cơ sở dữ liệu. Role này bỏ qua chính sách phân quyền từng dòng để đọc đủ mọi dòng. Lệnh cài đặt chỉ cấp cho role `lake` quyền `SELECT` trên các bảng, view đã khai và quyền `DELETE` trên các bảng trong mục `archive`. Bỏ một mục khỏi bản khai thì quyền của mục đó được thu lại. View chạy với quyền của role sở hữu schema, nên view đọc được mọi dòng của các bảng trong schema. Audit log ghi việc xóa dòng với role `lake` trong cột `db_role`.
