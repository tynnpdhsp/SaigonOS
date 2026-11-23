# SPDX-License-Identifier: Apache-2.0
import re
from importlib.resources import files
from itertools import takewhile

import pytest

COMPOSE = (files("saigonos") / "stack" / "compose.yaml").read_text(encoding="utf-8")


def services():
    section = COMPOSE.split("\nservices:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    blocks = {}
    name = None
    for line in section.splitlines():
        header = re.fullmatch(r"  ([a-z]+):", line)
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
