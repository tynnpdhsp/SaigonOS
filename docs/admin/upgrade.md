<!-- SPDX-License-Identifier: Apache-2.0 -->
# Cập nhật phiên bản

Khi cập nhật, dữ liệu, các mật khẩu trong file `.env` và chứng chỉ của Caddy được giữ nguyên. Các thay đổi của từng phiên bản được ghi trong [CHANGELOG.md](https://github.com/tynnpdhsp/SaigonOS/blob/main/CHANGELOG.md).

## 1. Dừng các service

```bash
saigonos down
```

## 2. Cài đặt phiên bản mới của package `saigonos`

Trong thư mục `SaigonOS` đã tạo bằng lệnh `git clone`:

```bash
git pull
pip install .
```

Khi cài đặt từ file release, tải file `saigonos-X.Y.Z.tar.gz` của phiên bản mới, giải nén rồi chạy `pip install .` trong thư mục vừa giải nén.

## 3. Cập nhật thư mục làm việc và khởi động lại

```bash
saigonos init
saigonos up
saigonos doctor
```

Lệnh `saigonos init` cập nhật file `compose.yaml`, thư mục `config` và thêm vào file `.env` các giá trị mà phiên bản mới cần. Lệnh `saigonos up` cập nhật cơ sở dữ liệu, realm của Keycloak và các ứng dụng đã cài đặt theo phiên bản mới.
