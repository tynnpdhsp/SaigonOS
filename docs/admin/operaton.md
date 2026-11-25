<!-- SPDX-License-Identifier: Apache-2.0 -->
# Quản lý quy trình

SaigonOS dùng Operaton để chạy các quy trình BPMN 2.0. Operaton lưu dữ liệu trong cơ sở dữ liệu `operaton` riêng. Role `operaton` của cơ sở dữ liệu không kết nối được tới các cơ sở dữ liệu khác.

Ba trang Cockpit, Tasklist và Admin của Operaton nằm ở địa chỉ `/operaton/` của API Gateway, ví dụ http://localhost:9080/operaton/. Cockpit dùng để theo dõi các quy trình đang chạy. Tasklist dùng để xem và xử lý các việc. Admin dùng để quản lý quyền trong Operaton.

Chỉ tài khoản có realm role `admin` đăng nhập được vào ba trang này. Cách tạo tài khoản được trình bày ở mục [Tạo tài khoản quản trị của realm saigonos](../install.md#tạo-tài-khoản-quản-trị-của-realm-saigonos). Mỗi lần đăng nhập, tài khoản phải nhập mật khẩu và mã OTP, kể cả khi đã đăng nhập vào một trang khác của hệ thống. Tài khoản không có realm role `admin` bị từ chối ngay sau khi nhập mật khẩu. Khi đó, trang đăng nhập báo rằng chỉ tài khoản quản trị mới vào được trang này. Nội dung thông báo có khóa `saigonos-operaton-admin-only` và sửa được trong Admin Console của realm `saigonos`, ở mục Realm settings, thẻ Localization, phần Realm overrides. Keycloak tính mỗi lần bị từ chối là một lần đăng nhập sai. Do đó, hai lần bị từ chối trong vòng 1 giây làm tài khoản tạm bị khóa 60 giây. Trang đăng nhập khóa nút đăng nhập ngay sau lần bấm đầu tiên, nên trường hợp này chỉ xảy ra khi một chương trình gửi form đăng nhập liên tục.

Operaton làm mới access token ở mỗi lời gọi của ba trang. Do đó, khi một tài khoản bị khóa trong Keycloak, phiên đăng nhập của tài khoản trong Operaton kết thúc ngay ở lời gọi tiếp theo. Nút đăng xuất của ba trang mở địa chỉ `/operaton/logout` để kết thúc phiên đăng nhập của Operaton. Sau khi đăng xuất, lần mở tiếp theo phải nhập lại mật khẩu và mã OTP. Phiên đăng nhập của Keycloak vẫn còn, nên các ứng dụng khác của hệ thống không bị đăng xuất.

Mỗi khi hệ thống khởi động, service `realm` kiểm tra client `operaton` của realm `saigonos` và luồng đăng nhập riêng của client này. Khi luồng đăng nhập bị thay đổi, service tạo lại luồng này. Các thiết lập bảo mật của client cũng được đặt lại, ví dụ địa chỉ chuyển hướng sau khi đăng nhập.

REST API của Operaton không mở qua API Gateway. Chỉ ba service `core`, `processes` và `apps` gọi REST API này, bằng tài khoản `core` của Operaton. Mật khẩu của tài khoản là giá trị `CORE_OPERATON_PASSWORD` trong file `.env`. Operaton tạo tài khoản này ở lần khởi động đầu tiên. Do đó, đổi giá trị này trong file `.env` sau đó không đổi mật khẩu của tài khoản. Sau mỗi lần đăng nhập sai, Operaton tạm khóa tài khoản trong 3 giây. Thời gian khóa tăng gấp đôi sau mỗi lần sai tiếp theo, tối đa là 60 giây. Sau 10 lần sai liên tiếp, tài khoản bị khóa hẳn.

Để tài khoản không bị khóa hẳn, service `core` ngừng gọi Operaton trong 60 giây sau mỗi lần Operaton từ chối tài khoản `core`. Trong thời gian này, các lời gọi cần Operaton nhận mã 503 và các bước máy làm chưa được chạy. Sau 5 lần bị từ chối liên tiếp, service ngừng gọi Operaton cho tới khi được khởi động lại, và log của service ghi cách khắc phục. Sau khi khôi phục giá trị đúng của `CORE_OPERATON_PASSWORD` trong file `.env`, chạy lại lệnh `saigonos up`. Nếu giá trị này vốn đúng, khởi động lại service `core` bằng lệnh sau:

```bash
cd ~/saigonos
docker compose restart core
```

## Quy trình của hệ thống

Mỗi quy trình nằm trong một file BPMN 2.0 ở thư mục `~/saigonos/config/operaton/processes`. Lệnh `saigonos init` tạo sẵn thư mục này. Mỗi khi hệ thống khởi động, service `processes` triển khai các file trong thư mục vào Operaton. Do đó, sau khi thêm hoặc sửa một file, cần chạy lại lệnh sau:

```bash
saigonos up
```

Service `processes` tuân theo các quy tắc sau:

- File không thay đổi thì không tạo phiên bản mới của quy trình. File đã sửa tạo một phiên bản mới. Các quy trình đang chạy vẫn dùng phiên bản cũ.
- Mỗi quy trình phải có thuộc tính `operaton:historyTimeToLive`, tức thời gian giữ lịch sử của quy trình. Ví dụ, giá trị `P30D` là 30 ngày. Mỗi ngày từ 01:00 đến 05:00 giờ Việt Nam, Operaton xóa lịch sử của các quy trình đã kết thúc quá thời gian này.
- Tên file chỉ gồm chữ cái không dấu, chữ số, dấu chấm, dấu gạch ngang, dấu gạch dưới và kết thúc bằng `.bpmn`.
- Mỗi mã quy trình, tức thuộc tính `id` của thẻ `process`, chỉ được khai báo trong một file. Khi một file khai báo lại mã quy trình của file khác, service gỡ bản triển khai vừa tạo và báo lỗi. Nhờ đó, một file không thay được quy trình của file khác.
- Xóa một file khỏi thư mục không gỡ quy trình khỏi Operaton.

Khi một file bị lỗi, lệnh `saigonos up` kết thúc với mã lỗi. Service `core` chờ service `processes` chạy xong, nên có thể chưa khởi động cho tới khi file được sửa. Để xem kết quả triển khai và lỗi của từng file:

```bash
cd ~/saigonos
docker compose logs --tail 20 processes
```

File BPMN có thể chứa mã chạy bên trong Operaton, ví dụ script task. Do đó, chỉ đặt vào thư mục này các file từ nguồn đáng tin cậy. File BPMN của ứng dụng được soát như mục [Quy trình của ứng dụng](../apps/workflow.md#quy-trình-của-ứng-dụng), nên không chứa được mã như vậy.

Ví dụ sau là một quy trình đơn giản gồm điểm bắt đầu và điểm kết thúc. Nội dung được lưu trong file `thu-nghiem.bpmn`:

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
