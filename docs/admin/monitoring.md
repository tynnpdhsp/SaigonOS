<!-- SPDX-License-Identifier: Apache-2.0 -->
# Giám sát

Giám sát gồm Prometheus, Loki, Grafana, Grafana Alloy, service `exporter` và service `socket-proxy`. Prometheus thu metrics của các service. Service `exporter` cung cấp metrics về trạng thái, RAM và CPU của các container. Alloy đọc log của mọi container rồi gửi tới Loki. Grafana hiển thị metrics và log. Giám sát mặc định tắt.

## Bật giám sát

```bash
saigonos init --monitoring
saigonos up
```

Ở lần bật đầu tiên, Docker tải khoảng 920 MB image. Các image này chiếm khoảng 3,6 GB đĩa. RAM của cả hệ thống tăng từ khoảng 2,6 GB lên 3,1 GB, rồi tăng dần theo lượng metrics và log.

Khi giám sát bật, lệnh `saigonos doctor` có thêm dòng của các service giám sát và dòng sau:

```text
BÌNH THƯỜNG    Giám sát        Grafana trả lời tại /grafana/, Prometheus đọc metrics của 9 target
```

Ngay sau khi khởi động, Prometheus cần khoảng 20 giây để đọc metrics lần đầu. Do đó, lệnh `saigonos doctor` chờ tối đa 30 giây ở dòng này.

## Grafana

Grafana có địa chỉ `/grafana/`, ví dụ http://localhost:9080/grafana/. Grafana không có tài khoản riêng. Chỉ tài khoản có realm role `admin` đăng nhập được qua Keycloak và luôn phải nhập mã OTP. Giới hạn dải mạng ở trang [Luật truy cập](access-rules.md#trang-quản-trị) cũng áp dụng cho Grafana. Nguồn dữ liệu và bảng theo dõi được nạp từ thư mục [`config/grafana`](https://github.com/tynnpdhsp/SaigonOS/tree/main/src/saigonos/stack/config/grafana) và không sửa được trong Grafana.

## Bảng theo dõi

Trang chủ của Grafana là bảng SaigonOS. Bảng gồm các phần sau:

- Số request, số lỗi 4xx, số lỗi 5xx, số request bị tường lửa chặn và số request bị OPA từ chối trong khoảng thời gian đang xem.
- Phần trăm CPU, tổng RAM của các container và phần trăm đã dùng của ổ chứa dữ liệu Docker.
- Trạng thái, CPU và RAM của từng service.
- Biểu đồ số request mỗi giây theo mã trạng thái.
- Số file và dung lượng của [hồ dữ liệu](data-lake.md), cùng số lần kiểm luật chất lượng không đạt. Ô cuối chuyển đỏ khi có ít nhất một lần không đạt.
- Khung Log, lọc được theo service và theo chữ cần tìm. Ví dụ, chọn `apisix` và tìm `Coraza` để xem các request bị tường lửa chặn.

## Metrics

Prometheus giữ metrics 7 ngày, tối đa 2 GB. Ngoài metrics có sẵn của APISIX, Keycloak, Centrifugo, PostgREST, etcd và Loki, hệ thống có các metrics sau:

| Metrics | Ý nghĩa |
|---|---|
| `saigonos:http_requests:total` | Tổng số request qua API Gateway, trừ request tới Grafana |
| `saigonos:http_client_errors:total` | Số request nhận mã 4xx |
| `saigonos:http_server_errors:total` | Số request nhận mã 5xx |
| `saigonos:waf_denied:total` | Số request bị tường lửa ứng dụng web chặn |
| `saigonos:opa_denied:total` | Số request bị luật OPA từ chối |
| `saigonos_service_up` | Bằng 1 khi service đang chạy và đạt healthcheck |
| `saigonos_service_memory_bytes` | RAM của container, tính như lệnh `docker stats` |
| `saigonos_service_cpu_seconds_total` | Tổng thời gian CPU mà container đã dùng, tính bằng giây |
| `saigonos_host_disk_used_bytes` | Dung lượng đã dùng của ổ chứa dữ liệu Docker |
| `saigonos_host_disk_available_bytes` | Dung lượng còn trống của ổ chứa dữ liệu Docker |
| `saigonos_lake_files` | Số file trong hồ dữ liệu. Label `app` là tên ứng dụng, label `type` là `archive` hoặc `snapshot` |
| `saigonos_lake_rows` | Số dòng trong các file của hồ dữ liệu |
| `saigonos_lake_bytes` | Dung lượng các file của hồ dữ liệu, tính bằng byte |
| `saigonos_lake_failed_checks_total` | Số lần kiểm luật chất lượng không đạt từ khi cài đặt hệ thống |

Năm tổng đầu bắt đầu từ 0 mỗi khi APISIX khởi động. Để đếm trong một khoảng thời gian, dùng hàm `increase()`. Ví dụ, `increase(saigonos:waf_denied:total[1h])` là số request bị chặn trong một giờ qua.

## Log

Loki giữ log 7 ngày. Trong Grafana, mở Explore, chọn nguồn Loki rồi lọc theo label `service`. Ví dụ, truy vấn sau tìm các request bị tường lửa chặn:

```
{service="apisix"} |= "Coraza"
```

Alloy và service `exporter` đọc Docker API qua service `socket-proxy`. Chỉ service này giữ Docker socket và chỉ cho các lời gọi GET để đọc thông tin, log và RAM của container. Ba service này không có kết nối Internet và không mở cổng nào.

## Tắt giám sát

```bash
saigonos init --no-monitoring
saigonos up
```

Metrics, log và dữ liệu của Grafana vẫn nằm trong các volume `prometheus-data`, `loki-data` và `grafana-data`. Khi dùng trực tiếp Docker Compose, chạy lệnh sau trước lệnh `docker compose up -d --wait`:

```bash
docker compose rm --stop --force socket-proxy exporter prometheus loki-probe loki alloy grafana
```
