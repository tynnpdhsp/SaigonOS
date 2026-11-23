# SPDX-License-Identifier: Apache-2.0
package saigonos.admin

networks := [network |
	some part in split(object.get(opa.runtime().env, "SAIGONOS_ADMIN_NETWORKS", ""), ",")
	network := trim_space(part)
	network != ""
]

config_errors contains sprintf("Dải mạng %s trong SAIGONOS_ADMIN_NETWORKS không hợp lệ.", [network]) if {
	some network in networks
	not net.cidr_is_valid(network)
}

default address_allowed := false

address_allowed if count(networks) == 0

address_allowed if {
	some network in networks
	net.cidr_is_valid(network)
	net.cidr_contains(network, input.var.remote_addr)
}

authorization := input.request.headers.authorization

token := substring(authorization, 7, -1) if {
	is_string(authorization)
	startswith(lower(authorization), "bearer ")
}

claims := payload if {
	[_, payload, _] := io.jwt.decode(token)
}

default otp := false

otp if "otp" in claims.amr

keycloak_admin if startswith(input.request.path, "/auth/admin/")

deny contains message if {
	some message in config_errors
}

deny contains "Địa chỉ IP này không được vào trang quản trị." if not address_allowed

deny contains "Trang quản trị cần đăng nhập bằng mật khẩu và mã OTP." if {
	keycloak_admin
	authorization
	not otp
}

decision := {"allow": true} if count(deny) == 0

decision := {
	"allow": false,
	"status_code": 403,
	"reason": concat(" ", deny),
	"headers": {"Content-Type": "text/plain; charset=utf-8"},
} if count(deny) > 0
