# SPDX-License-Identifier: Apache-2.0
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

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
WRITE = (
    "SET ROLE workflow; "
    "WITH added AS (INSERT INTO {table} (noi_dung) VALUES ({content}) RETURNING id) "
    "SELECT core.publish({channel}, jsonb_build_object('yeu_cau', id, 'noi_dung', {content})) "
    "FROM added"
)
INVALID_CHANNELS = {
    "khong-namespace": "thu",
    "namespace-khac": "khac:thu",
    "chu-hoa": "PUBLIC:thu",
    "ten-rong": "public:",
    "khoang-trang": "public:may 12",
    "hai-dau-hai-cham": "public:phong:may",
    "dau-thang": "public:may#12",
    "co-dau": "public:phòng-máy",
    "thieu-dau-thang": "user:nguoi-a",
    "nguoi-dung-rong": "user:#",
    "hai-nguoi-dung": "user:#nguoi-a,nguoi-b",
    "role-rong": "role:",
    "qua-dai": "public:" + "a" * 249,
}
PUBLISHERS = ["public", "anon", "authenticated", "authenticator", "core_service", "centrifugo"]
PERMISSION_DENIED = {"code": 103, "message": "permission denied"}
UNKNOWN_CHANNEL = {"code": 102, "message": "unknown channel"}
TOKEN_EXPIRED = {"code": 109, "message": "token expired"}
NO_ROLE = {"detail": "Người gọi không có realm role của kênh này"}
OUTSIDE_CHANNELS = {
    "khong-namespace": ("thu", PERMISSION_DENIED),
    "namespace-khac": ("khac:thu", UNKNOWN_CHANNEL),
    "user-thieu-dau-thang": ("user:thu", PERMISSION_DENIED),
    "role-khong-token": ("role:admin", PERMISSION_DENIED),
}
FORGED_CHANNEL_TOKENS = ["ky-bang-khoa-khac", "khong-ky", "access-token", "sua-kenh"]
TABLE_PRIVILEGES = """
SELECT c.oid::regclass::text, p.privilege
FROM pg_class AS c,
    unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE']) AS p (privilege)
WHERE c.relnamespace NOT IN ('pg_catalog'::regnamespace, 'information_schema'::regnamespace)
AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
AND has_table_privilege('centrifugo', c.oid, p.privilege)
ORDER BY 1, 2
"""


def decode(token, part=1):
    segment = token.split(".")[part]
    return json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))


def encode(data):
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def signed(claims, key):
    content = f"{encode({'alg': 'HS256', 'typ': 'JWT'})}.{encode(claims)}"
    signature = hmac.new(key.encode(), content.encode(), hashlib.sha256).digest()
    return f"{content}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


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


def literal(value):
    return "NULL" if value is None else "'" + value.replace("'", "''") + "'"


def psql(stack, query):
    options = ["--username=postgres", "--dbname=saigonos", "--no-psqlrc", "--tuples-only"]
    options += ["--no-align", "--set=ON_ERROR_STOP=1", f"--command={query}"]
    return stack.exec("postgres", "psql", *options)


def publish(stack, channel, data):
    arguments = f"{literal(channel)}, {literal(json.dumps(data))}"
    return stack.sql(f"SET ROLE workflow; SELECT core.publish({arguments})")[-1][0]


def write(stack, table, channel, content):
    query = WRITE.format(table=table, channel=literal(channel), content=literal(content))
    return stack.sql(query)[-1][0]


def received(client, timeout):
    client.connection.sock.settimeout(timeout)
    try:
        return client.receive()
    except TimeoutError:
        return None
    finally:
        client.connection.sock.settimeout(30)


def publication(message):
    push = (message or {}).get("push", {})
    return push.get("channel"), push.get("pub", {}).get("data"), push.get("pub", {}).get("tags")


def in_outbox(stack, message_id):
    query = f"SELECT count(*) FROM core.outbox WHERE payload -> 'tags' ->> 'id' = '{message_id}'"
    return int(stack.sql(query)[0][0])


@contextmanager
def connected_as(stack, user):
    with stack.realtime() as client:
        assert connected(client.connect(stack.token(user)))
        yield client


def subscribe(client, channel, token=None):
    body = {"channel": channel} if token is None else {"channel": channel, "token": token}
    return client.command("subscribe", body)


def error_of(reply):
    return reply.get("error") if isinstance(reply, dict) else reply


def request_channel_token(stack, user, channel):
    url = f"{stack.url}/core/realtime/token"
    return stack.call("POST", url, token=stack.token(user), body={"channel": channel})


def channel_token(stack, user, channel):
    reply = request_channel_token(stack, user, channel)
    assert reply.status == 200, reply.body
    return json.loads(reply.body)["token"]


def role_member(stack):
    role = f"thu-{secrets.token_hex(4)}"
    return stack.new_user(role=role), f"role:{role}"


@contextmanager
def listening(stack, user, channels):
    key = {"X-API-Key": stack.env["CENTRIFUGO_API_KEY"]}
    with stack.realtime() as client:
        client_id = client.connect(stack.token(user))["connect"]["client"]
        for channel in channels:
            body = {"user": user.id, "client": client_id, "channel": channel}
            reply = internal(stack, "POST", "/api/subscribe", body=body, headers=key)
            assert (reply.status, json.loads(reply.body)) == (200, {"result": {}}), reply.body
            assert client.receive() == {"push": {"channel": channel, "subscribe": {}}}
        yield client


@pytest.fixture
def user(stack):
    return stack.new_user()


@pytest.fixture(scope="module")
def requests_table(stack):
    schema = f"thu_tin_{secrets.token_hex(4)}"
    stack.sql(
        f"CREATE SCHEMA {schema}; "
        f"CREATE TABLE {schema}.yeu_cau ("
        "id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, "
        "noi_dung text NOT NULL CHECK (noi_dung <> '')); "
        f"GRANT USAGE ON SCHEMA {schema} TO workflow; "
        f"GRANT SELECT, INSERT ON {schema}.yeu_cau TO workflow"
    )
    return f"{schema}.yeu_cau"


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


def test_centrifugo_starts_after_migrate_has_finished(stack):
    services = json.loads(stack.compose("config", "--format", "json"))["services"]

    centrifugo = services["centrifugo"]["depends_on"]["migrate"]["condition"]
    migrate = services["migrate"]["depends_on"]["databases"]["condition"]

    assert centrifugo == migrate == "service_completed_successfully"


def test_row_and_message_written_together_reach_listener_within_one_second(
    stack, user, requests_table
):
    tag = secrets.token_hex(4)
    channels = [f"public:thu-{tag}", f"user:#{user.id}", f"role:thu-{tag}"]

    with listening(stack, user, channels) as client:
        for channel in channels:
            content = f"Máy 12 không lên nguồn, kênh {channel}"
            message_id = write(stack, requests_table, channel, content)
            message = received(client, 1)

            query = f"SELECT id FROM {requests_table} WHERE noi_dung = {literal(content)}"
            [[row]] = stack.sql(query)
            data = {"yeu_cau": int(row), "noi_dung": content}
            assert publication(message) == (channel, data, {"id": message_id})


def test_rolled_back_transaction_sends_nothing(stack, user, requests_table):
    channel = f"public:thu-{secrets.token_hex(4)}"
    content = f"Bị hủy {secrets.token_hex(4)}"
    undone = WRITE.format(table=requests_table, channel=literal(channel), content=literal(content))

    with listening(stack, user, [channel]) as client:
        failed = psql(stack, f"{undone}; INSERT INTO {requests_table} (noi_dung) VALUES ('')")
        marker = publish(stack, channel, {"moc": True})
        message = received(client, 5)

    assert failed.returncode != 0
    assert "violates check constraint" in failed.stderr
    assert publication(message) == (channel, {"moc": True}, {"id": marker})
    written = f"SELECT count(*) FROM {requests_table} WHERE noi_dung = {literal(content)}"
    assert stack.sql(written) == [["0"]]


def test_sent_message_is_deleted_from_outbox(stack, user):
    channel = f"public:thu-{secrets.token_hex(4)}"

    with listening(stack, user, [channel]) as client:
        message_id = publish(stack, channel, {"lan": 1})
        message = received(client, 5)

    assert publication(message) == (channel, {"lan": 1}, {"id": message_id})
    wait_for(lambda: in_outbox(stack, message_id) == 0, timeout=5)


def test_each_message_gets_its_own_id(stack, user):
    channel = f"public:thu-{secrets.token_hex(4)}"

    with listening(stack, user, [channel]) as client:
        sent = [publish(stack, channel, {"lan": 1}) for _ in range(2)]
        tags = [publication(received(client, 5))[2] for _ in sent]

    assert len(set(sent)) == 2
    assert tags == [{"id": message_id} for message_id in sent]


@pytest.mark.parametrize("channel", INVALID_CHANNELS.values(), ids=INVALID_CHANNELS.keys())
def test_publish_refuses_channel_outside_three_namespaces(stack, channel):
    refused = psql(stack, f"SET ROLE workflow; SELECT core.publish({literal(channel)}, '{{}}')")

    assert refused.returncode != 0
    assert f"Kênh {literal(channel)} không hợp lệ" in refused.stderr


def test_channel_may_have_up_to_255_characters(stack):
    channel = "public:" + "a" * 248

    message_id = publish(stack, channel, {})

    assert len(channel) == 255
    assert re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", message_id)


def test_publish_refuses_null_channel_and_null_data(stack):
    no_channel = psql(stack, "SET ROLE workflow; SELECT core.publish(NULL, '{}')")
    no_data = psql(stack, "SET ROLE workflow; SELECT core.publish('public:thu', NULL)")

    assert "Kênh NULL không hợp lệ" in no_channel.stderr
    assert "Nội dung của tin không được là NULL" in no_data.stderr


def test_only_role_workflow_can_publish(stack):
    roles = ", ".join(literal(role) for role in [*PUBLISHERS, "workflow"])
    query = (
        "SELECT role, has_function_privilege(role, 'core.publish(text, jsonb)', 'EXECUTE') "
        f"FROM unnest(ARRAY[{roles}]) AS role"
    )

    allowed = dict(stack.sql(query))
    refused = psql(stack, "SET ROLE authenticated; SELECT core.publish('public:thu', '{}')")

    assert allowed == {**dict.fromkeys(PUBLISHERS, "f"), "workflow": "t"}
    assert "permission denied for function publish" in refused.stderr


def test_role_centrifugo_only_reads_and_deletes_outbox(stack):
    attributes = stack.sql(
        "SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
        "FROM pg_roles WHERE rolname = 'centrifugo'"
    )
    groups = stack.sql("SELECT count(*) FROM pg_auth_members WHERE member = 'centrifugo'::regrole")

    assert stack.sql(TABLE_PRIVILEGES) == [["core.outbox", "DELETE"], ["core.outbox", "SELECT"]]
    assert attributes == [["t", "f", "f", "f", "f", "f"]]
    assert groups == [["0"]]
    for database in ("keycloak", "operaton"):
        options = ["--username=centrifugo", f"--dbname={database}", "--command=SELECT 1"]
        refused = stack.exec("postgres", "psql", *options)
        assert f'permission denied for database "{database}"' in refused.stderr


def test_any_user_can_listen_to_public_channel(stack, user):
    channel = f"public:thu-{secrets.token_hex(4)}"

    with connected_as(stack, user) as client:
        reply = subscribe(client, channel)
        message_id = publish(stack, channel, {"lan": 1})
        message = received(client, 1)

    assert reply["subscribe"] == {}
    assert publication(message) == (channel, {"lan": 1}, {"id": message_id})


def test_user_listens_only_to_own_channel(stack, user):
    other = stack.new_user()
    own, foreign = f"user:#{user.id}", f"user:#{other.id}"

    with connected_as(stack, user) as client:
        refused = subscribe(client, foreign)
        accepted = subscribe(client, own)
        publish(stack, foreign, {"cho": "nguoi-khac"})
        message_id = publish(stack, own, {"cho": "minh"})
        message = received(client, 1)

    assert error_of(refused) == PERMISSION_DENIED
    assert accepted["subscribe"] == {}
    assert publication(message) == (own, {"cho": "minh"}, {"id": message_id})


def test_member_of_role_listens_with_channel_token_from_core(stack):
    member, channel = role_member(stack)

    token = channel_token(stack, member, channel)
    with connected_as(stack, member) as client:
        without_token = subscribe(client, channel)
        reply = subscribe(client, channel, token)
        message_id = publish(stack, channel, {"lan": 1})
        message = received(client, 1)

    assert error_of(without_token) == PERMISSION_DENIED
    assert reply["subscribe"]["expires"] is True
    assert 0 < reply["subscribe"]["ttl"] <= 60
    assert publication(message) == (channel, {"lan": 1}, {"id": message_id})


def test_user_without_role_gets_no_channel_token_and_cannot_listen(stack, user):
    _, channel = role_member(stack)

    refused = request_channel_token(stack, user, channel)
    with connected_as(stack, user) as client:
        reply = subscribe(client, channel)

    assert (refused.status, json.loads(refused.body)) == (403, NO_ROLE)
    assert error_of(reply) == PERMISSION_DENIED


def test_channel_token_can_be_refreshed_before_it_expires(stack):
    member, channel = role_member(stack)

    with connected_as(stack, member) as client:
        assert "subscribe" in subscribe(client, channel, channel_token(stack, member, channel))
        refreshed = client.command(
            "sub_refresh", {"channel": channel, "token": channel_token(stack, member, channel)}
        )

    assert refreshed["sub_refresh"]["expires"] is True
    assert 0 < refreshed["sub_refresh"]["ttl"] <= 60


@pytest.mark.parametrize("kind", FORGED_CHANNEL_TOKENS)
def test_forged_channel_token_is_refused(stack, kind):
    member, own_channel = role_member(stack)
    _, channel = role_member(stack)
    claims = {"sub": member.id, "channel": channel, "exp": int(time.time()) + 60}
    header, payload, signature = channel_token(stack, member, own_channel).split(".")
    changed = decode(f"{header}.{payload}") | {"channel": channel}
    tokens = {
        "ky-bang-khoa-khac": signed(claims, secrets.token_hex(16)),
        "khong-ky": f"{encode({'alg': 'none', 'typ': 'JWT'})}.{encode(claims)}.",
        "access-token": stack.token(member),
        "sua-kenh": f"{header}.{encode(changed)}.{signature}",
    }

    with connected_as(stack, member) as client:
        reply = subscribe(client, channel, tokens[kind])

    assert error_of(reply) == PERMISSION_DENIED


def test_expired_channel_token_is_refused(stack):
    member, channel = role_member(stack)
    claims = {"sub": member.id, "channel": channel, "exp": int(time.time()) - 1}

    with connected_as(stack, member) as client:
        reply = subscribe(client, channel, signed(claims, stack.env["CENTRIFUGO_SUBSCRIPTION_KEY"]))

    assert error_of(reply) == TOKEN_EXPIRED


def test_channel_token_of_other_channel_closes_connection(stack):
    member, channel = role_member(stack)
    _, other_channel = role_member(stack)

    with connected_as(stack, member) as client:
        reply = subscribe(client, other_channel, channel_token(stack, member, channel))

    assert reply == INVALID_TOKEN


def test_channel_token_of_other_user_closes_connection(stack, user):
    member, channel = role_member(stack)

    with connected_as(stack, user) as client:
        reply = subscribe(client, channel, channel_token(stack, member, channel))

    assert reply == INVALID_TOKEN


@pytest.mark.parametrize(
    ("channel", "error"), OUTSIDE_CHANNELS.values(), ids=OUTSIDE_CHANNELS.keys()
)
def test_channel_without_permission_is_refused(stack, user, channel, error):
    with connected_as(stack, user) as client:
        assert error_of(subscribe(client, channel)) == error
