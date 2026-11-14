<!-- SPDX-License-Identifier: Apache-2.0 -->
# Thư viện và gói phụ thuộc

File này liệt kê các thư viện, phần mềm và công cụ mà SaigonOS sử dụng. Mỗi dòng ghi phiên bản, giấy phép, mô tả và nguồn. File do lệnh `make dependencies` tạo ra từ lock file, các thư viện đã cài đặt và file `compose.yaml`. Không sửa trực tiếp file này.

## Thư viện đi kèm sản phẩm

Các thư viện này được cài đặt cùng SaigonOS. Danh sách được lấy từ `requirements.txt`, kể cả phụ thuộc gián tiếp.

| Thư viện | Phiên bản | Giấy phép | Mô tả | Nguồn |
|---|---|---|---|---|
| click | 8.5.1 | BSD-3-Clause | Xây dựng giao diện dòng lệnh cho lệnh `saigonos` | https://pypi.org/project/click/8.5.1/ |

## Phần mềm chạy trong container

Các phần mềm này chạy trong container riêng. Danh sách image được lấy từ file `src/saigonos/stack/compose.yaml`. Image không ghi địa chỉ máy chủ được tải từ Docker Hub.

Cột giấy phép ghi giấy phép của phần mềm chính trong image. Giấy phép được kiểm tra tại mã nguồn của đúng phiên bản đó. Địa chỉ mã nguồn nằm ở cột nguồn. Hệ điều hành nền và các thư viện khác trong image giữ giấy phép riêng.

| Image | Phiên bản | Giấy phép | Mô tả | Nguồn |
|---|---|---|---|---|
| apache/apisix | 3.19.0-ubuntu | Apache-2.0 | Làm API Gateway cho mọi lời gọi từ bên ngoài | https://github.com/apache/apisix/tree/3.19.0 |
| caddy | 2.11.9-alpine | Apache-2.0 | Làm reverse proxy HTTPS và tự động lấy chứng chỉ khi được bật | https://github.com/caddyserver/caddy/tree/v2.11.9 |
| postgres | 18.6-alpine | PostgreSQL | Lưu dữ liệu của Keycloak và của các ứng dụng | https://github.com/postgres/postgres/tree/REL_18_6 |
| postgrest/postgrest | v16.5 | MIT | Tạo REST API từ cơ sở dữ liệu PostgreSQL | https://github.com/PostgREST/postgrest/tree/v16.5 |
| quay.io/coreos/etcd | v3.6.16 | Apache-2.0 | Lưu cấu hình của APISIX | https://github.com/etcd-io/etcd/tree/v3.6.16 |
| quay.io/keycloak/keycloak | 26.8.2 | Apache-2.0 | Quản lý định danh và đăng nhập một lần | https://github.com/keycloak/keycloak/tree/26.8.2 |

## Công cụ phát triển

Các công cụ này chỉ dùng khi phát triển và khi chạy CI. Chúng không được cài đặt cùng SaigonOS. Bảng chỉ liệt kê công cụ khai báo trực tiếp trong `pyproject.toml`. Phụ thuộc gián tiếp của chúng nằm trong `requirements-dev.txt`.

| Công cụ | Phiên bản | Giấy phép | Mô tả | Nguồn |
|---|---|---|---|---|
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | Đọc và so sánh số phiên bản | https://pypi.org/project/packaging/26.3/ |
| pip-licenses | 5.5.5 | MIT | Đọc giấy phép của các thư viện đã cài đặt | https://pypi.org/project/pip-licenses/5.5.5/ |
| pytest | 9.2.0 | MIT | Chạy kiểm thử | https://pypi.org/project/pytest/9.2.0/ |
| pytest-cov | 7.1.0 | MIT | Đo coverage khi chạy kiểm thử | https://pypi.org/project/pytest-cov/7.1.0/ |
| reuse | 6.3.0 | Apache-2.0 AND CC0-1.0 AND CC-BY-SA-4.0 AND GPL-3.0-or-later | Kiểm tra thông tin giấy phép của mọi file | https://pypi.org/project/reuse/6.3.0/ |
| ruff | 0.17.4 | MIT | Kiểm tra lỗi và định dạng mã Python | https://pypi.org/project/ruff/0.17.4/ |
| uv | 0.13.7 | MIT OR Apache-2.0 | Tạo lock file từ `pyproject.toml` | https://pypi.org/project/uv/0.13.7/ |

## Gói đính kèm

- File release `saigonos-X.Y.Z.tar.gz` chỉ chứa mã nguồn của SaigonOS.
- Các thư viện ở trên được pip tải từ PyPI khi cài đặt.
- Các image ở trên được Docker tải về khi khởi động lần đầu. SaigonOS dùng nguyên image gốc. Việc cấu hình chỉ thực hiện qua biến môi trường và file cấu hình.
- SaigonOS không sao chép và không sửa mã nguồn của dự án khác.

## Quy tắc về giấy phép

- Mỗi thư viện và phần mềm giữ nguyên giấy phép gốc.
- Thư viện đi kèm sản phẩm chỉ được dùng các giấy phép Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, MIT và PSF-2.0.
- Phần mềm chạy trong container chỉ được dùng các giấy phép Apache-2.0, MIT và PostgreSQL. Các giấy phép này đều được OSI công nhận.
- Công cụ phát triển được dùng thêm CC-BY-SA-4.0, CC0-1.0 và GPL-3.0-or-later. Các công cụ này không được phân phối cùng SaigonOS nên không ảnh hưởng đến giấy phép Apache-2.0 của dự án.
- Lệnh `make lint` báo lỗi khi gặp giấy phép khác hoặc gặp image chưa được khai báo.
