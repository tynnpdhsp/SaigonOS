<!-- SPDX-License-Identifier: Apache-2.0 -->
# Tường lửa ứng dụng web

Cấu hình của tường lửa nằm trong thư mục [`src/saigonos/stack/config/apisix`](https://github.com/tynnpdhsp/SaigonOS/tree/main/src/saigonos/stack/config/apisix):

- File `global-rules/waf.json` là global rule gắn plugin `saigonos-waf` và `coraza-filter` vào `/api`, `/apps` và `/core`. Bộ lọc `_meta.filter` của hai plugin phải giống nhau. Các chỉ thị của Coraza nằm trong `directives_map`. Service `routes` thay `${SAIGONOS_WAF_MODE}` và `${SAIGONOS_WAF_ENGINE}` theo giá trị `SAIGONOS_WAF_MODE` của file `.env`.
- File [`saigonos-waf.lua`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/config/apisix/saigonos-waf.lua) là plugin của SaigonOS. Plugin chạy ở pha rewrite với priority 8000, ngay trước Coraza với priority 7999.
- File [`fetch-coraza.sh`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/config/apisix/fetch-coraza.sh) là script của service `waf`.

Khi một luật CRS chặn nhầm lời gọi hợp lệ, tìm mã luật trong log của APISIX. Thêm chỉ thị `SecRuleRemoveById` với mã luật đó vào sau dòng `Include @owasp_crs/*.conf` trong file [`waf.json`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/config/apisix/global-rules/waf.json), rồi ghi mã luật và lý do vào trang [Tường lửa ứng dụng web](../admin/waf.md#phạm-vi-kiểm-tra).

Một số điểm cần giữ khi sửa plugin `saigonos-waf`:

- APISIX chỉ đưa body cho plugin wasm khi biến `wasm_process_req_body` có giá trị. Coraza 0.6.0 không tự đặt biến này. Khi không nhận body, Coraza chỉ chạy pha 2 của CRS lúc upstream đã trả lời. Do đó, plugin đặt biến này cho mọi lời gọi, kể cả lời gọi không có body.
- Khi Coraza chặn, wasm-nginx-module gọi `ngx.exit` trong pha rewrite của global rule, trước khi APISIX chọn plugin của route. Plugin nhận ra trường hợp này vì `ctx.plugins` còn trống, rồi thay nội dung trả về bằng JSON mã `SGN04`. Lỗi 401 của `openid-connect` và lỗi 403 của OPA xảy ra sau khi APISIX chọn plugin của route, nên không bị thay.
- Mỗi worker của APISIX giữ một bản Coraza cùng bộ luật CRS, khoảng 85 MB RAM. Thêm worker thì RAM tăng theo.

Khi đổi phiên bản coraza-proxy-wasm:

1. Sửa `CORAZA_VERSION` của service `waf` trong [`compose.yaml`](https://github.com/tynnpdhsp/SaigonOS/blob/main/src/saigonos/stack/compose.yaml).
2. Sửa `CORAZA_ZIP_SHA256` theo digest của file zip trên trang Releases của dự án.
3. Giải nén file zip, tính mã băm của file `coraza-proxy-wasm.wasm` bằng `sha256sum`, rồi sửa `CORAZA_WASM_SHA256`.
4. Đọc file giấy phép của đúng phiên bản đó, khai báo phiên bản mới trong `PLUGINS` ở [`scripts/dependencies.py`](https://github.com/tynnpdhsp/SaigonOS/blob/main/scripts/dependencies.py), rồi chạy `make dependencies`.
5. Kiểm tra phiên bản CRS đi kèm trong file `wasmplugin/rules/crs-setup.conf.example` của dự án.

APISIX chỉ bật các plugin trong danh sách `plugins` của `config.yaml`. Khi route hoặc lệnh `apply` dùng thêm plugin, thêm plugin đó vào danh sách. Kiểm thử `test_gateway_enables_exactly_the_plugins_that_routes_and_apps_use` báo lỗi khi danh sách lệch.