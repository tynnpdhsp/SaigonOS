<!-- SPDX-License-Identifier: Apache-2.0 -->
# Viết ứng dụng đầu tiên

Trang này đi qua từng file của ứng dụng mẫu trong thư mục [`examples/phong-may`](https://github.com/tynnpdhsp/SaigonOS/tree/main/examples/phong-may). Ứng dụng mẫu quản lý việc đặt phòng máy của một trường học. Ứng dụng chỉ gồm bản khai, file SQL, file BPMN và một trang HTML. Đăng nhập, API, quy trình, thông báo và tường lửa đều do lõi đảm nhận.

## Ứng dụng mẫu

Ứng dụng có bốn role:

| Role | Người dùng | Việc |
|---|---|---|
| `phong-may.giao-vien` | Giáo viên, giảng viên | Gửi đơn đặt phòng và xem đơn của mình |
| `phong-may.phu-trach` | Phụ trách phòng | Duyệt đơn, xem mọi đơn và sửa số máy của phòng |
| `phong-may.chuyen-vien` | Chuyên viên | Chuẩn bị phòng cho đơn đã duyệt |
| `phong-may.hoc-sinh` | Học sinh, sinh viên | Xem lịch phòng đã duyệt |

Mỗi đơn đặt phòng đi qua các bước sau:

1. Giáo viên gửi đơn gồm phòng, giờ bắt đầu, giờ kết thúc, số máy cần, lớp hoặc học phần, mục đích và phần mềm cần cài.
2. Hệ thống kiểm tra phòng còn trống và đủ máy rồi ghi đơn. Đơn không hợp lệ thì giáo viên nhận thông báo kèm lý do.
3. Phụ trách phòng đồng ý hoặc từ chối đơn, kèm ý kiến. Khi tới hạn duyệt mà đơn chưa được duyệt, mọi phụ trách phòng nhận lời nhắc trong ứng dụng và qua Telegram.
4. Đơn được duyệt thì chuyên viên chuẩn bị phòng và ghi số máy sẵn sàng.
5. Giáo viên nhận thông báo về kết quả của từng bước.

Thư mục của ứng dụng gồm các file sau:

```text
examples/phong-may/
├── saigonos-app.json
├── database/
│   ├── 0001_phong.sql
│   ├── 0002_nguoi_dung.sql
│   ├── 0003_don.sql
│   └── 0004_quy_trinh.sql
├── processes/
│   └── dat-phong.bpmn
└── ui/
    ├── index.html
    ├── style.css
    └── app.js
```

## Bản khai

File `saigonos-app.json` khai tên, phiên bản, bốn role, ba thư mục của ứng dụng và ba luật truy cập:

```json
{
  "$schema": "https://raw.githubusercontent.com/tynnpdhsp/SaigonOS/main/schemas/saigonos-app.schema.json",
  "name": "phong-may",
  "title": "Đặt phòng máy",
  "version": "0.1.0",
  "roles": [
    {
      "name": "phong-may.giao-vien",
      "description": "Giáo viên, giảng viên. Gửi đơn đặt phòng và xem đơn của mình"
    },
    {
      "name": "phong-may.phu-trach",
      "description": "Phụ trách phòng. Duyệt đơn, xem mọi đơn và sửa số máy của phòng"
    },
    {
      "name": "phong-may.chuyen-vien",
      "description": "Chuyên viên. Chuẩn bị phòng cho đơn đã duyệt"
    },
    {
      "name": "phong-may.hoc-sinh",
      "description": "Học sinh, sinh viên. Xem lịch phòng đã duyệt"
    }
  ],
  "database": "database",
  "processes": "processes",
  "ui": "ui",
  "access": [
    {
      "roles": [
        "phong-may.giao-vien",
        "phong-may.phu-trach",
        "phong-may.chuyen-vien",
        "phong-may.hoc-sinh"
      ]
    },
    {
      "methods": ["POST", "PATCH", "PUT", "DELETE"],
      "roles": ["phong-may.giao-vien", "phong-may.phu-trach", "phong-may.chuyen-vien"]
    },
    {
      "methods": ["PATCH"],
      "paths": ["/phong"],
      "roles": ["phong-may.phu-trach"]
    }
  ]
}
```

Luật thứ nhất chỉ cho người có role của ứng dụng gọi API. Luật thứ hai không cho học sinh ghi dữ liệu. Luật thứ ba chỉ cho phụ trách phòng sửa bảng `phong`. Ý nghĩa của từng trường được trình bày ở trang [Bản khai và cài đặt ứng dụng](apps/manifest.md) và trang [Luật truy cập của ứng dụng](apps/access-rules.md).

## File SQL

Bốn file trong thư mục `database` chạy theo thứ tự tên khi cài đặt, trong schema `phong_may`:

| File | Nội dung |
|---|---|
| `database/0001_phong.sql` | Bảng `phong` cùng bốn phòng mẫu. Mọi người dùng xem được phòng. Chỉ phụ trách phòng sửa được số máy |
| `database/0002_nguoi_dung.sql` | Bảng `nguoi_dung`, hàm `cap_nhat_nguoi_dung` ghi tên và role của người đang đăng nhập, hàm `bao_vai` gửi thông báo cho mọi người có một role |
| `database/0003_don.sql` | Bảng `don` chứa các đơn đặt phòng, view `lich` gồm các đơn đã duyệt và hàm `kiem_tra_don` kiểm tra một đơn trước khi gửi |
| `database/0004_quy_trinh.sql` | Bốn hàm của các bước máy làm: `ghi_don`, `nhac_duyet`, `ghi_ket_qua` và `ghi_san_sang` |

Bảng `don` dùng Row-Level Security (RLS) của PostgreSQL, tức các chính sách quyết định mỗi người thấy được những dòng nào của bảng. Giáo viên chỉ thấy đơn của mình. Phụ trách phòng thấy mọi đơn. Chuyên viên chỉ thấy đơn đã duyệt. Role `phong_may_user` chỉ có quyền đọc bảng này. Do đó, đơn chỉ được ghi và đổi trạng thái qua các bước máy làm của quy trình. Ràng buộc `khong_trung_lich` trong file `database/0003_don.sql` chặn hai đơn đã duyệt trùng giờ ở cùng một phòng, kể cả khi hai phụ trách phòng duyệt cùng lúc:

```sql
CONSTRAINT khong_trung_lich EXCLUDE USING gist (
    int4range(phong_id, phong_id, '[]') WITH =,
    tstzrange(bat_dau, ket_thuc) WITH &&
) WHERE (trang_thai IN ('da_duyet', 'san_sang'))
```

Thông báo của lõi gửi cho từng người theo mã người dùng. Để nhắc mọi phụ trách phòng, ứng dụng cần biết ai có role này. Do đó, giao diện gọi hàm `cap_nhat_nguoi_dung` mỗi khi mở trang. Hàm ghi tên và các role của ứng dụng từ access token vào bảng `nguoi_dung`. Hàm `bao_vai` đọc bảng này để gửi thông báo cho mọi người có một role.

## Quy trình

File `processes/dat-phong.bpmn` khai báo quy trình `phong_may.dat_phong` gồm các bước sau:

| Bước | Loại | Người làm | Việc |
|---|---|---|---|
| `gui_don` | Sự kiện bắt đầu có form | Giáo viên | Nhập thông tin của đơn |
| `ghi_don` | Bước máy làm | Hàm `phong_may.ghi_don` | Kiểm tra rồi ghi đơn, trả về `hop_le`, `ma_don` và `han_duyet` |
| `kiem_tra` | Gateway | Operaton | Kết thúc quy trình khi đơn không hợp lệ |
| `duyet` | Việc của người dùng | Phụ trách phòng | Đồng ý hoặc từ chối đơn, ghi ý kiến |
| `qua_han` | Hẹn giờ trên biên của việc `duyet` | Operaton | Tới `han_duyet` thì gọi hàm `phong_may.nhac_duyet`, việc duyệt vẫn còn |
| `ghi_ket_qua` | Bước máy làm | Hàm `phong_may.ghi_ket_qua` | Ghi kết quả, báo giáo viên, và báo chuyên viên khi đơn được duyệt |
| `kiem_duyet` | Gateway | Operaton | Kết thúc quy trình khi đơn bị từ chối |
| `chuan_bi` | Việc của người dùng | Chuyên viên | Ghi số máy sẵn sàng và ghi chú chuẩn bị |
| `ghi_san_sang` | Bước máy làm | Hàm `phong_may.ghi_san_sang` | Ghi phòng đã sẵn sàng và báo giáo viên |

File có đủ phần hình vẽ, nên Cockpit vẽ được quy trình kèm số đơn đang ở từng bước. Form, bước máy làm và hẹn giờ được trình bày ở trang [Quy trình](apps/workflow.md).

## Giao diện

Thư mục `ui` gồm ba file, không dùng thư viện ngoài và không cần build:

- `ui/index.html` là khung trang, gồm menu bên trái, thanh trên và vùng nội dung.
- `ui/style.css` chứa kiểu trình bày của trang.
- `ui/app.js` đăng nhập, gọi API và hiện đúng phần việc của từng role.

Trang đăng nhập bằng client `phong-may` theo luồng Authorization Code với PKCE, như ở trang [Đăng nhập](apps/login.md). Sau khi đăng nhập, trang gọi API của ứng dụng để đọc phòng, đơn và lịch, gọi `POST /core/processes/phong_may.dat_phong/start` để gửi đơn và gọi `GET /core/tasks` để lấy việc cần duyệt hoặc cần chuẩn bị. Dữ liệu trên trang được tải lại 30 giây một lần.

## Cài đặt ứng dụng mẫu

Trên hệ thống đã cài đặt theo trang [Cài đặt](install.md), chạy các lệnh sau trong thư mục `SaigonOS` đã tạo bằng `git clone`. Lệnh đầu soát ứng dụng, lệnh sau cài đặt ứng dụng vào hệ thống đang chạy:

```bash
saigonos apply --check examples/phong-may
saigonos apply examples/phong-may
```

Kết quả của hai lệnh được trình bày ở trang [Bản khai và cài đặt ứng dụng](apps/manifest.md#cài-đặt-ứng-dụng). Cũng có thể cài đặt bằng Docker Compose:

```bash
cp -r examples/phong-may ~/saigonos/apps/
cd ~/saigonos
docker compose run --rm apps apply phong-may
```

## Gán role cho người dùng

Người dùng cần một role của ứng dụng để dùng ứng dụng. Để gán role trong Admin Console của realm `saigonos`, chọn Users, chọn người dùng, mở thẻ Role mapping, bấm Assign role rồi chọn role. Role cũng gán được bằng dòng lệnh. Ví dụ, các lệnh sau tạo tài khoản `giaovien1` có role giáo viên:

```bash
cd ~/saigonos
docker compose exec keycloak /opt/keycloak/bin/kcadm.sh config credentials --server http://localhost:8080/auth --realm master --user admin
docker compose exec keycloak /opt/keycloak/bin/kcadm.sh create users -r saigonos -s username=giaovien1 -s email=giaovien1@example.com -s firstName=Giáo -s lastName=Viên -s enabled=true
docker compose exec keycloak /opt/keycloak/bin/kcadm.sh set-password -r saigonos --username giaovien1
docker compose exec keycloak /opt/keycloak/bin/kcadm.sh add-roles -r saigonos --uusername giaovien1 --rolename phong-may.giao-vien
```

Lệnh thứ hai hỏi mật khẩu `KEYCLOAK_ADMIN_PASSWORD` trong file `.env`. Lệnh thứ tư hỏi mật khẩu cho tài khoản mới. Tài khoản cho ba role còn lại được tạo theo cách tương tự.

## Dùng thử

1. Mở http://localhost:9080/apps/phong-may/ rồi đăng nhập bằng tài khoản giáo viên. Mở mục Đặt phòng, chọn phòng và giờ rồi gửi đơn.
2. Đăng nhập bằng tài khoản phụ trách phòng. Mở mục Đơn chờ duyệt rồi đồng ý đơn vừa gửi.
3. Đăng nhập bằng tài khoản chuyên viên. Mở mục Chuẩn bị phòng rồi ghi số máy sẵn sàng.
4. Đăng nhập bằng tài khoản giáo viên. Mục Thông báo có kết quả của từng bước. Mục Lịch phòng có đơn vừa được duyệt.

Tài khoản quản trị mở Cockpit tại http://localhost:9080/operaton/ để xem quy trình `phong_may.dat_phong` và các đơn đang chạy.

## Gỡ ứng dụng mẫu

```bash
saigonos remove phong-may
```

Lệnh gỡ client, route, giao diện và tạm dừng quy trình của ứng dụng. Phần còn lại của hệ thống vẫn chạy. Dữ liệu và các role được giữ lại, nên khi cài đặt lại, ứng dụng dùng tiếp các đơn cũ.

## Viết ứng dụng mới từ mẫu

Để viết ứng dụng mới, chép thư mục `examples/phong-may` rồi đổi mọi chữ `phong-may` và `phong_may` thành tên của ứng dụng mới. Tên này có mặt trong bản khai, tên role, tên schema trong các hàm SQL, mã quy trình và các hằng số ở đầu file `ui/app.js`. Sau đó, chạy lệnh soát để tìm chỗ còn sai.
