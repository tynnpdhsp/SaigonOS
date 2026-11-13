# SPDX-License-Identifier: Apache-2.0
import base64
import json
import time

import pytest

pytestmark = pytest.mark.integration

REALM_PATH = "/auth/realms/saigonos"
TOKEN_PATH = f"{REALM_PATH}/protocol/openid-connect/token"


def encode(data):
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def decode(segment):
    return json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))


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

    assert stack.compose("port", "apisix", "9080") == f"127.0.0.1:{env['SAIGONOS_HTTP_PORT']}"
    assert stack.compose("port", "apisix", "9180") == f"127.0.0.1:{env['SAIGONOS_ADMIN_PORT']}"


def test_keycloak_uses_address_of_direct_call(stack):
    discovery = stack.discovery()

    assert discovery["issuer"] == f"{stack.url}{REALM_PATH}"
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


def test_api_rejects_call_without_token(stack):
    assert stack.api().status == 401


def test_api_accepts_token_of_user(stack):
    token = stack.token(stack.new_user())

    assert "authenticated" in decode(token.split(".")[1])["realm_access"]["roles"]
    assert stack.api(token).status == 200


def test_api_rejects_forged_tokens(stack):
    header, payload, signature = stack.token(stack.new_user()).split(".")
    claims = decode(payload)
    forged = {
        "không phải JWT": "khong-phai-token",
        "sửa nội dung": f"{header}.{encode(claims | {'preferred_username': 'admin'})}.{signature}",
        "không ký": f"{encode({'alg': 'none', 'typ': 'JWT'})}.{payload}.",
    }

    statuses = {name: stack.api(token).status for name, token in forged.items()}

    assert statuses == dict.fromkeys(forged, 401)


def test_new_signing_key_is_accepted_after_reload(stack):
    user = stack.new_user()
    old_key = decode(stack.token(user).split(".")[0])["kid"]

    stack.rotate_keys()
    token = stack.token(user)

    assert decode(token.split(".")[0])["kid"] != old_key
    assert stack.api(token).status == 401
    assert stack.saigonos("up").returncode == 0
    assert stack.api(stack.token(user)).status == 200


def test_killed_service_restarts_by_itself(stack):
    user = stack.new_user()
    container = stack.container("postgrest")
    restarts = int(stack.inspect(container, "{{.RestartCount}}"))
    state = "{{.RestartCount}} {{.State.Health.Status}}"

    stack.kill(container)

    wait_for(lambda: stack.inspect(container, state) == f"{restarts + 1} healthy")
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
