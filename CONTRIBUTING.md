<!-- SPDX-License-Identifier: Apache-2.0 -->
# Đóng góp cho SaigonOS

Cảm ơn bạn đã quan tâm đến SaigonOS. Mọi đóng góp được tiếp nhận qua issue và pull request trên GitHub.

## Báo lỗi và đề xuất

Để báo lỗi hoặc đề xuất tính năng, hãy mở một [issue](https://github.com/tynnpdhsp/SaigonOS/issues/new/choose) và chọn mẫu phù hợp. Riêng lỗ hổng bảo mật thì không báo qua issue mà làm theo hướng dẫn trong [SECURITY.md](SECURITY.md).

## Chuẩn bị môi trường

Yêu cầu Python 3.11 trở lên, Git và make.

```bash
git clone https://github.com/tynnpdhsp/SaigonOS.git
cd SaigonOS
conda create -n saigonos python=3.12
conda activate saigonos
pip install -r requirements-dev.txt
pip install --no-deps -e .
```

## Kiểm tra trước khi commit

```bash
make check
```

Lệnh này thực hiện các bước sau:

- Kiểm tra thông tin giấy phép của mọi file bằng `reuse lint`.
- Kiểm tra lỗi và định dạng mã bằng `ruff`.
- Đối chiếu [DEPENDENCIES.md](DEPENDENCIES.md) với lock file và file `compose.yaml`.
- Chạy kiểm thử bằng `pytest` và đo coverage.

Để tự động sửa định dạng mã, chạy `make format`.

## Kiểm thử tích hợp

Kiểm thử tích hợp chạy cả bộ Docker Compose trên máy, do đó cần Docker đang hoạt động. Ở lần chạy đầu tiên, Docker tải các image với tổng dung lượng khoảng 2 GB.

```bash
make integration
```

Lệnh này chạy hai nhóm kiểm thử trong thư mục `tests/integration`. File `test_stack.py` dùng cấu hình mặc định. File `test_caddy.py` bật Caddy với chứng chỉ do Caddy tự cấp. Với mỗi nhóm, lệnh thực hiện các bước sau:

- Tạo một thư mục làm việc tạm bằng `saigonos init` với các cổng còn trống.
- Khởi động hệ thống bằng `saigonos up`.
- Chạy các kiểm thử của nhóm.
- Xóa container và dữ liệu bằng `saigonos down --volumes`.

Nhóm kiểm thử Caddy tạo thêm hai mạng Docker tạm với dải địa chỉ `192.0.2.0/28` và `2001:db8:5a1:9::/64`. Lời gọi từ hai mạng này giả lập máy gọi từ Internet qua IPv4 và IPv6. Do đó, máy chạy kiểm thử cần hỗ trợ IPv6.

Một lượt chạy mất khoảng 5 phút. Lệnh `make check` không chạy các kiểm thử này. CI chạy chúng ở job `integration` của mỗi pull request.

## Quy ước

- Mỗi file mới phải bắt đầu bằng một dòng `SPDX-License-Identifier` với giá trị `Apache-2.0`. Dòng này được viết dưới dạng comment theo cú pháp của loại file đó.
- Tính năng mới phải có kiểm thử đi kèm.
- Mỗi commit message chỉ gồm một dòng theo quy ước [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/). Ví dụ: `feat(cli): thêm lệnh doctor`.
- Mỗi thay đổi được thực hiện trên một branch riêng, sau đó mở pull request vào `main`. Pull request chỉ được merge khi CI chạy thành công.
- Những thay đổi ảnh hưởng đến người dùng được ghi vào mục "Chưa phát hành" của [CHANGELOG.md](CHANGELOG.md).

## Thêm thư viện

Chỉ sử dụng thư viện có giấy phép nguồn mở được OSI công nhận. Không sao chép mã nguồn của dự án khác vào repo.

1. Khai báo thư viện trong `pyproject.toml`.
2. Thêm một mô tả ngắn cho thư viện vào `DESCRIPTIONS` trong `scripts/dependencies.py`.
3. Chạy `make lock` để tạo lại lock file.
4. Chạy `pip install -r requirements-dev.txt` để cài đặt đúng các phiên bản trong lock file.
5. Chạy `make dependencies` để tạo lại [DEPENDENCIES.md](DEPENDENCIES.md).

Ở bước 5, lệnh sẽ báo lỗi "Giấy phép ngoài danh sách cho phép" nếu giấy phép của thư viện chưa có trong danh sách cho phép ở `scripts/dependencies.py`. Khi đó, hãy mở một issue để thảo luận trước khi thêm thư viện.

## Thêm hoặc đổi phiên bản image Docker

Chỉ sử dụng phần mềm có giấy phép nguồn mở được OSI công nhận. Mỗi image phải ghi rõ phiên bản và không dùng tag `latest`.

1. Sửa dòng `image` trong `src/saigonos/stack/compose.yaml`.
2. Đọc file giấy phép trong mã nguồn của đúng phiên bản đó.
3. Khai báo image trong `IMAGES` ở `scripts/dependencies.py`. Mỗi image cần giấy phép, mô tả và địa chỉ mã nguồn của phiên bản đó.
4. Chạy `make dependencies` để tạo lại [DEPENDENCIES.md](DEPENDENCIES.md).

Lệnh `make lint` báo lỗi khi một image trong `compose.yaml` chưa được khai báo. Giấy phép chưa có trong danh sách cho phép cũng bị báo lỗi. Khi đó, hãy mở một issue để thảo luận trước khi thêm image.

## Phát hành phiên bản mới

Phần này dành cho maintainer của repo.

1. Cập nhật `version` trong `pyproject.toml` thành số phiên bản mới, sau đó chạy lại `pip install --no-deps -e .`.
2. Trong [CHANGELOG.md](CHANGELOG.md), đổi tiêu đề mục "Chưa phát hành" thành `## [X.Y.Z] - YYYY-MM-DD`. Thêm một mục "Chưa phát hành" trống ở phía trên và cập nhật các đường dẫn ở cuối file.
3. Mở pull request và merge sau khi CI chạy thành công.
4. Tạo tag trên `main` rồi push tag lên GitHub:

```bash
git switch main
git pull
git tag vX.Y.Z
git push origin vX.Y.Z
```

Khi nhận được tag mới, CI thực hiện các bước sau:

- Chạy lại toàn bộ kiểm tra.
- Đóng gói `saigonos-X.Y.Z.tar.gz` kèm file `SHA256SUMS`.
- Tạo draft release và đính kèm hai file trên.
- Công bố release.

Release sau khi công bố sẽ không thể chỉnh sửa. Do đó, chỉ push tag khi CI trên `main` đã chạy thành công.

## Giấy phép của phần đóng góp

Mọi đóng góp được phát hành theo giấy phép Apache-2.0, giống như phần còn lại của dự án.
