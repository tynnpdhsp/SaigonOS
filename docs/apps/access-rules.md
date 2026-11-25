<!-- SPDX-License-Identifier: Apache-2.0 -->
# Luật truy cập của ứng dụng

Trường `access` của bản khai gồm tối đa 20 luật. OPA áp dụng các luật này cho API của ứng dụng tại `/apps/<tên ứng dụng>/api/`. Một lời gọi khớp với luật khi phương thức thuộc `methods` và đường dẫn khớp một mẫu trong `paths`. Lời gọi khớp với luật phải đạt mọi điều kiện của luật đó. Lời gọi không khớp luật nào vẫn được cho qua. Quyền trên từng bảng và từng dòng vẫn do file SQL của ứng dụng quyết định.

Ví dụ:

```json
"access": [
  {
    "methods": ["POST"],
    "paths": ["/rpc/duyet_don"],
    "roles": ["nghi-phep.quan-ly"],
    "otp": true
  },
  {
    "networks": ["192.168.1.0/24"]
  }
]
```

Luật thứ nhất chỉ cho người có role `nghi-phep.quan-ly` đã đăng nhập bằng mã OTP gọi hàm `duyet_don`. Luật thứ hai chỉ mở API của ứng dụng cho mạng `192.168.1.0/24`.

| Trường | Ý nghĩa |
|---|---|
| `methods` | Các phương thức `GET`, `POST`, `PATCH`, `PUT`, `DELETE`. `GET` áp dụng cả cho `HEAD`. Khi không khai, luật áp dụng cho mọi phương thức |
| `paths` | Các mẫu đường dẫn tính từ `/apps/<tên ứng dụng>/api`, theo cú pháp glob. Dấu `*` khớp với một cấp, dấu `**` khớp với nhiều cấp, `/` là gốc của API. Khi không khai, luật áp dụng cho mọi đường dẫn |
| `roles` | Người gọi phải có ít nhất một role trong danh sách. Các role phải được khai trong trường `roles` của bản khai |
| `networks` | Địa chỉ IP của người gọi phải thuộc một dải mạng trong danh sách, viết theo dạng CIDR |
| `otp` | Khi có giá trị `true`, người gọi phải đăng nhập bằng mật khẩu và mã OTP. Người dùng tự cài OTP ở trang tài khoản `/auth/realms/saigonos/account/` |

Mỗi luật có ít nhất một điều kiện `roles`, `networks` hoặc `otp`. Lệnh cài đặt ghi mỗi luật thành một label của route `app-<tên ứng dụng>` và thêm plugin `opa` vào route. Do đó, luật có hiệu lực ngay khi lệnh cài đặt chạy xong và được gỡ cùng route. Khi viết thành JSON không có khoảng trắng, mỗi luật dài tối đa 256 ký tự, vì đó là giới hạn của label trong APISIX. Luật dài hơn cần được tách thành nhiều luật. Ứng dụng không khai luật thì route không có plugin `opa`.

Lời gọi bị từ chối nhận mã 403. Khi luật cần access token mà lời gọi không có, mã trả về là 401. Nội dung trả về có dạng lỗi của PostgREST, ví dụ:

```json
{"code": "SGN03", "message": "Lời gọi này cần một trong các role: nghi-phep.quan-ly.", "details": null, "hint": null}
```

Khi OPA dừng, API của ứng dụng có luật bị từ chối. API của ứng dụng không có luật vẫn hoạt động.
