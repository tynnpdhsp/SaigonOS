# SPDX-License-Identifier: Apache-2.0
package saigonos.apps

labels := object.get(input, ["route", "labels"], {})

prefix := concat("", ["/apps/", labels["saigonos.app"], "/api"])

path := "/" if input.request.path == prefix

path := substring(input.request.path, count(prefix), -1) if {
	startswith(input.request.path, concat("", [prefix, "/"]))
}

method := "GET" if input.request.method == "HEAD"

method := input.request.method if input.request.method != "HEAD"

encoded contains value if {
	some key, value in labels
	startswith(key, "saigonos.access.")
}

rules contains rule if {
	some value in encoded
	json.is_valid(value)
	rule := json.unmarshal(value)
	valid_rule(rule)
}

broken if not path

broken if {
	some value in encoded
	not json.is_valid(value)
}

broken if {
	some value in encoded
	json.is_valid(value)
	not valid_rule(json.unmarshal(value))
}

valid_rule(rule) if {
	is_object(rule)
	every key, value in rule {
		valid_field(key, value)
	}
	condition(rule)
}

valid_field("methods", value) if {
	texts(value)
	every item in value {
		item in {"GET", "POST", "PATCH", "PUT", "DELETE"}
	}
}

valid_field("paths", value) if {
	texts(value)
	every item in value {
		regex.match(`^/[A-Za-z0-9_.*/-]*$`, item)
	}
}

valid_field("roles", value) if texts(value)

valid_field("networks", value) if {
	texts(value)
	every item in value {
		net.cidr_is_valid(item)
	}
}

valid_field("otp", value) if is_boolean(value)

texts(value) if {
	is_array(value)
	count(value) > 0
	every item in value {
		is_string(item)
	}
}

condition(rule) if rule.roles

condition(rule) if rule.networks

condition(rule) if rule.otp == true

applies contains rule if {
	not broken
	some rule in rules
	matches_method(rule)
	matches_path(rule)
}

matches_method(rule) if not rule.methods

matches_method(rule) if method in rule.methods

matches_path(rule) if not rule.paths

matches_path(rule) if {
	some pattern in rule.paths
	glob.match(pattern, ["/"], path)
}

authorization := input.request.headers.authorization

token := substring(authorization, 7, -1) if {
	is_string(authorization)
	startswith(lower(authorization), "bearer ")
}

claims := payload if {
	[_, payload, _] := io.jwt.decode(token)
}

missing_token if {
	some rule in applies
	needs_token(rule)
	not claims
}

needs_token(rule) if rule.roles

needs_token(rule) if rule.otp == true

has_role(rule) if {
	some role in rule.roles
	role in object.get(claims, ["realm_access", "roles"], [])
}

in_networks(rule) if {
	some network in rule.networks
	net.cidr_contains(network, input.var.remote_addr)
}

deny contains "Luật truy cập của ứng dụng bị lỗi, hãy cài đặt lại ứng dụng." if broken

deny contains "Lời gọi này cần access token." if missing_token

deny contains sprintf("Lời gọi này cần một trong các role: %s.", [concat(", ", rule.roles)]) if {
	some rule in applies
	rule.roles
	claims
	not has_role(rule)
}

deny contains "Địa chỉ IP này không được gọi đường dẫn này của ứng dụng." if {
	some rule in applies
	rule.networks
	not in_networks(rule)
}

deny contains "Lời gọi này cần đăng nhập bằng mật khẩu và mã OTP." if {
	some rule in applies
	rule.otp == true
	claims
	not "otp" in object.get(claims, "amr", [])
}

default status := 403

status := 503 if broken

status := 401 if missing_token

default headers := {"Content-Type": "application/json; charset=utf-8"}

headers := {"Content-Type": "application/json; charset=utf-8", "WWW-Authenticate": "Bearer"} if missing_token

default decision := {"allow": true}

decision := {
	"allow": false,
	"status_code": status,
	"reason": {"code": "SGN03", "message": concat(" ", deny), "details": null, "hint": null},
	"headers": headers,
} if count(deny) > 0
