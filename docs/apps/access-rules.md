<!-- SPDX-License-Identifier: Apache-2.0 -->
# Luật truy cập của ứng dụng

Trường `access` của bản khai gồm tối đa 20 luật. OPA áp dụng các luật này cho API của ứng dụng tại `/apps/<tên ứng dụng>/api/`. Một lời gọi khớp với luật khi phương thức thuộc `methods` và đường dẫn khớp một mẫu trong `paths`. Lời gọi khớp với luật phải đạt mọi điều kiện của luật đó. Lời gọi không khớp luật nào vẫn được cho qua. Quyền trên từng bảng và từng dòng vẫn do file SQL của ứng dụng quyết định.

Ví dụ, file [`saigonos-app.json`](https://github.com/tynnpdhsp/SaigonOS/blob/main/examples/phong-may/saigonos-app.json) của ứng dụng mẫu có ba luật:

```json
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
```

Luật thứ nhất chỉ cho người có một trong bốn role của ứng dụng gọi API. Luật thứ hai chỉ cho giáo viên, phụ trách phòng và chuyên viên ghi dữ liệu, nên học sinh chỉ đọc được. Luật thứ ba chỉ cho phụ trách phòng sửa bảng `phong`.

| Trường | Ý nghĩa |
|---|---|
| `methods` | Các phương thức `GET`, `POST`, `PATCH`, `PUT`, `DELETE`. `GET` áp dụng cả cho `HEAD`. Khi không khai, luật áp dụng cho mọi phương thức |
| `paths` | Các mẫu đường dẫn tính từ `/apps/<tên ứng dụng>/api`, theo cú pháp glob. Dấu `*` khớp với một cấp, dấu `**` khớp với nhiều cấp, `/` là gốc của API. Khi không khai, luật áp dụng cho mọi đường dẫn |
| `roles` | Người gọi phải có ít nhất một role trong danh sách. Các role phải được khai trong trường `roles` của bản khai |
| `networks` | Địa chỉ IP của người gọi phải thuộc một dải mạng trong danh sách, viết theo dạng CIDR |
| `otp` | Khi có giá trị `true`, người gọi phải đăng nhập bằng mật khẩu và mã OTP. Người dùng tự cài OTP ở trang tài khoản `/auth/realms/saigonos/account/` |

Mỗi luật có ít nhất một điều kiện `roles`, `networks` hoặc `otp`. Khi viết thành JSON không có khoảng trắng, mỗi luật dài tối đa 256 ký tự. Luật dài hơn cần được tách thành nhiều luật. Luật có hiệu lực ngay khi lệnh cài đặt chạy xong.

Lời gọi bị từ chối nhận mã 403, hoặc mã 401 khi luật cần access token mà lời gọi không có. Nội dung trả về có dạng lỗi của PostgREST với mã `SGN03`. Ví dụ, khi giáo viên sửa bảng `phong`:

```json
{"code": "SGN03", "message": "Lời gọi này cần một trong các role: phong-may.phu-trach.", "details": null, "hint": null}
```

Khi OPA dừng, API của ứng dụng có luật bị từ chối. API của ứng dụng không có luật vẫn hoạt động.
