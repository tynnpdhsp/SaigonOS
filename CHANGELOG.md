<!-- SPDX-License-Identifier: Apache-2.0 -->
# Nhật ký thay đổi

File này ghi lại các thay đổi đáng chú ý của SaigonOS. Cách ghi tuân theo [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Số phiên bản tuân theo [Semantic Versioning](https://semver.org/lang/vi/).

Mục "Chưa phát hành" ghi các thay đổi đã có trên `main` nhưng chưa có trong release nào.

## [Chưa phát hành]

## [1.2.0] - 2026-11-28

### Thay đổi

- Mỗi lời gọi tới REST API của dữ liệu, tức `/api/` và `/apps/<tên ứng dụng>/api/`, chạy tối đa 15 giây. Khi quá thời gian này, PostgreSQL dừng truy vấn và lời gọi nhận mã 500 với mã lỗi `57014`.

- Sơ đồ kiến trúc ghi việc của từng mũi tên thay cho tên giao thức SQL, S3 và REST. Ví dụ, mũi tên từ Centrifugo tới PostgreSQL ghi "lấy thông báo chờ gửi", vì Centrifugo chỉ lấy thông báo ra rồi xóa.

### Sửa

- Keycloak mở được tới 100 kết nối, bằng số kết nối tối đa của PostgreSQL. Do đó, lúc nhiều người đăng nhập cùng lúc, các service khác có thể không kết nối được PostgreSQL. Keycloak nay mở tối đa 20 kết nối. Mỗi role đăng nhập của các service có giới hạn số kết nối riêng, nên service mở quá phần của mình không làm service khác mất kết nối.

## [1.1.0] - 2026-11-28

### Thêm

- README có link tới trang web https://www.saigonos.org. Trang có tài liệu và tin tức về các bản phát hành.
- Service chạy một lần `zoneinfo` chép dữ liệu múi giờ từ image của PostgreSQL vào volume `zoneinfo` cho APISIX, PostgREST, SeaweedFS, Centrifugo và Socket Proxy, vì image của các service này không có dữ liệu múi giờ. Khi tên múi giờ không hợp lệ, service báo lỗi và lệnh `saigonos up` dừng trước khi khởi động PostgreSQL.

### Thay đổi

- Mọi service chạy theo múi giờ trong biến `SAIGONOS_TIMEZONE` của file `.env`, mặc định là `Asia/Ho_Chi_Minh`. Trước đây, các service chạy theo giờ UTC và biến này chỉ dùng cho hồ dữ liệu. Giờ trong log, ngày giờ mà PostgreSQL trả về và hàm `current_date` đều theo múi giờ này. Biểu thức cron và ngày giờ không ghi múi giờ trong hẹn giờ của Operaton cũng được tính theo múi giờ này. Audit log vẫn ghi ngày giờ trong `old_row` và `new_row` theo giờ UTC.
- Biến kiểu ngày giờ được truyền cho hàm của bước máy làm theo múi giờ của hệ thống, ví dụ `2026-12-01T07:00:00.000+0700`.
- Khi nâng cấp từ phiên bản 1.0.1 trở về trước, hạn của việc, hẹn giờ và lịch sử mà Operaton đã lưu bị đọc sớm hơn 7 giờ, vì các phiên bản này chạy Operaton theo giờ UTC. Nên hoàn tất các quy trình đang chạy trước khi nâng cấp.

## [1.0.1] - 2026-11-26

### Thêm

- Logo của SaigonOS trong thư mục `docs/assets/logo`, gồm logo và logo kèm chữ ở dạng SVG và PNG nhiều kích thước, cùng favicon, icon cho iPhone và ảnh xem trước khi chia sẻ link.
- Ứng dụng mẫu hiện logo của SaigonOS ở đầu menu và dùng logo làm favicon.
- Đầu README có logo kèm chữ đặt trên thẻ trắng, file `docs/assets/logo/saigonos-logo-text-card.svg`. Thẻ trắng giúp logo đọc rõ ở cả giao diện sáng và giao diện tối của GitHub.
- Sơ đồ kiến trúc trong README, file `docs/assets/architecture.svg`. Sơ đồ có mọi service chạy liên tục của lõi và chiều gửi yêu cầu giữa các service.

### Thay đổi

- Giao diện của ứng dụng mẫu dùng hai màu của logo. Trạng thái "Đã duyệt" có màu xanh lá, trạng thái "Sẵn sàng" có màu xanh đậm.

### Sửa

- Bảng Thành phần trong README ghi đủ các service có trên sơ đồ kiến trúc, thêm Caddy, etcd, Core API, Alloy, Exporter và Socket Proxy. Dòng Centrifugo không còn ghi việc gửi thông báo qua Telegram và email, vì Core API mới là service gửi các thông báo này.

## [1.0.0] - 2026-11-25

### Thêm

- Ứng dụng mẫu `examples/phong-may` quản lý việc đặt phòng máy của một trường học. Ứng dụng có bốn role, luật truy cập riêng, bảng có Row-Level Security và audit log, quy trình đặt phòng có hẹn giờ nhắc duyệt và một trang giao diện đăng nhập bằng PKCE.
- Trang `docs/first-app.md` giải thích từng file của ứng dụng mẫu, cách cài đặt và cách gán role cho người dùng.
- Trang `docs/reference/cli.md` liệt kê các lệnh của `saigonos`.

### Thay đổi

- Tài liệu được chia thành các trang trong thư mục `docs`, mỗi trang một chủ đề, theo các nhóm cài đặt, quản trị, viết ứng dụng, tham khảo và phát triển lõi. README chỉ còn giới thiệu, lệnh cài đặt và link tới tài liệu. CONTRIBUTING chỉ còn cách đóng góp.
- Ví dụ trong tài liệu dùng ứng dụng mẫu đặt phòng máy.

### Sửa

- Tường lửa ứng dụng web không còn chặn trang của ứng dụng ngay sau khi đăng nhập khi địa chỉ truy cập là địa chỉ IP. Các luật của CRS bỏ qua tham số `iss` mà Keycloak gửi về trang khi giá trị đúng bằng issuer của realm `saigonos`. Giá trị khác vẫn được kiểm tra.
- Lệnh `saigonos doctor` không còn báo lỗi ứng dụng có luật truy cập đòi đăng nhập ở mọi lời gọi, ví dụ ứng dụng mẫu. Lời gọi không có access token tới API của ứng dụng đó nhận mã 401 hoặc 403 với mã `SGN03`, và lệnh coi đây là trạng thái bình thường.

## [0.12.0] - 2026-11-25

### Thêm

- Mục `archive` trong bản khai báo ứng dụng liệt kê các bảng có dòng cũ được chuyển xuống hồ dữ liệu, kèm cột thời gian và số ngày giữ ở bảng. Mục `snapshots` liệt kê các view hoặc bảng được chốt số liệu theo tháng. Mỗi mục có luật chất lượng `not_null`, `unique` và `range`.
- Hồ dữ liệu gồm các file Parquet trong bucket `lake` của SeaweedFS. Service `core` ghi và đọc file bằng DuckDB 2.0.1. Mỗi giờ, service `core` chốt số liệu các tháng đã hết rồi chuyển dòng cũ hơn hạn xuống hồ, mỗi tháng một file. Dòng chỉ bị xóa khỏi bảng khi file đọc lại đúng mã băm và số dòng khớp. Lệnh `saigonos lake run` chạy ngay việc này.
- Luật chất lượng được kiểm tra bằng SQL trước khi chốt số liệu và trước khi chuyển dòng cũ. Khi không đạt, tháng không được chốt và dòng cũ ở lại bảng. Admin nhận tin qua kênh `role:admin` và nhóm Telegram, chỉ ra luật và các dòng vi phạm.
- Bảng `core.lineage` ghi phả hệ của từng file và kết quả của từng lần kiểm tra luật chất lượng. Bảng chỉ cho thêm dòng, mỗi dòng mới được ghi vào audit log.
- Lệnh `saigonos lake query` chạy câu truy vấn SQL của DuckDB trên hồ sau khi kiểm tra mã băm của từng file. Câu truy vấn không đọc được file khác trên máy chủ và không tải được extension. Lệnh `saigonos lake verify` tính lại mã băm của mọi file và chỉ ra file đã bị sửa.
- Role `lake` của cơ sở dữ liệu đọc và xóa dòng cho hồ dữ liệu. Lệnh cài đặt chỉ cấp quyền cho role này trên các bảng, view đã khai và thu lại quyền khi một mục bị bỏ khỏi bản khai báo.
- Service `core` trả metrics `saigonos_lake_files`, `saigonos_lake_rows`, `saigonos_lake_bytes` và `saigonos_lake_failed_checks_total` ở cổng 9100 bên trong mạng Docker. Prometheus đọc thêm target `core`.
- Bảng SaigonOS của Grafana có thêm ba ô số của hồ dữ liệu: số file, dung lượng và số lần kiểm tra luật chất lượng không đạt.
- Giá trị `SAIGONOS_TIMEZONE` trong file `.env` đặt múi giờ để tính tháng của hồ dữ liệu, mặc định là `Asia/Ho_Chi_Minh`.

### Thay đổi

- Grafana chỉ ghi log mức cảnh báo và lỗi, và bỏ cảnh báo lặp lại của `search-manifest-watcher`. Trước đây, mỗi lần bảng theo dõi làm mới, Grafana ghi hai dòng INFO cho mỗi ô, khoảng 120 dòng mỗi phút, làm khung Log ngập log của chính Grafana.
- Tên ứng dụng không được trùng `lake`, `main`, `memory`, `snapshots`, `system` và `temp`, vì lõi và DuckDB dùng các tên này.

## [0.11.0] - 2026-11-24

### Thêm

- Cấu hình tìm kiếm toàn văn tiếng Việt `core.vietnamese` trong PostgreSQL. Cấu hình này bỏ dấu bằng extension `unaccent` và không phân biệt chữ hoa, chữ thường. Hai hàm `core.search_vector` và `core.search_query` dùng cấu hình này, mọi role đều gọi được.
- Lời gọi `GET /core/files?q=` của service `core` tìm file theo tên, chỉ trong các file người gọi được đọc. Kết quả xếp theo độ khớp.
- Mục `search` trong bản khai báo ứng dụng liệt kê các bảng và cột cần tìm kiếm toàn văn. Khi cài đặt, lõi tạo index GIN và hàm `search_<bảng>` chạy với role `<schema>_user`. Kết quả xếp theo độ khớp và vẫn theo phân quyền từng dòng. Bỏ bảng khỏi bản khai báo thì lõi gỡ index và hàm của bảng đó.

## [0.10.0] - 2026-11-24

### Thêm

- Lệnh `saigonos backup` tạo gói sao lưu gồm toàn bộ cơ sở dữ liệu, các file trong SeaweedFS, file `.env`, thư mục `apps` và chứng chỉ của Caddy nếu có, kèm mã băm SHA-256 của từng phần. Gói có quyền 600 vì chứa mật khẩu. Service `seaweedfs` tạm dừng trong lúc chép file, rồi lệnh chờ service này đạt healthcheck trở lại.
- Lệnh `saigonos restore` khôi phục hệ thống từ gói sao lưu, kể cả vào thư mục làm việc chưa có. Lệnh kiểm tra phần đầu gzip, mã CRC và mã băm của từng phần, từ chối gói đã bị sửa hoặc gói của phiên bản mới hơn, và hỏi lại trước khi thay dữ liệu. Lệnh chỉ xóa các volume `postgres-data`, `seaweedfs-data` và `etcd-data`.
- Service một lần `backup` chép volume của SeaweedFS. Service này không có mạng và chỉ chạy khi được gọi.

## [0.9.0] - 2026-11-24

### Thêm

- Giám sát bằng Prometheus 3.16.0, Loki 3.7.10, Grafana 13.3.1 và Grafana Alloy 1.22.0 trong profile `monitoring`. Lệnh `saigonos init --monitoring` bật và `--no-monitoring` tắt giám sát. Các service này không mở cổng nào ra máy cài đặt, không gửi thống kê và không kiểm tra bản mới.
- Service `socket-proxy` là service duy nhất giữ Docker socket. Service này chỉ cho Alloy và `exporter` gọi các đường dẫn GET cần thiết của Docker API.
- Service một lần `loki-probe` chép lệnh `busybox` tĩnh vào volume `probe` để Loki có healthcheck, vì image của Loki không có shell.
- Bảng giấy phép cho phép AGPL-3.0-only cho phần mềm chạy trong container, vì Grafana và Loki dùng giấy phép này.
- Plugin `prometheus` của APISIX đếm mọi request qua API Gateway. Metrics chỉ mở ở cổng 9091 bên trong mạng Docker. Label `denied_by` có giá trị `waf` hoặc `opa` cho request bị tường lửa chặn hoặc bị luật OPA từ chối.
- Service `exporter` chạy bằng image của service `core`. Service này đọc trạng thái, healthcheck, CPU và RAM của từng container qua `socket-proxy`, cùng dung lượng ổ chứa dữ liệu Docker. Service trả metrics `saigonos_service_up`, `saigonos_service_memory_bytes`, `saigonos_service_cpu_seconds_total`, `saigonos_host_cpus`, `saigonos_host_disk_used_bytes` và `saigonos_host_disk_available_bytes` cho Prometheus. Service một lần không được tính.
- Prometheus giữ metrics 7 ngày và đọc metrics của APISIX, Keycloak, Centrifugo, PostgREST, etcd, Loki và `exporter`. Recording rule ghi tổng số request và số lỗi 4xx, 5xx, không tính request tới Grafana, cùng số request bị tường lửa chặn và số request bị OPA từ chối.
- Keycloak bật metrics ở cổng quản lý 9000. Centrifugo bật metrics ở cổng nội bộ 9000. Admin server của PostgREST lắng nghe trên mọi địa chỉ của container để Prometheus đọc `/metrics`. Các cổng này không mở ra máy cài đặt, trừ cổng 9000 của Centrifugo vốn đã mở trên `127.0.0.1`.
- Alloy đọc log của mọi container trong project qua `socket-proxy`, kể cả service một lần đã chạy xong, rồi gửi tới Loki với label `service` và `stream`. Loki giữ log 7 ngày.
- Grafana có địa chỉ `/grafana/` qua API Gateway. Route `grafana` đi qua luật trang quản trị của OPA như Operaton. Grafana chỉ cho đăng nhập bằng Keycloak qua client `grafana`, dùng luồng đăng nhập chỉ cho realm role `admin` và bắt buộc OTP. Grafana không có tài khoản cục bộ.
- Route có label `saigonos.profile` chỉ được service `routes` nạp khi profile đó được bật và được gỡ khi profile bị tắt. Service `realm` cũng tạo client `grafana` khi bật giám sát và xóa client này khi tắt.
- Lệnh `saigonos doctor` có thêm dòng `Giám sát` khi giám sát được bật. Dòng này kiểm tra Grafana qua API Gateway và các target của Prometheus. Ngay sau khi khởi động, lệnh chờ tối đa 30 giây để Prometheus đọc metrics của mọi target lần đầu.
- Lời gọi bị tường lửa chặn có thêm header `X-SaigonOS-Denied-By: waf`. Lời gọi bị luật OPA từ chối có thêm header `X-SaigonOS-Denied-By: opa`.
- Bảng theo dõi SaigonOS là trang chủ của Grafana, nạp từ file. Bảng có số request, số lỗi, số request bị tường lửa chặn, số request bị OPA từ chối, CPU, RAM, phần trăm đã dùng của ổ cứng, trạng thái của từng service, biểu đồ request theo mã trạng thái và khung log lọc theo service.
- README có mục Giám sát.

### Thay đổi

- Tên `grafana` được dành riêng cho lõi, nên ứng dụng không dùng được tên này.
- Bước 3 của mục Cài đặt trong README dùng lệnh `saigonos up`, giống lệnh mà `saigonos init` gợi ý.
- README nêu mức RAM nên có là 5 GB khi bật giám sát. Lúc mới khởi động, giám sát làm RAM của hệ thống tăng từ khoảng 2,6 GB lên 3,1 GB và cần thêm khoảng 3,6 GB dung lượng ổ cứng cho image.

### Sửa

- Tường lửa ứng dụng web không còn chặn lời gọi có header `Host` là địa chỉ IP. Trước đây luật 920350 của CRS đẩy tổng điểm bất thường lên 6, vượt ngưỡng 5, nên lời gọi tới `/api`, `/apps` và `/core` qua địa chỉ IP trong mạng nội bộ nhận mã 403. SaigonOS tắt luật 920350.

## [0.8.1] - 2026-11-23

### Sửa

- Claim `amr` của access token giữ các bước đăng nhập suốt phiên đăng nhập, kể cả khi access token được làm mới. Trước đây Keycloak chỉ ghi một bước vào `amr` khi access token được cấp trong cùng giây với bước đó. Do đó, khi trình duyệt đổi code chậm hoặc làm mới access token, Admin Console của realm `saigonos` qua API Gateway nhận mã 403 và luật `otp` trong bản khai báo của ứng dụng từ chối người dùng đã nhập mã OTP. Service `realm` đặt `default.reference.maxAge` bằng SSO Session Max của realm cho các bước có giá trị `amr` và đặt lại khi thiết lập này bị sửa.

## [0.8.0] - 2026-11-23

### Thêm

- Tường lửa ứng dụng web Coraza 3.3.3 với bộ luật OWASP CRS 4.14.0 chạy trong APISIX qua plugin coraza-proxy-wasm 0.6.0. Tường lửa kiểm tra lời gọi tới `/api`, `/apps` và `/core`, kể cả body JSON, và chặn lời gọi có dấu hiệu tấn công với mã 403. Lời gọi gửi nội dung file, Keycloak, Operaton và `/realtime` không đi qua tường lửa.
- Service `waf` tải coraza-proxy-wasm ở lần khởi động đầu tiên, kiểm tra mã băm SHA-256 của file zip và của file `.wasm`, rồi lưu file vào volume `wasm`. Các lần khởi động sau dùng lại file đã lưu.
- Plugin `saigonos-waf` của APISIX đưa body của lời gọi cho Coraza và trả nội dung JSON tiếng Việt với mã `SGN04` cho lời gọi bị chặn. Plugin ghi log mỗi lời gọi bị chặn kèm địa chỉ IP của người gọi.
- Giá trị `SAIGONOS_WAF_MODE=detect` trong file `.env` chuyển tường lửa sang chế độ chỉ ghi log. Khi giá trị không hợp lệ, lệnh `saigonos up` báo lỗi ở service `routes`.
- Lệnh `saigonos doctor` có thêm dòng `Tường lửa`, kiểm tra lời gọi có dấu hiệu tấn công bị chặn hay chỉ được ghi log theo chế độ trong file `.env`.
- Bảng giấy phép có thêm mục plugin của API Gateway.

### Thay đổi

- Lời gọi tới `/api`, `/apps` và `/core` có body lớn hơn 1 MB nhận mã 413, trừ lời gọi gửi nội dung file.
- APISIX chỉ bật các plugin mà SaigonOS dùng và tắt các plugin stream.
- Mức RAM nên có trong README tăng từ 3 GB lên 4 GB, vì tường lửa ứng dụng web dùng thêm khoảng 300 MB.
- Đường dẫn có `..` đã mã hóa tới `/apps/<tên>/` nhận mã 403 của tường lửa thay cho mã 404.

## [0.7.0] - 2026-11-23

### Thêm

- Service `opa` chạy Open Policy Agent 1.22.4 để API Gateway hỏi luật truy cập chung. Luật viết bằng Rego và nằm trong thư mục `config/opa`. OPA nạp lại luật ngay khi file thay đổi và giữ luật đang chạy khi file có lỗi. OPA chỉ nằm trong mạng nội bộ cùng APISIX, không nhận lời gọi sửa luật qua API và không gửi thông tin tới máy chủ của dự án OPA.
- Service `policies` kiểm tra các file luật mỗi lần chạy `saigonos up`. Khi có file lỗi, lệnh `saigonos up` báo lỗi và OPA chưa khởi động lần đầu.
- Lệnh `make opa-test` kiểm tra định dạng, lỗi và unit test của các luật trong `tests/opa`, với yêu cầu độ phủ 100%. CI chạy lệnh này trong job `lint`.
- Route `auth-admin` đưa Admin Console và Admin REST API của realm `saigonos` qua OPA. Route `operaton` cũng qua OPA. Khi OPA dừng hoặc trả lời sai định dạng, API Gateway từ chối hai route này với mã 403 hoặc 503. Trang đăng nhập và các route khác vẫn hoạt động.
- Giá trị `SAIGONOS_ADMIN_NETWORKS` trong file `.env` chỉ mở các route quản trị cho các dải mạng được khai báo. Khi có dải không hợp lệ, lệnh `saigonos up` báo lỗi ở service `policies`.
- Admin REST API của Keycloak qua API Gateway chỉ nhận access token của lần đăng nhập có mã OTP. Lời gọi bị từ chối nhận mã 403 kèm lý do bằng tiếng Việt.
- Access token có claim `amr` ghi các bước đăng nhập, gồm `pwd` cho mật khẩu và `otp` cho mã OTP. Service `realm` thêm thiết lập này vào realm do phiên bản cũ tạo và đặt lại thiết lập khi bị sửa.
- Trường `access` của bản khai báo chứa tối đa 20 luật truy cập API của ứng dụng. Mỗi luật chọn phương thức và mẫu đường dẫn, rồi đặt điều kiện về role, dải mạng hoặc việc đăng nhập bằng mã OTP. Lệnh cài đặt ghi mỗi luật thành một label của route `app-<tên>` và thêm plugin `opa`, nên luật có hiệu lực ngay sau khi cài đặt. Lời gọi không đạt luật nhận mã 403, hoặc 401 khi thiếu access token, với nội dung theo dạng lỗi của PostgREST và mã `SGN03`.

### Thay đổi

- Luồng đăng nhập `saigonos operaton` được tạo lại một lần khi cập nhật, để bước mật khẩu và bước OTP được ghi vào claim `amr`.
- Tên `auth-admin` được thêm vào danh sách tên mà ứng dụng không được dùng.
- Địa chỉ `/api/` chỉ phục vụ schema `api`. API Gateway ghi đè header `Accept-Profile` và `Content-Profile` của lời gọi tới địa chỉ này. Schema của ứng dụng chỉ gọi được qua địa chỉ `/apps/<tên>/api/`, nên không đi vòng được luật truy cập của ứng dụng.
- README hướng dẫn cài Miniforge khi máy chưa có conda, kích hoạt môi trường `saigonos` ở mỗi terminal mới, kiểm tra và mở rộng dung lượng ổ cứng bằng `lvextend`, kiểm tra và tạo swap. Mức RAM tối thiểu là 2 GB kèm ít nhất 2 GB swap, mức nên dùng vẫn là 3 GB. Máy có 1 GB RAM không được hỗ trợ.

## [0.6.0] - 2026-11-22

### Thêm

- Bản khai báo ứng dụng `saigonos-app.json` gồm tên, tên hiển thị, phiên bản, các realm role và ba thư mục không bắt buộc chứa file SQL, file BPMN và giao diện. JSON Schema của bản khai báo nằm trong file `schemas/saigonos-app.schema.json`, để trình soạn thảo kiểm tra và gợi ý khi viết bản khai báo.
- Lệnh `saigonos apply --check <thư mục>` kiểm tra bản khai báo và các thư mục của một ứng dụng mà không cần hệ thống đang chạy. Lệnh in mọi lỗi tìm thấy bằng tiếng Việt kèm vị trí trong bản khai báo, rồi kết thúc với mã thoát 1. Tên trùng tên mà lõi đã dùng, đường dẫn ra ngoài thư mục ứng dụng, symlink và file không đọc được đều bị báo lỗi.
- Service `apps` dùng image của service `core` và chỉ chạy khi được gọi bằng `docker compose run`. Lệnh `docker compose run --rm apps check <tên>` kiểm tra ứng dụng trong thư mục `apps` của thư mục làm việc. Lệnh `saigonos init` tạo thư mục này.
- Lệnh `saigonos apply <thư mục>` cài đặt ứng dụng vào hệ thống đang chạy. Lệnh này kiểm tra ứng dụng, chép bản khai báo và các thư mục đã khai vào thư mục `apps/<tên>` của thư mục làm việc, rồi chạy `docker compose run --rm apps apply <tên>`. Khi cài đặt lỗi, thư mục `apps/<tên>` được trả về bản đã cài đặt thành công gần nhất.
- Mỗi ứng dụng có schema và role riêng trong cơ sở dữ liệu, cùng tên với ứng dụng nhưng dấu gạch ngang đổi thành dấu gạch dưới. Các file SQL của ứng dụng chạy theo thứ tự tên bằng role này, không bằng superuser. Role chỉ đăng nhập được trong lúc cài đặt, với mật khẩu sinh mới mỗi lần. Mỗi file chạy trong một transaction và được ghi vào `core.migrations` với `scope` là tên ứng dụng. File đã chạy mà bị sửa thì lệnh cài đặt dừng.
- Role của ứng dụng không đọc được schema của ứng dụng khác và các bảng của lõi, không đổi được sang role khác. File SQL của ứng dụng không dùng được `COMMIT` hay `ROLLBACK`. Hàm do ứng dụng tạo chưa được cấp cho `PUBLIC`.
- Bảng `core.apps` ghi các ứng dụng đã cài đặt và có audit log. PostgREST đọc bảng này qua hàm `core.pre_config()` để phục vụ schema của ứng dụng tại `/api/`, với header `Accept-Profile` và `Content-Profile`. Sau khi cài đặt, PostgREST nạp lại cấu hình và schema cache mà không khởi động lại.
- Lệnh cài đặt tạo trên Keycloak các realm role của ứng dụng theo bản khai báo, kèm mô tả, và một public client trùng tên ứng dụng. Client chỉ dùng luồng Authorization Code với PKCE `S256` và chỉ chuyển hướng về địa chỉ `/apps/<tên>/`. Client tắt Full scope allowed, nên access token của ứng dụng chỉ mang realm role `authenticated` và các role của chính ứng dụng. Service `apps` giữ mật khẩu của tài khoản `admin` trong realm master, service `core` không có mật khẩu này.
- Mỗi lần cài đặt, client và realm role của ứng dụng được đặt lại theo bản khai báo, kể cả khi đã bị sửa trong Admin Console. Khi Keycloak đã có client hoặc realm role trùng tên mà không do SaigonOS tạo cho ứng dụng, lệnh cài đặt dừng trước khi thay đổi cơ sở dữ liệu.
- Lời gọi API vào schema của một ứng dụng chỉ nhận access token được cấp cho client của ứng dụng đó. Access token của client khác nhận mã 403. Lời gọi không có access token vẫn chạy với role `anon`.
- Lệnh cài đặt tạo trên APISIX route `app-<tên>` cho API của ứng dụng tại địa chỉ `/apps/<tên>/api/`. Route tự đặt header `Accept-Profile` và `Content-Profile` là schema của ứng dụng, kiểm tra access token và giới hạn tần suất như địa chỉ `/api/`. Tài liệu OpenAPI ở địa chỉ `/apps/<tên>/api/` chỉ có bảng và hàm của ứng dụng. Mỗi lần cài đặt, route được đặt lại theo bản khai báo. Khi APISIX đã có route trùng tên mà không do SaigonOS tạo, lệnh cài đặt dừng trước khi thay đổi cơ sở dữ liệu. Service `apps` giữ thêm khóa Admin API của APISIX.
- Service `core` phục vụ giao diện của ứng dụng đã cài đặt tại địa chỉ `/apps/<tên>/`. Địa chỉ không khớp file nào và không có phần mở rộng trả về `index.html`. Mỗi trả lời có header `Content-Security-Policy`, `X-Content-Type-Options` và `Referrer-Policy`. File `index.html` không được cache, các file khác được hỏi lại bằng `ETag`. Địa chỉ có `..`, file có tên bắt đầu bằng dấu chấm, symlink và ứng dụng chưa cài đặt đều nhận mã 404.
- PostgREST và service `core` niêm phong claims của mỗi lời gọi bằng HMAC-SHA256. Khi hàm SQL của ứng dụng đổi `request.jwt.claims`, các hàm `core.claims()`, `core.uid()`, `core.has_role()` và `core.unit()` trả về `NULL`. Do đó, mã của một ứng dụng không mạo danh được người dùng khác để đọc dữ liệu của ứng dụng khác.
- Mỗi ứng dụng có thêm role `<schema>_user` để chạy lời gọi API mang access token của ứng dụng. Schema của ứng dụng chỉ được cấp cho role này và role `anon`. Hàm của ứng dụng được đổi thành hàm `SECURITY DEFINER` của role này và giữ quyền `EXECUTE` như file SQL đã cấp. Bên trong hàm như vậy, PostgreSQL không cho đổi role. Do đó, hàm của một ứng dụng không đọc được dữ liệu của ứng dụng khác, kể cả dữ liệu của chính người gọi.
- Lệnh cài đặt triển khai các file BPMN của ứng dụng vào Operaton, trong tenant trùng tên ứng dụng và với nguồn `app:<tên>`. File không thay đổi thì không tạo phiên bản mới. File đã sửa tạo một phiên bản mới, còn quy trình đang chạy vẫn dùng phiên bản cũ. Service `apps` dùng tài khoản `core` của Operaton để triển khai.
- Việc kiểm tra ứng dụng bao gồm cả các file BPMN. Mã quy trình có dạng `<schema>.<tên quy trình>`. Nhóm ứng viên của việc và nhóm được bắt đầu quy trình chỉ gồm role của ứng dụng. Bước máy làm chỉ gọi hàm trong schema của ứng dụng. File chạy mã bên trong Operaton bị từ chối, ví dụ script task, listener, class Java, delegate expression và connector. Expression chỉ được gồm tên biến, giá trị, phép so sánh và phép logic. Mỗi lỗi có tên file và số dòng. File thiếu phần hình vẽ (BPMNDI) nhận cảnh báo, vì Cockpit không vẽ được quy trình.
- Service `core` lọc quy trình và việc theo client của access token. Access token của một ứng dụng chỉ thấy, nhận, hoàn thành và bắt đầu quy trình của ứng dụng đó. Access token của client khác, kể cả của ứng dụng khác, nhận mã 404 khi gọi tới quy trình hoặc việc của ứng dụng.
- Bước máy làm của quy trình trong một ứng dụng chỉ gọi được hàm trong schema của ứng dụng đó. Quy trình không thuộc ứng dụng nào không gọi được hàm của ứng dụng. Bước máy làm sai quy tắc này trở thành incident. Hàm của ứng dụng được khai báo cho bước máy làm bằng lệnh `GRANT EXECUTE` cho role `workflow`.
- Mã của ứng dụng gọi được `core.notify`, `core.publish` và `core.send_email`. Thông báo do ứng dụng gửi thuộc về ứng dụng đó và được gửi tới kênh `user:<tên ứng dụng>.<sub>`. Access token của ứng dụng chỉ thấy thông báo của ứng dụng đó, access token của client khác chỉ thấy thông báo không thuộc ứng dụng nào. Hàm SQL của ứng dụng cũng chỉ đọc được thông báo của chính ứng dụng. Khóa chống trùng của thông báo và email có hiệu lực riêng trong từng ứng dụng.
- Mã của ứng dụng chỉ gửi được tin vào kênh `role:<tên ứng dụng>.<vai trò>`, `public:<tên ứng dụng>.<tên>` và `user:<tên ứng dụng>.<sub>`. Lời gọi `POST /core/realtime/token` cấp token kênh cho kênh `user:<tên ứng dụng>.<sub>` khi access token được cấp cho client của ứng dụng đó và `<sub>` là mã của người gọi. Do đó, giao diện của ứng dụng khác không nghe được kênh này.
- Lệnh cài đặt ứng dụng chỉ in những gì đã thay đổi. Chạy lại khi ứng dụng không đổi thì lệnh in `Không có gì thay đổi.`
- Lệnh `saigonos up` cài đặt lại mọi ứng dụng đã cài đặt sau khi các service sẵn sàng. Do đó, phần của ứng dụng bị sửa tay trên Keycloak, APISIX hay Operaton được đặt lại theo bản khai báo. Service `apps` có lệnh `apply --all` cho việc này.
- Lệnh `saigonos remove <tên>` gỡ route, client, giao diện và quy trình của ứng dụng, rồi bỏ schema của ứng dụng khỏi API. Schema, dữ liệu, role và việc gán role được giữ lại. Cài đặt lại thì dùng tiếp dữ liệu cũ và chạy lại các quy trình đã tạm dừng. Tùy chọn `--purge` xóa hẳn ứng dụng sau khi hỏi lại.
- Lệnh `saigonos doctor` có thêm một dòng cho mỗi ứng dụng, kiểm tra API và giao diện của ứng dụng.

### Thay đổi

- Hàm `set_config` của PostgreSQL chỉ còn được cấp cho role `authenticator` của PostgREST và role `core_service`. Hàm trong cơ sở dữ liệu đổi giá trị cấu hình bằng lệnh `SET LOCAL`.
- Lệnh DDL trong cơ sở dữ liệu `saigonos` chỉ chạy được bằng superuser hoặc trong file SQL khi cài đặt ứng dụng.

## [0.5.0] - 2026-11-21

### Thêm

- Service `centrifugo` gửi cập nhật tức thời tới ứng dụng qua WebSocket. Ứng dụng kết nối tới địa chỉ `/realtime/connection/websocket` của API Gateway và gửi access token của Keycloak trong lệnh connect. Centrifugo kiểm tra chữ ký, issuer, thời hạn và audience của access token. Kết nối không có access token, kết nối bằng ID token và kết nối bằng access token không mang mã người dùng đều bị từ chối. Centrifugo chỉ nhận kết nối WebSocket từ trang có địa chỉ trùng với địa chỉ truy cập của hệ thống, kể cả khi địa chỉ truy cập là một địa chỉ IPv6.
- Khi dừng, Centrifugo báo cho các client kết nối lại rồi thoát trong khoảng 1 giây.
- API của server và Admin web của Centrifugo nằm ở cổng 9480, chỉ truy cập được từ chính máy cài đặt. API Gateway không mở hai địa chỉ này. Lệnh `saigonos init` có thêm tùy chọn `--centrifugo-port` để đổi cổng này.
- Lệnh `saigonos init` thêm các giá trị `SAIGONOS_CENTRIFUGO_PORT`, `CENTRIFUGO_ALLOWED_ORIGIN`, `CENTRIFUGO_API_KEY`, `CENTRIFUGO_ADMIN_PASSWORD`, `CENTRIFUGO_ADMIN_SECRET`, `CENTRIFUGO_DB_PASSWORD` và `CENTRIFUGO_SUBSCRIPTION_KEY` vào file `.env`. Dòng `CENTRIFUGO_ALLOWED_ORIGIN` được ghi lại từ địa chỉ truy cập mỗi lần chạy lệnh.
- Hàm `core.publish(channel, data)` của cơ sở dữ liệu gửi một tin tới một kênh của Centrifugo. Hàm ghi tin vào bảng `core.outbox` trong cùng transaction với dữ liệu. Ngay khi transaction được commit, Centrifugo đọc tin, gửi tới client rồi xóa tin khỏi bảng. Khi transaction bị hủy, không có tin nào được gửi.
- Hàm `core.publish` chỉ nhận kênh có dạng `public:<tên>`, `user:#<sub>` hoặc `role:<realm role>`. Mỗi tin mang một mã riêng trong tag `id` để client bỏ tin trùng. Chỉ role `workflow` gọi được hàm, nên hàm được dùng trong bước máy làm của quy trình.
- Mọi người dùng đã đăng nhập nghe được kênh `public:<tên>`. Chỉ người dùng có mã `<sub>` nghe được kênh `user:#<sub>`. Kênh `role:<realm role>` cần token kênh. Kênh không có namespace hoặc thuộc namespace khác bị từ chối.
- Lời gọi `POST /core/realtime/token` cấp token kênh cho kênh `role:<realm role>` khi người gọi có realm role này. Token kênh có hiệu lực 60 giây, hết hạn không muộn hơn access token của lời gọi và chỉ dùng được cho đúng kênh, đúng người dùng đã lấy token.
- Mỗi kênh có history giữ tối đa 100 tin gần nhất trong 5 phút. Client mất kết nối rồi kết nối lại nhận lại các tin bị lỡ còn trong history, theo đúng thứ tự. Client đang nghe kênh đọc được history của kênh đó.
- Tin ghi trong lúc Centrifugo dừng nằm lại trong bảng `core.outbox` và được gửi khi Centrifugo chạy lại. History mất khi Centrifugo khởi động lại, nên client kết nối lại nhận `recovered` là false và đọc được các tin này trong history.
- Bảng `core.notifications` lưu thông báo trong ứng dụng. Hàm `core.notify(recipient, dedup_key, title, body, link)` ghi một thông báo rồi gửi thông báo tới kênh `user:#<sub>` của người nhận trong cùng transaction với dữ liệu. Chỉ role `workflow` gọi được hàm.
- Mỗi người nhận chỉ có một thông báo cho mỗi khóa chống trùng. Khi hàm `core.notify` được gọi lại với cùng người nhận và cùng khóa, không có thông báo mới và không có tin mới, kể cả khi hai transaction gọi hàm cùng lúc.
- Đường dẫn của thông báo phải trỏ tới một trang trong hệ thống và bắt đầu bằng một dấu `/`. Đường dẫn tới web khác và đường dẫn `javascript:` bị từ chối.
- Lời gọi `GET /core/notifications` trả về thông báo của người gọi, thông báo mới nhất đứng đầu. Lời gọi `POST /core/notifications/{id}/read` đánh dấu thông báo đã đọc. Người dùng chỉ thấy và chỉ đánh dấu được thông báo gửi cho chính mình.
- Hàm `core.notify` có thêm tham số `telegram`. Khi tham số này có giá trị `true`, thông báo còn được gửi tới một nhóm Telegram qua Bot API. Tin gồm tiêu đề in đậm, nội dung và địa chỉ đầy đủ của đường dẫn. Mỗi khóa chống trùng chỉ có một tin Telegram, kể cả khi sự việc được báo cho nhiều người.
- Bảng `core.deliveries` là hàng đợi của tin Telegram. Tin được ghi trong cùng transaction với thông báo và được gửi ngay khi transaction được commit. Khi không kết nối được Telegram hoặc Telegram trả về mã 5xx, tin được gửi lại sau 5 giây, 30 giây, 2 phút và 10 phút. Khi Telegram trả về mã 429, service `core` chờ đúng số giây trong `retry_after`. Tin bị Telegram từ chối hoặc gửi lỗi 5 lần chuyển sang `failed` và được ghi vào log.
- Tin đã gửi không được gửi lại. Khi không biết Telegram đã nhận tin hay chưa, ví dụ mất kết nối trước khi Telegram trả lời, tin chuyển sang `unknown` và không được gửi lại.
- Cấu hình Telegram gồm `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_TOPIC_ID` và `TELEGRAM_API_URL`, được ghi trực tiếp vào file `.env`. Khi chưa cấu hình Telegram, tin Telegram được bỏ qua và hệ thống vẫn chạy bình thường.
- Hàm `core.send_email(address, dedup_key, title, body, link)` ghi một email vào hàng đợi `core.deliveries` trong cùng transaction với dữ liệu. Service `core` gửi email qua SMTP ngay khi transaction được commit. Người nhận không cần có tài khoản trong hệ thống. Mỗi địa chỉ chỉ nhận một email cho mỗi khóa chống trùng. Chỉ role `workflow` gọi được hàm.
- Email chỉ có phần văn bản thuần, gồm nội dung và địa chỉ đầy đủ của đường dẫn. Kết nối tới máy chủ SMTP được mã hóa bằng STARTTLS hoặc TLS, và chứng chỉ của máy chủ luôn được kiểm tra. Mật khẩu không được gửi qua kết nối chưa mã hóa.
- Khi không kết nối được máy chủ SMTP hoặc máy chủ trả về mã 4xx, email được gửi lại như tin Telegram. Khi máy chủ trả về mã 5xx hoặc không hỗ trợ STARTTLS, email chuyển sang `failed`. Khi mất kết nối sau khi đã gửi nội dung, email chuyển sang `unknown` và không được gửi lại. Telegram và email có vòng gửi riêng, nên lỗi của kênh này không làm chậm kênh kia.
- Cấu hình SMTP gồm `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` và `SMTP_FROM_NAME`, được ghi trực tiếp vào file `.env`. Khi chưa cấu hình SMTP, email được bỏ qua và hệ thống vẫn chạy bình thường.
- Service `databases` tạo role `centrifugo` của cơ sở dữ liệu khi chưa có, kể cả với cơ sở dữ liệu được tạo từ phiên bản cũ. Role này chỉ đọc và xóa được các dòng của bảng `core.outbox`.
- Service `realm` thêm audience `saigonos` vào access token của các client dùng client scope `roles`. Khi mapper này bị sửa hoặc bị xóa, service đặt lại như cũ.
- Lệnh `saigonos doctor` mở thử một kết nối WebSocket tới Centrifugo qua API Gateway và kiểm tra API của Centrifugo bị chặn. Khi reverse proxy không chuyển tiếp kết nối WebSocket, lệnh báo cần kiểm tra header `Upgrade` và `Connection`.

### Thay đổi

- Ví dụ cấu hình Nginx trong README chuyển tiếp kết nối WebSocket. Máy chủ đã có reverse proxy cần thêm khối `map` và ba dòng `proxy_http_version`, `Upgrade`, `Connection` như trong ví dụ.
- Lệnh `saigonos init` bỏ cổng mặc định khỏi địa chỉ truy cập. Ví dụ, `https://dx.example.com:443` được ghi thành `https://dx.example.com`. Trình duyệt gửi địa chỉ của trang không kèm cổng mặc định, nên Centrifugo cần địa chỉ ở dạng này để nhận kết nối. Địa chỉ IPv6 và cổng cũng được ghi theo dạng mà trình duyệt gửi. Ví dụ, `http://[2001:0DB8:0:0:0:0:0:1]:09080` được ghi thành `http://[2001:db8::1]:9080`.

### Sửa

- Sau khi một service khởi động lại, API Gateway trả lời bình thường ngay khi service chạy lại. Trước đây, trên máy chủ có DNS trả lỗi `name error`, API Gateway có thể trả mã 503 cho một phần lời gọi trong khoảng 30 giây sau khi service đã chạy lại.

## [0.4.0] - 2026-11-18

### Thêm

- Service `operaton` chạy các quy trình BPMN 2.0 bằng Operaton. Operaton lưu dữ liệu trong cơ sở dữ liệu `operaton` riêng. Service `databases` tạo cơ sở dữ liệu này và role `operaton` khi chưa có, kể cả với cơ sở dữ liệu được tạo từ phiên bản cũ.
- Cockpit, Tasklist và Admin của Operaton ở địa chỉ `/operaton/` của API Gateway. Chỉ tài khoản có realm role `admin` đăng nhập được, bằng mật khẩu và OTP. Tài khoản khác được báo rằng chỉ tài khoản quản trị mới vào được, bằng tiếng Việt hoặc tiếng Anh. Khi tài khoản bị khóa trong Keycloak, phiên đăng nhập của Operaton kết thúc ngay ở lời gọi tiếp theo. Nút đăng xuất của ba trang kết thúc phiên đăng nhập của Operaton, nên lần mở tiếp theo phải nhập lại mật khẩu và mã OTP.
- Service `realm` tạo client `operaton` và luồng đăng nhập riêng của client này trong realm `saigonos`. Khi luồng đăng nhập hoặc các thiết lập bảo mật của client bị thay đổi, service đặt lại như cũ.
- REST API của Operaton chỉ dành cho service `core`. REST API này không mở qua API Gateway và cần đăng nhập bằng tài khoản `core` của Operaton.
- Lệnh `saigonos init` thêm các giá trị `OPERATON_DB_PASSWORD`, `OPERATON_CLIENT_SECRET` và `CORE_OPERATON_PASSWORD` vào file `.env`.
- Service `processes` triển khai các file BPMN trong thư mục `config/operaton/processes` vào Operaton mỗi khi hệ thống khởi động. File không thay đổi thì không tạo phiên bản mới của quy trình. File bị lỗi làm lệnh `saigonos up` kết thúc với mã lỗi. Một file không thay được quy trình đã khai báo trong file khác. Lệnh `saigonos init` tạo sẵn thư mục này.
- Lệnh `saigonos doctor` kiểm tra Operaton qua API Gateway. Trang đăng nhập phải dùng đúng địa chỉ truy cập của hệ thống và REST API của Operaton phải bị chặn.
- Lời gọi `POST /core/processes/{key}/start` bắt đầu phiên bản mới nhất của một quy trình. Người gọi cần một realm role có trong thuộc tính `candidateStarterGroups` của quy trình. Quy trình không khai báo thuộc tính này thì không bắt đầu được qua API. Service `core` ghi mã người gọi vào biến `initiator` và người gọi không gửi được biến này.
- Lời gọi `GET /core/tasks` trả về các việc mà người gọi đã nhận và các việc chưa ai nhận có nhóm ứng viên là một realm role của người gọi. Việc mà người khác đã nhận không có trong danh sách.
- Lời gọi `POST /core/tasks/{id}/claim` nhận một việc chưa có người nhận. Người gọi cần một realm role nằm trong nhóm ứng viên của việc. Khi nhiều người cùng nhận một việc, chỉ một người nhận được. Những người còn lại nhận mã 409.
- Lời gọi `POST /core/tasks/{id}/complete` hoàn thành việc mà người gọi đã nhận. Các biến được gửi qua form của việc trong Operaton. Người hoàn thành việc không gửi được biến `initiator`.
- Lời gọi bắt đầu quy trình và lời gọi hoàn thành việc chỉ nhận các trường được khai báo trong form của file BPMN, tức các thẻ `operaton:formField`. Service `core` kiểm tra kiểu của từng trường và các ràng buộc `required`, `minlength`, `maxlength`, `min`, `max` và `readonly` trước khi gửi tới Operaton. Chuỗi chỉ có khoảng trắng được coi là chưa nhập. Khi một giá trị không đạt, lời gọi nhận mã 422 với nội dung bắt đầu bằng `LỖI TUÂN THỦ` và nêu tên trường. Khi đó, việc vẫn thuộc người nhận và quy trình không đi tiếp.
- Bước máy làm của quy trình gọi một hàm của cơ sở dữ liệu. Bước này là service task có topic `saigonos-function` và thuộc tính `function` nêu tên hàm. Hàm cần được cấp quyền `EXECUTE` cho role `workflow` và chạy với quyền của role này. Kết quả của hàm được ghi thành biến của quy trình.
- Mỗi bước máy làm chỉ chạy hàm một lần, kể cả khi service `core` dừng đột ngột trước khi báo Operaton. Hàm báo lỗi được thử lại sau 5 giây, 30 giây và 2 phút. Hàm chưa được khai báo hoặc sai kiểu làm bước máy làm trở thành incident trong Cockpit.
- Khi Operaton từ chối tài khoản `core`, service `core` ngừng gọi Operaton trong 60 giây. Sau 5 lần bị từ chối liên tiếp, service ngừng gọi Operaton cho tới khi khởi động lại. Nhờ đó, Operaton không khóa hẳn tài khoản `core`.
- Quy trình có thể gắn hẹn giờ trên biên của một việc. Khi việc quá hạn, quy trình rẽ sang nhánh khác, ví dụ chuyển việc cho nhóm quản lý. Operaton tìm các hẹn giờ đã tới hạn 2 giây một lần, nên hẹn giờ chạy chậm nhất khoảng 2 giây sau hạn. Hẹn giờ tới hạn trong lúc Operaton dừng sẽ chạy ngay khi Operaton chạy lại.
- Mỗi ngày từ 01:00 đến 05:00 giờ Việt Nam, Operaton xóa lịch sử của các quy trình đã kết thúc quá thời gian `historyTimeToLive`.
- Khi container dừng, Operaton dừng job executor và đóng các kết nối tới cơ sở dữ liệu trước khi thoát.

### Thay đổi

- Hệ thống cần khoảng 3 GB RAM và 6 GB dung lượng ổ cứng vì có thêm Operaton.

### Sửa

- Lời gọi tới service `core` có giá trị `NaN` hoặc `Infinity` trong nội dung nhận mã 422 thay cho 500. Nội dung lỗi 422 không còn chép lại giá trị mà người gọi đã gửi.

## [0.3.0] - 2026-11-17

### Thêm

- Service `migrate` chạy các file SQL của cơ sở dữ liệu mỗi khi hệ thống khởi động. Các file chạy theo thứ tự tên. Mỗi file chỉ chạy một lần và chạy trong một transaction. Bảng `core.migrations` ghi lại các file đã chạy. Khi nội dung của một file đã chạy bị thay đổi, service dừng và báo lỗi. PostgREST nhận ngay các bảng và view mới mà không cần khởi động lại.
- Các hàm `core.uid()`, `core.has_role()` và `core.unit()` cho biết thông tin của người gọi API. Hàm `core.uid()` trả về mã người dùng trong Keycloak. Hàm `core.has_role()` kiểm tra một realm role của người dùng. Hàm `core.unit()` trả về đơn vị của người dùng. Hàm `core.claims()` trả về toàn bộ nội dung của access token. Các hàm này đọc access token mà PostgREST đã kiểm tra. Chính sách phân quyền từng dòng (row-level security) của bảng dùng các hàm này để giới hạn dữ liệu theo người dùng, vai trò và đơn vị.
- Thuộc tính `unit` (Đơn vị) của người dùng trong realm `saigonos`. Quản trị viên đặt giá trị này ở trang thông tin người dùng trong Admin Console của Keycloak. Người dùng không tự đổi được giá trị này. Access token mang giá trị này trong claim `unit`.
- Service `realm` thêm các thiết lập mới vào realm `saigonos` mỗi khi hệ thống khởi động. Nhờ đó, realm được tạo từ phiên bản cũ cũng có thuộc tính `unit`. Service chỉ thêm thiết lập còn thiếu và giữ nguyên các thiết lập khác của realm.
- Role `anon` của cơ sở dữ liệu dành cho lời gọi API không có access token. Role này chưa được cấp quyền trên bảng, view hay hàm nào của API. Để mở một bảng, view hoặc hàm cho người chưa đăng nhập, cấp quyền cho role này bằng lệnh `GRANT`.
- Hàm `core.pre_request()` xóa các query plan đã lưu trước mỗi lời gọi API. PostgREST cũng không dùng prepared statement. Nhờ đó, quyền `EXECUTE` của hàm được kiểm tra lại ở mỗi lời gọi. Khi dùng lại query plan đã lập cho một role khác, PostgreSQL không kiểm tra lại quyền này.
- Bảng `core.audit_log` và hàm `core.audit()` ghi audit log của cơ sở dữ liệu. Để ghi audit log cho một bảng, gắn hàm `core.audit()` vào bảng đó bằng một lệnh `CREATE TRIGGER`. Mỗi lần một dòng được thêm, sửa hoặc xóa, audit log ghi người thực hiện, thời điểm, tên bảng, thao tác, giá trị trước và giá trị sau. Mỗi dòng audit log mang một mã băm SHA-256. Mã băm này được tính từ nội dung của dòng và mã băm của dòng trước. Do đó, khi một dòng audit log bị sửa hoặc bị xóa, chuỗi mã băm không còn khớp. Role `anon` và `authenticated` không đọc và không ghi được bảng `core.audit_log`.
- Bảng `core.audit_log` chỉ cho phép thêm dòng. Các lệnh `UPDATE`, `DELETE` và `TRUNCATE` trên bảng này bị từ chối, kể cả với role sở hữu bảng. Hàm `core.append_only()` cũng dùng được cho các bảng khác chỉ cho phép thêm dòng.
- Lệnh `saigonos audit verify` tính lại chuỗi mã băm của audit log. Khi một dòng đã bị sửa hoặc bị xóa, lệnh chỉ ra dòng sai đầu tiên và kết thúc với mã thoát 1. Lệnh tự tính mã băm và không dùng hàm lưu trong cơ sở dữ liệu.
- Tài liệu OpenAPI 2.0 của REST API ở địa chỉ `/api/`. PostgREST tự sinh tài liệu này. Tài liệu chỉ liệt kê các bảng, view và hàm mà người gọi được dùng. Các địa chỉ trong tài liệu được lấy từ `SAIGONOS_URL`. Tài liệu cũng ghi cách gửi access token trong header `Authorization`. Ở phiên bản 0.2.0, tài liệu ghi địa chỉ `0.0.0.0:3000` của PostgREST bên trong container.
- Hàm `core.mask_phone()` và `core.mask_email()` che một phần số điện thoại và email. Ví dụ: `0912345678` thành `091****678`, `nguyenvana@gmail.com` thành `ngu*******@gmail.com`. Role `anon` và `authenticated` gọi được hai hàm này. Khi dùng trong view, hai hàm cho phép chỉ hiện đủ dữ liệu cho người có quyền.
- Bảng `core.consents` ghi sự đồng ý với chính sách, gồm người đồng ý, tên chính sách, phiên bản chính sách và thời điểm đồng ý. Thời điểm đồng ý do máy chủ ghi. Bảng chỉ cho phép thêm dòng và có audit log. Role `anon` và `authenticated` không đọc và không ghi trực tiếp được bảng này.
- Tùy chọn `--keycloak-port` của lệnh `saigonos init` đặt cổng của Keycloak trên máy cài đặt. Cổng này mặc định là 9280 và chỉ lắng nghe trên địa chỉ `127.0.0.1`. Admin Console của realm master dùng cổng này.
- Hướng dẫn tạo tài khoản quản trị có OTP trong realm `saigonos` trong README.
- Service `seaweedfs` lưu file của các ứng dụng theo chuẩn S3. Hai bucket `quarantine` và `clean` được tạo sẵn. Lời gọi S3 phải được ký bằng khóa trong file `.env`. Service này nằm trong một mạng Docker riêng. Chỉ service `core` kết nối được tới SeaweedFS. SeaweedFS không gửi thống kê ra ngoài và không liệt kê nội dung thư mục.
- Admin UI của SeaweedFS ở địa chỉ http://127.0.0.1:9380/, chỉ truy cập được từ chính máy cài đặt. Tùy chọn `--seaweedfs-port` của lệnh `saigonos init` đổi cổng này.
- Lệnh `saigonos init` tạo khóa S3 và mật khẩu Admin UI của SeaweedFS trong file `.env`. Khi cập nhật từ phiên bản cũ, lệnh thêm các giá trị này và giữ nguyên các mật khẩu đã có.
- Service `clamav` quét mã độc bằng ClamAV. Service này nằm trong mạng Docker `scan` riêng. Mạng này không có kết nối Internet. Chỉ service `core` kết nối được tới ClamAV. Khi tiến trình quét dừng bất thường, container tự khởi động lại.
- Service `freshclam` kiểm tra bản cập nhật của cơ sở dữ liệu mã độc 12 lần mỗi ngày và tải bản mới từ `database.clamav.net`. Cơ sở dữ liệu nằm trong volume `clamav-data` nên được giữ lại khi khởi động lại hệ thống. Trong lúc nạp bản mới, ClamAV chỉ giữ một bản cơ sở dữ liệu trong RAM và dùng khoảng 1 GB RAM.
- Service `core` cung cấp API của lõi tại địa chỉ `/core/` của API Gateway. Service được viết bằng FastAPI. Tài liệu OpenAPI 3.1 nằm ở `/core/openapi.json`. Lời gọi `GET /core/me` trả về mã người dùng, đơn vị và role mà cơ sở dữ liệu nhận được.
- Docker Compose build image của service `core` trên máy cài đặt từ image `python` chính thức. Dòng `FROM` ghi cả digest của image. Các thư viện được cài từ lock file có mã băm. Do đó, file release vẫn chỉ chứa mã nguồn.
- API Gateway kiểm tra access token của lời gọi tới `/core` như với `/api`. Service `core` kiểm tra lại chữ ký, issuer, thời hạn, loại token và realm role `authenticated`. Do đó, lời gọi tới thẳng service với access token giả vẫn bị từ chối. Khi Keycloak đổi khóa ký, service tự lấy khóa mới.
- Service `core` kết nối PostgreSQL bằng role `core_service`. Mỗi truy vấn chạy với role và nội dung access token của người gọi, giống PostgREST. Lệnh `saigonos init` thêm mật khẩu của role này vào file `.env`.
- Bảng `core.files` lưu thông tin của các file được tải lên, gồm chủ file, tên, loại, dung lượng, mã băm SHA-256 và trạng thái. Bảng có audit log. Chính sách phân quyền từng dòng chỉ cho người dùng thấy file của chính mình. Chỉ role `core_service` thêm và sửa được dòng của bảng này.
- Lời gọi `POST /core/files` của service `core` khai báo một file mới và trả về đường dẫn tải lên. Service kiểm tra loại file, phần mở rộng của tên file và dung lượng. Lời gọi `PUT` tới đường dẫn tải lên gửi nội dung của file. Nội dung được lưu vào bucket `quarantine` và chờ quét mã độc. Nội dung có dung lượng hoặc phần đầu không khớp với thông tin đã khai báo bị từ chối. Lời gọi `GET /core/files/{id}` trả về thông tin và trạng thái của file.
- Tùy chọn `--max-file-size` của lệnh `saigonos init` đặt dung lượng tối đa của một file tải lên, tính bằng MB. Giá trị mặc định là 10.
- Service `core` quét mọi file bằng ClamAV ngay sau khi nhận nội dung. File không có mã độc được chuyển sang bucket `clean` và có trạng thái `clean`. File có mã độc được giữ trong bucket `quarantine` và có trạng thái `infected`. Tên mã độc được ghi vào trường `malware` của file và vào audit log. Khi ClamAV chưa sẵn sàng, file chờ ở trạng thái `pending_scan` và được quét lại sau, kể cả khi service `core` khởi động lại.
- ClamAV coi nội dung không quét hết được là mã độc. Ví dụ: file nén lồng nhau quá 17 lớp hoặc có tổng nội dung sau khi giải nén lớn hơn 400 MB. Khi đó, tên mã độc bắt đầu bằng `Heuristics.Limits.Exceeded`.
- Lời gọi `POST /core/files/{id}/download-url` của service `core` trả về đường dẫn tải về của một file. Đường dẫn dùng được trong 60 giây và mở được trong trình duyệt mà không cần access token. Chỉ file có trạng thái `clean` mới tải về được. Người dùng chỉ xin được đường dẫn cho file mà chính sách phân quyền từng dòng cho phép đọc. File được gửi kèm header `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff` và `Cache-Control: no-store`. Trước khi gửi, nội dung được so với mã băm SHA-256 đã ghi.
- Lệnh `saigonos init` tạo khóa `CORE_DOWNLOAD_KEY` trong file `.env`. Service `core` ký đường dẫn tải về bằng khóa này. Khi cập nhật từ phiên bản cũ, lệnh thêm khóa này và giữ nguyên các mật khẩu đã có.

### Thay đổi

- Hệ thống cần Docker Buildx để build image của service `core`. Hệ thống cũng cần khoảng 2,5 GB RAM và 5 GB dung lượng ổ cứng vì có thêm SeaweedFS, ClamAV và service `core`. Ở phiên bản 0.2.0, hệ thống cần khoảng 1 GB RAM và 2 GB dung lượng ổ cứng.
- Lệnh `saigonos up` cần đăng nhập được Keycloak bằng tài khoản `admin` của realm master. Service `realm` dùng tài khoản này với mật khẩu `KEYCLOAK_ADMIN_PASSWORD` trong file `.env`. Nếu mật khẩu của tài khoản đã được đổi trong Admin Console, cần ghi mật khẩu mới vào file `.env` trước khi cập nhật. Service chỉ đăng nhập bằng mật khẩu, nên không bật OTP cho tài khoản này.
- Admin Console của realm master có địa chỉ mới là http://localhost:9280/auth/admin/master/console/ trên máy cài đặt. Admin Console của realm `saigonos` vẫn mở qua API Gateway tại `/auth/admin/saigonos/console/`.
- Lời gọi `/api` không có access token chạy với role `anon`. Ở phiên bản 0.2.0, API Gateway trả về mã 401 cho lời gọi này. Khi dùng một bảng hoặc hàm chưa cấp cho `anon`, lời gọi nhận mã 401. Access token giả hoặc hết hạn vẫn nhận mã 401. Giới hạn tần suất gọi áp dụng cho cả lời gọi không có access token.
- Access token hợp lệ nhưng không có realm role `authenticated` chạy với role `anon`. Ở phiên bản 0.2.0, lời gọi này nhận mã 401. Lời gọi kèm ID token hoặc token khác không phải access token vẫn nhận mã 401.
- Hàm mới trong cơ sở dữ liệu `saigonos` chỉ gọi được sau khi được cấp quyền `EXECUTE`. Ở phiên bản 0.2.0, mọi role đều gọi được hàm mới. Các hàm đã có trong schema `api` được cấp cho role `authenticated`. Do đó, người dùng đã đăng nhập vẫn gọi được các hàm này sau khi cập nhật.
- Lệnh `saigonos doctor` kiểm tra hai lời gọi tới `/api/`. Lời gọi không có access token phải nhận mã 200. Lời gọi có access token không hợp lệ phải nhận mã 401.
- Lệnh `saigonos doctor` kiểm tra service `core` qua API Gateway. Lời gọi `/core/health` phải nhận mã 200. Lời gọi có access token không hợp lệ phải nhận mã 401.
- API Gateway từ chối lời gọi có nội dung lớn hơn dung lượng tối đa của một file tải lên, mặc định là 10 MB. Ở phiên bản 0.2.0, API Gateway không giới hạn dung lượng nội dung. Khi hệ thống chạy sau Nginx, giới hạn `client_max_body_size` của Nginx không được nhỏ hơn giới hạn này. Ví dụ cấu hình Nginx trong README đã có dòng này.

### Sửa

- API Gateway nhận địa chỉ IP mới của một service trong khoảng 1 giây sau khi service được tạo lại hoặc khởi động lại. Ở phiên bản 0.2.0, API Gateway có thể dùng địa chỉ cũ thêm tới 30 giây. Trong thời gian đó, lời gọi tới service nhận mã 502 hoặc bị treo.

### Bảo mật

- API Gateway trả về mã 404 cho mọi địa chỉ của realm master. Realm master chỉ mở qua cổng của Keycloak trên chính máy cài đặt. Ở phiên bản 0.2.0, trang đăng nhập và Admin Console của realm master mở ra ngoài qua API Gateway và chỉ cần mật khẩu.
- Realm master khóa tạm một tài khoản sau nhiều lần đăng nhập sai. Ở phiên bản 0.2.0, realm master không giới hạn số lần đăng nhập sai.

## [0.2.0] - 2026-11-14

### Thêm

- Service `caddy` nhận kết nối HTTPS trên máy chủ chưa có reverse proxy. Caddy tự lấy chứng chỉ từ Let's Encrypt và bật HSTS. Caddy cũng hỗ trợ HTTP/3 và chuyển các kết nối HTTP sang HTTPS. Caddy dùng mạng của máy chủ nên thấy đúng địa chỉ IP của người dùng qua IPv4 và IPv6. Các header `X-Forwarded-*` do người dùng tự gửi bị bỏ qua.
- Tùy chọn `--caddy` và `--no-caddy` của lệnh `saigonos init` bật và tắt Caddy. Caddy mặc định tắt. Khi Caddy bật, địa chỉ truy cập phải bắt đầu bằng `https://`.
- Lệnh `saigonos doctor` tin chứng chỉ do Caddy tự cấp, ví dụ chứng chỉ cho `localhost`.
- Lệnh `saigonos doctor` báo lỗi khi Keycloak nhận lời gọi qua một địa chỉ khác với `SAIGONOS_URL`. Lỗi này xảy ra khi reverse proxy không gửi đủ các header `X-Forwarded-Proto`, `X-Forwarded-Host` và `X-Forwarded-Port`.
- Hướng dẫn triển khai trên máy chủ chưa có reverse proxy trong README.

### Thay đổi

- Lệnh `saigonos doctor` ghi `BÌNH THƯỜNG` thay cho `ĐẠT` và ghi `healthcheck báo lỗi` thay cho `không đạt healthcheck`. Các cột cách nhau 4 dấu cách.
- Lệnh `saigonos init` từ chối cổng HTTP trùng các cổng 7085, 9090, 9091, 9180 và 9443. APISIX dùng các cổng này bên trong container. Ở phiên bản 0.1.1, các cổng này vẫn được chấp nhận.
- Lệnh `saigonos up` và `saigonos down` xóa container của Caddy sau khi Caddy bị tắt bằng lệnh `saigonos init --no-caddy`.
- Mục "Triển khai sau reverse proxy HTTPS" của README đổi tên thành "Triển khai trên máy chủ đã có reverse proxy".

### Sửa

- Khi người dùng truy cập thẳng API Gateway qua cổng 80, `token_endpoint` của Keycloak không còn kèm cổng 9080. Lỗi này có từ phiên bản 0.1.0. Để sửa lỗi, APISIX lắng nghe trong container đúng cổng HTTP được mở ra máy chủ.

## [0.1.1] - 2026-11-13

### Thêm

- Tùy chọn `--http-host` của lệnh `saigonos init` đặt địa chỉ IP mà cổng HTTP của API Gateway lắng nghe. Giá trị `0.0.0.0` cho phép truy cập từ máy khác.
- Hướng dẫn triển khai sau reverse proxy HTTPS và hướng dẫn cập nhật phiên bản trong README.

### Thay đổi

- Cổng HTTP của API Gateway mặc định chỉ lắng nghe trên địa chỉ `127.0.0.1`. Ở phiên bản 0.1.0, cổng này lắng nghe trên mọi địa chỉ của máy cài đặt. Để các máy khác vẫn truy cập được sau khi cập nhật, chạy lệnh `saigonos init --http-host 0.0.0.0`.

### Sửa

- Khi SaigonOS chạy sau reverse proxy, APISIX giữ nguyên các header `X-Forwarded-Proto`, `X-Forwarded-Host` và `X-Forwarded-Port` do proxy trong mạng nội bộ gửi tới. Địa chỉ IP của người dùng được lấy từ header `X-Forwarded-For`. Ở phiên bản 0.1.0, Keycloak trả về địa chỉ `http` kèm cổng 9080 và giới hạn tần suất gọi tính mọi người dùng vào cùng một địa chỉ IP.

### Bảo mật

- APISIX bỏ header `X-Forwarded-For` do máy ngoài mạng nội bộ gửi tới. Ở phiên bản 0.1.0, một máy bên ngoài có thể dùng header này để khai báo với Keycloak một địa chỉ IP trong mạng nội bộ.

## [0.1.0] - 2026-11-12

### Thêm

- Package Python `saigonos` có lệnh `saigonos --version`.
- Giấy phép Apache-2.0 với dòng SPDX ở đầu mọi file, được kiểm tra bằng REUSE.
- Lock file `requirements.txt` và `requirements-dev.txt` cố định phiên bản thư viện.
- Bộ tài liệu khung gồm README, hướng dẫn đóng góp, chính sách bảo mật và mẫu issue.
- `DEPENDENCIES.md` liệt kê thư viện, phần mềm chạy trong container và công cụ phát triển kèm giấy phép, được tạo bằng lệnh `make dependencies`.
- File nén mã nguồn `.tar.gz` kèm `SHA256SUMS`, được tạo tự động khi push tag phiên bản.
- Bộ Docker Compose gồm PostgreSQL, Keycloak, etcd, APISIX và PostgREST. Mỗi service được cố định phiên bản, có healthcheck và tự khởi động lại.
- Realm `saigonos` của Keycloak được nạp từ file. Tài khoản có vai trò `admin` phải nhập OTP khi đăng nhập. Access token có thời hạn 60 giây.
- Route `/auth` tới Keycloak và route `/api` tới PostgREST trên API Gateway. Route `/api` kiểm tra access token và giới hạn tần suất gọi.
- Lệnh `saigonos init` tạo thư mục làm việc gồm file `compose.yaml`, thư mục `config` và file `.env` chứa mật khẩu ngẫu nhiên. Khi chạy lại, các giá trị đã có trong file `.env` được giữ nguyên.
- Lệnh `saigonos up` và `saigonos down` khởi động và dừng các service bằng Docker Compose.
- Lệnh `saigonos doctor` kiểm tra trạng thái từng service và API Gateway.
- Hướng dẫn cài đặt bằng pip và Docker Compose trong README.

[Chưa phát hành]: https://github.com/tynnpdhsp/SaigonOS/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v1.2.0
[1.1.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v1.1.0
[1.0.1]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v1.0.1
[1.0.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v1.0.0
[0.12.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.12.0
[0.11.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.11.0
[0.10.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.10.0
[0.9.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.9.0
[0.8.1]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.8.1
[0.8.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.8.0
[0.7.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.7.0
[0.6.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.6.0
[0.5.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.5.0
[0.4.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.4.0
[0.3.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.3.0
[0.2.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.2.0
[0.1.1]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.1.1
[0.1.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.1.0
