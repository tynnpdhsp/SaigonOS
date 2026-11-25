<!-- SPDX-License-Identifier: Apache-2.0 -->
# Cập nhật phiên bản

Các thay đổi của từng phiên bản được ghi trong [CHANGELOG.md](https://github.com/tynnpdhsp/SaigonOS/blob/main/CHANGELOG.md). Khi cập nhật, dữ liệu, các mật khẩu trong file `.env` và chứng chỉ của Caddy được giữ nguyên.

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

Nếu cài đặt từ file release, tải file `saigonos-X.Y.Z.tar.gz` của phiên bản mới, giải nén rồi chạy `pip install .` trong thư mục vừa giải nén.

## 3. Cập nhật thư mục làm việc và khởi động lại

```bash
saigonos init
saigonos up
saigonos doctor
```

Lệnh `saigonos init` cập nhật file `compose.yaml` và thư mục `config` theo phiên bản mới. Lệnh này cũng thêm vào file `.env` các giá trị mà phiên bản mới cần, ví dụ mật khẩu của service mới. Lệnh `saigonos up` build lại image của service `core` và tạo lại các container với cấu hình mới. Service `migrate` chạy các file SQL mới của phiên bản để cập nhật cơ sở dữ liệu. Service `realm` thêm các thiết lập mới của phiên bản vào realm `saigonos` của Keycloak.
