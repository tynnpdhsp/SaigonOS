-- SPDX-License-Identifier: Apache-2.0
COMMENT ON SCHEMA api IS $$SaigonOS API

REST API của SaigonOS do PostgREST tự sinh. Tài liệu này chỉ liệt kê các bảng, view và hàm mà người gọi được dùng. Lời gọi không có access token nhận tài liệu theo quyền của role anon. Lời gọi có access token trong header Authorization nhận tài liệu theo quyền của người dùng đã đăng nhập.$$;
