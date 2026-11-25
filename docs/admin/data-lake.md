<!-- SPDX-License-Identifier: Apache-2.0 -->
# Hồ dữ liệu

Hồ dữ liệu giữ dữ liệu lịch sử của các ứng dụng dưới dạng file Parquet trong bucket `lake` của SeaweedFS. Dữ liệu vào hồ bằng hai việc lưu trữ và chốt số liệu, như mục [Lưu trữ và chốt số liệu của ứng dụng](../apps/archive.md). Service `core` ghi và đọc file bằng DuckDB. Bucket `lake` chỉ đọc được bằng khóa S3 của service `core`. Do đó, người dùng của ứng dụng không đọc được file trong hồ. Admin đọc hồ bằng các lệnh ở mục này trên máy cài đặt.

Tháng của dữ liệu tính theo múi giờ `Asia/Ho_Chi_Minh`. Để dùng múi giờ khác, thêm dòng sau vào file `.env` rồi chạy `saigonos up`:

```
SAIGONOS_TIMEZONE=Asia/Bangkok
```

## File trong hồ

| Việc | Đường dẫn trong bucket `lake` |
|---|---|
| Lưu trữ | `archive/<tên ứng dụng>/<bảng>/<năm>/<tháng>/<số>.parquet` |
| Chốt số liệu | `snapshots/<tên ứng dụng>/<view>/<năm>-<tháng>.parquet` |

Mỗi file chỉ được ghi một lần. Một tháng của bảng có thể có nhiều file lưu trữ, mỗi lần chạy một file. Giá trị của cột được giữ đúng kiểu, ví dụ số thập phân, ngày giờ có múi giờ và JSON. Mảng và kiểu tổ hợp được lưu dạng JSON. Kiểu `interval` và các kiểu khác được lưu dạng chuỗi.

Lệnh `saigonos backup` sao lưu cả hồ dữ liệu, vì hồ nằm trong SeaweedFS.

## Phả hệ

Bảng `core.lineage` ghi phả hệ của từng file và kết quả của từng lần kiểm luật chất lượng. Bảng chỉ cho thêm dòng, không cho sửa hay xóa. Mỗi dòng mới cũng được ghi vào audit log. Các cột của bảng như sau:

| Cột | Ý nghĩa |
|---|---|
| `kind` | `check` cho một lần kiểm luật chất lượng, `file` cho một file trong hồ |
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

Lệnh `saigonos lake query "SQL"` chạy một câu truy vấn SQL của DuckDB trên hồ. Mỗi bảng trong mục `archive` là một view cùng tên, ví dụ `nghi_phep.don`. Mỗi mục `snapshots` là một view trong catalog `snapshots`, ví dụ `snapshots.nghi_phep.chot_don`. Bảng `lineage` chứa các dòng của `core.lineage`. Ví dụ:

```bash
saigonos lake query "SELECT date_trunc('month', tao_luc) AS thang, count(*) FROM nghi_phep.don GROUP BY 1 ORDER BY 1"
saigonos lake query --csv "SELECT * FROM snapshots.nghi_phep.chot_don"
```

Trước khi đọc, lệnh tải các file vào một thư mục tạm của container `core` và so mã băm của từng file với phả hệ. Khi một file không khớp, lệnh dừng mà không trả kết quả. Câu truy vấn không đọc được file khác trên máy chủ, không tải được extension và không đổi được các thiết lập này. DuckDB dùng tối đa 512 MB RAM cho mỗi lệnh. Lệnh tương đương bằng Docker Compose như sau:

```bash
docker compose exec -T core python -m saigonos_core.lake query "SELECT count(*) FROM nghi_phep.don"
```

## Kiểm tra mã băm

```bash
saigonos lake verify
```

Lệnh đọc lại mọi file trong hồ và so mã băm SHA-256 với bảng `core.lineage`. Khi một file đã bị sửa dù chỉ một byte, hoặc đã bị xóa, lệnh chỉ ra file đó và kết thúc với mã thoát 1. Ví dụ:

```text
Hồ dữ liệu có 6 file. Mã băm của mọi file khớp với phả hệ.
```

## Hẹn giờ

Service `core` chạy việc của hồ lần đầu sau khi khởi động 1 phút, rồi mỗi giờ một lần. Mỗi lần chạy là một tiến trình riêng, nên RAM của DuckDB được trả lại khi chạy xong. Thông báo của việc này nằm trong log của service `core`. Hai lần chạy không chồng lên nhau. Khi hẹn giờ đang chạy, lệnh `saigonos lake run` chờ lần chạy đó xong rồi mới chạy. Lệnh kết thúc với mã thoát 1 khi dữ liệu không đạt luật chất lượng hoặc khi có lỗi.

Service `core` trả metrics của hồ ở cổng 9100 bên trong mạng Docker. Khi bật [giám sát](monitoring.md), Prometheus đọc các metrics sau. Bảng SaigonOS của Grafana có ba ô số lấy từ các metrics này.

| Metrics | Ý nghĩa |
|---|---|
| `saigonos_lake_files` | Số file trong hồ. Label `app` là tên ứng dụng, label `type` là `archive` hoặc `snapshot` |
| `saigonos_lake_rows` | Số dòng trong các file của hồ |
| `saigonos_lake_bytes` | Dung lượng các file của hồ, tính bằng byte |
| `saigonos_lake_failed_checks_total` | Số lần kiểm luật chất lượng không đạt từ khi cài đặt hệ thống |
