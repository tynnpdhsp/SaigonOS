<!-- SPDX-License-Identifier: Apache-2.0 -->
# Phát hành phiên bản mới

Phần này dành cho maintainer của repo.

1. Cập nhật `version` trong [`pyproject.toml`](https://github.com/tynnpdhsp/SaigonOS/blob/main/pyproject.toml) và `__version__` trong [`src/saigonos/stack/core/saigonos_core/__init__.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/core/saigonos_core/__init__.py) thành số phiên bản mới, sau đó chạy lại `pip install --no-deps -e .`.
2. Trong [CHANGELOG.md](https://github.com/tynnpdhsp/SaigonOS/blob/main/CHANGELOG.md), đổi tiêu đề mục "Chưa phát hành" thành `## [X.Y.Z] - YYYY-MM-DD`. Thêm một mục "Chưa phát hành" trống ở phía trên và cập nhật các đường dẫn ở cuối file.
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