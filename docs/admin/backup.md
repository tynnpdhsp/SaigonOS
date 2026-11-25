<!-- SPDX-License-Identifier: Apache-2.0 -->
# Sao lưu và khôi phục

## Sao lưu

Lệnh sau tạo một gói sao lưu trong thư mục `backups` của thư mục làm việc. Hệ thống phải đang chạy.

```bash
saigonos backup
```

Gói có tên dạng `saigonos-20261124-153000.tar.gz` và gồm các phần sau:

| Phần | Nội dung |
|---|---|
| `postgres.sql` | Toàn bộ cơ sở dữ liệu, tạo bằng `pg_dumpall` trong lúc hệ thống vẫn chạy |
| `seaweedfs.tar` | Các file trong SeaweedFS |
| `env` | File `.env` cùng các mật khẩu |
| `apps.tar` | Thư mục `apps` chứa các ứng dụng đã cài đặt |
| `caddy.tar` | Chứng chỉ của Caddy, chỉ có khi thư mục `data/caddy` tồn tại |
| `manifest.json` | Phiên bản SaigonOS và thời điểm tạo gói |
| `SHA256SUMS` | Mã băm SHA-256 của từng phần |

Trong lúc chép các file của SeaweedFS, service `seaweedfs` tạm dừng. Do đó, lời gọi tải file lên hoặc tải file về phải chờ tới khi chép xong. Sau đó, lệnh chờ service `seaweedfs` đạt healthcheck trở lại. Việc chờ này thường mất dưới 30 giây, vì Docker chỉ báo service đạt healthcheck sau lần kiểm tra kế tiếp. Etcd, JWKS và cơ sở dữ liệu mã độc không nằm trong gói, vì lệnh `saigonos up` tự tạo lại. Metrics, log và dữ liệu của Grafana cũng không nằm trong gói.

Gói chứa các mật khẩu của file `.env`, nên chỉ tài khoản tạo gói đọc được. Tùy chọn `--output` chọn thư mục khác để lưu gói. Nên chép gói sang một máy khác, để dữ liệu không mất cùng máy chủ.

Nếu dùng trực tiếp Docker Compose, chạy các lệnh sau trong thư mục làm việc để lấy cơ sở dữ liệu và các file của SeaweedFS:

```bash
docker compose exec -T postgres pg_dumpall --username=postgres --clean --if-exists > postgres.sql
docker compose pause seaweedfs
docker compose run --rm -T backup -C /seaweedfs -cf - . > seaweedfs.tar
docker compose unpause seaweedfs
```

## Khôi phục

Lệnh sau khôi phục hệ thống từ một gói sao lưu:

```bash
saigonos restore ~/saigonos/backups/saigonos-20261124-153000.tar.gz
```

Trước khi thay dữ liệu, lệnh kiểm tra phần đầu gzip, mã CRC và mã băm SHA-256 của từng phần. Gói bị sửa dù chỉ một byte sẽ bị từ chối. Gói do phiên bản SaigonOS mới hơn bản đang cài tạo ra cũng bị từ chối. Lệnh hỏi lại trước khi thay dữ liệu. Tùy chọn `--yes` bỏ qua câu hỏi này.

Khi khôi phục, lệnh làm các việc sau:

1. Dừng hệ thống đang chạy.
2. Thay file `.env` và thư mục `apps` bằng bản trong gói, rồi cập nhật file `compose.yaml` và thư mục `config` như lệnh `saigonos init`.
3. Xóa các volume `postgres-data`, `seaweedfs-data` và `etcd-data`. Các volume khác được giữ nguyên, ví dụ cơ sở dữ liệu mã độc và dữ liệu giám sát.
4. Khởi động PostgreSQL rồi nạp cơ sở dữ liệu từ gói. Sau đó nạp các file của SeaweedFS, và chứng chỉ của Caddy nếu gói có.
5. Khởi động hệ thống như lệnh `saigonos up`.

Lệnh dùng được với thư mục làm việc chưa có, ví dụ trên một máy mới vừa cài package `saigonos`. Tên project của Docker Compose là tên của thư mục làm việc. Lệnh khôi phục xóa các volume ở bước 3 của project này. Do đó, nếu máy đã có một thư mục làm việc khác, thư mục khôi phục phải có tên khác với thư mục đó, ví dụ `~/saigonos-moi`. Gói được giải nén tạm trong thư mục làm việc, nên máy cần còn trống dung lượng gấp khoảng hai lần dữ liệu trong gói. Sau khi khôi phục, chạy `saigonos doctor` và `saigonos audit verify` để kiểm tra. Nếu máy mới có địa chỉ truy cập khác máy cũ, chạy lệnh `saigonos init` với tùy chọn `--url`, rồi chạy `saigonos up`.

Nếu dùng trực tiếp Docker Compose, trước hết giải nén gói và kiểm tra mã băm:

```bash
mkdir khoi-phuc
tar -xzf saigonos-20261124-153000.tar.gz -C khoi-phuc
(cd khoi-phuc && sha256sum -c SHA256SUMS)
```

Sau đó, trong thư mục làm việc, chép file `khoi-phuc/env` thành `.env` và giải nén `khoi-phuc/apps.tar` vào thư mục `apps`. Rồi chạy các lệnh sau. Nếu thư mục làm việc không tên là `saigonos`, thay `saigonos` ở đầu tên volume bằng tên thư mục làm việc:

```bash
docker compose down
docker volume rm saigonos_postgres-data saigonos_seaweedfs-data saigonos_etcd-data
docker compose up -d --wait postgres
docker compose exec -T postgres psql --username=postgres --dbname=postgres < khoi-phuc/postgres.sql
docker compose run --rm -T backup -C /seaweedfs -xf - < khoi-phuc/seaweedfs.tar
saigonos up
```

Lệnh `psql` báo hai lỗi về role `postgres`, vì role này đã có sẵn. Hai lỗi này không ảnh hưởng tới dữ liệu.
