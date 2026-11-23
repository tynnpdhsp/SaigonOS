# SPDX-License-Identifier: Apache-2.0
import json
import re
from importlib.resources import files

import pytest

from saigonos_core.app_gateway import wanted_route
from saigonos_core.manifest import Manifest

APISIX = files("saigonos") / "stack" / "config" / "apisix"
CONFIG = (APISIX / "config.yaml").read_text(encoding="utf-8")
PLUGIN = (APISIX / "saigonos-waf.lua").read_text(encoding="utf-8")
COMPOSE = (files("saigonos") / "stack" / "compose.yaml").read_text(encoding="utf-8")
WAF = json.loads((APISIX / "global-rules" / "waf.json").read_text(encoding="utf-8"))
DIRECTIVES = WAF["plugins"]["coraza-filter"]["conf"]["directives_map"]["saigonos"]
GUARDED = Manifest.model_validate(
    {
        "name": "nghi-phep",
        "title": "Nghỉ phép",
        "version": "0.1.0",
        "roles": [{"name": "nghi-phep.quan-ly", "description": "Duyệt đơn"}],
        "access": [{"methods": ["POST"], "roles": ["nghi-phep.quan-ly"]}],
    }
)


def section(name):
    block = CONFIG.split(f"\n{name}:\n", 1)[1]
    lines = []
    for line in block.splitlines():
        if line and not line.startswith(" "):
            break
        lines.append(line)
    return lines


def enabled_plugins():
    return [line.removeprefix("  - ") for line in section("plugins") if line.startswith("  - ")]


def wasm_plugin():
    pairs = (line.strip().removeprefix("- ").split(": ", 1) for line in section("wasm")[1:])
    return dict(pair for pair in pairs if len(pair) == 2)


def used_plugins():
    used = set()
    for folder in ("routes", "global-rules"):
        for path in (APISIX / folder).iterdir():
            used |= set(json.loads(path.read_text(encoding="utf-8")).get("plugins", {}))
    return used | set(wanted_route(GUARDED)["plugins"])


def matches(rules, uri):
    for rule in rules:
        negated = len(rule) == 4
        _, *operator, pattern = rule
        assert operator[-1] == "~~"
        if bool(re.search(pattern, uri)) == negated:
            return False
    return True


def test_gateway_enables_exactly_the_plugins_that_routes_and_apps_use():
    assert set(enabled_plugins()) | {wasm_plugin()["name"]} == used_plugins()


def test_stream_plugins_are_turned_off():
    assert "stream_plugins: []" in CONFIG.splitlines()


def test_coraza_runs_in_rewrite_phase_right_after_plugin_that_hands_it_the_body():
    coraza = wasm_plugin()
    priority = int(re.search(r"priority = (\d+),", PLUGIN)[1])

    assert coraza["name"] == "coraza-filter"
    assert coraza["http_request_phase"] == "rewrite"
    assert int(coraza["priority"]) == priority - 1
    assert coraza["file"] == "/usr/local/apisix/wasm/coraza-proxy-wasm.wasm"
    assert 'ngx.var.wasm_process_req_body = "on"' in PLUGIN


@pytest.mark.parametrize(
    "uri",
    ["/api", "/api/", "/api/notes", "/apps/thu/", "/apps/thu/api/notes", "/core", "/core/files"],
)
def test_waf_checks_api_apps_and_core(uri):
    for plugin in WAF["plugins"].values():
        assert matches(plugin["_meta"]["filter"], uri)


@pytest.mark.parametrize(
    "uri",
    [
        "/core/files/0b9c/content",
        "/auth/realms/saigonos",
        "/auth/admin/saigonos/console/",
        "/operaton/app/cockpit/",
        "/realtime/connection/websocket",
        "/apisix",
        "/corex",
    ],
)
def test_waf_leaves_file_content_login_workflow_and_realtime_alone(uri):
    for plugin in WAF["plugins"].values():
        assert not matches(plugin["_meta"]["filter"], uri)


def test_waf_mode_and_engine_come_from_env():
    assert WAF["plugins"]["saigonos-waf"]["mode"] == "${SAIGONOS_WAF_MODE}"
    assert DIRECTIVES[1] == "SecRuleEngine ${SAIGONOS_WAF_ENGINE}"


def test_waf_loads_crs_after_its_setup_and_allows_methods_of_api():
    setup = DIRECTIVES.index("Include @crs-setup-conf")
    rules = DIRECTIVES.index("Include @owasp_crs/*.conf")
    methods = next(index for index, line in enumerate(DIRECTIVES) if "tx.allowed_methods" in line)

    assert DIRECTIVES[0] == "Include @recommended-conf"
    assert setup < methods < rules
    assert "GET HEAD POST OPTIONS PUT PATCH DELETE" in DIRECTIVES[methods]


def test_coraza_and_plugin_share_one_body_limit():
    limit = int(re.search(r"local LIMIT = (\d+)", PLUGIN)[1])

    assert f"SecRequestBodyLimit {limit}" in DIRECTIVES
    assert f"SecRequestBodyInMemoryLimit {limit}" in DIRECTIVES
    assert "SecResponseBodyAccess Off" in DIRECTIVES


def test_routes_service_loads_global_rules_with_block_as_default_mode():
    routes = COMPOSE.split("\n  routes:\n", 1)[1].split("\n\n", 1)[0]

    assert "SAIGONOS_WAF_MODE: ${SAIGONOS_WAF_MODE:-block}" in routes
    assert "/config/routes/*.json /config/global-rules/*.json" in routes


def test_prometheus_counts_every_request_of_gateway():
    rule = json.loads((APISIX / "global-rules" / "prometheus.json").read_text(encoding="utf-8"))

    assert rule == {"plugins": {"prometheus": {}}}


def test_metrics_are_exported_inside_docker_networks_only_with_label_of_denial():
    attributes = "\n".join(section("plugin_attr"))

    assert "    export_addr:\n      ip: 0.0.0.0\n      port: 9091\n" in attributes
    assert "    refresh_interval: 5\n" in attributes
    assert "          - denied_by: $sent_http_x_saigonos_denied_by" in attributes
    assert "9091" not in COMPOSE


def test_waf_and_opa_mark_the_requests_they_refuse():
    policies = files("saigonos") / "stack" / "config" / "opa"

    assert 'core.response.set_header("X-SaigonOS-Denied-By", "waf")' in PLUGIN
    for name in ("admin.rego", "apps.rego"):
        assert '"X-SaigonOS-Denied-By": "opa"' in (policies / name).read_text(encoding="utf-8")
