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
from datetime import datetime
from urllib.parse import urlencode

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
NAMESPACES = ["public", "user", "role"]
HISTORY_SIZE = 100
OUTAGE = 60
RECIPIENT = "nguoi-a"
KEY = "thu"
TITLE = "Thông báo thử"
NOTIFY = "core.notify(text, text, text, text, text, boolean)"
NOT_FOUND = {"detail": "Không tìm thấy thông báo"}
BAD_LINKS = {
    "javascript": "javascript:alert(1)",
    "web-khac": "https://web-khac.example/dang-nhap",
    "khong-giao-thuc": "//web-khac.example",
    "gach-nguoc": "/" + chr(92) + "web-khac.example",
    "co-tab": "/" + chr(9) + "/web-khac.example",
    "tuong-doi": "yeu-cau/YC-001",
    "rong": "",
    "qua-dai": "/" + "a" * 1000,
}
GOOD_LINKS = {
    "goc": "/",
    "co-query-va-fragment": "/yeu-cau/YC-001?tab=lich-su#cuoi",
    "dai-nhat": "/" + "a" * 999,
}
INVALID_NOTIFICATIONS = {
    "nguoi-nhan-null": ((None, KEY, TITLE), "Người nhận NULL không hợp lệ"),
    "nguoi-nhan-rong": (("", KEY, TITLE), "Người nhận '' không hợp lệ"),
    "nguoi-nhan-co-khoang-trang": (("nguoi a", KEY, TITLE), "Người nhận 'nguoi a' không hợp lệ"),
    "nguoi-nhan-la-kenh": (
        ("user:#nguoi-a", KEY, TITLE),
        "Người nhận 'user:#nguoi-a' không hợp lệ",
    ),
    "nguoi-nhan-co-dau": (("người-a", KEY, TITLE), "Người nhận 'người-a' không hợp lệ"),
    "nguoi-nhan-qua-dai": (("a" * 250, KEY, TITLE), "Người nhận '" + "a" * 250 + "' không hợp lệ"),
    "khoa-null": ((RECIPIENT, None, TITLE), "Khóa chống trùng không hợp lệ"),
    "khoa-rong": ((RECIPIENT, "", TITLE), "Khóa chống trùng không hợp lệ"),
    "khoa-qua-dai": ((RECIPIENT, "k" * 256, TITLE), "Khóa chống trùng không hợp lệ"),
    "tieu-de-null": ((RECIPIENT, KEY, None), "Tiêu đề không hợp lệ"),
    "tieu-de-chi-co-khoang-trang": ((RECIPIENT, KEY, " " + chr(9) + " "), "Tiêu đề không hợp lệ"),
    "tieu-de-xuong-dong": ((RECIPIENT, KEY, "Dòng 1" + chr(10) + "Dòng 2"), "Tiêu đề không hợp lệ"),
    "tieu-de-khoang-trang-khong-ngat": (
        (RECIPIENT, KEY, chr(0xA0) + chr(0x2007) + chr(0x202F)),
        "Tiêu đề không hợp lệ",
    ),
    "tieu-de-qua-dai": ((RECIPIENT, KEY, "t" * 201), "Tiêu đề không hợp lệ"),
    "noi-dung-qua-dai": ((RECIPIENT, KEY, TITLE, "n" * 2001), "Nội dung dài quá 2000 ký tự"),
}
NOTIFICATION_PRIVILEGES = """
SELECT r.rolname, p.privilege
FROM pg_roles AS r,
    unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'])
        AS p (privilege)
WHERE NOT r.rolsuper AND r.rolname !~ '^pg_'
AND has_table_privilege(r.oid, 'core.notifications', p.privilege)
UNION ALL
SELECT r.rolname, 'UPDATE (' || a.attname || ')'
FROM pg_roles AS r, pg_attribute AS a
WHERE a.attrelid = 'core.notifications'::regclass AND a.attnum > 0 AND NOT a.attisdropped
AND NOT r.rolsuper AND r.rolname !~ '^pg_'
AND has_column_privilege(r.oid, a.attrelid, a.attnum, 'UPDATE')
ORDER BY 1, 2
"""
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


def listener(stack, namespace):
    if namespace == "role":
        member, channel = role_member(stack)
        return member, channel, lambda: channel_token(stack, member, channel)
    user = stack.new_user()
    channel = f"user:#{user.id}" if namespace == "user" else f"public:thu-{secrets.token_hex(4)}"
    return user, channel, lambda: None


def position(reply):
    result = reply["subscribe"]
    return result["epoch"], result.get("offset", 0)


def resubscribe(client, channel, since, token=None):
    epoch, offset = since
    body = {"channel": channel, "recover": True, "epoch": epoch, "offset": offset}
    return client.command("subscribe", body if token is None else body | {"token": token})


def history(client, channel):
    return client.command("history", {"channel": channel, "limit": -1})


def recovery(result):
    return result.get("was_recovering", False), result.get("recovered", False)


def contents(publications):
    return [(item["data"], item["tags"]) for item in publications]


def outbox_size(stack, channel=None):
    condition = "" if channel is None else f" WHERE payload ->> 'channel' = {literal(channel)}"
    return int(stack.sql(f"SELECT count(*) FROM core.outbox{condition}")[0][0])


@contextmanager
def listening(stack, user, channels):
    key = {"X-API-Key": stack.env["CENTRIFUGO_API_KEY"]}
    with stack.realtime() as client:
        client_id = client.connect(stack.token(user))["connect"]["client"]
        for channel in channels:
            body = {"user": user.id, "client": client_id, "channel": channel}
            reply = internal(stack, "POST", "/api/subscribe", body=body, headers=key)
            assert (reply.status, json.loads(reply.body)) == (200, {"result": {}}), reply.body
            pushed = client.receive()["push"]
            assert (pushed["channel"], "subscribe" in pushed) == (channel, True)
        yield client


@contextmanager
def inbox(stack, user):
    with connected_as(stack, user) as client:
        assert "subscribe" in subscribe(client, f"user:#{user.id}")
        yield client


def arguments_of(values):
    return ", ".join(literal(value) for value in values)


def notify(stack, *values):
    return stack.sql(f"SET ROLE workflow; SELECT core.notify({arguments_of(values)})")[-1][0]


def refused_notification(stack, values):
    return psql(stack, f"SET ROLE workflow; SELECT core.notify({arguments_of(values)})")


def notifications_of(stack, user, **page):
    query = f"?{urlencode(page)}" if page else ""
    reply = stack.call("GET", f"{stack.url}/core/notifications{query}", token=stack.token(user))
    assert reply.status == 200, reply.body
    return json.loads(reply.body)


def mark_read(stack, user, notification_id):
    url = f"{stack.url}/core/notifications/{notification_id}/read"
    return stack.call("POST", url, token=stack.token(user))


def quoted(value):
    text = value.replace("'", "''")
    if chr(92) in value:
        return "E'" + text.replace(chr(92), chr(92) * 2) + "'"
    return f"'{text}'"


def as_caller(stack, role, subject, query):
    claims = literal(json.dumps({"sub": subject}))
    prefix = f"SELECT set_config('request.jwt.claims', {claims}, false) IS NULL; SET ROLE {role}; "
    return stack.sql(prefix + query)[-1]


def audit_of(stack, notification_id):
    return stack.sql(
        "SELECT operation, actor, db_role FROM core.audit_log "
        "WHERE table_name = 'notifications' "
        f"AND coalesce(new_row, old_row) ->> 'id' = {literal(notification_id)} ORDER BY id"
    )


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

    assert "expires" not in reply["subscribe"]
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
    assert "expires" not in accepted["subscribe"]
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


@pytest.mark.parametrize("namespace", NAMESPACES)
def test_reconnecting_client_receives_missed_messages(stack, namespace):
    user, channel, token = listener(stack, namespace)

    with connected_as(stack, user) as client:
        reply = subscribe(client, channel, token())
        first = publish(stack, channel, {"lan": 1})
        last = received(client, 5)["push"]["pub"]
    missed = [publish(stack, channel, {"lan": lan}) for lan in (2, 3)]
    wait_for(lambda: outbox_size(stack, channel) == 0, timeout=5)
    since = (reply["subscribe"]["epoch"], last["offset"])
    with connected_as(stack, user) as client:
        recovered = resubscribe(client, channel, since, token())["subscribe"]

    assert reply["subscribe"]["recoverable"] is True
    assert last["tags"] == {"id": first}
    assert recovery(recovered) == (True, True)
    assert contents(recovered["publications"]) == [
        ({"lan": 2}, {"id": missed[0]}),
        ({"lan": 3}, {"id": missed[1]}),
    ]


def test_client_that_missed_more_than_history_is_not_recovered(stack, user):
    channel = f"public:thu-{secrets.token_hex(4)}"
    query = (
        "SET ROLE workflow; "
        f"SELECT core.publish({literal(channel)}, jsonb_build_object('lan', lan)) "
        f"FROM generate_series(1, {HISTORY_SIZE + 1}) AS lan"
    )

    with connected_as(stack, user) as client:
        since = position(subscribe(client, channel))
    stack.sql(query)
    wait_for(lambda: outbox_size(stack, channel) == 0, timeout=10)
    with connected_as(stack, user) as client:
        reply = resubscribe(client, channel, since)["subscribe"]
        kept = history(client, channel)["history"]

    assert recovery(reply) == (True, False)
    assert "publications" not in reply
    assert [item["data"]["lan"] for item in kept["publications"]] == list(
        range(2, HISTORY_SIZE + 2)
    )
    assert kept["offset"] == HISTORY_SIZE + 1


def test_messages_written_while_centrifugo_is_stopped_reach_client_after_restart(stack):
    listeners = [listener(stack, namespace) for namespace in NAMESPACES]
    positions = []
    for user, channel, token in listeners:
        with connected_as(stack, user) as client:
            positions.append(position(subscribe(client, channel, token())))

    stopped_at = time.monotonic()
    stopped = stack.compose_result("stop", "centrifugo")
    written = [
        [publish(stack, channel, {"lan": lan}) for lan in (1, 2)] for _, channel, _ in listeners
    ]
    waiting = sum(outbox_size(stack, channel) for _, channel, _ in listeners)
    time.sleep(max(0, OUTAGE - (time.monotonic() - stopped_at)))
    started = stack.compose_result("up", "-d", "--wait", "centrifugo")
    wait_for(lambda: outbox_size(stack) == 0, timeout=15)
    replies = []
    for (user, channel, token), since in zip(listeners, positions, strict=True):
        with connected_as(stack, user) as client:
            reply = resubscribe(client, channel, since, token())["subscribe"]
            replies.append((reply, history(client, channel)["history"]))

    assert stopped.returncode == 0, stopped.stderr
    assert waiting == 2 * len(listeners)
    assert started.returncode == 0, started.stderr
    for (reply, kept), (epoch, _), ids in zip(replies, positions, written, strict=True):
        assert recovery(reply) == (True, False)
        assert reply["epoch"] != epoch
        assert contents(kept["publications"]) == [
            ({"lan": 1}, {"id": ids[0]}),
            ({"lan": 2}, {"id": ids[1]}),
        ]


def test_only_subscribed_client_reads_history(stack, user):
    other = stack.new_user()
    _, role_channel = role_member(stack)
    own = f"user:#{user.id}"
    channels = [own, f"user:#{other.id}", role_channel, f"public:thu-{secrets.token_hex(4)}"]
    for channel in channels:
        publish(stack, channel, {"lan": 1})
    wait_for(lambda: all(outbox_size(stack, channel) == 0 for channel in channels), timeout=5)

    with connected_as(stack, user) as client:
        refused = [history(client, channel) for channel in channels]
        recovering = resubscribe(client, f"user:#{other.id}", ("khac", 0))
        subscribe(client, own)
        allowed = history(client, own)

    assert [error_of(reply) for reply in refused] == [PERMISSION_DENIED] * len(channels)
    assert error_of(recovering) == PERMISSION_DENIED
    assert [data for data, _ in contents(allowed["history"]["publications"])] == [{"lan": 1}]


def test_notification_reaches_recipient_within_one_second_as_listed(stack, user):
    title, body, link = "Yêu cầu YC-001 đã được xử lý", "Máy 12 đã được thay cáp", "/yeu-cau/YC-001"

    with inbox(stack, user) as client:
        notification_id = notify(stack, user.id, "yeu-cau:YC-001:da-xu-ly", title, body, link)
        message = received(client, 1)
    [listed] = notifications_of(stack, user)

    assert message is not None, "Thông báo không tới trong 1 giây"
    channel, data, tags = publication(message)
    pushed = data["notification"]
    assert (channel, set(data), set(tags)) == (f"user:#{user.id}", {"notification"}, {"id"})
    assert listed == {
        "id": notification_id,
        "title": title,
        "body": body,
        "link": link,
        "created_at": listed["created_at"],
        "read_at": None,
    }
    assert pushed | {"created_at": None} == listed | {"created_at": None}
    assert datetime.fromisoformat(pushed["created_at"]) == datetime.fromisoformat(
        listed["created_at"]
    )


def test_recipient_marks_notification_as_read_once(stack, user):
    notification_id = notify(stack, user.id, KEY, TITLE)

    first = mark_read(stack, user, notification_id)
    again = mark_read(stack, user, notification_id)
    [listed] = notifications_of(stack, user)

    read = json.loads(first.body)
    assert (first.status, again.status) == (200, 200)
    assert read["id"] == notification_id
    assert read["read_at"] is not None
    assert json.loads(again.body) == read == listed
    assert audit_of(stack, notification_id) == [
        ["INSERT", "", "workflow"],
        ["UPDATE", user.id, "core_service"],
    ]


def test_other_user_neither_sees_nor_marks_notification(stack, user):
    other = stack.new_user()
    notification_id = notify(stack, user.id, KEY, TITLE)

    seen = notifications_of(stack, other)
    refused = mark_read(stack, other, notification_id)
    [listed] = notifications_of(stack, user)

    assert seen == []
    assert (refused.status, json.loads(refused.body)) == (404, NOT_FOUND)
    assert listed["read_at"] is None


def test_same_key_gives_one_notification_and_one_message(stack, user):
    key = "yeu-cau:YC-002:da-xu-ly"

    with inbox(stack, user) as client:
        first = notify(stack, user.id, key, "Lần đầu")
        pushed = received(client, 1)
        again = notify(stack, user.id, key, "Lần hai", "Nội dung khác", "/khac")
        extra = received(client, 2)
    listed = notifications_of(stack, user)

    assert again == first
    assert publication(pushed)[1]["notification"]["id"] == first
    assert extra is None
    assert [(item["id"], item["title"], item["body"]) for item in listed] == [
        (first, "Lần đầu", None)
    ]


def test_same_key_for_other_recipient_gives_own_notification(stack, user):
    other = stack.new_user()
    key = "yeu-cau:YC-003:da-xu-ly"

    ids = [notify(stack, recipient.id, key, TITLE) for recipient in (user, other)]

    assert ids[0] != ids[1]
    assert [item["id"] for item in notifications_of(stack, user)] == [ids[0]]
    assert [item["id"] for item in notifications_of(stack, other)] == [ids[1]]


@pytest.mark.parametrize("ending", ["COMMIT", "ROLLBACK"], ids=["commit", "rollback"])
def test_notify_waits_for_other_transaction_with_same_key(stack, user, ending):
    key = f"dua-{secrets.token_hex(4)}"
    held = (
        f"BEGIN; SET ROLE workflow; SELECT core.notify({arguments_of([user.id, key, 'Lần đầu'])}); "
        f"SELECT pg_sleep(2); {ending}"
    )
    sleeping = (
        "SELECT count(*) FROM pg_stat_activity "
        f"WHERE wait_event = 'PgSleep' AND query LIKE {literal('%' + key + '%')}"
    )

    with inbox(stack, user) as client, ThreadPoolExecutor(1) as pool:
        holder = pool.submit(psql, stack, held)
        wait_for(lambda: stack.sql(sleeping) == [["1"]], timeout=10)
        second = notify(stack, user.id, key, "Lần hai")
        pushed = publication(received(client, 5))[1]["notification"]
        extra = received(client, 2)
        first = re.search(r"^[0-9a-f-]{36}$", holder.result().stdout, re.MULTILINE)[0]
    listed = notifications_of(stack, user)

    kept = (first, "Lần đầu") if ending == "COMMIT" else (second, "Lần hai")
    assert (second == first) == (ending == "COMMIT")
    assert (pushed["id"], pushed["title"]) == kept
    assert extra is None
    assert [(item["id"], item["title"]) for item in listed] == [kept]


def test_rolled_back_notification_is_neither_saved_nor_sent(stack, user):
    key = f"huy-{secrets.token_hex(4)}"
    channel = f"user:#{user.id}"
    undone = f"SELECT core.notify({arguments_of([user.id, key, TITLE])}); SELECT 1 / 0"

    with inbox(stack, user) as client:
        failed = psql(stack, f"SET ROLE workflow; {undone}")
        marker = publish(stack, channel, {"moc": True})
        message = received(client, 5)
    saved = stack.sql(f"SELECT count(*) FROM core.notifications WHERE dedup_key = {literal(key)}")

    assert "division by zero" in failed.stderr
    assert publication(message) == (channel, {"moc": True}, {"id": marker})
    assert saved == [["0"]]


def test_list_gives_newest_notifications_first_page_by_page(stack, user):
    ids = [notify(stack, user.id, f"trang-{number}", f"Thông báo {number}") for number in range(3)]

    first_page = notifications_of(stack, user, limit=2)
    second_page = notifications_of(stack, user, offset=2, limit=2)

    assert [item["id"] for item in first_page + second_page] == ids[::-1]


@pytest.mark.parametrize(
    ("values", "message"), INVALID_NOTIFICATIONS.values(), ids=INVALID_NOTIFICATIONS.keys()
)
def test_notify_refuses_invalid_values(stack, values, message):
    refused = refused_notification(stack, values)

    assert refused.returncode != 0
    assert f"ERROR:  {message}\n" in refused.stderr


@pytest.mark.parametrize("link", BAD_LINKS.values(), ids=BAD_LINKS.keys())
def test_notify_refuses_link_outside_system(stack, link):
    refused = refused_notification(stack, (RECIPIENT, KEY, TITLE, None, link))

    assert refused.returncode != 0
    assert f"ERROR:  Đường dẫn {quoted(link)} không hợp lệ\n" in refused.stderr


@pytest.mark.parametrize("link", GOOD_LINKS.values(), ids=GOOD_LINKS.keys())
def test_notify_accepts_link_inside_system(stack, user, link):
    notification_id = notify(stack, user.id, KEY, TITLE, None, link)

    [listed] = notifications_of(stack, user)

    assert (listed["id"], listed["link"]) == (notification_id, link)


def test_notify_accepts_longest_values(stack):
    values = [
        secrets.token_hex(4) + "a" * 241,
        "k" * 255,
        "t" * 200,
        "Dòng 1" + chr(10) + "n" * 1993,
    ]

    notification_id = notify(stack, *values)
    stored = stack.sql(
        "SELECT recipient = {}, dedup_key = {}, title = {}, body = {} "
        "FROM core.notifications WHERE id = {}".format(*map(literal, [*values, notification_id]))
    )

    assert [len(value) for value in values] == [249, 255, 200, 2000]
    assert stored == [["t", "t", "t", "t"]]


def test_only_role_workflow_can_notify(stack):
    roles = ", ".join(literal(role) for role in [*PUBLISHERS, "workflow"])
    query = (
        f"SELECT role, has_function_privilege(role, {literal(NOTIFY)}, 'EXECUTE') "
        f"FROM unnest(ARRAY[{roles}]) AS role"
    )

    allowed = dict(stack.sql(query))
    refused = psql(
        stack,
        f"SET ROLE authenticated; SELECT core.notify({arguments_of([RECIPIENT, KEY, TITLE])})",
    )

    assert allowed == {**dict.fromkeys(PUBLISHERS, "f"), "workflow": "t"}
    assert "permission denied for function notify" in refused.stderr


def test_only_core_service_may_change_read_time_of_notifications(stack):
    assert stack.sql(NOTIFICATION_PRIVILEGES) == [
        ["authenticated", "SELECT"],
        ["core_service", "SELECT"],
        ["core_service", "UPDATE (read_at)"],
    ]


def test_row_security_limits_roles_to_notifications_of_caller(stack):
    first, second = (f"nguoi-{secrets.token_hex(4)}" for _ in range(2))
    for recipient in (first, second):
        notify(stack, recipient, KEY, TITLE)
    both = f"recipient IN ({literal(first)}, {literal(second)})"

    seen = as_caller(
        stack,
        "authenticated",
        first,
        f"SELECT string_agg(recipient, ',') FROM core.notifications WHERE {both}",
    )
    marked = as_caller(
        stack,
        "core_service",
        first,
        "WITH marked AS (UPDATE core.notifications SET read_at = now() "
        f"WHERE {both} RETURNING recipient) SELECT string_agg(recipient, ',') FROM marked",
    )
    unread = stack.sql(f"SELECT recipient FROM core.notifications WHERE {both} AND read_at IS NULL")

    assert seen == marked == [first]
    assert unread == [[second]]
