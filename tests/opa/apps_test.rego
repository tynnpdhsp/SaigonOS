# SPDX-License-Identifier: Apache-2.0
package saigonos.apps_test

import data.saigonos.apps

key := {"kty": "oct", "k": "a2hvYS1raWVtLXRodQ"}

bearer(claims) := concat(" ", ["Bearer", io.jwt.encode_sign({"alg": "HS256", "typ": "JWT"}, claims, key)])

manager := bearer({"realm_access": {"roles": ["authenticated", "nghi-phep.quan-ly"]}, "amr": ["pwd", "otp"]})

staff := bearer({"realm_access": {"roles": ["authenticated", "nghi-phep.nhan-vien"]}, "amr": ["pwd"]})

route(rules) := {"labels": object.union(
	{"saigonos.app": "nghi-phep"},
	{sprintf("saigonos.access.%d", [index + 1]): json.marshal(rule) | some index, rule in rules},
)}

call(method, path, authorization, rules) := {
	"request": {"method": method, "path": path, "headers": headers(authorization)},
	"var": {"remote_addr": "192.168.1.20"},
	"route": route(rules),
}

headers(authorization) := {} if authorization == ""

headers(authorization) := {"authorization": authorization} if authorization != ""

approve := {"methods": ["POST"], "paths": ["/rpc/duyet_don"], "roles": ["nghi-phep.quan-ly"]}

refused(decision, status, message) if {
	not decision.allow
	decision.status_code == status
	decision.reason == {"code": "SGN03", "message": message, "details": null, "hint": null}
	decision.headers["Content-Type"] == "application/json; charset=utf-8"
}

test_app_without_rules_is_open if {
	apps.decision == {"allow": true} with input as call("POST", "/apps/nghi-phep/api/don", "", [])
}

test_caller_with_role_passes_rule if {
	apps.decision.allow with input as call("POST", "/apps/nghi-phep/api/rpc/duyet_don", manager, [approve])
}

test_caller_without_role_is_refused if {
	decision := apps.decision with input as call("POST", "/apps/nghi-phep/api/rpc/duyet_don", staff, [approve])
	refused(decision, 403, "Lời gọi này cần một trong các role: nghi-phep.quan-ly.")
}

test_call_without_token_gets_401 if {
	decision := apps.decision with input as call("POST", "/apps/nghi-phep/api/rpc/duyet_don", "", [approve])
	refused(decision, 401, "Lời gọi này cần access token.")
	decision.headers["WWW-Authenticate"] == "Bearer"
}

test_header_that_is_not_bearer_token_counts_as_no_token if {
	request := call("POST", "/apps/nghi-phep/api/rpc/duyet_don", "Basic dGh1OnRodQ==", [approve])
	refused(apps.decision, 401, "Lời gọi này cần access token.") with input as request
}

test_rule_skips_other_methods_and_paths if {
	apps.decision.allow with input as call("GET", "/apps/nghi-phep/api/rpc/duyet_don", staff, [approve])
	apps.decision.allow with input as call("POST", "/apps/nghi-phep/api/rpc/tu_choi", staff, [approve])
}

test_rule_for_get_also_covers_head if {
	rule := {"methods": ["GET"], "roles": ["nghi-phep.quan-ly"]}
	not apps.decision.allow with input as call("HEAD", "/apps/nghi-phep/api/don", staff, [rule])
}

test_rule_without_methods_and_paths_covers_every_call if {
	rule := {"roles": ["nghi-phep.quan-ly"]}
	not apps.decision.allow with input as call("DELETE", "/apps/nghi-phep/api/don", staff, [rule])
	not apps.decision.allow with input as call("GET", "/apps/nghi-phep/api", staff, [rule])
}

test_star_matches_one_level_only if {
	rule := {"paths": ["/rpc/*"], "roles": ["nghi-phep.quan-ly"]}
	not apps.decision.allow with input as call("POST", "/apps/nghi-phep/api/rpc/duyet_don", staff, [rule])
	apps.decision.allow with input as call("POST", "/apps/nghi-phep/api/rpc/a/b", staff, [rule])
}

test_double_star_matches_many_levels if {
	rule := {"paths": ["/rpc/**"], "roles": ["nghi-phep.quan-ly"]}
	not apps.decision.allow with input as call("POST", "/apps/nghi-phep/api/rpc/a/b", staff, [rule])
}

test_prefix_pattern_matches_tables_with_same_start if {
	rule := {"paths": ["/don*"], "roles": ["nghi-phep.quan-ly"]}
	not apps.decision.allow with input as call("GET", "/apps/nghi-phep/api/don", staff, [rule])
	not apps.decision.allow with input as call("GET", "/apps/nghi-phep/api/don_tu", staff, [rule])
	apps.decision.allow with input as call("GET", "/apps/nghi-phep/api/ngay_nghi", staff, [rule])
}

test_root_of_api_is_slash if {
	rule := {"paths": ["/"], "roles": ["nghi-phep.quan-ly"]}
	not apps.decision.allow with input as call("GET", "/apps/nghi-phep/api", staff, [rule])
}

test_address_inside_network_passes if {
	rule := {"networks": ["192.168.1.0/24", "2001:db8::/32"]}
	apps.decision.allow with input as call("GET", "/apps/nghi-phep/api/don", "", [rule])
}

test_address_outside_networks_is_refused if {
	request := call("GET", "/apps/nghi-phep/api/don", "", [{"networks": ["10.0.0.0/8"]}])
	message := "Địa chỉ IP này không được gọi đường dẫn này của ứng dụng."
	refused(apps.decision, 403, message) with input as request
}

test_login_with_otp_passes if {
	apps.decision.allow with input as call("DELETE", "/apps/nghi-phep/api/don", manager, [{"otp": true}])
}

test_login_without_otp_is_refused if {
	request := call("DELETE", "/apps/nghi-phep/api/don", staff, [{"otp": true}])
	refused(apps.decision, 403, "Lời gọi này cần đăng nhập bằng mật khẩu và mã OTP.") with input as request
}

test_token_without_claims_of_login_is_refused if {
	request := call("DELETE", "/apps/nghi-phep/api/don", bearer({"sub": "u"}), [approve, {"otp": true}])
	reasons := "Lời gọi này cần một trong các role: nghi-phep.quan-ly. Lời gọi này cần đăng nhập bằng mật khẩu và mã OTP."
	request_post := object.union(request, {"request": {"method": "POST", "path": "/apps/nghi-phep/api/rpc/duyet_don"}})
	refused(apps.decision, 403, reasons) with input as request_post
}

test_every_failing_rule_is_reported if {
	rules := [approve, {"networks": ["10.0.0.0/8"]}]
	request := call("POST", "/apps/nghi-phep/api/rpc/duyet_don", staff, rules)
	reasons := "Lời gọi này cần một trong các role: nghi-phep.quan-ly. Địa chỉ IP này không được gọi đường dẫn này của ứng dụng."
	refused(apps.decision, 403, reasons) with input as request
}

broken := "Luật truy cập của ứng dụng bị lỗi, hãy cài đặt lại ứng dụng."

test_label_that_is_not_json_refuses_every_call if {
	request := call("GET", "/apps/nghi-phep/api/don", manager, [])
	labels := {"saigonos.app": "nghi-phep", "saigonos.access.1": "{khong-phai-json"}
	refused(apps.decision, 503, broken) with input as object.union(request, {"route": {"labels": labels}})
}

test_rule_with_wrong_shape_refuses_every_call if {
	shapes := [
		["roles"],
		{"methods": "POST", "otp": true},
		{"methods": ["OPTIONS"], "otp": true},
		{"paths": ["don"], "otp": true},
		{"networks": ["192.168.1.5"], "otp": true},
		{"roles": [], "otp": true},
		{"roles": [1]},
		{"otp": "true"},
		{"otp": false},
		{"methods": ["GET"]},
		{"otp": true, "message": "x"},
	]
	every shape in shapes {
		refused(apps.decision, 503, broken) with input as call("GET", "/apps/nghi-phep/api/don", manager, [shape])
	}
}

test_route_without_app_label_refuses_every_call if {
	request := {
		"request": {"method": "GET", "path": "/apps/nghi-phep/api/don", "headers": {}},
		"var": {"remote_addr": "192.168.1.20"},
		"route": {"labels": {"saigonos.access.1": json.marshal({"otp": true})}},
	}
	refused(apps.decision, 503, broken) with input as request
}

test_path_outside_api_of_app_refuses_every_call if {
	refused(apps.decision, 503, broken) with input as call("GET", "/apps/khac/api/don", manager, [{"otp": true}])
	refused(apps.decision, 503, broken) with input as call("GET", "/apps/nghi-phep/apidon", manager, [{"otp": true}])
}
