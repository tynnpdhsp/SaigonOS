<!-- SPDX-License-Identifier: Apache-2.0 -->
# Hồ dữ liệu

Hồ dữ liệu giữ dữ liệu lịch sử của các ứng dụng dưới dạng file Parquet trong bucket `lake` của SeaweedFS. Dữ liệu vào hồ bằng hai việc lưu trữ và chốt số liệu, do ứng dụng khai trong bản khai báo như ở trang [Lưu trữ và chốt số liệu](../apps/archive.md). Chỉ service `core` đọc được bucket `lake`. Người quản trị đọc hồ bằng các lệnh ở trang này.

Tháng của dữ liệu được tính theo [múi giờ của hệ thống](configuration.md#múi-giờ), mặc định là `Asia/Ho_Chi_Minh`.

## File trong hồ

| Việc | Đường dẫn trong bucket `lake` |
|---|---|
| Lưu trữ | `archive/<tên ứng dụng>/<bảng>/<năm>/<tháng>/<số>.parquet` |
| Chốt số liệu | `snapshots/<tên ứng dụng>/<view>/<năm>-<tháng>.parquet` |

Mỗi file chỉ được ghi một lần. Giá trị của cột giữ đúng kiểu, ví dụ số thập phân, ngày giờ có múi giờ và JSON. Lệnh `saigonos backup` sao lưu cả hồ dữ liệu.

## Phả hệ

Bảng `core.lineage` ghi phả hệ của từng file và kết quả của từng lần kiểm tra luật chất lượng. Bảng chỉ cho thêm dòng. Mỗi dòng mới cũng được ghi vào audit log. Các cột của bảng như sau:

| Cột | Ý nghĩa |
|---|---|
| `kind` | `check` cho một lần kiểm tra luật chất lượng, `file` cho một file trong hồ |
| `job` | `archive` cho lưu trữ, `snapshot` cho chốt số liệu |
| `started_by` | `timer` khi hẹn giờ của service `core` chạy, `command` khi chạy bằng lệnh |
| `app`, `source` | Tên ứng dụng và bảng hoặc view nguồn, dạng `<schema>.<tên>` |
| `period` | Tháng của dữ liệu, dạng `YYYY-MM` |
| `time_from`, `time_to` | Khoảng thời gian của các dòng, tính cả `time_from` và không tính `time_to` |
| `rows` | Số dòng đã kiểm, hoặc số dòng trong file |
| `passed`, `results` | Kết quả chung và kết quả của từng luật, ở dòng `check` |
| `check_id` | Dòng `check` đã đạt trước khi file được ghi, ở dòng `file` |
| `file`, `size`, `sha256` | Đường dẫn trong bucket, dung lượng và mã băm SHA-256 của file |
| `created_at` | Lúc ghi dòng |

Ví dụ, lệnh sau xem các file của hồ:

```bash
docker compose exec postgres psql -U postgres -d saigonos -c "SELECT id, job, source, period, rows, file FROM core.lineage WHERE kind = 'file' ORDER BY id"
```

## Truy vấn hồ

Lệnh `saigonos lake query "SQL"` chạy một câu truy vấn SQL của DuckDB trên hồ. Mỗi bảng trong mục `archive` là một view cùng tên, ví dụ `phong_may.don`. Mỗi mục `snapshots` là một view trong catalog `snapshots`, ví dụ `snapshots.phong_may.lich`. Bảng `lineage` chứa các dòng của `core.lineage`. Ví dụ:

```bash
saigonos lake query "SELECT date_trunc('month', bat_dau) AS thang, count(*) FROM phong_may.don GROUP BY 1 ORDER BY 1"
saigonos lake query --csv "SELECT * FROM snapshots.phong_may.lich"
```

Trước khi đọc, lệnh so mã băm của từng file với phả hệ. Khi một file không khớp, lệnh dừng mà không trả kết quả. Câu truy vấn không đọc được file khác trên máy chủ và dùng tối đa 512 MB RAM.

## Kiểm tra mã băm

```bash
saigonos lake verify
```

Lệnh đọc lại mọi file trong hồ và so mã băm SHA-256 với bảng `core.lineage`. Khi một file đã bị sửa dù chỉ một byte, hoặc đã bị xóa, lệnh chỉ ra file đó và kết thúc với mã thoát 1. Khi mọi file đều khớp, lệnh in ra kết quả như sau:

```text
Hồ dữ liệu có 6 file. Mã băm của mọi file khớp với phả hệ.
```

## Hẹn giờ

Service `core` chạy việc lưu trữ và chốt số liệu một phút sau khi khởi động, rồi mỗi giờ một lần. Lệnh `saigonos lake run` chạy ngay hai việc này. Khi hẹn giờ đang chạy, lệnh chờ lần chạy đó xong rồi mới chạy. Lệnh kết thúc với mã thoát 1 khi dữ liệu không đạt luật chất lượng hoặc khi có lỗi. Các metrics của hồ được trình bày ở trang [Giám sát](monitoring.md#metrics).
