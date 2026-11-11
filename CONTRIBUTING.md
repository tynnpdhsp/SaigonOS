<!-- SPDX-License-Identifier: Apache-2.0 -->
# Đóng góp cho SaigonOS

Cảm ơn bạn đã quan tâm đến SaigonOS. Mọi đóng góp đi qua Issue và pull request trên GitHub.

## Báo lỗi và đề xuất

Mở [Issue](https://github.com/tynnpdhsp/SaigonOS/issues/new/choose) rồi chọn mẫu phù hợp. Lỗ hổng bảo mật thì không mở Issue, hãy làm theo [SECURITY.md](SECURITY.md).

## Chuẩn bị môi trường

Cần Python 3.11 trở lên, Git và make.

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

Lệnh này chạy `reuse lint`, `ruff`, so bảng giấy phép và chạy `pytest` có đo độ phủ. Muốn tự sửa định dạng mã thì chạy `make format`.

## Quy ước

- Mỗi tệp mới mở đầu bằng một dòng `SPDX-License-Identifier` với giá trị `Apache-2.0`, viết trong chú thích của loại tệp đó.
- Tính năng mới phải kèm kiểm thử.
- Commit viết một dòng theo [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/), ví dụ `feat(cli): thêm lệnh doctor`.
- Mỗi thay đổi làm trên một nhánh riêng rồi mở pull request vào `main`. CI xanh mới được merge.
- Thay đổi mà người dùng thấy được thì ghi vào mục "Chưa phát hành" của [CHANGELOG.md](CHANGELOG.md).

## Thêm thư viện

Chỉ dùng thư viện có giấy phép nguồn mở được OSI công nhận. Không chép mã của dự án khác vào kho.

1. Khai thư viện trong `pyproject.toml`.
2. Chạy `make lock` để sinh lại tệp khóa.
3. Chạy `pip install -r requirements-dev.txt` để cài đúng phiên bản đã khóa.
4. Chạy `make third-party` để sinh lại [THIRD-PARTY.md](THIRD-PARTY.md).

Bước 4 báo "Giấy phép lạ" khi giấy phép của thư viện chưa nằm trong danh sách cho phép ở `scripts/third_party.py`. Lúc đó hãy mở Issue để bàn trước khi thêm.

## Phát hành

Phần này dành cho người giữ kho.

1. Đổi `version` trong `pyproject.toml` thành số phiên bản mới rồi chạy lại `pip install --no-deps -e .`.
2. Trong [CHANGELOG.md](CHANGELOG.md), đổi mục "Chưa phát hành" thành `## [X.Y.Z] - YYYY-MM-DD`. Thêm một mục "Chưa phát hành" trống lên trên và sửa các đường dẫn ở cuối tệp.
3. Mở pull request, chờ CI xanh rồi merge.
4. Gắn thẻ trên `main` rồi đẩy thẻ:

```bash
git switch main
git pull
git tag vX.Y.Z
git push origin vX.Y.Z
```

CI sẽ chạy lại mọi kiểm tra, đóng gói `saigonos-X.Y.Z.tar.gz` kèm `SHA256SUMS`, lập bản nháp, đính tệp rồi công bố. Bản đã công bố không sửa được. Vì vậy chỉ đẩy thẻ khi CI trên `main` đã xanh.

## Giấy phép của phần đóng góp

Phần bạn đóng góp được phát hành theo giấy phép Apache-2.0, giống phần còn lại của dự án.
