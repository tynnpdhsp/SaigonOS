# SPDX-License-Identifier: Apache-2.0
package saigonos.admin_test

import data.saigonos.admin

key := {"kty": "oct", "k": "a2hvYS1raWVtLXRodQ"}

bearer(claims) := concat(" ", ["Bearer", io.jwt.encode_sign({"alg": "HS256", "typ": "JWT"}, claims, key)])

call(path, address, headers) := {
	"request": {"method": "GET", "path": path, "headers": headers},
	"var": {"remote_addr": address},
}

console := call("/auth/admin/saigonos/console/", "203.0.113.7", {})

users(headers) := call("/auth/admin/realms/saigonos/users", "203.0.113.7", headers)

env(value) := {"env": {"SAIGONOS_ADMIN_NETWORKS": value}}

reason(decision) := decision.reason if not decision.allow

test_console_is_open_when_networks_are_not_set if {
	admin.decision.allow with input as console with opa.runtime as {"env": {}}
}

test_empty_setting_does_not_limit_networks if {
	admin.decision.allow with input as console with opa.runtime as env(" , ")
}

test_address_inside_declared_network_is_allowed if {
	admin.decision.allow with input as console with opa.runtime as env("10.0.0.0/8, 203.0.113.0/24")
}

test_ipv6_address_inside_declared_network_is_allowed if {
	page := call("/operaton/app/cockpit/", "2001:db8::7", {})
	admin.decision.allow with input as page with opa.runtime as env("2001:db8::/32")
}

test_address_outside_declared_networks_is_refused if {
	decision := admin.decision with input as console with opa.runtime as env("10.0.0.0/8")
	decision.status_code == 403
	reason(decision) == "Địa chỉ IP này không được vào trang quản trị."
	decision.headers["Content-Type"] == "text/plain; charset=utf-8"
}

test_invalid_network_refuses_every_call if {
	setting := env("203.0.113.0/24, 203.0.113.7")
	decision := admin.decision with input as console with opa.runtime as setting
	reason(decision) == "Dải mạng 203.0.113.7 trong SAIGONOS_ADMIN_NETWORKS không hợp lệ."
	admin.config_errors == {reason(decision)} with opa.runtime as setting
}

test_call_without_address_is_refused if {
	page := {"request": {"method": "GET", "path": "/operaton/app/", "headers": {}}, "var": {}}
	not admin.decision.allow with input as page with opa.runtime as env("10.0.0.0/8")
}

test_token_with_otp_reaches_admin_api if {
	headers := {"authorization": bearer({"sub": "u", "amr": ["pwd", "otp"]})}
	admin.decision.allow with input as users(headers) with opa.runtime as {"env": {}}
}

test_token_without_otp_is_refused_by_admin_api if {
	headers := {"authorization": bearer({"sub": "u", "amr": ["pwd"]})}
	decision := admin.decision with input as users(headers) with opa.runtime as {"env": {}}
	reason(decision) == "Trang quản trị cần đăng nhập bằng mật khẩu và mã OTP."
}

test_token_without_amr_is_refused_by_admin_api if {
	headers := {"authorization": bearer({"sub": "u"})}
	not admin.decision.allow with input as users(headers) with opa.runtime as {"env": {}}
}

test_header_that_is_not_bearer_token_is_refused_by_admin_api if {
	headers := {"authorization": "Basic YWRtaW46YWRtaW4="}
	not admin.decision.allow with input as users(headers) with opa.runtime as {"env": {}}
}

test_repeated_authorization_header_is_refused_by_admin_api if {
	token := bearer({"sub": "u", "amr": ["otp"]})
	headers := {"authorization": [token, token]}
	not admin.decision.allow with input as users(headers) with opa.runtime as {"env": {}}
}

test_both_reasons_are_given_together if {
	headers := {"authorization": bearer({"sub": "u", "amr": ["pwd"]})}
	decision := admin.decision with input as users(headers) with opa.runtime as env("10.0.0.0/8")
	reason(decision) == "Trang quản trị cần đăng nhập bằng mật khẩu và mã OTP. Địa chỉ IP này không được vào trang quản trị."
}

test_operaton_does_not_read_tokens if {
	page := call("/operaton/app/cockpit/", "203.0.113.7", {"authorization": "Bearer khong-hop-le"})
	admin.decision.allow with input as page with opa.runtime as {"env": {}}
}
