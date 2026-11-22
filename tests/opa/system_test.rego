# SPDX-License-Identifier: Apache-2.0
package system.authz_test

import data.system.authz

test_health_is_allowed if {
	authz.allow with input as {"method": "GET", "path": ["health"]}
}

test_decision_is_allowed if {
	authz.allow with input as {"method": "POST", "path": ["v1", "data", "saigonos", "admin", "decision"]}
}

test_other_document_is_refused if {
	not authz.allow with input as {"method": "POST", "path": ["v1", "data", "saigonos", "admin", "networks"]}
}

test_decision_outside_saigonos_is_refused if {
	not authz.allow with input as {"method": "POST", "path": ["v1", "data", "system", "authz", "decision"]}
}

test_reading_decision_with_get_is_refused if {
	not authz.allow with input as {"method": "GET", "path": ["v1", "data", "saigonos", "admin", "decision"]}
}

test_changing_policy_is_refused if {
	not authz.allow with input as {"method": "PUT", "path": ["v1", "policies", "saigonos"]}
}

test_changing_data_is_refused if {
	not authz.allow with input as {"method": "PATCH", "path": ["v1", "data"]}
}

test_metrics_are_refused if {
	not authz.allow with input as {"method": "GET", "path": ["metrics"]}
}
