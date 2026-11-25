<!-- SPDX-License-Identifier: Apache-2.0 -->
# Quản lý quy trình

SaigonOS dùng Operaton để chạy các quy trình BPMN 2.0. Trang này dành cho người quản trị. Cách viết quy trình cho ứng dụng được trình bày ở trang [Quy trình](../apps/workflow.md).

## Cockpit, Tasklist và Admin

Ba trang Cockpit, Tasklist và Admin của Operaton nằm ở địa chỉ `/operaton/`, ví dụ http://localhost:9080/operaton/. Cockpit dùng để theo dõi các quy trình đang chạy và xử lý incident. Tasklist dùng để xem và xử lý các việc. Admin dùng để quản lý quyền trong Operaton.

Chỉ tài khoản có realm role `admin` đăng nhập được vào ba trang này. Mỗi lần đăng nhập phải nhập mật khẩu và mã OTP, kể cả khi đã đăng nhập vào một trang khác của hệ thống. Tài khoản không có realm role `admin` bị từ chối ngay sau khi nhập mật khẩu. Nội dung thông báo từ chối có khóa `saigonos-operaton-admin-only` và sửa được trong Admin Console của realm `saigonos`, ở mục Realm settings, thẻ Localization, phần Realm overrides.

Khi một tài khoản bị khóa trong Keycloak, phiên đăng nhập của tài khoản trong Operaton kết thúc ngay ở lời gọi tiếp theo. Nút đăng xuất của ba trang chỉ kết thúc phiên của Operaton, nên các ứng dụng khác của hệ thống không bị đăng xuất.

## Tài khoản core

REST API của Operaton không mở qua API Gateway. Chỉ ba service `core`, `processes` và `apps` gọi REST API này, bằng tài khoản `core` của Operaton. Mật khẩu của tài khoản là giá trị `CORE_OPERATON_PASSWORD` trong file `.env`. Operaton tạo tài khoản ở lần khởi động đầu tiên. Do đó, đổi giá trị này về sau không đổi mật khẩu của tài khoản.

Operaton tạm khóa tài khoản sau mỗi lần đăng nhập sai và khóa hẳn sau 10 lần sai liên tiếp. Để tài khoản không bị khóa hẳn, service `core` ngừng gọi Operaton trong 60 giây sau mỗi lần bị từ chối. Sau 5 lần liên tiếp, service ngừng gọi Operaton cho tới khi được khởi động lại. Trong thời gian này, các lời gọi cần Operaton nhận mã 503. Sau khi khôi phục giá trị đúng của `CORE_OPERATON_PASSWORD`, chạy lại `saigonos up`. Nếu giá trị này vốn đúng, khởi động lại service `core`:

```bash
cd ~/saigonos
docker compose restart core
```

## Quy trình của hệ thống

Ngoài quy trình của các ứng dụng, người quản trị có thể đặt file BPMN vào thư mục `~/saigonos/config/operaton/processes`. Mỗi khi hệ thống khởi động, service `processes` triển khai các file trong thư mục này vào Operaton. Do đó, sau khi thêm hoặc sửa một file, cần chạy lại `saigonos up`. Các file tuân theo các quy tắc sau:

- File không thay đổi thì không tạo phiên bản mới của quy trình. File đã sửa tạo một phiên bản mới, còn các quy trình đang chạy vẫn dùng phiên bản cũ.
- Mỗi quy trình phải có thuộc tính `operaton:historyTimeToLive`, tức thời gian giữ lịch sử của quy trình. Ví dụ, giá trị `P30D` là 30 ngày. Mỗi ngày từ 01:00 đến 05:00 giờ Việt Nam, Operaton xóa lịch sử của các quy trình đã kết thúc quá thời gian này.
- Tên file chỉ gồm chữ cái không dấu, chữ số, dấu chấm, dấu gạch ngang, dấu gạch dưới và kết thúc bằng `.bpmn`.
- Mỗi mã quy trình, tức thuộc tính `id` của thẻ `process`, chỉ được khai báo trong một file.
- Xóa một file khỏi thư mục không gỡ quy trình khỏi Operaton.

File trong thư mục này có thể chứa mã chạy bên trong Operaton, ví dụ script task. Do đó, chỉ đặt vào đây các file từ nguồn đáng tin cậy. Khi một file bị lỗi, lệnh `saigonos up` kết thúc với mã lỗi. Kết quả triển khai và lỗi của từng file được xem bằng lệnh sau:

```bash
cd ~/saigonos
docker compose logs --tail 20 processes
```

Ví dụ sau là một quy trình gồm điểm bắt đầu và điểm kết thúc, lưu trong file `thu-nghiem.bpmn`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:operaton="http://operaton.org/schema/1.0/bpmn"
                  id="thu_nghiem_dinh_nghia" targetNamespace="https://dx.example.com/bpmn">
  <bpmn:process id="thu_nghiem" name="Quy trình thử nghiệm" isExecutable="true"
                operaton:historyTimeToLive="P30D">
    <bpmn:startEvent id="bat_dau" />
    <bpmn:sequenceFlow id="luong_1" sourceRef="bat_dau" targetRef="ket_thuc" />
    <bpmn:endEvent id="ket_thuc" />
  </bpmn:process>
</bpmn:definitions>
```

Bước máy làm của quy trình hệ thống gọi hàm được cấp cho role `workflow`, như mục [Bước máy làm](../apps/workflow.md#bước-máy-làm). Role `workflow` cần thêm quyền `USAGE` trên schema và quyền trên các bảng mà hàm dùng. Quy trình của hệ thống không gọi được hàm của ứng dụng.
