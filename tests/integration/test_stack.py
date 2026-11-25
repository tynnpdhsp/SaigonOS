# SPDX-License-Identifier: Apache-2.0
import base64
import hashlib
import html
import json
import re
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

pytestmark = pytest.mark.integration

REALM_PATH = "/auth/realms/saigonos"
DISCOVERY_PATH = f"{REALM_PATH}/.well-known/openid-configuration"
TOKEN_PATH = f"{REALM_PATH}/protocol/openid-connect/token"
MASTER_DISCOVERY = "/realms/master/.well-known/openid-configuration"
MASTER_PATHS = {
    f"/auth{MASTER_DISCOVERY}": 404,
    "/auth/realms/master/account": 404,
    "/auth/admin/master/console/": 404,
    "/auth/admin/realms/master/users": 404,
    "/auth/realms/%6Daster/.well-known/openid-configuration": 404,
    "//auth/realms/master/.well-known/openid-configuration": 404,
    "/auth/realms/saigonos/../master/.well-known/openid-configuration": 404,
    "/auth/realms/master;x=1/.well-known/openid-configuration": 400,
}
CONSOLE_CLIENT = "security-admin-console"
ADMIN_CONSOLE = "/auth/admin/saigonos/console/"
ADMIN_USERS = "/admin/realms/saigonos/users?max=1"
COCKPIT = "/operaton/app/cockpit/"
OUTSIDE_REASON = "Địa chỉ IP này không được vào trang quản trị."
OTP_REASON = "Trang quản trị cần đăng nhập bằng mật khẩu và mã OTP."
LOCKED_REASON = "Admin Console đang tạm khóa để bảo trì."
LOCAL_RULE = f"""# SPDX-License-Identifier: Apache-2.0
package saigonos.admin

deny contains "{LOCKED_REASON}" if input.request.path == "{ADMIN_CONSOLE}"
"""
REFERENCES = {
    "saigonos browser forms": "pwd",
    "saigonos browser admin otp": "otp",
    "saigonos browser optional otp": "otp",
}
ENVIRONMENT = re.compile(r'<script id="environment" type="application/json">(.*?)</script>', re.S)
WAF_BLOCKED = "Tường lửa ứng dụng web đã chặn lời gọi này vì có dấu hiệu tấn công."
WAF_TOO_BIG = "Nội dung của lời gọi lớn hơn 1 MB nên tường lửa ứng dụng web không kiểm tra được."
SQL_INJECTION = "/api/?id=1%27%20OR%201%3D1--"
ATTACKS = {
    "sql-injection": ("GET", SQL_INJECTION, None),
    "xss": ("GET", "/core/health?q=%3Cscript%3Ealert(1)%3C%2Fscript%3E", None),
    "path-traversal": ("GET", "/apps/thu/?file=..%2F..%2F..%2Fetc%2Fpasswd", None),
    "xss-json": ("POST", "/api/notes", {"body": "<script>alert(1)</script>"}),
    "sql-injection-json": ("PATCH", "/api/notes", {"body": "1' UNION SELECT password FROM t--"}),
    "command-json": ("POST", "/core/files", {"name": "a.txt; cat /etc/passwd"}),
}


def decode(segment):
    return json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))


def cookies_of(reply):
    return "; ".join(cookie.split(";", 1)[0] for cookie in reply.headers.get_all("Set-Cookie", []))


def console_login(stack, password):
    console = f"{stack.keycloak}/admin/master/console/"
    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    query = urlencode(
        {
            "client_id": CONSOLE_CLIENT,
            "redirect_uri": console,
            "response_type": "code",
            "scope": "openid",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    page = stack.call("GET", f"{stack.keycloak}/realms/master/protocol/openid-connect/auth?{query}")
    action = html.unescape(re.search(r'action="([^"]+)"', page.body.decode())[1])
    form = {"username": "admin", "password": password}
    sent = stack.call("POST", action, form=form, headers={"Cookie": cookies_of(page)})
    location = sent.headers["Location"]
    exchange = {
        "grant_type": "authorization_code",
        "client_id": CONSOLE_CLIENT,
        "redirect_uri": console,
        "code": parse_qs(urlsplit(location).query)["code"][0],
        "code_verifier": verifier,
    }
    token = f"{stack.keycloak}/realms/master/protocol/openid-connect/token"
    return action, location, stack.call("POST", token, form=exchange).status


def opa_status(stack, method, path):
    request = json.dumps(
        {"method": method, "url": f"http://127.0.0.1:8181{path}", "raw_body": "{}"}
    )
    result = stack.exec("opa", "/opa", "eval", "--format=raw", f"http.send({request}).status_code")
    return int(result.stdout)


def set_admin_networks(stack, value):
    path = stack.home / ".env"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines = [line for line in lines if not line.startswith("SAIGONOS_ADMIN_NETWORKS=")]
    if value is not None:
        lines.append(f"SAIGONOS_ADMIN_NETWORKS={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return stack.compose_result("up", "-d", "--wait", "opa", timeout=180)


def subnet_of(stack, network):
    template = "{{(index .IPAM.Config 0).Subnet}}"
    return stack.run_docker("network", "inspect", "--format", template, network).stdout.strip()


def gateway_page(stack, path, token=None):
    return stack.call("GET", f"{stack.url}{path}", token=token)


def wait_for_reason(stack, reason):
    wait_for(lambda: gateway_page(stack, ADMIN_CONSOLE).body.decode() == reason)


def console_token(stack, user, otp=None, step=1):
    redirect = f"{stack.url}{ADMIN_CONSOLE}"
    reply, otp = stack.browser_login(CONSOLE_CLIENT, redirect, user, otp, step)
    assert reply.status == 200, reply.body
    return json.loads(reply.body)["access_token"], otp


def grant_client_role(stack, user, client, role):
    found = json.loads(stack.admin("GET", f"/clients?clientId={client}").body)[0]
    roles = f"/clients/{found['id']}/roles/{role}"
    wanted = json.loads(stack.admin("GET", roles).body)
    path = f"/users/{user.id}/role-mappings/clients/{found['id']}"
    assert stack.admin("POST", path, [wanted]).status == 204


def executions(stack, flow):
    path = f"/authentication/flows/{flow.replace(' ', '%20')}/executions"
    return json.loads(stack.admin("GET", path).body)


def reference_config(stack, flow):
    for execution in executions(stack, flow):
        config = execution.get("authenticationConfig")
        if (
            execution["level"] == 0
            and config
            and "conditional" not in execution.get("providerId", "")
        ):
            return json.loads(stack.admin("GET", f"/authentication/config/{config}").body)
    return None


def reference_of(stack, flow, key="default.reference.value"):
    found = reference_config(stack, flow)
    return found and found["config"].get(key)


def wait_for(condition, timeout=60):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "Hết thời gian chờ"
        time.sleep(0.5)


def test_doctor_reports_working_stack(stack):
    result = stack.saigonos("doctor")

    assert result.returncode == 0, result.stdout
    assert "Hệ thống hoạt động bình thường." in result.stdout
    assert re.search(r"^BÌNH THƯỜNG +opa +đang chạy$", result.stdout, re.MULTILINE)
    assert re.search(r"^BÌNH THƯỜNG +policies +đã chạy xong$", result.stdout, re.MULTILINE)


def test_gateway_ports_listen_on_loopback_only(stack):
    env = stack.env

    http_port = env["SAIGONOS_HTTP_PORT"]

    assert stack.compose("port", "apisix", http_port) == f"127.0.0.1:{http_port}"
    assert stack.compose("port", "apisix", "9180") == f"127.0.0.1:{env['SAIGONOS_ADMIN_PORT']}"


def test_keycloak_port_listens_on_loopback_only(stack):
    port = stack.env["SAIGONOS_KEYCLOAK_PORT"]

    assert stack.compose("port", "keycloak", "8080") == f"127.0.0.1:{port}"


def test_gateway_refuses_every_path_of_realm_master(stack):
    statuses = {path: stack.call("GET", f"{stack.url}{path}").status for path in MASTER_PATHS}
    password = stack.env["KEYCLOAK_ADMIN_PASSWORD"]

    login = stack.master_login("admin", password, f"{stack.url}/auth")

    assert statuses == MASTER_PATHS
    assert login.status == 404
    assert stack.call("GET", f"{stack.url}/auth/admin/saigonos/console/").status == 200


def test_master_admin_console_works_through_keycloak_port(stack):
    page = stack.call("GET", f"{stack.keycloak}/admin/master/console/")
    environment = json.loads(ENVIRONMENT.search(page.body.decode())[1])
    discovery = json.loads(stack.call("GET", f"{stack.keycloak}{MASTER_DISCOVERY}").body)

    action, location, token = console_login(stack, stack.env["KEYCLOAK_ADMIN_PASSWORD"])

    assert page.status == 200
    assert {environment[key] for key in ("authUrl", "adminBaseUrl", "serverBaseUrl")} == {
        stack.keycloak
    }
    assert discovery["issuer"] == f"{stack.keycloak}/realms/master"
    assert action.startswith(f"{stack.keycloak}/realms/master/login-actions/")
    assert location.startswith(f"{stack.keycloak}/admin/master/console/")
    assert token == 200


def test_realm_master_locks_account_after_quick_wrong_passwords(stack):
    name, password = f"thu-{secrets.token_hex(4)}", secrets.token_urlsafe(12)
    user = {
        "username": name,
        "enabled": True,
        "firstName": "Người",
        "lastName": "Thử",
        "email": f"{name}@example.com",
        "credentials": [{"type": "password", "value": password, "temporary": False}],
    }
    created = stack.admin("POST", "/users", user, realm="master")
    assert created.status == 201, created.body
    user_id = created.headers["Location"].rsplit("/", 1)[1]
    lockout = f"/attack-detection/brute-force/users/{user_id}"

    def locked():
        return json.loads(stack.admin("GET", lockout, realm="master").body)["disabled"]

    try:
        before = stack.master_login(name, password).status
        wrong = [stack.master_login(name, f"sai-{number}").status for number in range(3)]
        wait_for(locked, timeout=10)
        after = stack.master_login(name, password).status
    finally:
        stack.admin("DELETE", f"/users/{user_id}", realm="master")

    assert before == 200
    assert wrong == [400, 400, 400]
    assert after == 400


def test_caddy_does_not_run_by_default(stack):
    services = stack.compose("ps", "--all", "--services").split()

    assert "apisix" in services
    assert "caddy" not in services


def test_keycloak_uses_address_of_direct_call(stack):
    discovery = stack.discovery()

    assert discovery["issuer"] == f"{stack.url}{REALM_PATH}"
    assert discovery["token_endpoint"] == f"{stack.url}{TOKEN_PATH}"


def test_keycloak_uses_port_of_gateway_when_host_header_has_no_port(stack):
    discovery = stack.discovery(headers={"Host": "localhost"})

    assert discovery["token_endpoint"] == f"{stack.url}{TOKEN_PATH}"


def test_keycloak_uses_address_sent_by_reverse_proxy(stack):
    proxy = {
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "dx.example.com",
        "X-Forwarded-Port": "443",
    }

    discovery = stack.discovery(headers=proxy)

    assert discovery["token_endpoint"] == f"https://dx.example.com{TOKEN_PATH}"


def test_rate_limit_counts_address_sent_by_reverse_proxy(stack):
    token = stack.token(stack.new_user())

    def remaining(address):
        reply = stack.api(token, headers={"X-Forwarded-For": address})
        assert reply.status == 200, reply.body
        return int(reply.headers["X-RateLimit-Remaining"])

    counts = [remaining("203.0.113.7"), remaining("203.0.113.7"), remaining("203.0.113.8")]

    assert counts == [299, 298, 299]


def test_caller_outside_local_network_cannot_pose_as_local_address(stack):
    with stack.outside_network() as network:
        reached = stack.outside_status(network, "/api/")
        forged = stack.outside_status(network, DISCOVERY_PATH, {"X-Forwarded-For": "10.0.0.5"})

    assert reached == 200
    assert forged == 403


def test_api_answers_call_without_token(stack):
    assert stack.api().status == 200


def test_api_document_gives_saigonos_url_and_authorization_header(stack):
    reply = stack.api()
    document = json.loads(reply.body)
    parts = urlsplit(stack.url)
    scheme = document["securityDefinitions"]["JWT"]

    assert reply.headers.get_content_type() == "application/openapi+json"
    assert (document["swagger"], document["info"]["title"]) == ("2.0", "SaigonOS API")
    assert (document["schemes"], document["host"], document["basePath"]) == (
        [parts.scheme],
        parts.netloc,
        "/api",
    )
    assert (scheme["type"], scheme["in"], scheme["name"]) == ("apiKey", "header", "Authorization")
    assert document["security"] == [{"JWT": []}]


def test_rate_limit_counts_calls_without_token(stack):
    def remaining():
        reply = stack.api(headers={"X-Forwarded-For": "203.0.113.9"})
        assert reply.status == 200, reply.body
        return int(reply.headers["X-RateLimit-Remaining"])

    assert [remaining(), remaining()] == [299, 298]


def test_api_accepts_token_of_user(stack):
    token = stack.token(stack.new_user())

    assert "authenticated" in decode(token.split(".")[1])["realm_access"]["roles"]
    assert stack.api(token).status == 200


def test_api_rejects_forged_tokens(stack):
    forged = stack.forged_tokens(stack.new_user())

    statuses = {name: stack.api(token).status for name, token in forged.items()}

    assert statuses == dict.fromkeys(forged, 401)


def test_access_token_carries_unit_of_user(stack):
    member = decode(stack.token(stack.new_user(unit="khoa-a")).split(".")[1])
    outsider = decode(stack.token(stack.new_user()).split(".")[1])

    assert member["unit"] == "khoa-a"
    assert "unit" not in outsider


@pytest.mark.parametrize("unit", ["khoa-a", None])
def test_user_cannot_change_own_unit(stack, unit):
    user = stack.new_user(unit=unit)
    account = f"{stack.url}{REALM_PATH}/account/"
    json_reply = {"Accept": "application/json"}
    profile = json.loads(
        stack.call("GET", account, token=stack.token(user), headers=json_reply).body
    )
    assert profile["username"] == user.name

    profile["attributes"] = {"unit": ["khoa-b"]}
    reply = stack.call("POST", account, token=stack.token(user), body=profile, headers=json_reply)

    error = json.loads(reply.body)
    assert reply.status == 400
    assert (error["field"], error["errorMessage"]) == ("unit", "error-user-attribute-read-only")
    assert decode(stack.token(user).split(".")[1]).get("unit") == unit


def test_realm_service_adds_unit_to_realm_created_by_older_version(stack):
    user = stack.new_user(unit="khoa-a")
    profile = json.loads(stack.admin("GET", "/users/profile").body)
    custom = {
        "name": "phone",
        "displayName": "Điện thoại",
        "permissions": {"view": [], "edit": ["admin"]},
        "validations": {},
        "annotations": {},
        "multivalued": False,
    }
    older = [attribute for attribute in profile["attributes"] if attribute["name"] != "unit"]
    names = [attribute["name"] for attribute in older]
    profile["attributes"] = [*older, custom]
    assert stack.admin("PUT", "/users/profile", profile).status == 200
    scopes = json.loads(stack.admin("GET", "/client-scopes").body)
    roles = next(scope for scope in scopes if scope["name"] == "roles")
    mapper = next(mapper for mapper in roles["protocolMappers"] if mapper["name"] == "unit")
    mappers = f"/client-scopes/{roles['id']}/protocol-mappers/models"
    assert stack.admin("DELETE", f"{mappers}/{mapper['id']}").status == 204
    assert "unit" not in decode(stack.token(user).split(".")[1])
    before = json.loads(stack.admin("GET", "/users/profile").body)["attributes"]

    first = stack.up()
    added = stack.logs("realm").splitlines()[-2:]
    second = stack.up()

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert added == [
        "Đã thêm thuộc tính unit vào user profile của realm saigonos",
        "Đã thêm mapper unit vào client scope roles của realm saigonos",
    ]
    assert stack.logs("realm").splitlines()[-1] == "Realm saigonos không cần thay đổi"
    after = json.loads(stack.admin("GET", "/users/profile").body)["attributes"]
    assert [attribute["name"] for attribute in before] == [*names, "phone"]
    assert after[:-1] == before
    assert after[-1]["name"] == "unit"
    assert decode(stack.token(stack.new_user(unit="khoa-b")).split(".")[1])["unit"] == "khoa-b"


def test_realm_service_restores_settings_of_realm_master(stack):
    master = json.loads(stack.admin("GET", "", realm="master").body)
    attributes = {key: value for key, value in master["attributes"].items() if key != "frontendUrl"}
    older = {"attributes": attributes, "bruteForceProtected": False}
    assert stack.admin("PUT", "", older, realm="master").status == 204
    discovery = f"{stack.keycloak}{MASTER_DISCOVERY}"
    before = json.loads(stack.call("GET", discovery).body)["issuer"]

    first = stack.up()
    added = stack.logs("realm").splitlines()[-3:-1]
    second = stack.up()

    restored = json.loads(stack.admin("GET", "", realm="master").body)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert before == f"{stack.url}/auth/realms/master"
    assert added == [
        f"Đã đặt Frontend URL của realm master là {stack.keycloak}",
        "Đã bật chặn đăng nhập sai nhiều lần cho realm master",
    ]
    assert stack.logs("realm").splitlines()[-2:] == [
        "Realm master không cần thay đổi",
        "Realm saigonos không cần thay đổi",
    ]
    assert restored["attributes"]["frontendUrl"] == stack.keycloak
    assert restored["bruteForceProtected"] is True
    assert (
        json.loads(stack.call("GET", discovery).body)["issuer"] == f"{stack.keycloak}/realms/master"
    )


def test_new_signing_key_is_accepted_after_reload(stack):
    user = stack.new_user()
    old_key = decode(stack.token(user).split(".")[0])["kid"]

    stack.rotate_keys()
    token = stack.token(user)

    assert decode(token.split(".")[0])["kid"] != old_key
    assert stack.api(token).status == 401
    assert stack.up().returncode == 0
    assert stack.api(stack.token(user)).status == 200


def test_killed_service_restarts_by_itself(stack):
    user = stack.new_user()
    container = stack.container("postgrest")
    restarts = int(stack.inspect(container, "{{.RestartCount}}"))
    state = "{{.RestartCount}} {{.State.Health.Status}}"

    stack.kill(container)

    wait_for(lambda: stack.inspect(container, state) == f"{restarts + 1} healthy")
    stack.wait_until_answers("/api/")
    assert stack.api(stack.token(user)).status == 200


def test_disabled_account_loses_access_within_60_seconds(stack):
    user = stack.new_user()
    tokens = json.loads(stack.login(user).body)
    claims = decode(tokens["access_token"].split(".")[1])
    assert stack.api(tokens["access_token"]).status == 200

    assert stack.admin("PUT", f"/users/{user.id}", {"enabled": False}).status == 204

    assert stack.login(user).status == 400
    assert stack.refresh(tokens["refresh_token"]).status == 400
    assert claims["exp"] - claims["iat"] <= 60
    time.sleep(max(0, claims["exp"] - time.time()) + 1)
    assert stack.api(tokens["access_token"]).status == 401


def test_burst_of_calls_gets_429(stack):
    token = stack.token(stack.new_user())
    time.sleep(float(stack.api(token).headers["X-RateLimit-Reset"]) + 0.5)

    statuses = stack.burst(token, calls=400)

    assert statuses.count(200) == 300
    assert statuses.count(429) == 100
    assert "Gọi API quá nhiều lần" in stack.api(token).body.decode()


def test_opa_answers_only_health_and_decisions(stack):
    statuses = {
        ("GET", "/health"): 200,
        ("POST", "/v1/data/saigonos/admin/decision"): 200,
        ("POST", "/v1/data/saigonos/admin/networks"): 401,
        ("GET", "/v1/data"): 401,
        ("GET", "/v1/policies"): 401,
        ("PUT", "/v1/policies/saigonos"): 401,
        ("PATCH", "/v1/data"): 401,
    }

    assert {call: opa_status(stack, *call) for call in statuses} == statuses


def test_admin_routes_are_refused_while_opa_is_stopped(stack):
    assert stack.compose_result("stop", "opa").returncode == 0
    try:
        refused = [gateway_page(stack, path).status for path in (ADMIN_CONSOLE, COCKPIT)]
        others = [gateway_page(stack, path).status for path in (DISCOVERY_PATH, "/core/health")]
    finally:
        started = stack.compose_result("up", "-d", "--wait", "opa", timeout=180)
    stack.wait_until_answers(ADMIN_CONSOLE)

    assert refused == [403, 403]
    assert others == [200, 200]
    assert started.returncode == 0, started.stderr


def test_admin_networks_in_env_limit_admin_routes(stack):
    with stack.outside_network() as network:
        subnet = subnet_of(stack, network)
        try:
            narrowed = set_admin_networks(stack, "192.0.2.0/24")
            wait_for_reason(stack, OUTSIDE_REASON)
            local = gateway_page(stack, ADMIN_CONSOLE)
            refused = [stack.outside_status(network, path) for path in (ADMIN_CONSOLE, COCKPIT)]
            health = stack.outside_status(network, "/core/health")
            widened = set_admin_networks(stack, f"192.0.2.0/24, {subnet}")
            wait_for(lambda: stack.outside_status(network, COCKPIT) != 403)
        finally:
            restored = set_admin_networks(stack, None)
            stack.wait_until_answers(ADMIN_CONSOLE)

    assert narrowed.returncode == 0, narrowed.stderr
    assert local.headers["Content-Type"] == "text/plain; charset=utf-8"
    assert refused == [403, 403]
    assert health == 200
    assert widened.returncode == 0, widened.stderr
    assert restored.returncode == 0, restored.stderr


def test_invalid_admin_network_stops_up_with_message(stack):
    try:
        failed = set_admin_networks(stack, "192.0.2.0/24, 192.0.2.7")
        message = stack.logs("policies").splitlines()[-1]
        refused = gateway_page(stack, ADMIN_CONSOLE).status
    finally:
        restored = set_admin_networks(stack, None)
        stack.wait_until_answers(ADMIN_CONSOLE)

    assert failed.returncode != 0
    assert message == "Dải mạng 192.0.2.7 trong SAIGONOS_ADMIN_NETWORKS không hợp lệ."
    assert refused == 403
    assert restored.returncode == 0, restored.stderr


def test_new_rule_file_changes_access_after_saigonos_up(stack):
    rule = stack.home / "config" / "opa" / "local.rego"
    rule.write_text(LOCAL_RULE, encoding="utf-8")
    try:
        locked = stack.up()
        console = gateway_page(stack, ADMIN_CONSOLE)
        cockpit = gateway_page(stack, COCKPIT).status
    finally:
        rule.unlink()
    unlocked = stack.up()

    assert locked.returncode == 0, locked.stderr
    assert (console.status, console.body.decode()) == (403, LOCKED_REASON)
    assert cockpit != 403
    assert unlocked.returncode == 0, unlocked.stderr
    stack.wait_until_answers(ADMIN_CONSOLE)


def test_broken_rule_file_stops_up_and_keeps_running_rules(stack):
    broken = stack.home / "config" / "opa" / "broken.rego"
    broken.write_text("package saigonos.admin\n\ndecision := {\n", encoding="utf-8")
    try:
        failed = stack.saigonos("up")
        logs = stack.logs("policies")
        console = gateway_page(stack, ADMIN_CONSOLE).status
    finally:
        broken.unlink()
    restored = stack.up()

    assert failed.returncode != 0
    assert "/policies/broken.rego:4: rego_parse_error" in logs
    assert console == 200
    assert restored.returncode == 0, restored.stderr


def test_admin_api_through_gateway_needs_login_with_otp(stack):
    admin = stack.new_user(role="admin")
    viewer = stack.new_user()
    grant_client_role(stack, viewer, "realm-management", "view-users")

    first, otp = console_token(stack, admin)
    second, _ = console_token(stack, admin, otp)
    third, _ = console_token(stack, viewer)

    tokens = (first, second, third)
    replies = [gateway_page(stack, f"/auth{ADMIN_USERS}", token) for token in tokens]
    direct = [stack.call("GET", f"{stack.keycloak}{ADMIN_USERS}", token=token) for token in tokens]
    assert [decode(token.split(".")[1]).get("amr") for token in tokens] == [
        ["pwd"],
        ["pwd", "otp"],
        ["pwd"],
    ]
    assert [reply.status for reply in replies] == [403, 200, 403]
    assert replies[0].body.decode() == OTP_REASON
    assert [reply.status for reply in direct] == [200, 200, 200]


def test_realm_service_adds_amr_to_realm_created_by_older_version(stack):
    scopes = json.loads(stack.admin("GET", "/client-scopes").body)
    basic = next(scope for scope in scopes if scope["name"] == "basic")
    mapper = next(mapper for mapper in basic["protocolMappers"] if mapper["name"] == "amr")
    path = f"/client-scopes/{basic['id']}/protocol-mappers/models/{mapper['id']}"
    assert stack.admin("DELETE", path).status == 204
    for flow in REFERENCES:
        for execution in executions(stack, flow):
            config = execution.get("authenticationConfig")
            provider = execution.get("providerId", "")
            if execution["level"] == 0 and "conditional" not in provider and config:
                assert stack.admin("DELETE", f"/authentication/config/{config}").status == 204
    assert {flow: reference_of(stack, flow) for flow in REFERENCES} == dict.fromkeys(REFERENCES)

    first = stack.up()
    added = stack.logs("realm").splitlines()[-4:]
    second = stack.up()

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert added == [
        "Đã thêm mapper amr vào client scope basic của realm saigonos",
        "Đã đặt giá trị amr pwd cho bước auth-username-password-form của luồng "
        "saigonos browser forms",
        "Đã đặt giá trị amr otp cho bước auth-otp-form của luồng saigonos browser admin otp",
        "Đã đặt giá trị amr otp cho bước auth-otp-form của luồng saigonos browser optional otp",
    ]
    assert stack.logs("realm").splitlines()[-1] == "Realm saigonos không cần thay đổi"
    assert {flow: reference_of(stack, flow) for flow in REFERENCES} == REFERENCES


def waf_reply(reply):
    error = json.loads(reply.body)
    return reply.status, reply.headers["Content-Type"], error["code"], error["message"]


def set_waf_mode(stack, value):
    path = stack.home / ".env"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines = [line for line in lines if not line.startswith("SAIGONOS_WAF_MODE=")]
    if value is not None:
        lines.append(f"SAIGONOS_WAF_MODE={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return stack.compose_result("run", "--rm", "--no-deps", "routes", timeout=180)


@pytest.mark.parametrize(("method", "path", "body"), ATTACKS.values(), ids=ATTACKS)
def test_waf_blocks_attack_at_gateway(stack, method, path, body):
    reply = stack.call(method, f"{stack.url}{path}", body=body)

    assert waf_reply(reply) == (403, "application/json; charset=utf-8", "SGN04", WAF_BLOCKED)


def test_waf_logs_rule_and_address_of_blocked_call(stack):
    stack.call("GET", f"{stack.url}{SQL_INJECTION}")

    logs = stack.logs("apisix")

    assert '[id "942100"]' in logs
    assert "Tường lửa ứng dụng web trả mã 403 cho GET /api/ từ " in logs


def test_waf_lets_valid_calls_of_api_and_core_through(stack):
    token = stack.token(stack.new_user())
    calls = [
        ("GET", "/api/?select=id,body&order=id.desc&or=(id.eq.1,id.eq.2)&limit=10", None),
        ("PATCH", "/api/notes?id=eq.1", {"body": "Ghi chú: sửa lại lúc 8:30, phòng I.201"}),
        ("DELETE", "/api/notes?id=in.(1,2,3)", None),
        ("POST", "/core/files", {"name": "Báo cáo 11.pdf", "type": "application/pdf", "size": 9}),
    ]

    replies = [
        stack.call(method, f"{stack.url}{path}", token=token, body=body)
        for method, path, body in calls
    ]

    assert [reply.status for reply in replies] == [200, 404, 404, 201]


def test_waf_lets_address_as_host_through_and_still_blocks_attack(stack):
    address = f"http://127.0.0.1:{stack.env['SAIGONOS_HTTP_PORT']}"

    allowed = stack.call("GET", f"{address}/api/")
    attack = stack.call("GET", f"{address}{SQL_INJECTION}")

    assert allowed.status == 200
    assert waf_reply(attack) == (403, "application/json; charset=utf-8", "SGN04", WAF_BLOCKED)


def load_global_rules(stack, *options):
    return stack.compose_result("run", "--rm", "--no-deps", *options, "routes", timeout=180)


def test_waf_lets_issuer_of_system_reach_page_of_app_and_blocks_other_addresses(stack):
    address = f"http://127.0.0.1:{stack.env['SAIGONOS_HTTP_PORT']}"
    issuer = f"{address}/auth/realms/saigonos"
    page = f"{stack.url}/apps/khong-co/"
    callback = {"state": "a1", "session_state": "b2", "iss": issuer, "code": "c3"}
    stranger = callback | {"iss": "http://10.1.2.3/auth/realms/saigonos"}
    before = stack.call("GET", f"{page}?{urlencode(callback)}")
    try:
        loaded = load_global_rules(stack, "-e", f"SAIGONOS_URL={address}")
        wait_for(lambda: stack.call("GET", f"{page}?{urlencode(callback)}").status == 404)
        allowed = stack.call("GET", f"{page}?{urlencode(callback)}")
        foreign = stack.call("GET", f"{page}?{urlencode(stranger)}")
        elsewhere = stack.call("GET", f"{page}?{urlencode({'next': issuer})}")
    finally:
        restored = load_global_rules(stack)

    assert waf_reply(before) == (403, "application/json; charset=utf-8", "SGN04", WAF_BLOCKED)
    assert loaded.returncode == 0, loaded.stderr
    assert allowed.status == 404, allowed.body
    for reply in (foreign, elsewhere):
        assert waf_reply(reply) == (403, "application/json; charset=utf-8", "SGN04", WAF_BLOCKED)
    assert restored.returncode == 0, restored.stderr


def test_waf_refuses_body_larger_than_it_checks(stack):
    reply = stack.call("POST", f"{stack.url}/api/notes", body={"body": "a" * 1_100_000})

    assert waf_reply(reply) == (413, "application/json; charset=utf-8", "SGN04", WAF_TOO_BIG)


def test_waf_detect_mode_only_logs_attack(stack):
    try:
        switched = set_waf_mode(stack, "detect")
        wait_for(lambda: stack.call("GET", f"{stack.url}{SQL_INJECTION}").status != 403)
        reply = stack.call("GET", f"{stack.url}{SQL_INJECTION}")
        doctor = stack.saigonos("doctor")
        logs = stack.logs("apisix")
    finally:
        restored = set_waf_mode(stack, None)
        wait_for(lambda: stack.call("GET", f"{stack.url}{SQL_INJECTION}").status == 403)

    assert switched.returncode == 0, switched.stderr
    assert (reply.status, json.loads(reply.body)["code"]) == (400, "PGRST100")
    assert "Tường lửa     chế độ chỉ ghi log, lời gọi có dấu hiệu tấn công không bị chặn" in (
        doctor.stdout
    )
    assert "Coraza: Warning. SQL Injection Attack Detected via libinjection" in logs
    assert restored.returncode == 0, restored.stderr


def test_invalid_waf_mode_stops_routes_and_keeps_blocking(stack):
    try:
        failed = set_waf_mode(stack, "chan")
        reply = stack.call("GET", f"{stack.url}{SQL_INJECTION}")
    finally:
        restored = set_waf_mode(stack, None)

    assert failed.returncode != 0
    assert "Giá trị SAIGONOS_WAF_MODE không hợp lệ: 'chan'. Chỉ dùng block hoặc detect." in (
        failed.stdout + failed.stderr
    )
    assert reply.status == 403
    assert restored.returncode == 0, restored.stderr


def test_amr_lasts_for_session_after_slow_exchange_and_refresh(stack):
    admin = stack.new_user(role="admin")
    _, otp = console_token(stack, admin)
    redirect = f"{stack.url}{ADMIN_CONSOLE}"
    reply, _ = stack.browser_login(CONSOLE_CLIENT, redirect, admin, otp, wait=2)
    tokens = json.loads(reply.body)
    time.sleep(2)
    form = {
        "grant_type": "refresh_token",
        "client_id": CONSOLE_CLIENT,
        "refresh_token": tokens["refresh_token"],
    }
    refreshed = json.loads(stack.call("POST", f"{stack.url}{TOKEN_PATH}", form=form).body)
    access = [tokens["access_token"], refreshed["access_token"]]

    statuses = [gateway_page(stack, f"/auth{ADMIN_USERS}", token).status for token in access]

    assert [decode(token.split(".")[1]).get("amr") for token in access] == [["pwd", "otp"]] * 2
    assert statuses == [200, 200]


def test_realm_service_sets_amr_max_age_on_realm_of_older_version(stack):
    for flow in REFERENCES:
        found = reference_config(stack, flow)
        found["config"].pop("default.reference.maxAge")
        assert stack.admin("PUT", f"/authentication/config/{found['id']}", found).status == 204

    first = stack.up()
    added = [line for line in stack.logs("realm").splitlines() if "thời hạn amr" in line][-3:]
    second = stack.up()

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert added == [
        "Đã đặt thời hạn amr 36000 giây cho bước auth-username-password-form của luồng "
        "saigonos browser forms",
        "Đã đặt thời hạn amr 36000 giây cho bước auth-otp-form của luồng "
        "saigonos browser admin otp",
        "Đã đặt thời hạn amr 36000 giây cho bước auth-otp-form của luồng "
        "saigonos browser optional otp",
    ]
    assert stack.logs("realm").splitlines()[-1] == "Realm saigonos không cần thay đổi"
    maximum = {flow: reference_of(stack, flow, "default.reference.maxAge") for flow in REFERENCES}
    assert maximum == dict.fromkeys(REFERENCES, "36000")
