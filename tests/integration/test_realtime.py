# SPDX-License-Identifier: Apache-2.0
import base64
import json
import re
import secrets
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

pytestmark = pytest.mark.integration

INVALID_TOKEN = (3500, "invalid token")
NO_USER = (3507, "permission denied")
SHUTDOWN = (3001, "shutdown")
EXPIRED = {"id": 1, "error": {"code": 109, "message": "token expired"}}
AUDIENCE_MAPPER = "audience saigonos"
OTHER_ISSUER = "http://khac.example/auth"
INFO = {"method": "info", "params": {}}
CLOSED_PATHS = [
    ("GET", "/realtime/"),
    ("GET", "/realtime/api"),
    ("POST", "/realtime/api/publish"),
    ("GET", "/realtime/health"),
    ("POST", "/realtime/admin/auth"),
    ("GET", "/realtime/connection/http_stream"),
    ("GET", "/realtime/connection/sse"),
    ("GET", "/realtime/connection/websocket/"),
    ("GET", "/realtime/connection/websocket/../../api"),
    ("GET", "/realtime/connection/websocket;x"),
    ("GET", "/connection/websocket"),
]


def decode(token, part=1):
    segment = token.split(".")[part]
    return json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))


def wait_for(condition, timeout=60):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "Hết thời gian chờ"
        time.sleep(0.5)


def internal(stack, method, path, **options):
    port = stack.env["SAIGONOS_CENTRIFUGO_PORT"]
    return stack.call(method, f"http://127.0.0.1:{port}{path}", **options)


def connect(stack, token):
    with stack.realtime() as client:
        return client.connect(token)


def connected(reply):
    return isinstance(reply, dict) and "connect" in reply


def new_client(stack, **fields):
    client_id = f"kiem-thu-{secrets.token_hex(4)}"
    client = {
        "clientId": client_id,
        "publicClient": True,
        "directAccessGrantsEnabled": True,
        "standardFlowEnabled": False,
        **fields,
    }
    assert stack.admin("POST", "/clients", client).status == 201
    return client_id


def tokens_of(stack, user, client_id=None, scope=None):
    form = {
        "grant_type": "password",
        "client_id": client_id or "kiem-thu",
        "username": user.name,
        "password": user.password,
    }
    if scope:
        form["scope"] = scope
    path = "/auth/realms/saigonos/protocol/openid-connect/token"
    reply = stack.call("POST", f"{stack.url}{path}", form=form)
    assert reply.status == 200, reply.body
    return json.loads(reply.body)


def audience_mapper(stack):
    scopes = json.loads(stack.admin("GET", "/client-scopes").body)
    roles = next(scope for scope in scopes if scope["name"] == "roles")
    path = f"/client-scopes/{roles['id']}/protocol-mappers/models"
    mapper = next(item for item in roles["protocolMappers"] if item["name"] == AUDIENCE_MAPPER)
    return f"{path}/{mapper['id']}", mapper


def set_frontend_url(stack, url):
    attributes = json.loads(stack.admin("GET", "").body)["attributes"]
    reply = stack.admin("PUT", "", {"attributes": {**attributes, "frontendUrl": url}})
    assert reply.status == 204, reply.body


@pytest.fixture
def user(stack):
    return stack.new_user()


def test_doctor_reports_centrifugo(stack):
    result = stack.saigonos("doctor")

    assert result.returncode == 0, result.stdout
    assert re.search(r"BÌNH THƯỜNG\s+centrifugo\s+đang chạy", result.stdout)
    assert re.search(r"BÌNH THƯỜNG\s+Centrifugo\s+Centrifugo nhận kết nối WebSocket", result.stdout)


def test_access_token_connects_through_gateway(stack, user):
    token = stack.token(user)

    with stack.realtime() as client:
        reply = client.connect(token)

    assert client.accepted
    assert reply["connect"]["expires"] is True
    assert 0 < reply["connect"]["ttl"] <= 60


def test_connection_continues_with_new_access_token_of_same_user(stack, user):
    other = stack.new_user()

    with stack.realtime() as client:
        assert connected(client.connect(stack.token(user)))
        refreshed = client.command("refresh", {"token": stack.token(user)})
        taken = client.command("refresh", {"token": stack.token(other)})

    assert refreshed["refresh"]["expires"] is True
    assert taken == INVALID_TOKEN


def test_connection_without_token_is_refused(stack):
    with stack.realtime() as client:
        assert client.connect() == (3501, "bad request")


@pytest.mark.parametrize("kind", ["khong-phai-jwt", "sua-noi-dung", "khong-ky"])
def test_forged_token_is_refused(stack, user, kind):
    assert connect(stack, stack.forged_tokens(user)[kind]) == INVALID_TOKEN


def test_expired_access_token_is_refused(stack, user):
    client_id = new_client(stack, attributes={"access.token.lifespan": "1"})
    token = tokens_of(stack, user, client_id)["access_token"]

    time.sleep(max(0, decode(token)["exp"] - time.time()) + 1)

    assert connect(stack, token) == EXPIRED


def test_access_token_of_other_issuer_is_refused(stack, user):
    set_frontend_url(stack, OTHER_ISSUER)
    try:
        token = stack.token(user)
    finally:
        set_frontend_url(stack, "")

    assert decode(token)["iss"] == f"{OTHER_ISSUER}/realms/saigonos"
    assert connect(stack, token) == INVALID_TOKEN
    assert connected(connect(stack, stack.token(user)))


def test_id_token_is_refused(stack, user):
    tokens = tokens_of(stack, user, scope="openid")

    assert decode(tokens["id_token"])["typ"] == "ID"
    assert "saigonos" in decode(tokens["access_token"])["aud"]
    assert connect(stack, tokens["id_token"]) == INVALID_TOKEN
    assert connected(connect(stack, tokens["access_token"]))


def test_access_token_without_user_is_refused(stack, user):
    client_id = new_client(stack, defaultClientScopes=["roles"])
    token = tokens_of(stack, user, client_id)["access_token"]

    assert "sub" not in decode(token)
    assert "saigonos" in decode(token)["aud"]
    assert connect(stack, token) == NO_USER


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            "sua",
            "Mapper audience saigonos của client scope roles đã bị thay đổi nên được đặt lại",
        ),
        ("xoa", "Đã thêm mapper audience saigonos vào client scope roles của realm saigonos"),
    ],
    ids=["sua", "xoa"],
)
def test_realm_service_restores_audience_of_access_token(stack, user, change, message):
    path, mapper = audience_mapper(stack)
    if change == "sua":
        config = mapper["config"] | {"access.token.claim": "false", "id.token.claim": "true"}
        assert stack.admin("PUT", path, mapper | {"config": config}).status == 204
    else:
        assert stack.admin("DELETE", path).status == 204
    refused = connect(stack, stack.token(user))

    result = stack.compose_result("run", "--rm", "--no-deps", "realm")

    tokens = tokens_of(stack, user, scope="openid")
    assert refused == INVALID_TOKEN
    assert result.returncode == 0, result.stderr
    assert message in result.stdout.splitlines()
    assert connected(connect(stack, tokens["access_token"]))
    assert connect(stack, tokens["id_token"]) == INVALID_TOKEN


def test_page_of_other_site_cannot_open_connection(stack, user):
    with stack.realtime({"Origin": "http://evil.example"}) as client:
        assert client.status == 403

    with stack.realtime({}) as client:
        assert connected(client.connect(stack.token(user)))


def test_gateway_counts_connections_in_rate_limit(stack):
    with stack.realtime() as client:
        assert client.status == 101
        assert client.headers["x-ratelimit-limit"] == "300"


@pytest.mark.parametrize(("method", "path"), CLOSED_PATHS)
def test_gateway_opens_only_websocket_of_centrifugo(stack, method, path):
    body = {} if method == "POST" else None

    assert stack.call(method, f"{stack.url}{path}", body=body).status == 404


def test_only_internal_port_is_published_on_loopback(stack):
    port = stack.env["SAIGONOS_CENTRIFUGO_PORT"]

    published = json.loads(
        stack.inspect(stack.container("centrifugo"), "{{json .NetworkSettings.Ports}}")
    )

    assert published == {"9000/tcp": [{"HostIp": "127.0.0.1", "HostPort": port}]}


def test_server_api_requires_key(stack):
    key = stack.env["CENTRIFUGO_API_KEY"]

    missing = internal(stack, "POST", "/api/info", body={})
    wrong = internal(stack, "POST", "/api/info", body={}, headers={"X-API-Key": "sai"})
    right = internal(stack, "POST", "/api/info", body={}, headers={"X-API-Key": key})

    assert (missing.status, wrong.status, right.status) == (401, 401, 200)
    assert json.loads(right.body)["result"]["nodes"]


def test_admin_web_requires_password(stack):
    page = internal(stack, "GET", "/")
    wrong = internal(stack, "POST", "/admin/auth", form={"password": "sai-mat-khau"})
    password = stack.env["CENTRIFUGO_ADMIN_PASSWORD"]
    right = internal(stack, "POST", "/admin/auth", form={"password": password})
    token = json.loads(right.body)["token"]
    forged = {"Authorization": "token khong-hop-le"}

    assert page.status == 200
    assert b"<html" in page.body
    assert internal(stack, "POST", "/admin/api", body=INFO).status == 401
    assert internal(stack, "POST", "/admin/api", body=INFO, headers=forged).status == 401
    assert wrong.status == 400
    assert right.status == 200
    signed_in = {"Authorization": f"token {token}"}
    reply = internal(stack, "POST", "/admin/api", body=INFO, headers=signed_in)
    assert reply.status == 200
    assert json.loads(reply.body)["result"]["nodes"]


def test_stopping_centrifugo_tells_clients_to_reconnect(stack, user):
    container = stack.container("centrifugo")

    with stack.realtime() as client, ThreadPoolExecutor(1) as pool:
        assert connected(client.connect(stack.token(user)))
        closing = pool.submit(client.receive)
        started = time.monotonic()
        stopped = stack.compose_result("stop", "centrifugo")
        took = time.monotonic() - started
        closed = closing.result(timeout=10)
    exit_code = stack.inspect(container, "{{.State.ExitCode}}")
    restarted = stack.compose_result("up", "-d", "--wait", "centrifugo")

    assert stopped.returncode == 0, stopped.stderr
    assert closed == SHUTDOWN
    assert exit_code == "0"
    assert took < 5
    assert restarted.returncode == 0, restarted.stderr
    assert connected(connect(stack, stack.token(user)))


def test_killed_centrifugo_restarts_by_itself(stack, user):
    container = stack.container("centrifugo")
    restarts = int(stack.inspect(container, "{{.RestartCount}}"))
    state = "{{.RestartCount}} {{.State.Health.Status}}"

    stack.kill(container)

    wait_for(lambda: stack.inspect(container, state) == f"{restarts + 1} healthy")
    wait_for(lambda: connected(connect(stack, stack.token(user))))


def test_new_signing_key_is_accepted_without_restart(stack, user):
    old_key = decode(stack.token(user), 0)["kid"]

    stack.rotate_keys()

    assert decode(stack.token(user), 0)["kid"] != old_key
    wait_for(lambda: connected(connect(stack, stack.token(user))), timeout=15)
