# SPDX-License-Identifier: Apache-2.0
import secrets
import time

import pytest

pytestmark = pytest.mark.integration

REALM_PATH = "/auth/realms/saigonos"
DISCOVERY_PATH = f"{REALM_PATH}/.well-known/openid-configuration"
TOKEN_PATH = f"{REALM_PATH}/protocol/openid-connect/token"
FORGED = {
    "X-Forwarded-For": "10.0.0.5",
    "X-Forwarded-Proto": "http",
    "X-Forwarded-Host": "evil.example",
    "X-Forwarded-Port": "1234",
}


@pytest.fixture(scope="module")
def public_addresses(caddy_stack):
    with caddy_stack.public_network("IPv4") as ipv4, caddy_stack.public_network("IPv6") as ipv6:
        yield {"IPv4": ipv4, "IPv6": ipv6}


def test_doctor_trusts_certificate_of_caddy(caddy_stack):
    result = caddy_stack.saigonos("doctor")

    assert result.returncode == 0, result.stdout
    assert "BÌNH THƯỜNG    caddy" in result.stdout


def test_http_is_redirected_to_https(caddy_stack):
    http_port = caddy_stack.env["CADDY_HTTP_PORT"]

    reply = caddy_stack.call("GET", f"http://localhost:{http_port}/auth/?a=1")

    assert reply.status == 308
    assert reply.headers["Location"] == f"{caddy_stack.url}/auth/?a=1"


def test_https_reply_has_hsts(caddy_stack):
    reply = caddy_stack.call("GET", f"{caddy_stack.url}{DISCOVERY_PATH}")

    assert reply.status == 200
    assert reply.headers["Strict-Transport-Security"] == "max-age=31536000"


def test_token_endpoint_matches_url_despite_forged_headers(caddy_stack):
    discovery = caddy_stack.discovery(headers=FORGED)

    assert discovery["token_endpoint"] == f"{caddy_stack.url}{TOKEN_PATH}"


@pytest.mark.parametrize("family", ["IPv4", "IPv6"])
def test_gateway_logs_address_of_caller_on_public_network(caddy_stack, public_addresses, family):
    agent = f"kiem-thu-{secrets.token_hex(4)}"
    address = public_addresses[family]

    caddy_stack.discovery(headers={**FORGED, "User-Agent": agent}, address=address)

    assert caddy_stack.logged_address(agent) == address


def test_rate_limit_counts_address_of_caller_despite_forged_header(caddy_stack, public_addresses):
    token = caddy_stack.token(caddy_stack.new_user())

    def remaining(forged):
        headers = {"X-Forwarded-For": forged}
        reply = caddy_stack.api(token, headers=headers, address=public_addresses["IPv4"])
        assert reply.status == 200, reply.body
        return reply.headers

    time.sleep(float(remaining("203.0.113.7")["X-RateLimit-Reset"]) + 0.5)
    counts = [
        int(remaining(forged)["X-RateLimit-Remaining"])
        for forged in ("203.0.113.7", "203.0.113.8", "10.0.0.5")
    ]

    assert counts == [299, 298, 297]


def test_certificate_is_kept_after_down_with_volumes(caddy_stack):
    before = caddy_stack.certificate()

    assert caddy_stack.saigonos("down", "--volumes").returncode == 0
    started = caddy_stack.saigonos("up")
    assert started.returncode == 0, started.stderr
    caddy_stack.create_client()

    assert caddy_stack.certificate() == before
