<!-- SPDX-License-Identifier: Apache-2.0 -->
# Kiểm tra audit log

Bảng `core.audit_log` của cơ sở dữ liệu lưu audit log. Với những bảng đã gắn hàm `core.audit()`, mỗi lần một dòng được thêm, sửa hoặc xóa đều được ghi lại. Cách gắn hàm này cho một bảng được trình bày trong [CONTRIBUTING.md](https://github.com/tynnpdhsp/SaigonOS/blob/main/CONTRIBUTING.md#ghi-audit-log-cho-bảng).

Bảng `core.audit_log` chỉ cho phép thêm dòng. Các lệnh `UPDATE`, `DELETE` và `TRUNCATE` trên bảng này bị từ chối, kể cả với role sở hữu bảng. Mỗi dòng audit log mang một mã băm được tính từ nội dung của dòng và mã băm của dòng trước. Do đó, các dòng nối thành một chuỗi.

Để kiểm tra audit log có bị sửa hoặc bị xóa bớt hay không:

```bash
saigonos audit verify
```

Lệnh này tính lại mã băm của từng dòng và so sánh với mã băm đã lưu. Khi mọi dòng đều khớp, lệnh in ra kết quả sau:

```text
Audit log có 1250 dòng. Chuỗi mã băm khớp.
Mã băm của dòng cuối: 1df5c68192da0b9f077c8e6dd77ad3196de0d1d42fae945e2e31f4ad1c5710f9
```

Khi một dòng đã bị sửa hoặc bị xóa, lệnh chỉ ra dòng sai đầu tiên và kết thúc với mã thoát 1. Ví dụ:

```text
Dòng 57 của audit log không khớp mã băm. Nội dung hoặc mã băm của dòng này đã bị sửa.
```

Tài khoản superuser của PostgreSQL vẫn tắt được trigger chặn sửa và xóa. Lệnh `saigonos audit verify` phát hiện các dòng đã bị sửa hoặc bị xóa theo cách này. Lệnh tự tính mã băm và không dùng hàm lưu trong cơ sở dữ liệu.

Lệnh không phát hiện được hai trường hợp. Trường hợp thứ nhất là các dòng cuối cùng bị xóa. Trường hợp thứ hai là một dòng bị sửa và mã băm của mọi dòng từ đó về sau được tính lại. Trong cả hai trường hợp, các dòng còn lại vẫn nối đúng với nhau. Do đó, nên lưu kết quả của lệnh ở một nơi ngoài máy chủ sau mỗi lần kiểm tra. Số dòng của audit log chỉ tăng. Với cùng một số dòng, mã băm của dòng cuối không đổi.
