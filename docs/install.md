<!-- SPDX-License-Identifier: Apache-2.0 -->
# Cài đặt

Trang này trình bày cách cài đặt SaigonOS trên một máy Linux và cách đăng nhập lần đầu.

## Yêu cầu hệ thống

- Linux. SaigonOS được kiểm thử trên Ubuntu 22.04 và 24.04.
- Python 3.11 trở lên. Ubuntu 22.04 chỉ có Python 3.10, nên cần cài Miniforge như bước 1.
- Docker Engine 25.0 trở lên, Docker Compose 2.20.2 trở lên và Docker Buildx. Tài khoản cài đặt chạy được lệnh `docker` mà không cần `sudo`.
- Git và kết nối Internet.
- 4 GB RAM, hoặc 5 GB khi bật giám sát. Máy có 2 GB RAM cần thêm ít nhất 2 GB swap.
- 6 GB dung lượng ổ cứng còn trống, chưa tính các file được tải lên. Khi bật giám sát, cần thêm khoảng 5,6 GB.

### Dung lượng ổ cứng

Lệnh `df -h /` cho biết dung lượng còn trống của thư mục gốc. Bộ cài Ubuntu Server dùng LVM thường chỉ cấp khoảng một nửa ổ cứng cho thư mục gốc. Phần chưa cấp nằm ở cột `VFree` của lệnh `sudo vgs`. Để cấp phần này cho thư mục gốc, thay đường dẫn trong lệnh sau bằng giá trị ở cột `Filesystem` của lệnh `df -h /`:

```bash
sudo lvextend --resizefs --extents +100%FREE /dev/mapper/ubuntu--vg-ubuntu--lv
```

### Swap

Lệnh `swapon --show` cho biết swap hiện có. Các lệnh sau tạo thêm một file swap 2 GB. Dòng cuối giữ swap sau khi khởi động lại máy.

```bash
sudo fallocate --length 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## Các bước cài đặt

Việc cài đặt chỉ cần pip và Docker Compose. Mọi cấu hình đều có giá trị mặc định. Do đó, không cần sửa file cấu hình nào.

### 1. Cài đặt package `saigonos`

Package nên được cài trong một môi trường conda riêng. Máy chưa có conda thì cài Miniforge trước:

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

Mỗi phiên bản cũng có file `saigonos-X.Y.Z.tar.gz` ở trang [Releases](https://github.com/tynnpdhsp/SaigonOS/releases). Tải file này, giải nén rồi chạy `pip install .` trong thư mục vừa giải nén.

Lệnh `saigonos` chỉ có trong môi trường `saigonos`. Do đó, mỗi lần mở terminal mới cần chạy `conda activate saigonos` trước.

### 2. Tạo thư mục làm việc

```bash
saigonos init
```

Lệnh tạo thư mục làm việc `~/saigonos`, gồm file `compose.yaml`, thư mục `config`, thư mục `apps` chứa các ứng dụng và file `.env` chứa các mật khẩu ngẫu nhiên. Hệ thống dùng các cổng 9080, 9180, 9280, 9380 và 9480. Khi một cổng đã có chương trình khác dùng, chọn cổng khác theo trang [Cấu hình](admin/configuration.md).

### 3. Khởi động các service

```bash
saigonos up
```

Lần chạy đầu tiên mất vài phút để tải các image. Những lần sau mất khoảng một phút.

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

Mỗi ứng dụng đã cài đặt có thêm một dòng. Dòng này kiểm tra API của ứng dụng, và giao diện khi ứng dụng có giao diện.

## Truy cập hệ thống

Với cấu hình mặc định, hệ thống chỉ truy cập được từ chính máy cài đặt, qua các địa chỉ sau:

| Địa chỉ | Nội dung | Đăng nhập |
|---|---|---|
| http://localhost:9080/auth/admin/saigonos/console/ | Admin Console của realm `saigonos`, dùng để quản lý người dùng và role | Tài khoản quản trị của realm `saigonos`, có mã OTP |
| http://localhost:9080/operaton/ | Cockpit, Tasklist và Admin của [Operaton](admin/operaton.md) | Tài khoản quản trị của realm `saigonos`, có mã OTP |
| http://localhost:9080/grafana/ | Grafana, khi bật [giám sát](admin/monitoring.md) | Tài khoản quản trị của realm `saigonos`, có mã OTP |
| http://localhost:9080/api/ | REST API và [tài liệu API](reference/api.md) | Access token do Keycloak cấp. Lời gọi không có access token chỉ dùng được bảng và hàm đã cấp cho role `anon` |
| `http://localhost:9080/apps/<tên ứng dụng>/` | Giao diện và API của từng ứng dụng | Giao diện không cần đăng nhập. API cần access token do client của ứng dụng cấp |
| http://localhost:9280/auth/admin/master/console/ | Admin Console của realm master | Tài khoản `admin`, mật khẩu là giá trị `KEYCLOAK_ADMIN_PASSWORD` |
| http://127.0.0.1:9180/ui/ | Dashboard của APISIX | Khóa quản trị là giá trị `APISIX_ADMIN_KEY` |
| http://127.0.0.1:9380/ | Admin UI của SeaweedFS | Tài khoản `admin`, mật khẩu là giá trị `SEAWEEDFS_ADMIN_PASSWORD` |
| http://127.0.0.1:9480/ | Admin web của Centrifugo | Mật khẩu là giá trị `CENTRIFUGO_ADMIN_PASSWORD` |

Bốn địa chỉ cuối chỉ mở được trên chính máy cài đặt, kể cả khi hệ thống đã mở cho máy khác. Các mật khẩu và khóa nằm trong file `~/saigonos/.env`. Ví dụ, để xem mật khẩu của tài khoản `admin`:

```bash
grep KEYCLOAK_ADMIN_PASSWORD ~/saigonos/.env
```

Mỗi khi hệ thống khởi động, service `realm` dùng tài khoản `admin` để cập nhật hai realm của Keycloak. Do đó, không xóa tài khoản này và không bật OTP cho tài khoản này. Sau khi đổi mật khẩu của tài khoản, cần ghi mật khẩu mới vào dòng `KEYCLOAK_ADMIN_PASSWORD` của file `.env`.

## Tài khoản quản trị

Keycloak có hai loại tài khoản quản trị. Tài khoản `admin` của realm master có toàn quyền và chỉ đăng nhập được trên chính máy cài đặt. Tài khoản quản trị của realm `saigonos` chỉ quản lý được realm `saigonos`, đăng nhập bằng mật khẩu và mã OTP từ mọi máy. Công việc hằng ngày nên dùng loại tài khoản thứ hai.

### Realm master

API Gateway trả về mã 404 cho mọi địa chỉ của realm master. Để mở Admin Console của realm master từ một máy khác, tạo SSH tunnel tới máy cài đặt, với `ubuntu@dx.example.com` là tài khoản SSH và địa chỉ của máy cài đặt:

```bash
ssh -L 9280:127.0.0.1:9280 ubuntu@dx.example.com
```

Sau đó mở địa chỉ http://localhost:9280/auth/admin/master/console/ trên máy đang dùng. Cổng trên máy đang dùng cũng phải là 9280, vì Keycloak tạo các địa chỉ của realm master theo cổng này.

### Tạo tài khoản quản trị của realm saigonos

Tài khoản quản trị của realm `saigonos` có realm role `admin`. Các lệnh sau tạo tài khoản `quantri` bằng công cụ `kcadm.sh` có sẵn trong container của Keycloak:

```bash
cd ~/saigonos
docker compose exec keycloak /opt/keycloak/bin/kcadm.sh config credentials --server http://localhost:8080/auth --realm master --user admin
docker compose exec keycloak /opt/keycloak/bin/kcadm.sh create users -r saigonos -s username=quantri -s email=quantri@example.com -s firstName=Quản -s lastName=Trị -s enabled=true -s 'requiredActions=["CONFIGURE_TOTP"]'
docker compose exec keycloak /opt/keycloak/bin/kcadm.sh set-password -r saigonos --username quantri
docker compose exec keycloak /opt/keycloak/bin/kcadm.sh add-roles -r saigonos --uusername quantri --rolename admin
```

Lệnh thứ hai hỏi mật khẩu của tài khoản `admin`. Lệnh thứ tư hỏi mật khẩu cho tài khoản mới. Sau đó, đăng nhập Admin Console của realm `saigonos` bằng tài khoản mới. Ở lần đăng nhập đầu tiên, Keycloak yêu cầu cài đặt OTP bằng một ứng dụng xác thực, ví dụ FreeOTP hoặc Google Authenticator. Lần đăng nhập này chưa được tính là đăng nhập có OTP. Do đó, sau khi cài đặt OTP, cần đăng xuất rồi đăng nhập lại bằng mật khẩu và mã OTP.

Người biết mật khẩu cũng có thể đăng nhập lần đầu và tự cài đặt OTP cho tài khoản. Do đó, tài khoản mới nên được đăng nhập lần đầu ngay sau khi tạo.
