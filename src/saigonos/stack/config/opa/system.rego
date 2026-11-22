# SPDX-License-Identifier: Apache-2.0
package system.authz

default allow := false

allow if {
	input.method == "GET"
	input.path == ["health"]
}

allow if {
	input.method == "POST"
	["v1", "data", "saigonos", _, "decision"] = input.path
}
