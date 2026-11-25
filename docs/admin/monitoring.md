<!-- SPDX-License-Identifier: Apache-2.0 -->
# Giám sát

Giám sát gồm Prometheus, Loki, Grafana và Grafana Alloy. Prometheus thu metrics của các service. Alloy đọc log của mọi container và gửi tới Loki. Grafana hiển thị metrics và log. Giám sát mặc định tắt.

## Bật giám sát

```bash
saigonos init --monitoring
saigonos up
```

Lệnh `saigonos init` thêm `monitoring` vào dòng `COMPOSE_PROFILES` của file `.env`. Do đó, lệnh `docker compose up -d --wait` cũng khởi động các service giám sát. Ở lần bật đầu tiên, Docker tải khoảng 920 MB image. Các image này chiếm khoảng 3,6 GB đĩa.

Lúc mới khởi động, các service giám sát dùng khoảng 460 MB RAM, trong đó Grafana dùng khoảng 250 MB. APISIX dùng thêm khoảng 70 MB khi Prometheus đọc metrics. Do đó, RAM của cả hệ thống tăng từ khoảng 2,6 GB lên 3,1 GB. RAM của Prometheus và Loki còn tăng dần theo lượng metrics và log.

Khi giám sát bật, lệnh `saigonos doctor` có thêm dòng của các service giám sát và dòng `Giám sát`. Dòng này kiểm tra Grafana qua API Gateway và kiểm tra Prometheus đọc được metrics của mọi target:

```text
BÌNH THƯỜNG    Giám sát        Grafana trả lời tại /grafana/, Prometheus đọc metrics của 9 target
```

Ngay sau khi khởi động, Prometheus cần khoảng 20 giây để đọc metrics của mọi target lần đầu. Do đó, lệnh `saigonos doctor` chờ tối đa 30 giây trước khi báo kết quả của dòng `Giám sát`.

## Grafana

Grafana có địa chỉ `/grafana/`, ví dụ http://localhost:9080/grafana/. Grafana không có tài khoản riêng. Người dùng đăng nhập bằng Keycloak qua client `grafana`. Chỉ tài khoản có realm role `admin` đăng nhập được và luôn phải nhập mã OTP, giống Operaton. Route `grafana` đi qua luật trang quản trị của OPA, nên giới hạn `SAIGONOS_ADMIN_NETWORKS` ở mục [Trang quản trị](access-rules.md#trang-quản-trị) cũng áp dụng cho Grafana.

Nguồn dữ liệu Prometheus và Loki được nạp từ thư mục `config/grafana/provisioning` và không sửa được trong Grafana. Grafana không gửi thống kê sử dụng, không kiểm tra bản mới, không tải plugin và không cho chia sẻ dashboard công khai. Grafana chỉ ghi log mức cảnh báo và lỗi. Nếu ghi cả mức INFO, mỗi lần bảng theo dõi làm mới, Grafana ghi hai dòng cho mỗi ô, làm khung Log ngập log của chính Grafana. Cảnh báo lặp lại của `search-manifest-watcher` trong Grafana cũng không được ghi, vì cảnh báo này không cần xử lý.

## Bảng theo dõi

Trang chủ của Grafana là bảng SaigonOS. Bảng được nạp từ file `config/grafana/dashboards/saigonos.json` và không sửa được trong Grafana. Bảng gồm:

- Năm ô số đếm trong khoảng thời gian đang xem: số request, số lỗi 4xx, số lỗi 5xx, số request bị tường lửa chặn và số request bị OPA từ chối.
- Ba ô số cho biết tài nguyên hiện tại: phần trăm CPU của máy mà các container đang dùng, tổng RAM của các container và phần trăm đã dùng của ổ chứa dữ liệu Docker.
- Bảng Service cho biết từng service đang chạy hay không theo healthcheck, kèm CPU và RAM.
- Biểu đồ số request mỗi giây theo mã trạng thái.
- Ba ô số của [hồ dữ liệu](data-lake.md): số file trong hồ, tổng dung lượng các file và số lần kiểm luật chất lượng không đạt từ khi cài đặt hệ thống. Ô cuối chuyển đỏ khi có ít nhất một lần không đạt.
- Khung Log. Ô Service và ô Tìm trong log ở đầu trang dùng để lọc log. Ví dụ, chọn `apisix` và tìm `Coraza` để xem các request bị tường lửa chặn.

## Metrics

Prometheus giữ metrics 7 ngày, tối đa 2 GB, trong volume `prometheus-data`. Prometheus đọc metrics của các nguồn sau:

| Job | Nguồn |
|---|---|
| `apisix` | Plugin `prometheus` của APISIX, đếm mọi request qua API Gateway |
| `keycloak` | Metrics có sẵn của Keycloak ở cổng quản lý 9000 |
| `centrifugo` | Metrics có sẵn của Centrifugo ở cổng nội bộ 9000 |
| `postgrest` | Admin server của PostgREST ở cổng 3001 |
| `etcd` | Metrics có sẵn của etcd |
| `loki` | Metrics của Loki |
| `services` | Service `exporter`, cho biết trạng thái, healthcheck, CPU và RAM của từng container, cùng dung lượng ổ đĩa |
| `core` | Service `core` ở cổng 9100, cho biết số file, số dòng và số lần kiểm luật chất lượng không đạt của [hồ dữ liệu](data-lake.md) |
| `prometheus` | Metrics của chính Prometheus |

Metrics `apisix_http_status` có label `denied_by`. Label này có giá trị `waf` khi tường lửa ứng dụng web chặn request và `opa` khi luật OPA từ chối request. API Gateway lấy giá trị này từ header `X-SaigonOS-Denied-By` của phản hồi. Prometheus ghi các tổng sau bằng recording rule trong file `config/prometheus/rules.yml`:

| Metrics | Ý nghĩa |
|---|---|
| `saigonos:http_requests:total` | Tổng số request qua API Gateway, trừ request tới Grafana |
| `saigonos:http_client_errors:total` | Số request nhận mã 4xx |
| `saigonos:http_server_errors:total` | Số request nhận mã 5xx |
| `saigonos:waf_denied:total` | Số request bị tường lửa ứng dụng web chặn |
| `saigonos:opa_denied:total` | Số request bị luật OPA từ chối |

Ba tổng đầu không tính request tới route `grafana`, vì chính Grafana gửi request qua API Gateway mỗi khi bảng theo dõi làm mới. Các tổng bắt đầu từ 0 mỗi khi APISIX khởi động. Để đếm trong một khoảng thời gian, dùng hàm `increase()`. Ví dụ, `increase(saigonos:waf_denied:total[1h])` là số request bị chặn trong một giờ qua.

Service `exporter` cung cấp các metrics sau. Service chạy một lần không được tính.

| Metrics | Ý nghĩa |
|---|---|
| `saigonos_service_up` | Bằng 1 khi service đang chạy và đạt healthcheck |
| `saigonos_service_memory_bytes` | RAM của container, tính như lệnh `docker stats` |
| `saigonos_service_cpu_seconds_total` | Tổng thời gian CPU container đã dùng, tính bằng giây |
| `saigonos_host_cpus` | Số nhân CPU của máy, dùng để tính phần trăm CPU |
| `saigonos_host_disk_used_bytes` | Dung lượng đã dùng của ổ chứa dữ liệu Docker, tính như lệnh `df` |
| `saigonos_host_disk_available_bytes` | Dung lượng còn trống của ổ này, tính như lệnh `df` |

Service `exporter` đọc dung lượng của hệ thống file gốc trong container của chính nó. Docker đặt hệ thống file này trên ổ chứa dữ liệu của Docker. Do đó, `exporter` không cần mount thư mục nào của máy cài đặt. Hai số này tính cả dữ liệu ngoài SaigonOS trên cùng ổ.

## Log

Alloy đọc log của mọi container trong project, kể cả service chạy một lần, rồi gửi tới Loki với label `service` và `stream`. Loki giữ log 7 ngày trong volume `loki-data`. Trong Grafana, mở Explore, chọn nguồn Loki rồi lọc theo service. Ví dụ, truy vấn sau tìm các request bị tường lửa chặn:

```
{service="apisix"} |= "Coraza"
```

## Docker socket

Alloy và `exporter` đọc Docker API qua service `socket-proxy`. Chỉ service này giữ Docker socket. Service `socket-proxy` chạy không có capability nào, với hệ thống file chỉ đọc. Service này chỉ nhận lời gọi từ Alloy và `exporter`, và chỉ cho các đường dẫn GET để liệt kê container, đọc cấu hình, log và RAM của container. Lời gọi tạo, sửa hay xóa container đều bị từ chối. Cấu hình của container gồm cả biến môi trường. Do đó, ba service này chỉ nằm trong hai mạng nội bộ `docker` và `monitoring`, không có kết nối Internet và không mở cổng nào.

## Tắt giám sát

```bash
saigonos init --no-monitoring
saigonos up
```

Lệnh `saigonos up` xóa container của các service giám sát rồi khởi động các service còn lại. Route `grafana` và client `grafana` cũng được gỡ. Metrics, log và dữ liệu của Grafana vẫn nằm trong các volume `prometheus-data`, `loki-data` và `grafana-data`. Nếu dùng trực tiếp Docker Compose, chạy lệnh sau trước lệnh `docker compose up -d --wait`:

```bash
docker compose rm --stop --force socket-proxy exporter prometheus loki-probe loki alloy grafana
```
