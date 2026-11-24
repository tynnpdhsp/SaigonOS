# SPDX-License-Identifier: Apache-2.0
import json
import secrets
import time
from urllib.parse import quote

import pytest

from saigonos.home import MONITORING_PROFILE, OPTIONAL_SERVICES

pytestmark = pytest.mark.integration

TARGETS = 9
ATTACK = f"/api/?kiem_tra={quote('<script>alert(1)</script>')}"
DENIED = "Chỉ tài khoản quản trị mới vào được trang này."
TOTALS = ("http_requests", "http_client_errors", "waf_denied", "opa_denied")


def wait_for(check, timeout=120):
    deadline = time.monotonic() + timeout
    while True:
        value = check()
        if value:
            return value
        assert time.monotonic() < deadline, "Hết thời gian chờ giá trị của giám sát"
        time.sleep(2)


def totals(stack):
    return {name: stack.prometheus(f"saigonos:{name}:total").get("") for name in TOTALS}


def recorded(stack):
    found = totals(stack)
    return found if None not in found.values() else None


def test_doctor_checks_grafana_and_every_target_of_prometheus(monitoring_stack):
    wait_for(lambda: monitoring_stack.prometheus("count(up == 1)").get("") == TARGETS)

    result = monitoring_stack.saigonos("doctor")

    assert result.returncode == 0, result.stdout
    assert f"metrics của {TARGETS} target" in result.stdout


def test_requests_errors_and_denials_change_the_totals(monitoring_stack):
    stack = monitoring_stack
    before = wait_for(lambda: recorded(stack))

    for _ in range(3):
        assert stack.api().status == 200
    assert stack.call("GET", f"{stack.url}/khong-co-route").status == 404
    attack = stack.call("GET", f"{stack.url}{ATTACK}")
    token = stack.token(stack.new_user())
    denied = stack.call("GET", f"{stack.url}/auth/admin/realms/saigonos/users", token=token)

    assert (attack.status, attack.headers["X-SaigonOS-Denied-By"]) == (403, "waf")
    assert (denied.status, denied.headers["X-SaigonOS-Denied-By"]) == (403, "opa")
    wanted = {"http_requests": 7, "http_client_errors": 3, "waf_denied": 1, "opa_denied": 1}
    wait_for(
        lambda: all(totals(stack)[name] - before[name] >= count for name, count in wanted.items())
    )


def test_every_long_running_service_is_reported_and_a_stopped_one_is_down(monitoring_stack):
    stack = monitoring_stack
    services = json.loads(stack.compose("config", "--format", "json"))["services"]
    expected = {name for name, service in services.items() if service.get("restart", "no") != "no"}

    def all_up():
        found = stack.prometheus("saigonos_service_up")
        return found if set(found) == expected and all(found.values()) else None

    wait_for(all_up)
    memory = stack.prometheus("saigonos_service_memory_bytes")
    assert set(memory) == expected
    assert min(memory.values()) > 0
    assert set(stack.prometheus("saigonos_service_cpu_seconds_total")) == expected
    assert stack.prometheus("saigonos_host_cpus")[""] >= 1
    assert stack.prometheus("saigonos_host_disk_used_bytes")[""] > 0
    assert stack.prometheus("saigonos_host_disk_available_bytes")[""] > 0

    stack.compose("stop", "freshclam")
    try:
        wait_for(lambda: stack.prometheus('saigonos_service_up{service="freshclam"} == 0'))
    finally:
        stack.compose("start", "freshclam")
    wait_for(lambda: stack.prometheus('saigonos_service_up{service="freshclam"} == 1'), 180)


def test_blocked_request_is_found_in_logs_of_apisix(monitoring_stack):
    stack = monitoring_stack
    marker = f"kiem-thu-{secrets.token_hex(4)}"

    def logged():
        lines = stack.loki(f'{{service="apisix"}} |= "{marker}"')
        blocked = any("Coraza" in line for line in lines)
        return blocked and any('" 403 ' in line for line in lines)

    reply = stack.call("GET", f"{stack.url}{ATTACK}&dau={marker}")

    assert reply.status == 403
    assert wait_for(logged)
    assert not stack.loki(f'{{service="core"}} |= "{marker}"')


def test_only_admin_with_otp_logs_in_to_grafana_and_sees_sources_from_files(monitoring_stack):
    stack = monitoring_stack
    admin = stack.new_user(role="admin")

    reply, cookies, _ = stack.grafana_login(admin)
    user = json.loads(stack.grafana(cookies, "/api/user").body)
    sources = json.loads(stack.grafana(cookies, "/api/datasources").body)

    assert reply.status == 200, reply.body[:300]
    assert (user["login"], user["isGrafanaAdmin"]) == (admin.name, True)
    assert sorted((item["uid"], item["type"], item["readOnly"]) for item in sources) == [
        ("loki", "loki", True),
        ("prometheus", "prometheus", True),
    ]

    reply, cookies, _ = stack.grafana_login(stack.new_user())
    assert (reply.status, DENIED in reply.body.decode()) == (401, True)
    assert stack.grafana(cookies, "/api/user").status == 401


def test_turning_monitoring_off_removes_its_services_route_and_client(monitoring_stack):
    stack = monitoring_stack

    assert stack.saigonos("init", "--no-monitoring").returncode == 0
    started = stack.up()
    assert started.returncode == 0, started.stderr

    running = set(stack.compose("ps", "--services").split())
    assert not running & set(OPTIONAL_SERVICES[MONITORING_PROFILE])
    assert stack.call("GET", f"{stack.url}/grafana/").status == 404
    assert json.loads(stack.admin("GET", "/clients?clientId=grafana").body) == []
    result = stack.saigonos("doctor")
    assert result.returncode == 0, result.stdout
    assert "Giám sát" not in result.stdout
