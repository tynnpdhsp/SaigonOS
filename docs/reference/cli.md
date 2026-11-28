<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lệnh saigonos

Lệnh `saigonos` có trong môi trường đã cài package `saigonos`, như ở trang [Cài đặt](../install.md). Bảng sau liệt kê các lệnh con của lệnh `saigonos`. Mọi lệnh con làm việc với thư mục làm việc `~/saigonos`. Tùy chọn `--home` hoặc biến môi trường `SAIGONOS_HOME` chọn thư mục khác. Tùy chọn `--help` của mỗi lệnh in đủ các tùy chọn của lệnh đó.

| Lệnh | Việc | Tài liệu |
|---|---|---|
| `init` | Tạo hoặc cập nhật thư mục làm việc | [Cấu hình](../admin/configuration.md) |
| `up` | Khởi động các service và cài đặt lại các ứng dụng đã cài đặt | [Cấu hình](../admin/configuration.md#khởi-động-và-dừng) |
| `down` | Dừng các service | [Cấu hình](../admin/configuration.md#khởi-động-và-dừng) |
| `doctor` | Kiểm tra các service, API Gateway và các ứng dụng | [Cài đặt](../install.md#4-kiểm-tra-hệ-thống) |
| `apply` | Soát và cài đặt một ứng dụng | [Bản khai báo và cài đặt ứng dụng](../apps/manifest.md) |
| `remove` | Gỡ một ứng dụng | [Bản khai báo và cài đặt ứng dụng](../apps/manifest.md#gỡ-ứng-dụng) |
| `audit verify` | Kiểm tra chuỗi mã băm của audit log | [Kiểm tra audit log](../admin/audit-log.md) |
| `backup` | Tạo gói sao lưu | [Sao lưu và khôi phục](../admin/backup.md) |
| `restore` | Khôi phục hệ thống từ một gói sao lưu | [Sao lưu và khôi phục](../admin/backup.md#khôi-phục) |
| `lake run` | Chốt số liệu và lưu trữ dữ liệu cũ ngay | [Hồ dữ liệu](../admin/data-lake.md#hẹn-giờ) |
| `lake query` | Truy vấn hồ dữ liệu bằng SQL của DuckDB | [Hồ dữ liệu](../admin/data-lake.md#truy-vấn-hồ) |
| `lake verify` | Kiểm tra mã băm của các file trong hồ dữ liệu | [Hồ dữ liệu](../admin/data-lake.md#kiểm-tra-mã-băm) |
