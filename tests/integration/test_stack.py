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
ENVIRONMENT = re.compile(r'<script id="environment" type="application/json">(.*?)</script>', re.S)


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


def wait_for(condition, timeout=60):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "Hết thời gian chờ"
        time.sleep(0.5)


def test_doctor_reports_working_stack(stack):
    result = stack.saigonos("doctor")

    assert result.returncode == 0, result.stdout
    assert "Hệ thống hoạt động bình thường." in result.stdout


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
