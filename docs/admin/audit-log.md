<!-- SPDX-License-Identifier: Apache-2.0 -->
# Kiểm tra audit log

Bảng `core.audit_log` lưu audit log của cơ sở dữ liệu. Với những bảng đã gắn hàm `core.audit()`, mỗi lần một dòng được thêm, sửa hoặc xóa đều được ghi lại. Cách gắn hàm này cho bảng của ứng dụng được trình bày ở trang [Dữ liệu và API](../apps/database.md#file-sql-của-ứng-dụng).

Bảng `core.audit_log` chỉ cho phép thêm dòng, kể cả với role sở hữu bảng. Mỗi dòng mang một mã băm được tính từ nội dung của dòng và mã băm của dòng trước. Do đó, các dòng nối thành một chuỗi.

Để kiểm tra audit log có bị sửa hoặc bị xóa bớt hay không:

```bash
saigonos audit verify
```

Lệnh tính lại mã băm của từng dòng rồi so với mã băm đã lưu. Khi mọi dòng đều khớp, lệnh in ra kết quả sau:

```text
Audit log có 1250 dòng. Chuỗi mã băm khớp.
Mã băm của dòng cuối: 1df5c68192da0b9f077c8e6dd77ad3196de0d1d42fae945e2e31f4ad1c5710f9
```

Khi một dòng đã bị sửa hoặc bị xóa, lệnh chỉ ra dòng sai đầu tiên và kết thúc với mã thoát 1. Ví dụ:

```text
Dòng 57 của audit log không khớp mã băm. Nội dung hoặc mã băm của dòng này đã bị sửa.
```

Lệnh phát hiện được cả dòng bị sửa sau khi superuser của PostgreSQL tắt trigger chặn sửa. Lệnh không phát hiện được hai trường hợp. Trường hợp thứ nhất là các dòng cuối cùng bị xóa. Trường hợp thứ hai là một dòng bị sửa rồi mã băm của mọi dòng sau đó được tính lại. Do đó, sau mỗi lần kiểm tra nên lưu số dòng và mã băm của dòng cuối ở một nơi ngoài máy chủ. Với cùng một số dòng, mã băm của dòng cuối không đổi.
