<!-- SPDX-License-Identifier: Apache-2.0 -->
# Thư viện và gói phụ thuộc

File này liệt kê các thư viện, phần mềm và công cụ mà SaigonOS sử dụng. Mỗi dòng ghi phiên bản, giấy phép, mô tả và nguồn. File do lệnh `make dependencies` tạo ra từ các lock file, các thư viện đã cài đặt và file `compose.yaml`. Không sửa trực tiếp file này.

## Thư viện đi kèm sản phẩm

Các thư viện này được cài đặt cùng SaigonOS. Danh sách được lấy từ `requirements.txt`, kể cả phụ thuộc gián tiếp.

| Thư viện | Phiên bản | Giấy phép | Mô tả | Nguồn |
|---|---|---|---|---|
| click | 8.5.1 | BSD-3-Clause | Xây dựng giao diện dòng lệnh cho lệnh `saigonos` | https://pypi.org/project/click/8.5.1/ |

## Thư viện của service `core`

Các thư viện này được cài đặt vào image của service `core` khi Docker Compose build image trên máy cài đặt. Danh sách được lấy từ `src/saigonos/stack/core/requirements.txt`, kể cả phụ thuộc gián tiếp. Lock file này ghi mã băm của từng file. Khi cài đặt, pip từ chối file có mã băm khác.

| Thư viện | Phiên bản | Giấy phép | Mô tả | Nguồn |
|---|---|---|---|---|
| annotated-doc | 0.0.6 | MIT | Phụ thuộc gián tiếp | https://pypi.org/project/annotated-doc/0.0.6/ |
| annotated-types | 0.8.0 | MIT | Phụ thuộc gián tiếp | https://pypi.org/project/annotated-types/0.8.0/ |
| anyio | 4.16.0 | MIT | Phụ thuộc gián tiếp | https://pypi.org/project/anyio/4.16.0/ |
| asyncpg | 0.32.0 | Apache-2.0 | Kết nối service `core` với PostgreSQL | https://pypi.org/project/asyncpg/0.32.0/ |
| cffi | 2.1.1 | MIT-0 | Phụ thuộc gián tiếp | https://pypi.org/project/cffi/2.1.1/ |
| click | 8.5.1 | BSD-3-Clause | Phụ thuộc gián tiếp | https://pypi.org/project/click/8.5.1/ |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | Phụ thuộc gián tiếp | https://pypi.org/project/cryptography/50.0.2/ |
| fastapi | 0.163.1 | MIT | Xây dựng REST API của service `core` | https://pypi.org/project/fastapi/0.163.1/ |
| h11 | 0.16.0 | MIT | Phụ thuộc gián tiếp | https://pypi.org/project/h11/0.16.0/ |
| idna | 3.20 | BSD-3-Clause | Phụ thuộc gián tiếp | https://pypi.org/project/idna/3.20/ |
| opentelemetry-api | 1.45.2 | Apache-2.0 | Phụ thuộc gián tiếp | https://pypi.org/project/opentelemetry-api/1.45.2/ |
| pycparser | 3.12 | BSD-3-Clause | Phụ thuộc gián tiếp | https://pypi.org/project/pycparser/3.12/ |
| pydantic | 2.14.3 | MIT | Phụ thuộc gián tiếp | https://pypi.org/project/pydantic/2.14.3/ |
| pydantic-core | 2.50.4 | MIT | Phụ thuộc gián tiếp | https://pypi.org/project/pydantic-core/2.50.4/ |
| pyjwt | 2.15.1 | MIT | Kiểm tra chữ ký và thời hạn của access token | https://pypi.org/project/pyjwt/2.15.1/ |
| starlette | 1.10.0 | BSD-3-Clause | Phụ thuộc gián tiếp | https://pypi.org/project/starlette/1.10.0/ |
| typing-extensions | 4.16.0 | PSF-2.0 | Phụ thuộc gián tiếp | https://pypi.org/project/typing-extensions/4.16.0/ |
| typing-inspection | 0.4.5 | MIT | Phụ thuộc gián tiếp | https://pypi.org/project/typing-inspection/0.4.5/ |
| uvicorn | 0.54.0 | BSD-3-Clause | Chạy service `core` trong container | https://pypi.org/project/uvicorn/0.54.0/ |

## Phần mềm chạy trong container

Các phần mềm này chạy trong container riêng. Danh sách image được lấy từ file `src/saigonos/stack/compose.yaml` và dòng `FROM` của file `src/saigonos/stack/core/Dockerfile`. Image không ghi địa chỉ máy chủ được tải từ Docker Hub.

Cột giấy phép ghi giấy phép của phần mềm chính trong image. Giấy phép được kiểm tra tại mã nguồn của đúng phiên bản đó. Địa chỉ mã nguồn nằm ở cột nguồn. Hệ điều hành nền và các thư viện khác trong image giữ giấy phép riêng.

| Image | Phiên bản | Giấy phép | Mô tả | Nguồn |
|---|---|---|---|---|
| apache/apisix | 3.19.0-ubuntu | Apache-2.0 | Làm API Gateway cho mọi lời gọi từ bên ngoài | https://github.com/apache/apisix/tree/3.19.0 |
| busybox | 1.38.0-musl | GPL-2.0-only | Cung cấp lệnh wget tĩnh cho healthcheck của Loki khi giám sát được bật | https://busybox.net/downloads/busybox-1.38.0.tar.bz2 |
| caddy | 2.11.9-alpine | Apache-2.0 | Làm reverse proxy HTTPS và tự động lấy chứng chỉ khi được bật | https://github.com/caddyserver/caddy/tree/v2.11.9 |
| centrifugo/centrifugo | v6.10.3 | Apache-2.0 | Gửi cập nhật tức thời tới ứng dụng qua WebSocket | https://github.com/centrifugal/centrifugo/tree/v6.10.3 |
| chrislusf/seaweedfs | 4.54 | Apache-2.0 | Lưu file của các ứng dụng theo chuẩn S3 | https://github.com/seaweedfs/seaweedfs/tree/4.54 |
| clamav/clamav-debian | 1.5.4 | GPL-2.0-only | Quét mã độc trong file được tải lên | https://github.com/Cisco-Talos/clamav/tree/clamav-1.5.4 |
| grafana/alloy | v1.22.0 | Apache-2.0 | Đọc log của các container và gửi tới Loki khi giám sát được bật | https://github.com/grafana/alloy/tree/v1.22.0 |
| grafana/grafana | 13.3.1 | AGPL-3.0-only | Hiển thị bảng theo dõi, metrics và log khi giám sát được bật | https://github.com/grafana/grafana/tree/v13.3.1 |
| grafana/loki | 3.7.10 | AGPL-3.0-only | Lưu log của các service khi giám sát được bật | https://github.com/grafana/loki/tree/v3.7.10 |
| openpolicyagent/opa | 1.22.4 | Apache-2.0 | Kiểm tra luật truy cập chung trước khi API Gateway chuyển lời gọi đi | https://github.com/open-policy-agent/opa/tree/v1.22.4 |
| operaton/operaton | 2.2.1 | Apache-2.0 | Chạy các quy trình BPMN, có Cockpit, Tasklist và Admin | https://github.com/operaton/operaton/tree/v2.2.1 |
| postgres | 18.6-alpine | PostgreSQL | Lưu dữ liệu của Keycloak và của các ứng dụng | https://github.com/postgres/postgres/tree/REL_18_6 |
| postgrest/postgrest | v16.5 | MIT | Tạo REST API từ cơ sở dữ liệu PostgreSQL | https://github.com/PostgREST/postgrest/tree/v16.5 |
| prom/prometheus | v3.16.0 | Apache-2.0 | Thu và lưu metrics của các service khi giám sát được bật | https://github.com/prometheus/prometheus/tree/v3.16.0 |
| python | 3.14.10-slim-trixie | Python-2.0.1 | Làm base image của service `core` | https://github.com/python/cpython/tree/v3.14.10 |
| quay.io/coreos/etcd | v3.6.16 | Apache-2.0 | Lưu cấu hình của APISIX | https://github.com/etcd-io/etcd/tree/v3.6.16 |
| quay.io/keycloak/keycloak | 26.8.2 | Apache-2.0 | Quản lý định danh và đăng nhập một lần | https://github.com/keycloak/keycloak/tree/26.8.2 |
| wollomatic/socket-proxy | 1.13.2 | MIT AND Apache-2.0 | Cho Alloy và exporter chỉ đọc Docker API khi giám sát được bật | https://github.com/wollomatic/socket-proxy/tree/1.13.2 |

## Plugin của API Gateway

Plugin này không nằm trong image nào. Service `waf` tải file zip của plugin từ trang Releases của dự án, kiểm tra mã băm SHA-256 của file zip và của file `.wasm`, rồi đưa file `.wasm` cho APISIX. Phiên bản và hai mã băm được ghi trong service `waf` của file `src/saigonos/stack/compose.yaml`.

| Plugin | Phiên bản | Giấy phép | Mô tả | Nguồn |
|---|---|---|---|---|
| coraza-proxy-wasm | 0.6.0 | Apache-2.0 | Chặn tấn công web ở API Gateway. File .wasm gồm Coraza 3.3.3 và bộ luật OWASP CRS 4.14.0, cả hai theo giấy phép Apache-2.0 | https://github.com/corazawaf/coraza-proxy-wasm/tree/0.6.0 |

## Công cụ phát triển

Các công cụ này chỉ dùng khi phát triển và khi chạy CI. Chúng không được cài đặt cùng SaigonOS. Bảng chỉ liệt kê công cụ khai báo trực tiếp trong `pyproject.toml`. Phụ thuộc gián tiếp của chúng nằm trong `requirements-dev.txt`.

| Công cụ | Phiên bản | Giấy phép | Mô tả | Nguồn |
|---|---|---|---|---|
| httpx2 | 2.16.2 | BSD-3-Clause | Gọi service `core` trong kiểm thử | https://pypi.org/project/httpx2/2.16.2/ |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | Đọc và so sánh số phiên bản | https://pypi.org/project/packaging/26.3/ |
| pip-licenses | 5.5.5 | MIT | Đọc giấy phép của các thư viện đã cài đặt | https://pypi.org/project/pip-licenses/5.5.5/ |
| pytest | 9.2.0 | MIT | Chạy kiểm thử | https://pypi.org/project/pytest/9.2.0/ |
| pytest-cov | 7.1.0 | MIT | Đo coverage khi chạy kiểm thử | https://pypi.org/project/pytest-cov/7.1.0/ |
| reuse | 6.3.0 | Apache-2.0 AND CC0-1.0 AND CC-BY-SA-4.0 AND GPL-3.0-or-later | Kiểm tra thông tin giấy phép của mọi file | https://pypi.org/project/reuse/6.3.0/ |
| ruff | 0.17.4 | MIT | Kiểm tra lỗi và định dạng mã Python | https://pypi.org/project/ruff/0.17.4/ |
| uv | 0.13.7 | MIT OR Apache-2.0 | Tạo lock file từ `pyproject.toml` | https://pypi.org/project/uv/0.13.7/ |

## Gói đính kèm

- File release `saigonos-X.Y.Z.tar.gz` chỉ chứa mã nguồn của SaigonOS.
- Các thư viện đi kèm sản phẩm được pip tải từ PyPI khi cài đặt.
- Các image ở trên được Docker tải về khi khởi động lần đầu. Trừ image `python`, SaigonOS dùng nguyên image gốc. Việc cấu hình chỉ thực hiện qua biến môi trường và file cấu hình.
- Image `python` là base image của service `core`. Docker Compose build image của service này trên máy cài đặt và dùng pip để cài các thư viện của service `core` từ PyPI. File `Dockerfile` ghi digest của base image. Lock file ghi mã băm của từng thư viện. Do đó, mọi file được tải về khi build đều được đối chiếu mã băm. SaigonOS không phân phối image đã build.
- Plugin của API Gateway được service `waf` tải từ trang Releases của dự án khi khởi động lần đầu, rồi được đối chiếu mã băm. SaigonOS dùng nguyên file của dự án và không phân phối lại file này.
- SaigonOS không sao chép và không sửa mã nguồn của dự án khác.

## Quy tắc về giấy phép

- Mỗi thư viện và phần mềm giữ nguyên giấy phép gốc.
- Thư viện đi kèm sản phẩm và thư viện của service `core` chỉ được dùng các giấy phép Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, MIT, MIT-0 và PSF-2.0.
- Phần mềm chạy trong container và plugin của API Gateway chỉ được dùng các giấy phép AGPL-3.0-only, Apache-2.0, GPL-2.0-only, MIT, PostgreSQL và Python-2.0.1. Các giấy phép này đều được OSI công nhận.
- Phần mềm theo giấy phép GPL-2.0-only và AGPL-3.0-only chỉ được chạy trong container riêng từ image gốc. SaigonOS không sửa mã nguồn của các phần mềm này, chỉ trao đổi với chúng qua kết nối mạng và không phân phối lại image. Do đó, các giấy phép này không ảnh hưởng đến giấy phép Apache-2.0 của SaigonOS. Mã nguồn của đúng phiên bản đang dùng nằm ở cột nguồn.
- Công cụ phát triển được dùng thêm CC-BY-SA-4.0, CC0-1.0 và GPL-3.0-or-later. Các công cụ này không được phân phối cùng SaigonOS nên không ảnh hưởng đến giấy phép Apache-2.0 của dự án.
- Lệnh `make lint` báo lỗi khi gặp giấy phép khác, gặp image hoặc plugin chưa được khai báo hoặc gặp base image chưa ghi digest.
