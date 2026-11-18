<!-- SPDX-License-Identifier: Apache-2.0 -->
# Nhật ký thay đổi

File này ghi lại các thay đổi đáng chú ý của SaigonOS. Cách ghi tuân theo [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Số phiên bản tuân theo [Semantic Versioning](https://semver.org/lang/vi/).

Mục "Chưa phát hành" ghi các thay đổi đã có trên `main` nhưng chưa có trong release nào.

## [Chưa phát hành]

### Thêm

- Service `centrifugo` gửi cập nhật tức thời tới ứng dụng qua WebSocket. Ứng dụng kết nối tới địa chỉ `/realtime/connection/websocket` của API Gateway và gửi access token của Keycloak trong lệnh connect. Centrifugo kiểm tra chữ ký, issuer, thời hạn và audience của access token. Kết nối không có access token, kết nối bằng ID token và kết nối bằng access token không mang mã người dùng đều bị từ chối. Centrifugo chỉ nhận kết nối WebSocket từ trang có địa chỉ trùng với địa chỉ truy cập của hệ thống.
- Khi dừng, Centrifugo báo cho các client kết nối lại rồi thoát trong khoảng 1 giây.
- API của server và Admin web của Centrifugo nằm ở cổng 9480, chỉ truy cập được từ chính máy cài đặt. API Gateway không mở hai địa chỉ này. Lệnh `saigonos init` có thêm tùy chọn `--centrifugo-port` để đổi cổng này.
- Lệnh `saigonos init` thêm các giá trị `SAIGONOS_CENTRIFUGO_PORT`, `CENTRIFUGO_API_KEY`, `CENTRIFUGO_ADMIN_PASSWORD` và `CENTRIFUGO_ADMIN_SECRET` vào file `.env`.
- Service `realm` thêm audience `saigonos` vào access token của các client dùng client scope `roles`. Khi mapper này bị sửa hoặc bị xóa, service đặt lại như cũ.
- Lệnh `saigonos doctor` mở thử một kết nối WebSocket tới Centrifugo qua API Gateway và kiểm tra API của Centrifugo bị chặn. Khi reverse proxy không chuyển tiếp kết nối WebSocket, lệnh báo cần kiểm tra header `Upgrade` và `Connection`.

### Thay đổi

- Ví dụ cấu hình Nginx trong README chuyển tiếp kết nối WebSocket. Máy chủ đã có reverse proxy cần thêm khối `map` và ba dòng `proxy_http_version`, `Upgrade`, `Connection` như trong ví dụ.

## [0.4.0] - 2026-11-18

### Thêm

- Service `operaton` chạy các quy trình BPMN 2.0 bằng Operaton. Operaton lưu dữ liệu trong cơ sở dữ liệu `operaton` riêng. Service `databases` tạo cơ sở dữ liệu này và role `operaton` khi chưa có, kể cả với cơ sở dữ liệu được tạo từ phiên bản cũ.
- Cockpit, Tasklist và Admin của Operaton ở địa chỉ `/operaton/` của API Gateway. Chỉ tài khoản có realm role `admin` đăng nhập được, bằng mật khẩu và OTP. Tài khoản khác được báo rằng chỉ tài khoản quản trị mới vào được, bằng tiếng Việt hoặc tiếng Anh. Khi tài khoản bị khóa trong Keycloak, phiên đăng nhập của Operaton kết thúc ngay ở lời gọi tiếp theo. Nút đăng xuất của ba trang kết thúc phiên đăng nhập của Operaton, nên lần mở tiếp theo phải nhập lại mật khẩu và mã OTP.
- Service `realm` tạo client `operaton` và luồng đăng nhập riêng của client này trong realm `saigonos`. Khi luồng đăng nhập hoặc các thiết lập bảo mật của client bị thay đổi, service đặt lại như cũ.
- REST API của Operaton chỉ dành cho service `core`. REST API này không mở qua API Gateway và cần đăng nhập bằng tài khoản `core` của Operaton.
- Lệnh `saigonos init` thêm các giá trị `OPERATON_DB_PASSWORD`, `OPERATON_CLIENT_SECRET` và `CORE_OPERATON_PASSWORD` vào file `.env`.
- Service `processes` triển khai các file BPMN trong thư mục `config/operaton/processes` vào Operaton mỗi khi hệ thống khởi động. File không thay đổi thì không tạo phiên bản mới của quy trình. File bị lỗi làm lệnh `saigonos up` kết thúc với mã lỗi. Một file không thay được quy trình đã khai báo trong file khác. Lệnh `saigonos init` tạo sẵn thư mục này.
- Lệnh `saigonos doctor` kiểm tra Operaton qua API Gateway. Trang đăng nhập phải dùng đúng địa chỉ truy cập của hệ thống và REST API của Operaton phải bị chặn.
- Lời gọi `POST /core/processes/{key}/start` bắt đầu phiên bản mới nhất của một quy trình. Người gọi cần một realm role có trong thuộc tính `candidateStarterGroups` của quy trình. Quy trình không khai báo thuộc tính này thì không bắt đầu được qua API. Service `core` ghi mã người gọi vào biến `initiator` và người gọi không gửi được biến này.
- Lời gọi `GET /core/tasks` trả về các việc mà người gọi đã nhận và các việc chưa ai nhận có nhóm ứng viên là một realm role của người gọi. Việc mà người khác đã nhận không có trong danh sách.
- Lời gọi `POST /core/tasks/{id}/claim` nhận một việc chưa có người nhận. Người gọi cần một realm role nằm trong nhóm ứng viên của việc. Khi nhiều người cùng nhận một việc, chỉ một người nhận được. Những người còn lại nhận mã 409.
- Lời gọi `POST /core/tasks/{id}/complete` hoàn thành việc mà người gọi đã nhận. Các biến được gửi qua form của việc trong Operaton. Người hoàn thành việc không gửi được biến `initiator`.
- Lời gọi bắt đầu quy trình và lời gọi hoàn thành việc chỉ nhận các trường được khai báo trong form của file BPMN, tức các thẻ `operaton:formField`. Service `core` kiểm tra kiểu của từng trường và các ràng buộc `required`, `minlength`, `maxlength`, `min`, `max` và `readonly` trước khi gửi tới Operaton. Chuỗi chỉ có khoảng trắng được coi là chưa nhập. Khi một giá trị không đạt, lời gọi nhận mã 422 với nội dung bắt đầu bằng `LỖI TUÂN THỦ` và nêu tên trường. Khi đó, việc vẫn thuộc người nhận và quy trình không đi tiếp.
- Bước máy làm của quy trình gọi một hàm của cơ sở dữ liệu. Bước này là service task có topic `saigonos-function` và thuộc tính `function` nêu tên hàm. Hàm cần được cấp quyền `EXECUTE` cho role `workflow` và chạy với quyền của role này. Kết quả của hàm được ghi thành biến của quy trình.
- Mỗi bước máy làm chỉ chạy hàm một lần, kể cả khi service `core` dừng đột ngột trước khi báo Operaton. Hàm báo lỗi được thử lại sau 5 giây, 30 giây và 2 phút. Hàm chưa được khai báo hoặc sai kiểu làm bước máy làm trở thành incident trong Cockpit.
- Khi Operaton từ chối tài khoản `core`, service `core` ngừng gọi Operaton trong 60 giây. Sau 5 lần bị từ chối liên tiếp, service ngừng gọi Operaton cho tới khi khởi động lại. Nhờ đó, Operaton không khóa hẳn tài khoản `core`.
- Quy trình có thể gắn hẹn giờ trên biên của một việc. Khi việc quá hạn, quy trình rẽ sang nhánh khác, ví dụ chuyển việc cho nhóm quản lý. Operaton tìm các hẹn giờ đã tới hạn 2 giây một lần, nên hẹn giờ chạy chậm nhất khoảng 2 giây sau hạn. Hẹn giờ tới hạn trong lúc Operaton dừng sẽ chạy ngay khi Operaton chạy lại.
- Mỗi ngày từ 01:00 đến 05:00 giờ Việt Nam, Operaton xóa lịch sử của các quy trình đã kết thúc quá thời gian `historyTimeToLive`.
- Khi container dừng, Operaton dừng job executor và đóng các kết nối tới cơ sở dữ liệu trước khi thoát.

### Thay đổi

- Hệ thống cần khoảng 3 GB RAM và 6 GB dung lượng đĩa vì có thêm Operaton.

### Sửa

- Lời gọi tới service `core` có giá trị `NaN` hoặc `Infinity` trong nội dung nhận mã 422 thay cho 500. Nội dung lỗi 422 không còn chép lại giá trị mà người gọi đã gửi.

## [0.3.0] - 2026-11-17

### Thêm

- Service `migrate` chạy các file SQL của cơ sở dữ liệu mỗi khi hệ thống khởi động. Các file chạy theo thứ tự tên. Mỗi file chỉ chạy một lần và chạy trong một transaction. Bảng `core.migrations` ghi lại các file đã chạy. Khi nội dung của một file đã chạy bị thay đổi, service dừng và báo lỗi. PostgREST nhận ngay các bảng và view mới mà không cần khởi động lại.
- Các hàm `core.uid()`, `core.has_role()` và `core.unit()` cho biết thông tin của người gọi API. Hàm `core.uid()` trả về mã người dùng trong Keycloak. Hàm `core.has_role()` kiểm tra một realm role của người dùng. Hàm `core.unit()` trả về đơn vị của người dùng. Hàm `core.claims()` trả về toàn bộ nội dung của access token. Các hàm này đọc access token mà PostgREST đã kiểm tra. Chính sách phân quyền từng dòng (row-level security) của bảng dùng các hàm này để giới hạn dữ liệu theo người dùng, vai trò và đơn vị.
- Thuộc tính `unit` (Đơn vị) của người dùng trong realm `saigonos`. Quản trị viên đặt giá trị này ở trang thông tin người dùng trong Admin Console của Keycloak. Người dùng không tự đổi được giá trị này. Access token mang giá trị này trong claim `unit`.
- Service `realm` thêm các thiết lập mới vào realm `saigonos` mỗi khi hệ thống khởi động. Nhờ đó, realm được tạo từ phiên bản cũ cũng có thuộc tính `unit`. Service chỉ thêm thiết lập còn thiếu và giữ nguyên các thiết lập khác của realm.
- Role `anon` của cơ sở dữ liệu dành cho lời gọi API không có access token. Role này chưa được cấp quyền trên bảng, view hay hàm nào của API. Để mở một bảng, view hoặc hàm cho người chưa đăng nhập, cấp quyền cho role này bằng lệnh `GRANT`.
- Hàm `core.pre_request()` xóa các query plan đã lưu trước mỗi lời gọi API. PostgREST cũng không dùng prepared statement. Nhờ đó, quyền `EXECUTE` của hàm được kiểm tra lại ở mỗi lời gọi. Khi dùng lại query plan đã lập cho một role khác, PostgreSQL không kiểm tra lại quyền này.
- Bảng `core.audit_log` và hàm `core.audit()` ghi audit log của cơ sở dữ liệu. Để ghi audit log cho một bảng, gắn hàm `core.audit()` vào bảng đó bằng một lệnh `CREATE TRIGGER`. Mỗi lần một dòng được thêm, sửa hoặc xóa, audit log ghi người thực hiện, thời điểm, tên bảng, thao tác, giá trị trước và giá trị sau. Mỗi dòng audit log mang một mã băm SHA-256. Mã băm này được tính từ nội dung của dòng và mã băm của dòng trước. Do đó, khi một dòng audit log bị sửa hoặc bị xóa, chuỗi mã băm không còn khớp. Role `anon` và `authenticated` không đọc và không ghi được bảng `core.audit_log`.
- Bảng `core.audit_log` chỉ cho phép thêm dòng. Các lệnh `UPDATE`, `DELETE` và `TRUNCATE` trên bảng này bị từ chối, kể cả với role sở hữu bảng. Hàm `core.append_only()` cũng dùng được cho các bảng khác chỉ cho phép thêm dòng.
- Lệnh `saigonos audit verify` tính lại chuỗi mã băm của audit log. Khi một dòng đã bị sửa hoặc bị xóa, lệnh chỉ ra dòng sai đầu tiên và kết thúc với mã thoát 1. Lệnh tự tính mã băm và không dùng hàm lưu trong cơ sở dữ liệu.
- Tài liệu OpenAPI 2.0 của REST API ở địa chỉ `/api/`. PostgREST tự sinh tài liệu này. Tài liệu chỉ liệt kê các bảng, view và hàm mà người gọi được dùng. Các địa chỉ trong tài liệu được lấy từ `SAIGONOS_URL`. Tài liệu cũng ghi cách gửi access token trong header `Authorization`. Ở phiên bản 0.2.0, tài liệu ghi địa chỉ `0.0.0.0:3000` của PostgREST bên trong container.
- Hàm `core.mask_phone()` và `core.mask_email()` che một phần số điện thoại và email. Ví dụ: `0912345678` thành `091****678`, `nguyenvana@gmail.com` thành `ngu*******@gmail.com`. Role `anon` và `authenticated` gọi được hai hàm này. Khi dùng trong view, hai hàm cho phép chỉ hiện đủ dữ liệu cho người có quyền.
- Bảng `core.consents` ghi sự đồng ý với chính sách, gồm người đồng ý, tên chính sách, phiên bản chính sách và thời điểm đồng ý. Thời điểm đồng ý do máy chủ ghi. Bảng chỉ cho phép thêm dòng và có audit log. Role `anon` và `authenticated` không đọc và không ghi trực tiếp được bảng này.
- Tùy chọn `--keycloak-port` của lệnh `saigonos init` đặt cổng của Keycloak trên máy cài đặt. Cổng này mặc định là 9280 và chỉ lắng nghe trên địa chỉ `127.0.0.1`. Admin Console của realm master dùng cổng này.
- Hướng dẫn tạo tài khoản quản trị có OTP trong realm `saigonos` trong README.
- Service `seaweedfs` lưu file của các ứng dụng theo chuẩn S3. Hai bucket `quarantine` và `clean` được tạo sẵn. Lời gọi S3 phải được ký bằng khóa trong file `.env`. Service này nằm trong một mạng Docker riêng. Chỉ service `core` kết nối được tới SeaweedFS. SeaweedFS không gửi thống kê ra ngoài và không liệt kê nội dung thư mục.
- Admin UI của SeaweedFS ở địa chỉ http://127.0.0.1:9380/, chỉ truy cập được từ chính máy cài đặt. Tùy chọn `--seaweedfs-port` của lệnh `saigonos init` đổi cổng này.
- Lệnh `saigonos init` tạo khóa S3 và mật khẩu Admin UI của SeaweedFS trong file `.env`. Khi cập nhật từ phiên bản cũ, lệnh thêm các giá trị này và giữ nguyên các mật khẩu đã có.
- Service `clamav` quét mã độc bằng ClamAV. Service này nằm trong mạng Docker `scan` riêng. Mạng này không có kết nối Internet. Chỉ service `core` kết nối được tới ClamAV. Khi tiến trình quét dừng bất thường, container tự khởi động lại.
- Service `freshclam` kiểm tra bản cập nhật của cơ sở dữ liệu mã độc 12 lần mỗi ngày và tải bản mới từ `database.clamav.net`. Cơ sở dữ liệu nằm trong volume `clamav-data` nên được giữ lại khi khởi động lại hệ thống. Trong lúc nạp bản mới, ClamAV chỉ giữ một bản cơ sở dữ liệu trong RAM và dùng khoảng 1 GB RAM.
- Service `core` cung cấp API của lõi tại địa chỉ `/core/` của API Gateway. Service được viết bằng FastAPI. Tài liệu OpenAPI 3.1 nằm ở `/core/openapi.json`. Lời gọi `GET /core/me` trả về mã người dùng, đơn vị và role mà cơ sở dữ liệu nhận được.
- Docker Compose build image của service `core` trên máy cài đặt từ image `python` chính thức. Dòng `FROM` ghi cả digest của image. Các thư viện được cài từ lock file có mã băm. Do đó, file release vẫn chỉ chứa mã nguồn.
- API Gateway kiểm tra access token của lời gọi tới `/core` như với `/api`. Service `core` kiểm tra lại chữ ký, issuer, thời hạn, loại token và realm role `authenticated`. Do đó, lời gọi tới thẳng service với access token giả vẫn bị từ chối. Khi Keycloak đổi khóa ký, service tự lấy khóa mới.
- Service `core` kết nối PostgreSQL bằng role `core_service`. Mỗi truy vấn chạy với role và nội dung access token của người gọi, giống PostgREST. Lệnh `saigonos init` thêm mật khẩu của role này vào file `.env`.
- Bảng `core.files` lưu thông tin của các file được tải lên, gồm chủ file, tên, loại, dung lượng, mã băm SHA-256 và trạng thái. Bảng có audit log. Chính sách phân quyền từng dòng chỉ cho người dùng thấy file của chính mình. Chỉ role `core_service` thêm và sửa được dòng của bảng này.
- Lời gọi `POST /core/files` của service `core` khai báo một file mới và trả về đường dẫn tải lên. Service kiểm tra loại file, phần mở rộng của tên file và dung lượng. Lời gọi `PUT` tới đường dẫn tải lên gửi nội dung của file. Nội dung được lưu vào bucket `quarantine` và chờ quét mã độc. Nội dung có dung lượng hoặc phần đầu không khớp với thông tin đã khai báo bị từ chối. Lời gọi `GET /core/files/{id}` trả về thông tin và trạng thái của file.
- Tùy chọn `--max-file-size` của lệnh `saigonos init` đặt dung lượng tối đa của một file tải lên, tính bằng MB. Giá trị mặc định là 10.
- Service `core` quét mọi file bằng ClamAV ngay sau khi nhận nội dung. File không có mã độc được chuyển sang bucket `clean` và có trạng thái `clean`. File có mã độc được giữ trong bucket `quarantine` và có trạng thái `infected`. Tên mã độc được ghi vào trường `malware` của file và vào audit log. Khi ClamAV chưa sẵn sàng, file chờ ở trạng thái `pending_scan` và được quét lại sau, kể cả khi service `core` khởi động lại.
- ClamAV coi nội dung không quét hết được là mã độc. Ví dụ: file nén lồng nhau quá 17 lớp hoặc có tổng nội dung sau khi giải nén lớn hơn 400 MB. Khi đó, tên mã độc bắt đầu bằng `Heuristics.Limits.Exceeded`.
- Lời gọi `POST /core/files/{id}/download-url` của service `core` trả về đường dẫn tải về của một file. Đường dẫn dùng được trong 60 giây và mở được trong trình duyệt mà không cần access token. Chỉ file có trạng thái `clean` mới tải về được. Người dùng chỉ xin được đường dẫn cho file mà chính sách phân quyền từng dòng cho phép đọc. File được gửi kèm header `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff` và `Cache-Control: no-store`. Trước khi gửi, nội dung được so với mã băm SHA-256 đã ghi.
- Lệnh `saigonos init` tạo khóa `CORE_DOWNLOAD_KEY` trong file `.env`. Service `core` ký đường dẫn tải về bằng khóa này. Khi cập nhật từ phiên bản cũ, lệnh thêm khóa này và giữ nguyên các mật khẩu đã có.

### Thay đổi

- Hệ thống cần Docker Buildx để build image của service `core`. Hệ thống cũng cần khoảng 2,5 GB RAM và 5 GB dung lượng đĩa vì có thêm SeaweedFS, ClamAV và service `core`. Ở phiên bản 0.2.0, hệ thống cần khoảng 1 GB RAM và 2 GB dung lượng đĩa.
- Lệnh `saigonos up` cần đăng nhập được Keycloak bằng tài khoản `admin` của realm master. Service `realm` dùng tài khoản này với mật khẩu `KEYCLOAK_ADMIN_PASSWORD` trong file `.env`. Nếu mật khẩu của tài khoản đã được đổi trong Admin Console, cần ghi mật khẩu mới vào file `.env` trước khi cập nhật. Service chỉ đăng nhập bằng mật khẩu, nên không bật OTP cho tài khoản này.
- Admin Console của realm master có địa chỉ mới là http://localhost:9280/auth/admin/master/console/ trên máy cài đặt. Admin Console của realm `saigonos` vẫn mở qua API Gateway tại `/auth/admin/saigonos/console/`.
- Lời gọi `/api` không có access token chạy với role `anon`. Ở phiên bản 0.2.0, API Gateway trả về mã 401 cho lời gọi này. Khi dùng một bảng hoặc hàm chưa cấp cho `anon`, lời gọi nhận mã 401. Access token giả hoặc hết hạn vẫn nhận mã 401. Giới hạn tần suất gọi áp dụng cho cả lời gọi không có access token.
- Access token hợp lệ nhưng không có realm role `authenticated` chạy với role `anon`. Ở phiên bản 0.2.0, lời gọi này nhận mã 401. Lời gọi kèm ID token hoặc token khác không phải access token vẫn nhận mã 401.
- Hàm mới trong cơ sở dữ liệu `saigonos` chỉ gọi được sau khi được cấp quyền `EXECUTE`. Ở phiên bản 0.2.0, mọi role đều gọi được hàm mới. Các hàm đã có trong schema `api` được cấp cho role `authenticated`. Do đó, người dùng đã đăng nhập vẫn gọi được các hàm này sau khi cập nhật.
- Lệnh `saigonos doctor` kiểm tra hai lời gọi tới `/api/`. Lời gọi không có access token phải nhận mã 200. Lời gọi có access token không hợp lệ phải nhận mã 401.
- Lệnh `saigonos doctor` kiểm tra service `core` qua API Gateway. Lời gọi `/core/health` phải nhận mã 200. Lời gọi có access token không hợp lệ phải nhận mã 401.
- API Gateway từ chối lời gọi có nội dung lớn hơn dung lượng tối đa của một file tải lên, mặc định là 10 MB. Ở phiên bản 0.2.0, API Gateway không giới hạn dung lượng nội dung. Khi hệ thống chạy sau Nginx, giới hạn `client_max_body_size` của Nginx không được nhỏ hơn giới hạn này. Ví dụ cấu hình Nginx trong README đã có dòng này.

### Sửa

- API Gateway nhận địa chỉ IP mới của một service trong khoảng 1 giây sau khi service được tạo lại hoặc khởi động lại. Ở phiên bản 0.2.0, API Gateway có thể dùng địa chỉ cũ thêm tới 30 giây. Trong thời gian đó, lời gọi tới service nhận mã 502 hoặc bị treo.

### Bảo mật

- API Gateway trả về mã 404 cho mọi địa chỉ của realm master. Realm master chỉ mở qua cổng của Keycloak trên chính máy cài đặt. Ở phiên bản 0.2.0, trang đăng nhập và Admin Console của realm master mở ra ngoài qua API Gateway và chỉ cần mật khẩu.
- Realm master khóa tạm một tài khoản sau nhiều lần đăng nhập sai. Ở phiên bản 0.2.0, realm master không giới hạn số lần đăng nhập sai.

## [0.2.0] - 2026-11-14

### Thêm

- Service `caddy` nhận kết nối HTTPS trên máy chủ chưa có reverse proxy. Caddy tự lấy chứng chỉ từ Let's Encrypt và bật HSTS. Caddy cũng hỗ trợ HTTP/3 và chuyển các kết nối HTTP sang HTTPS. Caddy dùng mạng của máy chủ nên thấy đúng địa chỉ IP của người dùng qua IPv4 và IPv6. Các header `X-Forwarded-*` do người dùng tự gửi bị bỏ qua.
- Tùy chọn `--caddy` và `--no-caddy` của lệnh `saigonos init` bật và tắt Caddy. Caddy mặc định tắt. Khi Caddy bật, địa chỉ truy cập phải bắt đầu bằng `https://`.
- Lệnh `saigonos doctor` tin chứng chỉ do Caddy tự cấp, ví dụ chứng chỉ cho `localhost`.
- Lệnh `saigonos doctor` báo lỗi khi Keycloak nhận lời gọi qua một địa chỉ khác với `SAIGONOS_URL`. Lỗi này xảy ra khi reverse proxy không gửi đủ các header `X-Forwarded-Proto`, `X-Forwarded-Host` và `X-Forwarded-Port`.
- Hướng dẫn triển khai trên máy chủ chưa có reverse proxy trong README.

### Thay đổi

- Lệnh `saigonos doctor` ghi `BÌNH THƯỜNG` thay cho `ĐẠT` và ghi `healthcheck báo lỗi` thay cho `không đạt healthcheck`. Các cột cách nhau 4 dấu cách.
- Lệnh `saigonos init` từ chối cổng HTTP trùng các cổng 7085, 9090, 9091, 9180 và 9443. APISIX dùng các cổng này bên trong container. Ở phiên bản 0.1.1, các cổng này vẫn được chấp nhận.
- Lệnh `saigonos up` và `saigonos down` xóa container của Caddy sau khi Caddy bị tắt bằng lệnh `saigonos init --no-caddy`.
- Mục "Triển khai sau reverse proxy HTTPS" của README đổi tên thành "Triển khai trên máy chủ đã có reverse proxy".

### Sửa

- Khi người dùng truy cập thẳng API Gateway qua cổng 80, `token_endpoint` của Keycloak không còn kèm cổng 9080. Lỗi này có từ phiên bản 0.1.0. Để sửa lỗi, APISIX lắng nghe trong container đúng cổng HTTP được mở ra máy chủ.

## [0.1.1] - 2026-11-13

### Thêm

- Tùy chọn `--http-host` của lệnh `saigonos init` đặt địa chỉ IP mà cổng HTTP của API Gateway lắng nghe. Giá trị `0.0.0.0` cho phép truy cập từ máy khác.
- Hướng dẫn triển khai sau reverse proxy HTTPS và hướng dẫn cập nhật phiên bản trong README.

### Thay đổi

- Cổng HTTP của API Gateway mặc định chỉ lắng nghe trên địa chỉ `127.0.0.1`. Ở phiên bản 0.1.0, cổng này lắng nghe trên mọi địa chỉ của máy cài đặt. Để các máy khác vẫn truy cập được sau khi cập nhật, chạy lệnh `saigonos init --http-host 0.0.0.0`.

### Sửa

- Khi SaigonOS chạy sau reverse proxy, APISIX giữ nguyên các header `X-Forwarded-Proto`, `X-Forwarded-Host` và `X-Forwarded-Port` do proxy trong mạng nội bộ gửi tới. Địa chỉ IP của người dùng được lấy từ header `X-Forwarded-For`. Ở phiên bản 0.1.0, Keycloak trả về địa chỉ `http` kèm cổng 9080 và giới hạn tần suất gọi tính mọi người dùng vào cùng một địa chỉ IP.

### Bảo mật

- APISIX bỏ header `X-Forwarded-For` do máy ngoài mạng nội bộ gửi tới. Ở phiên bản 0.1.0, một máy bên ngoài có thể dùng header này để khai báo với Keycloak một địa chỉ IP trong mạng nội bộ.

## [0.1.0] - 2026-11-12

### Thêm

- Package Python `saigonos` có lệnh `saigonos --version`.
- Giấy phép Apache-2.0 với dòng SPDX ở đầu mọi file, được kiểm tra bằng REUSE.
- Lock file `requirements.txt` và `requirements-dev.txt` cố định phiên bản thư viện.
- Bộ tài liệu khung gồm README, hướng dẫn đóng góp, chính sách bảo mật và mẫu issue.
- `DEPENDENCIES.md` liệt kê thư viện, phần mềm chạy trong container và công cụ phát triển kèm giấy phép, được tạo bằng lệnh `make dependencies`.
- File nén mã nguồn `.tar.gz` kèm `SHA256SUMS`, được tạo tự động khi push tag phiên bản.
- Bộ Docker Compose gồm PostgreSQL, Keycloak, etcd, APISIX và PostgREST. Mỗi service được cố định phiên bản, có healthcheck và tự khởi động lại.
- Realm `saigonos` của Keycloak được nạp từ file. Tài khoản có vai trò `admin` phải nhập OTP khi đăng nhập. Access token có thời hạn 60 giây.
- Route `/auth` tới Keycloak và route `/api` tới PostgREST trên API Gateway. Route `/api` kiểm tra access token và giới hạn tần suất gọi.
- Lệnh `saigonos init` tạo thư mục làm việc gồm file `compose.yaml`, thư mục `config` và file `.env` chứa mật khẩu ngẫu nhiên. Khi chạy lại, các giá trị đã có trong file `.env` được giữ nguyên.
- Lệnh `saigonos up` và `saigonos down` khởi động và dừng các service bằng Docker Compose.
- Lệnh `saigonos doctor` kiểm tra trạng thái từng service và API Gateway.
- Hướng dẫn cài đặt bằng pip và Docker Compose trong README.

[Chưa phát hành]: https://github.com/tynnpdhsp/SaigonOS/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.4.0
[0.3.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.3.0
[0.2.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.2.0
[0.1.1]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.1.1
[0.1.0]: https://github.com/tynnpdhsp/SaigonOS/releases/tag/v0.1.0
