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
| `seaweedfs.tar` | Các file trong SeaweedFS, gồm cả hồ dữ liệu |
| `env` | File `.env` cùng các mật khẩu |
| `apps.tar` | Thư mục `apps` chứa các ứng dụng đã cài đặt |
| `caddy.tar` | Chứng chỉ của Caddy, chỉ có khi thư mục `data/caddy` tồn tại |
| `manifest.json` | Phiên bản SaigonOS và thời điểm tạo gói |
| `SHA256SUMS` | Mã băm SHA-256 của từng phần |

Trong lúc chép các file của SeaweedFS, service `seaweedfs` tạm dừng. Lời gọi tải file lên hoặc tải file về trong lúc này phải chờ. Sau khi chép xong, lệnh chờ service đạt healthcheck trở lại, thường dưới 30 giây. Etcd, JWKS và cơ sở dữ liệu mã độc không nằm trong gói, vì lệnh `saigonos up` tự tạo lại. Metrics, log và dữ liệu của Grafana cũng không nằm trong gói.

Gói chứa các mật khẩu của file `.env`, nên chỉ tài khoản tạo gói đọc được. Tùy chọn `--output` chọn thư mục khác để lưu gói. Gói nên được chép sang một máy khác, để dữ liệu không mất cùng máy chủ.

Khi dùng trực tiếp Docker Compose, các lệnh sau trong thư mục làm việc lấy cơ sở dữ liệu và các file của SeaweedFS:

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

Trước khi thay dữ liệu, lệnh kiểm tra mã băm SHA-256 của từng phần. Gói bị sửa dù chỉ một byte, hoặc do phiên bản SaigonOS mới hơn bản đang cài tạo ra, đều bị từ chối. Lệnh hỏi lại trước khi thay dữ liệu. Tùy chọn `--yes` bỏ qua câu hỏi này. Lệnh thực hiện các bước sau:

1. Dừng hệ thống đang chạy.
2. Thay file `.env` và thư mục `apps` bằng bản trong gói, rồi cập nhật file `compose.yaml` và thư mục `config` như lệnh `saigonos init`.
3. Xóa các volume `postgres-data`, `seaweedfs-data` và `etcd-data`. Các volume khác được giữ nguyên.
4. Nạp cơ sở dữ liệu, các file của SeaweedFS và chứng chỉ của Caddy nếu gói có.
5. Khởi động hệ thống như lệnh `saigonos up`.

Lệnh dùng được với thư mục làm việc chưa có, ví dụ trên một máy mới vừa cài package `saigonos`. Tên của thư mục làm việc là tên project của Docker Compose. Do đó, khi máy đã có một thư mục làm việc khác, thư mục khôi phục phải có tên khác, ví dụ `~/saigonos-moi`. Máy cần còn trống dung lượng gấp khoảng hai lần dữ liệu trong gói. Sau khi khôi phục, chạy `saigonos doctor` và `saigonos audit verify` để kiểm tra. Khi máy mới có địa chỉ truy cập khác máy cũ, chạy lệnh `saigonos init` với tùy chọn `--url` rồi chạy `saigonos up`.

Khi dùng trực tiếp Docker Compose, giải nén gói và kiểm tra mã băm trước:

```bash
mkdir khoi-phuc
tar -xzf saigonos-20261124-153000.tar.gz -C khoi-phuc
(cd khoi-phuc && sha256sum -c SHA256SUMS)
```

Sau đó, trong thư mục làm việc, chép file `khoi-phuc/env` thành `.env` và giải nén `khoi-phuc/apps.tar` vào thư mục `apps`. Rồi chạy các lệnh sau, với `saigonos` ở đầu tên volume là tên của thư mục làm việc:

```bash
docker compose down
docker volume rm saigonos_postgres-data saigonos_seaweedfs-data saigonos_etcd-data
docker compose up -d --wait postgres
docker compose exec -T postgres psql --username=postgres --dbname=postgres < khoi-phuc/postgres.sql
docker compose run --rm -T backup -C /seaweedfs -xf - < khoi-phuc/seaweedfs.tar
saigonos up
```

Lệnh `psql` báo hai lỗi về role `postgres`, vì role này đã có sẵn. Hai lỗi này không ảnh hưởng tới dữ liệu.
