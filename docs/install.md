<!-- SPDX-License-Identifier: Apache-2.0 -->
# Cài đặt

## Yêu cầu hệ thống

- Hệ điều hành Linux. SaigonOS được kiểm thử trên Ubuntu 22.04 và 24.04.
- Python 3.11 trở lên và pip. Ubuntu 22.04 chỉ có sẵn Python 3.10, nên cần cài Miniforge như bước 1 của mục [Cài đặt](#các-bước-cài-đặt).
- Docker Engine 25.0 trở lên, Docker Compose 2.20.2 trở lên và Docker Buildx. Ba thành phần này có sẵn khi cài Docker theo hướng dẫn của Docker. Tài khoản cài đặt chạy được lệnh `docker` mà không cần `sudo`.
- Git.
- Kết nối Internet để tải các image Docker, các thư viện của service `core` và bản cập nhật của cơ sở dữ liệu mã độc.
- Khoảng 6 GB dung lượng đĩa còn trống cho các image Docker và dữ liệu ban đầu, chưa tính các file được tải lên. Khi bật [giám sát](admin/monitoring.md), cần thêm khoảng 3,6 GB cho image và tối đa 2 GB cho metrics. Cách kiểm tra ở mục [Dung lượng đĩa](#dung-lượng-đĩa).
- Nên có 4 GB RAM cho các service, hoặc 5 GB khi bật giám sát. Tường lửa ứng dụng web dùng khoảng 300 MB trong số này, vì mỗi worker của APISIX giữ một bản Coraza. Máy có 2 GB RAM chạy được khi có thêm ít nhất 2 GB swap, như mục [Swap](#swap). Máy có 1 GB RAM không được hỗ trợ, vì Keycloak và ClamAV khởi động quá thời hạn của healthcheck.

### Dung lượng đĩa

Kiểm tra dung lượng còn trống của thư mục gốc:

```bash
df -h /
```

Bộ cài Ubuntu Server dùng LVM và thường chỉ cấp khoảng một nửa đĩa cho thư mục gốc. Cột `VFree` của lệnh sau cho biết phần đĩa chưa được cấp:

```bash
sudo vgs
```

Nếu `VFree` lớn hơn 0, cấp toàn bộ phần còn lại cho thư mục gốc. Thay `/dev/mapper/ubuntu--vg-ubuntu--lv` bằng giá trị ở cột `Filesystem` của lệnh `df -h /`:

```bash
sudo lvextend --resizefs --extents +100%FREE /dev/mapper/ubuntu--vg-ubuntu--lv
```

### Swap

Kiểm tra swap hiện có:

```bash
swapon --show
```

Máy có 2 GB RAM cần tổng swap từ 2 GB trở lên. Nếu chưa đủ, tạo thêm một file swap 2 GB:

```bash
sudo fallocate --length 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Dòng cuối giúp swap vẫn được bật sau khi khởi động lại máy.

## Các bước cài đặt

Việc cài đặt chỉ cần pip và Docker Compose. Mọi cấu hình đều có giá trị mặc định. Do đó, không cần chỉnh sửa file cấu hình nào.

### 1. Cài đặt package `saigonos`

Nên cài đặt trong một môi trường riêng, ví dụ môi trường conda. Máy chưa có conda thì cài Miniforge trước:

```bash
curl -fsSLO "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
bash "Miniforge3-$(uname)-$(uname -m).sh" -b
~/miniforge3/bin/conda init bash
exec bash
```

Sau đó tạo môi trường và cài đặt package:

```bash
conda create -n saigonos python=3.12
conda activate saigonos
git clone https://github.com/tynnpdhsp/SaigonOS.git
cd SaigonOS
pip install .
```

Mã nguồn của từng phiên bản cũng có ở trang [Releases](https://github.com/tynnpdhsp/SaigonOS/releases). Tải file `saigonos-X.Y.Z.tar.gz`, giải nén rồi chạy `pip install .` trong thư mục vừa giải nén.

Lệnh `saigonos` chỉ có trong môi trường `saigonos`. Mỗi lần mở terminal mới, chạy `conda activate saigonos` trước khi dùng lệnh `saigonos`. Nếu không, terminal báo `saigonos: command not found`.

### 2. Tạo thư mục làm việc

```bash
saigonos init
```

Lệnh này tạo thư mục làm việc `~/saigonos`. Thư mục bao gồm file `compose.yaml`, thư mục `config`, thư mục `apps` chứa các ứng dụng và file `.env`. File `.env` chứa các mật khẩu được tạo ngẫu nhiên.

Hệ thống dùng các cổng 9080, 9180, 9280, 9380 và 9480. Nếu một trong các cổng này đang được chương trình khác sử dụng, hãy chọn cổng khác theo mục [Cấu hình](admin/configuration.md).

### 3. Khởi động các service

```bash
saigonos up
```

Ở lần chạy đầu tiên, Docker tải các image nên lệnh mất vài phút. Ở những lần sau, lệnh mất khoảng một phút.

### 4. Kiểm tra hệ thống

```bash
saigonos doctor
```

Khi mọi service hoạt động bình thường, lệnh in ra kết quả sau:

```text
BÌNH THƯỜNG    apisix        đang chạy
BÌNH THƯỜNG    centrifugo    đang chạy
BÌNH THƯỜNG    clamav        đang chạy
BÌNH THƯỜNG    core          đang chạy
BÌNH THƯỜNG    databases     đã chạy xong
BÌNH THƯỜNG    etcd          đang chạy
BÌNH THƯỜNG    freshclam     đang chạy
BÌNH THƯỜNG    jwks          đã chạy xong
BÌNH THƯỜNG    keycloak      đang chạy
BÌNH THƯỜNG    migrate       đã chạy xong
BÌNH THƯỜNG    opa           đang chạy
BÌNH THƯỜNG    operaton      đang chạy
BÌNH THƯỜNG    policies      đã chạy xong
BÌNH THƯỜNG    postgres      đang chạy
BÌNH THƯỜNG    postgrest     đang chạy
BÌNH THƯỜNG    processes     đã chạy xong
BÌNH THƯỜNG    realm         đã chạy xong
BÌNH THƯỜNG    routes        đã chạy xong
BÌNH THƯỜNG    seaweedfs     đang chạy
BÌNH THƯỜNG    waf           đã chạy xong
BÌNH THƯỜNG    Đăng nhập     Keycloak trả lời tại http://localhost:9080/auth
BÌNH THƯỜNG    API           PostgREST trả lời, access token không hợp lệ bị từ chối
BÌNH THƯỜNG    Core API      service core trả lời, access token không hợp lệ bị từ chối
BÌNH THƯỜNG    Operaton      Operaton chuyển tới trang đăng nhập, REST của Operaton bị chặn
BÌNH THƯỜNG    Centrifugo    Centrifugo nhận kết nối WebSocket, API của Centrifugo bị chặn
BÌNH THƯỜNG    Tường lửa     API Gateway chặn lời gọi có dấu hiệu tấn công
Hệ thống hoạt động bình thường.
```

Khi đã cài đặt ứng dụng, lệnh có thêm một dòng cho mỗi ứng dụng trong thư mục `apps`. Dòng này kiểm tra API của ứng dụng tại `/apps/<tên ứng dụng>/api/` và giao diện tại `/apps/<tên ứng dụng>/` khi bản khai có thư mục `ui`.

## Truy cập hệ thống

Với cấu hình mặc định, hệ thống chỉ truy cập được từ chính máy cài đặt và có các địa chỉ sau:

| Địa chỉ | Nội dung | Thông tin đăng nhập |
|---|---|---|
| http://localhost:9080/auth/admin/saigonos/console/ | Admin Console của realm `saigonos`, dùng để quản lý người dùng | Tài khoản quản trị của realm `saigonos`, đăng nhập bằng mật khẩu và OTP. Cách tạo tài khoản được trình bày ở mục [Tài khoản quản trị](#tài-khoản-quản-trị) |
| http://localhost:9080/operaton/ | Cockpit, Tasklist và Admin của [Operaton](admin/operaton.md), dùng để theo dõi và quản lý các quy trình | Tài khoản quản trị của realm `saigonos`, đăng nhập bằng mật khẩu và OTP |
| http://localhost:9080/grafana/ | Grafana, dùng để xem metrics và log của hệ thống khi [giám sát](admin/monitoring.md) được bật | Tài khoản quản trị của realm `saigonos`, đăng nhập bằng mật khẩu và OTP |
| http://localhost:9280/auth/admin/master/console/ | Admin Console của realm master, chỉ truy cập được từ chính máy cài đặt | Tài khoản `admin`, mật khẩu là giá trị `KEYCLOAK_ADMIN_PASSWORD` |
| http://127.0.0.1:9180/ui/ | Dashboard của APISIX, chỉ truy cập được từ chính máy cài đặt | Khóa quản trị (Admin Key) là giá trị `APISIX_ADMIN_KEY` |
| http://127.0.0.1:9380/ | Admin UI của SeaweedFS, dùng để xem các bucket và file, chỉ truy cập được từ chính máy cài đặt | Tài khoản `admin`, mật khẩu là giá trị `SEAWEEDFS_ADMIN_PASSWORD` |
| http://127.0.0.1:9480/ | Admin web của Centrifugo, dùng để xem số kết nối và gọi thử API của server, chỉ truy cập được từ chính máy cài đặt | Mật khẩu là giá trị `CENTRIFUGO_ADMIN_PASSWORD` |
| http://localhost:9080/api/ | REST API của PostgREST và [tài liệu API](reference/api.md#rest-api-của-dữ-liệu) | Access token do Keycloak cấp. Lời gọi không có access token chỉ dùng được các bảng và hàm đã cấp cho role `anon` |
| http://localhost:9080/core/openapi.json | Tài liệu OpenAPI của [service core](reference/api.md#api-của-service-core) | Không cần đăng nhập. Các API trong tài liệu cần access token do Keycloak cấp, trừ `/core/health` và [đường dẫn tải về](apps/files.md#tải-file-về) |
| ws://localhost:9080/realtime/connection/websocket | Kết nối WebSocket của Centrifugo, dùng để nhận [cập nhật tức thời](apps/realtime.md) | Access token do Keycloak cấp, gửi trong lệnh connect |
| `http://localhost:9080/apps/<tên ứng dụng>/` | [Giao diện](apps/ui.md) và [API](apps/database.md#gọi-api-của-ứng-dụng) của từng ứng dụng đã cài đặt | Giao diện không cần đăng nhập. API cần access token do client của ứng dụng cấp |

Các giá trị trên nằm trong file `~/saigonos/.env`. Ví dụ, để xem mật khẩu quản trị của Keycloak:

```bash
grep KEYCLOAK_ADMIN_PASSWORD ~/saigonos/.env
```

Mỗi khi hệ thống khởi động, service `realm` đăng nhập Keycloak bằng tài khoản `admin` này để cập nhật realm master và realm `saigonos`. Service này chỉ đăng nhập bằng mật khẩu. Do đó, không xóa tài khoản này và không bật OTP cho tài khoản này. Sau khi đổi mật khẩu của tài khoản trong Admin Console, cần ghi mật khẩu mới vào dòng `KEYCLOAK_ADMIN_PASSWORD` của file `.env`.

## Tài khoản quản trị

Keycloak có hai loại tài khoản quản trị:

- Tài khoản `admin` của realm master có toàn quyền trên Keycloak. Tài khoản này đăng nhập bằng mật khẩu và chỉ dùng được trên chính máy cài đặt.
- Tài khoản quản trị của realm `saigonos` chỉ quản lý được realm `saigonos`, ví dụ người dùng, role và client. Tài khoản này đăng nhập bằng mật khẩu và OTP, dùng được từ mọi máy. Nên dùng loại tài khoản này cho công việc hằng ngày.

### Realm master

API Gateway trả về mã 404 cho mọi địa chỉ của realm master. Realm master chỉ mở qua cổng 9280 của Keycloak trên chính máy cài đặt. Realm master khóa tạm một tài khoản sau nhiều lần đăng nhập sai. Mỗi khi hệ thống khởi động, service `realm` bật lại tính năng này nếu tính năng đã bị tắt.

Để mở Admin Console của realm master từ một máy khác, tạo SSH tunnel tới máy cài đặt. Thay `ubuntu@dx.example.com` bằng tài khoản SSH và địa chỉ của máy cài đặt.

```bash
ssh -L 9280:127.0.0.1:9280 ubuntu@dx.example.com
```

Sau đó, mở địa chỉ http://localhost:9280/auth/admin/master/console/ trên máy đang dùng. Cổng trên máy đang dùng cũng phải là 9280, vì Keycloak tạo các địa chỉ của realm master theo cổng này.

Trên máy chủ có tên miền, có thể kiểm tra realm master từ một máy khác bằng lệnh sau. Kết quả đúng là `404`.

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://dx.example.com/auth/realms/master
```

### Tạo tài khoản quản trị của realm saigonos

Tài khoản quản trị của realm `saigonos` có realm role `admin`. Các lệnh sau dùng công cụ `kcadm.sh` có sẵn trong container của Keycloak. Thay `quantri` và các thông tin đi kèm bằng giá trị thật.

```bash
cd ~/saigonos
docker compose exec keycloak /opt/keycloak/bin/kcadm.sh config credentials --server http://localhost:8080/auth --realm master --user admin
docker compose exec keycloak /opt/keycloak/bin/kcadm.sh create users -r saigonos -s username=quantri -s email=quantri@example.com -s firstName=Quản -s lastName=Trị -s enabled=true -s 'requiredActions=["CONFIGURE_TOTP"]'
docker compose exec keycloak /opt/keycloak/bin/kcadm.sh set-password -r saigonos --username quantri
docker compose exec keycloak /opt/keycloak/bin/kcadm.sh add-roles -r saigonos --uusername quantri --rolename admin
```

Lệnh thứ hai hỏi mật khẩu của tài khoản `admin`, tức giá trị `KEYCLOAK_ADMIN_PASSWORD`. Lệnh thứ tư hỏi mật khẩu cho tài khoản mới.

Sau đó, mở địa chỉ http://localhost:9080/auth/admin/saigonos/console/ và đăng nhập bằng tài khoản mới. Trên máy chủ có tên miền, địa chỉ này có dạng `https://dx.example.com/auth/admin/saigonos/console/`. Ở lần đăng nhập đầu tiên, Keycloak yêu cầu cài đặt OTP. Hãy quét mã QR bằng một ứng dụng xác thực, ví dụ FreeOTP hoặc Google Authenticator, rồi nhập mã gồm 6 chữ số. Từ lần sau, tài khoản đăng nhập bằng mật khẩu và mã OTP.

Keycloak không ghi mã OTP của lần cài đặt vào access token. Do đó, ngay sau khi cài đặt OTP, Admin Console báo lỗi khi gọi Admin REST API qua API Gateway. Hãy đăng xuất rồi đăng nhập lại bằng mật khẩu và mã OTP, như mục [Trang quản trị](admin/access-rules.md#trang-quản-trị).

Trước khi cài đặt OTP, tài khoản chưa lấy được access token. Tuy vậy, người nào biết mật khẩu cũng có thể đăng nhập lần đầu và cài đặt OTP cho tài khoản. Do đó, hãy đăng nhập lần đầu ngay sau khi tạo tài khoản.
