# SPDX-License-Identifier: Apache-2.0
import json
import re
from importlib.resources import files
from itertools import takewhile

import pytest

from saigonos.home import MONITORING_PROFILE, OPTIONAL_SERVICES

COMPOSE = (files("saigonos") / "stack" / "compose.yaml").read_text(encoding="utf-8")


def services():
    section = COMPOSE.split("\nservices:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    blocks = {}
    name = None
    for line in section.splitlines():
        header = re.fullmatch(r"  ([a-z][a-z-]*):", line)
        if header:
            name = header[1]
            blocks[name] = []
        elif name:
            blocks[name].append(line.strip())
    return blocks


LONG_RUNNING = [name for name, lines in services().items() if "restart: unless-stopped" in lines]


def test_stack_lists_long_running_services():
    assert {"postgres", "keycloak", "seaweedfs", "clamav", "freshclam", "core"} <= set(LONG_RUNNING)


@pytest.mark.parametrize("name", LONG_RUNNING)
def test_long_running_service_has_healthcheck_that_compose_2_can_wait_for(name):
    lines = services()[name]
    checks = [line for line in lines if line.startswith("test:")]

    assert "healthcheck:" in lines
    assert len(checks) == 1
    assert "NONE" not in checks[0]
    assert "disable: true" not in lines


def test_apps_service_uses_build_of_core_and_runs_only_when_called():
    apps, core = services()["apps"], services()["core"]

    assert [line for line in apps if line.startswith("build:")] == ["build: ./core"]
    assert [line for line in core if line.startswith("build:")] == ["build: ./core"]
    assert 'profiles: ["apps"]' in apps
    assert "- ./apps:/apps:ro" in apps


def test_only_apps_service_gets_admin_secrets_for_installing_apps():
    secrets = ("POSTGRES_PASSWORD", "KEYCLOAK_ADMIN_PASSWORD", "APISIX_ADMIN_KEY")

    for secret in secrets:
        assert any(f"${{{secret}:?}}" in line for line in services()["apps"])
        assert not any(secret in line for line in services()["core"])


def image_of(name):
    return [line for line in services()[name] if line.startswith("image:")]


def test_opa_runs_pinned_image_without_asking_for_new_versions():
    opa = services()["opa"]

    assert re.fullmatch(r"image: openpolicyagent/opa:\d+\.\d+\.\d+", image_of("opa")[0])
    for flag in ("--skip-version-check", "--watch", "--authorization=basic", "--ignore=.*"):
        assert f"- {flag}" in opa


def test_opa_starts_only_after_rules_and_admin_networks_pass_check():
    opa, policies = services()["opa"], services()["policies"]
    needs = opa[opa.index("policies:") + 1]
    command = list(
        takewhile(lambda line: line.startswith("- "), policies[policies.index("command:") + 1 :])
    )
    setting = "SAIGONOS_ADMIN_NETWORKS: ${SAIGONOS_ADMIN_NETWORKS:-}"

    assert image_of("policies") == image_of("opa")
    assert command == [
        "- eval",
        "- --fail-defined",
        "- --format=raw",
        "- --ignore=.*",
        "- --data=/policies",
        "- data.saigonos.admin.config_errors[_]",
    ]
    assert "network_mode: none" in policies
    assert needs == "condition: service_completed_successfully"
    assert setting in policies
    assert setting in opa


def test_waf_service_fetches_pinned_coraza_and_checks_zip_and_wasm():
    waf = services()["waf"]
    version = next(line for line in waf if line.startswith("CORAZA_VERSION:"))

    assert image_of("waf") == image_of("jwks")
    assert 'restart: "no"' in waf
    assert re.fullmatch(r'CORAZA_VERSION: "\d+\.\d+\.\d+"', version)
    for key in ("CORAZA_ZIP_SHA256", "CORAZA_WASM_SHA256"):
        assert any(re.fullmatch(rf"{key}: [0-9a-f]{{64}}", line) for line in waf)
    assert [name for name, lines in services().items() if "- waf" in lines] == ["waf"]
    assert 'entrypoint: ["sh", "/config/fetch-coraza.sh"]' in waf


def test_apisix_waits_for_coraza_and_reads_it_read_only():
    apisix = services()["apisix"]
    holders = [name for name, lines in services().items() if any("- wasm:" in x for x in lines)]

    assert apisix[apisix.index("waf:") + 1] == "condition: service_completed_successfully"
    assert "- wasm:/usr/local/apisix/wasm:ro" in apisix
    assert "- wasm:/wasm" in services()["waf"]
    assert sorted(holders) == ["apisix", "waf"]


def test_only_apisix_shares_internal_network_with_opa():
    networks = COMPOSE.split("\nnetworks:\n", 1)[1]

    assert sorted(name for name, lines in services().items() if "- policy" in lines) == [
        "apisix",
        "opa",
    ]
    assert "  policy:\n    internal: true\n" in networks


MONITORING = OPTIONAL_SERVICES[MONITORING_PROFILE]


def block(name, key):
    lines = services()[name]
    return list(takewhile(lambda line: line.startswith("- "), lines[lines.index(f"{key}:") + 1 :]))


def test_monitoring_profile_has_exactly_the_optional_services():
    profiled = [name for name, lines in services().items() if 'profiles: ["monitoring"]' in lines]

    assert sorted(profiled) == sorted(MONITORING)


@pytest.mark.parametrize("name", MONITORING)
def test_monitoring_service_is_pinned_and_publishes_no_port(name):
    lines = services()[name]
    images = image_of(name)

    assert "ports:" not in lines
    if images:
        assert re.fullmatch(r"image: [a-z./-]+:v?\d+\.\d+\.\d+(-musl)?", images[0])
    else:
        assert "build: ./core" in lines


def test_only_socket_proxy_holds_docker_socket_read_only_and_without_privileges():
    proxy = services()["socket-proxy"]
    holders = [name for name, lines in services().items() if any("docker.sock" in x for x in lines)]

    assert holders == ["socket-proxy"]
    assert "- /var/run/docker.sock:/var/run/docker.sock:ro" in proxy
    assert 'cap_drop: ["ALL"]' in proxy
    assert "read_only: true" in proxy
    assert 'security_opt: ["no-new-privileges:true"]' in proxy
    assert block("socket-proxy", "networks") == ["- docker"]
    assert not any(line.startswith("- -allowPOST") or "allowGET=.*" in line for line in proxy)


def test_docker_and_monitoring_networks_are_internal():
    networks = COMPOSE.split("\nnetworks:\n", 1)[1]

    assert "  monitoring:\n    internal: true\n" in networks
    assert "  docker:\n    internal: true\n" in networks
    assert sorted(name for name, lines in services().items() if "- docker" in lines) == sorted(
        name for name in ("socket-proxy", "alloy", "exporter") if name in services()
    )


def test_log_collector_runs_as_user_of_its_image_without_capabilities():
    alloy = services()["alloy"]

    assert 'user: "473:473"' in alloy
    assert 'cap_drop: ["ALL"]' in alloy
    assert "- --disable-reporting" in alloy


def test_loki_reports_nothing_and_checks_readiness_with_static_busybox():
    probe, loki = services()["loki-probe"], services()["loki"]
    config = (files("saigonos") / "stack" / "config" / "loki" / "config.yaml").read_text("utf-8")

    assert 'restart: "no"' in probe
    assert "network_mode: none" in probe
    assert loki[loki.index("loki-probe:") + 1] == "condition: service_completed_successfully"
    assert "- probe:/probe:ro" in loki
    assert "/probe/busybox" in next(line for line in loki if line.startswith("test:"))
    assert "analytics:\n  reporting_enabled: false\n" in config
    assert "retention_period: 168h" in config


def test_grafana_sends_nothing_outside_and_allows_only_keycloak_login():
    grafana = services()["grafana"]
    settings = (
        "GF_ANALYTICS_REPORTING_ENABLED",
        "GF_ANALYTICS_CHECK_FOR_UPDATES",
        "GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES",
        "GF_ANALYTICS_FEEDBACK_LINKS_ENABLED",
        "GF_NEWS_NEWS_FEED_ENABLED",
        "GF_PLUGINS_PLUGIN_ADMIN_ENABLED",
        "GF_PUBLIC_DASHBOARDS_ENABLED",
        "GF_SNAPSHOTS_EXTERNAL_ENABLED",
        "GF_CLOUD_MIGRATION_ENABLED",
        "GF_AUTH_BASIC_ENABLED",
    )

    for setting in settings:
        assert f'{setting}: "false"' in grafana
    for setting in (
        "GF_PLUGINS_PREINSTALL_DISABLED",
        "GF_PLUGINS_PUBLIC_KEY_RETRIEVAL_DISABLED",
        "GF_SECURITY_DISABLE_GRAVATAR",
        "GF_SECURITY_DISABLE_INITIAL_ADMIN_CREATION",
        "GF_AUTH_DISABLE_LOGIN_FORM",
        "GF_AUTH_GENERIC_OAUTH_ROLE_ATTRIBUTE_STRICT",
        "GF_AUTH_GENERIC_OAUTH_USE_PKCE",
    ):
        assert f'{setting}: "true"' in grafana
    assert "GF_SERVER_ROOT_URL: ${SAIGONOS_URL:?}/grafana/" in grafana


def test_grafana_logs_only_warnings_so_queries_of_dashboard_do_not_flood_logs():
    grafana = services()["grafana"]

    assert "GF_LOG_LEVEL: warn" in grafana
    assert "GF_LOG_FILTERS: search-manifest-watcher:error" in grafana


CONFIG = files("saigonos") / "stack" / "config"


def test_prometheus_keeps_seven_days_and_reads_metrics_of_services():
    prometheus = services()["prometheus"]
    scrape = (CONFIG / "prometheus" / "prometheus.yml").read_text(encoding="utf-8")
    targets = re.findall(r'- targets: \["([^"]+)"\]', scrape)

    assert "- --storage.tsdb.retention.time=7d" in prometheus
    assert targets == [
        "127.0.0.1:9090",
        "exporter:9100",
        "apisix:9091",
        "keycloak:9000",
        "centrifugo:9000",
        "postgrest:3001",
        "etcd:2379",
        "loki:3100",
        "core:9100",
    ]
    assert 'KC_METRICS_ENABLED: "true"' in services()["keycloak"]
    assert "PGRST_ADMIN_SERVER_HOST: 0.0.0.0" in services()["postgrest"]
    centrifugo = (CONFIG / "centrifugo" / "config.yaml").read_text(encoding="utf-8")
    assert "prometheus:\n  enabled: true\n" in centrifugo


def test_recorded_totals_start_at_zero_only_while_gateway_answers():
    rules = (CONFIG / "prometheus" / "rules.yml").read_text(encoding="utf-8")
    records = re.findall(r"- record: (\S+)\n\s+expr: (.+)", rules)

    assert [name for name, _ in records] == [
        "saigonos:http_requests:total",
        "saigonos:http_client_errors:total",
        "saigonos:http_server_errors:total",
        "saigonos:waf_denied:total",
        "saigonos:opa_denied:total",
    ]
    for _, expression in records:
        assert expression.endswith(' or sum(up{job="apisix"} == 1) * 0')
    for _, expression in records[:3]:
        assert 'route!="grafana"' in expression
    assert '{denied_by="waf"}' in records[3][1]
    assert '{denied_by="opa"}' in records[4][1]


def test_alloy_ships_logs_of_this_project_only_with_service_label():
    config = (CONFIG / "alloy" / "config.alloy").read_text(encoding="utf-8")

    assert config.count('host             = "tcp://socket-proxy:2375"') == 1
    assert config.count('host          = "tcp://socket-proxy:2375"') == 1
    assert '"com.docker.compose.project=" + sys.env("COMPOSE_PROJECT")' in config
    assert 'values = ["running", "exited"]' in config
    assert 'target_label  = "service"' in config
    assert 'url = "http://loki:3100/loki/api/v1/push"' in config
    assert "COMPOSE_PROJECT: ${COMPOSE_PROJECT_NAME}" in services()["alloy"]


def test_prometheus_starts_after_every_service_it_reads():
    prometheus = services()["prometheus"]
    scrape = (CONFIG / "prometheus" / "prometheus.yml").read_text(encoding="utf-8")
    hosts = {target.split(":")[0] for target in re.findall(r'- targets: \["([^"]+)"\]', scrape)}

    for host in hosts - {"127.0.0.1"}:
        assert prometheus[prometheus.index(f"{host}:") + 1] == "condition: service_healthy"


def test_dashboard_reads_only_provisioned_sources_and_existing_metrics():
    grafana = services()["grafana"]
    dashboard = json.loads((CONFIG / "grafana" / "dashboards" / "saigonos.json").read_text("utf-8"))
    rules = (CONFIG / "prometheus" / "rules.yml").read_text(encoding="utf-8")
    sources = (CONFIG / "grafana" / "provisioning" / "datasources" / "datasources.yaml").read_text(
        encoding="utf-8"
    )
    known = {"apisix_http_status", "saigonos_service_up", "saigonos_service_memory_bytes"}
    known |= {"saigonos_service_cpu_seconds_total", "saigonos_host_cpus"}
    known |= {"saigonos_host_disk_used_bytes", "saigonos_host_disk_available_bytes"}
    known |= {"saigonos_lake_failed_checks_total", "saigonos_lake_files", "saigonos_lake_rows"}
    known |= set(re.findall(r"- record: (\S+)", rules))

    for panel in dashboard["panels"]:
        assert f"uid: {panel['datasource']['uid']}" in sources
        for target in panel["targets"]:
            if panel["datasource"]["type"] == "prometheus":
                assert (
                    set(re.findall(r"saigonos[:_][a-z_:]+|apisix_[a-z_]+", target["expr"])) <= known
                )
    assert (
        "GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH: /etc/grafana/dashboards/saigonos.json"
        in grafana
    )
    assert "- ./config/grafana/dashboards:/etc/grafana/dashboards:ro" in grafana
