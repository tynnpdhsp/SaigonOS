<!-- SPDX-License-Identifier: Apache-2.0 -->
# SaigonOS

SaigonOS là hệ điều hành chuyển đổi số (DX-OS) nguồn mở. Phần lõi được ghép từ phần mềm nguồn mở và không có giao diện cho người dùng cuối. Ứng dụng chỉ cần viết giao diện rồi gọi vào lõi.

Lõi lo sẵn bốn việc:

- Đăng nhập một lần (SSO)
- Cổng API (API Gateway)
- Quản lý dữ liệu dạng bảng và dạng tệp
- Quy trình

Dự án đang dựng khung và chưa có bản phát hành. Thay đổi được ghi ở [CHANGELOG.md](CHANGELOG.md).

## Cài từ mã nguồn

Cần Python 3.11 trở lên. Nên cài trong một môi trường riêng, ví dụ conda:

```bash
conda create -n saigonos python=3.12
conda activate saigonos
git clone https://github.com/tynnpdhsp/SaigonOS.git
cd SaigonOS
pip install .
saigonos --version
```

## Tham gia

- Báo lỗi hoặc đề xuất: mở [Issue](https://github.com/tynnpdhsp/SaigonOS/issues/new/choose).
- Đóng góp mã: xem [CONTRIBUTING.md](CONTRIBUTING.md).
- Báo lỗ hổng bảo mật: xem [SECURITY.md](SECURITY.md).

## Giấy phép

SaigonOS phát hành theo giấy phép [Apache-2.0](LICENSE). Mỗi tệp trong kho có một dòng `SPDX-License-Identifier` ở đầu và được kiểm bằng [REUSE](https://reuse.software/).

Thư viện bên thứ ba và giấy phép của từng thư viện được kê ở [THIRD-PARTY.md](THIRD-PARTY.md).
