<!-- SPDX-License-Identifier: Apache-2.0 -->
# Đóng góp cho SaigonOS

Cảm ơn bạn đã quan tâm đến SaigonOS. Mọi đóng góp được tiếp nhận qua issue và pull request trên GitHub.

## Báo lỗi và đề xuất

Để báo lỗi hoặc đề xuất tính năng, mở một [issue](https://github.com/tynnpdhsp/SaigonOS/issues/new/choose) và chọn mẫu phù hợp. Lỗ hổng bảo mật không báo qua issue mà làm theo hướng dẫn trong [SECURITY.md](SECURITY.md).

## Chuẩn bị môi trường

Cần Python 3.11 trở lên, Git, make và Docker.

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

Lệnh này kiểm tra thông tin giấy phép của mọi file bằng `reuse lint`, kiểm tra lỗi và định dạng mã bằng `ruff`, đối chiếu [DEPENDENCIES.md](DEPENDENCIES.md) với các lock file, rồi chạy unit test và test luật OPA. Lệnh `make format` tự sửa định dạng mã.

Integration test chạy cả hệ thống bằng Docker Compose. Mỗi nhóm kiểm thử cần khoảng 3 GB RAM, và một lượt chạy mất khoảng 40 phút. CI chạy các kiểm thử này ở mỗi pull request. Chi tiết được trình bày ở trang [Kiểm thử](docs/development/testing.md).

```bash
make integration
```

## Quy ước

- Mỗi file mới bắt đầu bằng một dòng `SPDX-License-Identifier` với giá trị `Apache-2.0`, viết dưới dạng comment theo cú pháp của loại file đó.
- Tính năng mới có kiểm thử đi kèm.
- Id của kiểm thử có tham số viết bằng chữ thường không dấu, các từ nối với nhau bằng dấu gạch ngang, ví dụ `khoang-trang`. Khi gặp id có chữ có dấu, pytest dừng ngay ở bước thu thập kiểm thử.
- Mỗi commit message chỉ gồm một dòng theo quy ước [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/), ví dụ `feat(cli): thêm lệnh doctor`.
- Mỗi thay đổi được thực hiện trên một branch riêng, rồi mở pull request vào `main`. Pull request chỉ được merge khi CI chạy thành công.
- Thay đổi ảnh hưởng đến người dùng được ghi vào mục "Chưa phát hành" của [CHANGELOG.md](CHANGELOG.md).
- Chỉ dùng thư viện và phần mềm có giấy phép nguồn mở được OSI công nhận. Cách thêm thư viện hoặc đổi phiên bản image được trình bày ở trang [Thư viện và image](docs/development/dependencies.md).

## Tài liệu

Tài liệu nằm trong thư mục [docs](docs/README.md), mỗi trang một chủ đề. Trang mới được thêm vào mục lục `docs/README.md`. Link giữa các trang là link tương đối. Link tới file nằm ngoài thư mục `docs` dùng địa chỉ đầy đủ trên GitHub. Ngoài code, nội dung không dùng các ký tự `<`, `{` và `}`, để các trang dựng được thành trang web bằng Docusaurus. Unit test trong `tests/test_docs.py` kiểm tra các quy tắc này, cùng với các lệnh, giá trị mặc định và trích đoạn của ứng dụng mẫu trong tài liệu.

Các trang trong thư mục `docs/development` ghi những điều cần giữ khi sửa từng phần của lõi. Phần này dành cho người sửa mã của lõi, không cần cho người cài đặt hay viết ứng dụng. Cách phát hành phiên bản mới được trình bày ở trang [Phát hành phiên bản mới](docs/development/release.md).

## Giấy phép của phần đóng góp

Mọi đóng góp được phát hành theo giấy phép Apache-2.0, giống như phần còn lại của dự án.
