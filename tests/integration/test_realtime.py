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
from email import message_from_string
from email.policy import default
from http.client import HTTPException
from pathlib import Path
from urllib.parse import urlencode

import fake_smtp
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
IPV6_URL = "http://[2001:db8::1]:9080"
IPV6_ORIGINS = {
    "dung-dia-chi": ("http://[2001:db8::1]:9080", 101),
    "chu-hoa": ("http://[2001:DB8::1]:9080", 101),
    "mot-ky-tu": ("http://1:9080", 403),
    "dia-chi-khac": ("http://[2001:db8::2]:9080", 403),
    "cong-khac": ("http://[2001:db8::1]:9081", 403),
}
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
DELIVERY_PRIVILEGES = NOTIFICATION_PRIVILEGES.replace("core.notifications", "core.deliveries")
TELEGRAM_TOKEN = "123456789:token-cua-bot-gia"
TELEGRAM_CHAT = -1001234567890
TELEGRAM_TOPIC = 7
BOT_API = "telegram-gia"
STOPPED_WHILE_SENDING = (
    "Service core dừng khi đang gửi tin nên không biết tin đã tới Telegram hay chưa"
)
STATE = "{{.RestartCount}} {{.State.Health.Status}}"
SEND_EMAIL = "core.send_email(text, text, text, text, text)"
CHECK_MESSAGE = "core.check_message(text, text, text, text)"
ADDRESS = "nguyen.van.a@example.com"
OTHER_ADDRESS = "tran.thi.b@example.com"
BAD_ADDRESSES = {
    "null": None,
    "rong": "",
    "thieu-a-cong": "nguyen.van.a",
    "thieu-ten-mien": "nguyen.van.a@",
    "thieu-ten": "@example.com",
    "co-khoang-trang": "nguyen van a@example.com",
    "co-dau": "người@example.com",
    "ten-mien-hai-dau-cham": "a@example..com",
    "ten-mien-dau-gach": "a@-example.com",
    "chen-header": "a@example.com" + chr(10) + "Bcc: b@example.com",
    "hai-dia-chi": "a@example.com,b@example.com",
    "ngoac-nhon": "<a@example.com>",
    "qua-dai": "a" * 243 + "@example.com",
}
GOOD_ADDRESSES = {
    "thuong": ADDRESS,
    "dau-nhay-va-cong": "o'brien+yeu-cau@sub.example.com",
    "may-noi-bo": "quan-tri@localhost",
    "dai-nhat": "a" * 242 + "@example.com",
}
SMTP_HOST = "smtp-gia"
SMTP_USER = "thong-bao@example.com"
SMTP_PASSWORD = "mat-khau-ung-dung-gia"
SMTP_NAME = "Phòng Kỹ thuật"
INVALID_EMAILS = {
    name: ((ADDRESS, *values[1:]), message)
    for name, (values, message) in INVALID_NOTIFICATIONS.items()
    if not name.startswith("nguoi-nhan")
}
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


def websocket_status(stack, url, origin=None):
    headers = {
        "Upgrade": "websocket",
        "Connection": "Upgrade",
        "Sec-WebSocket-Key": base64.b64encode(secrets.token_bytes(16)).decode(),
        "Sec-WebSocket-Version": "13",
    }
    if origin is not None:
        headers["Origin"] = origin
    return stack.call("GET", url, headers=headers).status


def websocket_answers(stack, url):
    try:
        return websocket_status(stack, url) == 101
    except (OSError, HTTPException):
        return False


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


@pytest.fixture(scope="module")
def ipv6_centrifugo(idle_stack):
    created = idle_stack.saigonos("init", "--url", IPV6_URL)
    assert created.returncode == 0, created.stdout + created.stderr
    service = json.loads(idle_stack.compose("config", "--format", "json"))["services"]["centrifugo"]
    allowed = service["environment"]["CENTRIFUGO_CLIENT_ALLOWED_ORIGINS"]
    options = ["--rm", "--detach", "--publish", "127.0.0.1::8000"]
    options += ["--env", f"CENTRIFUGO_CLIENT_ALLOWED_ORIGINS={allowed}"]
    started = idle_stack.run_docker("run", *options, service["image"], "centrifugo")
    container = started.stdout.strip()
    try:
        address = idle_stack.run_docker("port", container, "8000/tcp").stdout.split()[0]
        url = f"http://{address}/connection/websocket"
        wait_for(lambda: websocket_answers(idle_stack, url))
        yield url
    finally:
        idle_stack.run_docker("rm", "--force", container, check=False)


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


@pytest.mark.parametrize(("origin", "status"), IPV6_ORIGINS.values(), ids=IPV6_ORIGINS.keys())
def test_centrifugo_accepts_only_page_at_ipv6_url(idle_stack, ipv6_centrifugo, origin, status):
    assert websocket_status(idle_stack, ipv6_centrifugo, origin) == status


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


class BotApi:
    def __init__(self, stack, url):
        self.stack = stack
        self.url = url

    def plan(self, *steps):
        reply = self.stack.call("POST", f"{self.url}/plan", body=list(steps))
        assert reply.status == 200, reply.body

    def requests(self):
        reply = self.stack.call("GET", f"{self.url}/requests")
        assert reply.status == 200, reply.body
        return json.loads(reply.body)

    def ready(self):
        try:
            return isinstance(self.requests(), list)
        except OSError:
            return False

    def received(self, count, timeout=20):
        wait_for(lambda: len(self.requests()) >= count, timeout)
        return self.requests()


def telegram_notify(stack, recipient, key, title=TITLE, body=None, link=None):
    return notify(stack, recipient, key, title, body, link, "true")


def deliveries_of(stack, key):
    return stack.sql(
        "SELECT status, failures, coalesce(sent_id, ''), coalesce(error, '') "
        f"FROM core.deliveries WHERE dedup_key = {literal(key)} ORDER BY id"
    )


def wait_for_status(stack, key, status, timeout=30):
    wait_for(lambda: [row[0] for row in deliveries_of(stack, key)] == [status], timeout)


def event_key(name):
    return f"{name}-{secrets.token_hex(4)}"


def test_only_core_service_reads_and_changes_state_of_deliveries(stack):
    assert stack.sql(DELIVERY_PRIVILEGES) == [
        ["core_service", "SELECT"],
        ["core_service", "UPDATE (error)"],
        ["core_service", "UPDATE (failures)"],
        ["core_service", "UPDATE (finished_at)"],
        ["core_service", "UPDATE (next_attempt_at)"],
        ["core_service", "UPDATE (sent_id)"],
        ["core_service", "UPDATE (status)"],
    ]


def test_telegram_message_is_skipped_while_telegram_is_not_configured(stack, user):
    key = event_key("khong-cau-hinh")

    telegram_notify(stack, user.id, key)
    wait_for_status(stack, key, "skipped", timeout=15)
    doctor = stack.saigonos("doctor")

    assert deliveries_of(stack, key) == [["skipped", "0", "", "Chưa cấu hình Telegram"]]
    assert "Chưa cấu hình Telegram nên tin Telegram" in stack.logs("core")
    assert doctor.returncode == 0, doctor.stdout
    assert [item["title"] for item in notifications_of(stack, user)] == [TITLE]


@pytest.fixture(scope="module")
def bot_api(stack):
    name = f"{stack.home.name}-telegram"
    script = Path(__file__).with_name("fake_telegram.py")
    image = stack.inspect(stack.container("core"), "{{.Config.Image}}")
    options = ["--detach", "--rm", "--name", name, "--network", stack.network("default")]
    options += ["--network-alias", BOT_API, "--publish", "127.0.0.1::8081"]
    options += ["--volume", f"{script}:/fake_telegram.py:ro"]
    stack.run_docker("run", *options, image, "python", "/fake_telegram.py", TELEGRAM_TOKEN)
    try:
        address = stack.run_docker("port", name, "8081").stdout.split()[0]
        api = BotApi(stack, f"http://{address}")
        wait_for(api.ready, timeout=30)
        settings = {
            "TELEGRAM_API_URL": f"http://{BOT_API}:8081",
            "TELEGRAM_BOT_TOKEN": TELEGRAM_TOKEN,
            "TELEGRAM_CHAT_ID": str(TELEGRAM_CHAT),
            "TELEGRAM_TOPIC_ID": str(TELEGRAM_TOPIC),
        }
        with (stack.home / ".env").open("a", encoding="utf-8") as env:
            env.writelines(f"{key}={value}\n" for key, value in settings.items())
        started = stack.up()
        assert started.returncode == 0, started.stderr
        yield api
    finally:
        stack.run_docker("rm", "--force", name, check=False)


@pytest.fixture
def bot(bot_api):
    bot_api.plan()
    return bot_api


def test_notification_reaches_telegram_group_once_within_two_seconds(stack, user, bot):
    key = event_key("da-xu-ly")
    title = "Phòng I.102 mất mạng 🔌"
    delays = []

    for count, name in enumerate([event_key("truoc"), key], start=1):
        started = time.time()
        telegram_notify(stack, user.id, name, title, "Máy 12 đã được thay cáp", "/yeu-cau/YC-001")
        request = bot.received(count)[-1]
        delays.append(request["at"] - started)
        wait_for_status(stack, name, "sent")
    time.sleep(2)

    assert all(delay < 2 for delay in delays), delays
    assert request["path"] == f"/bot{TELEGRAM_TOKEN}/sendMessage"
    assert request["body"] == {
        "chat_id": TELEGRAM_CHAT,
        "message_thread_id": TELEGRAM_TOPIC,
        "text": f"{title}\nMáy 12 đã được thay cáp\n{stack.url}/yeu-cau/YC-001",
        "entities": [{"type": "bold", "offset": 0, "length": 23}],
        "link_preview_options": {"is_disabled": True},
    }
    assert len(bot.requests()) == 2
    assert deliveries_of(stack, key) == [["sent", "0", str(request["message_id"]), ""]]


def test_server_error_is_retried_after_five_seconds_and_group_gets_one_message(stack, user, bot):
    key = event_key("loi-500")
    bot.plan({"status": 500, "description": "Internal Server Error"})

    telegram_notify(stack, user.id, key)
    first, second = bot.received(2)
    wait_for_status(stack, key, "sent")
    time.sleep(2)

    assert (first["reply"], second["reply"]) == (500, 200)
    assert 5 <= second["at"] - first["at"] < 7
    assert len(bot.requests()) == 2
    assert deliveries_of(stack, key) == [["sent", "1", str(second["message_id"]), ""]]
    assert (
        "Telegram trả về mã 500: Internal Server Error. Tin sẽ được gửi lại sau 5 giây"
        in stack.logs("core")
    )


def test_rate_limit_waits_exactly_retry_after_without_counting_failure(stack, user, bot):
    key = event_key("qua-tai")
    bot.plan({"status": 429, "description": "Too Many Requests: retry after 3", "retry_after": 3})

    telegram_notify(stack, user.id, key)
    first, second = bot.received(2)
    wait_for_status(stack, key, "sent")

    assert (first["reply"], second["reply"]) == (429, 200)
    assert 3 <= second["at"] - first["at"] < 4.5
    assert deliveries_of(stack, key) == [["sent", "0", str(second["message_id"]), ""]]
    assert "Telegram yêu cầu chờ 3 giây trước khi gửi tiếp" in stack.logs("core")


def test_message_refused_by_telegram_fails_at_once_and_is_logged(stack, user, bot):
    key = event_key("tu-choi")
    bot.plan({"status": 400, "description": "Bad Request: chat not found"})

    telegram_notify(stack, user.id, key)
    wait_for_status(stack, key, "failed")
    time.sleep(2)

    reason = "Telegram trả về mã 400: Bad Request: chat not found"
    assert len(bot.requests()) == 1
    assert deliveries_of(stack, key) == [["failed", "1", "", reason]]
    assert f"sau 1 lần thử: {reason}" in stack.logs("core")


def test_lost_reply_is_marked_unknown_and_not_sent_again(stack, user, bot):
    key = event_key("mat-ket-noi")
    bot.plan({"drop": True})

    telegram_notify(stack, user.id, key)
    wait_for_status(stack, key, "unknown")
    time.sleep(2)

    reason = "Mất kết nối khi chờ Telegram trả lời: Remote end closed connection without response"
    assert len(bot.requests()) == 1
    assert deliveries_of(stack, key) == [["unknown", "0", "", reason]]
    assert "Tin không được gửi lại để tránh gửi trùng" in stack.logs("core")


def test_message_being_sent_when_core_dies_is_not_sent_again(stack, user, bot):
    key = event_key("core-chet")
    bot.plan({"delay": 30})

    telegram_notify(stack, user.id, key)
    bot.received(1)
    sending = deliveries_of(stack, key)
    container = stack.container("core")
    restarts = int(stack.inspect(container, "{{.RestartCount}}"))
    stack.kill(container)
    wait_for(lambda: stack.inspect(container, STATE) == f"{restarts + 1} healthy", 120)
    stack.wait_until_answers("/core/health")
    wait_for_status(stack, key, "unknown")
    time.sleep(2)

    assert [row[0] for row in sending] == ["sending"]
    assert len(bot.requests()) == 1
    assert deliveries_of(stack, key) == [["unknown", "0", "", STOPPED_WHILE_SENDING]]
    assert "đang được gửi khi service core dừng" in stack.logs("core")


def test_event_told_to_many_recipients_gives_one_telegram_message(stack, user, bot):
    other = stack.new_user()
    key = event_key("nhieu-nguoi")

    for recipient in (user, other):
        telegram_notify(stack, recipient.id, key)
    marker = event_key("moc")
    telegram_notify(stack, user.id, marker, "Tin mốc")
    requests = bot.received(2)
    wait_for_status(stack, marker, "sent")

    assert [request["body"]["text"] for request in requests] == [TITLE, "Tin mốc"]
    assert len(deliveries_of(stack, key)) == 1
    assert [len(notifications_of(stack, person)) for person in (user, other)] == [2, 1]


def test_notification_without_telegram_and_rolled_back_one_send_nothing(stack, user, bot):
    plain, undone = event_key("khong-telegram"), event_key("huy")

    notify(stack, user.id, plain, "Chỉ trong ứng dụng")
    failed = psql(
        stack,
        f"SET ROLE workflow; SELECT core.notify({arguments_of([user.id, undone, TITLE])}, "
        "telegram => true); SELECT 1 / 0",
    )
    marker = event_key("moc")
    telegram_notify(stack, user.id, marker, "Tin mốc")
    requests = bot.received(1)
    wait_for_status(stack, marker, "sent")
    time.sleep(1)

    assert "division by zero" in failed.stderr
    assert [request["body"]["text"] for request in bot.requests()] == ["Tin mốc"]
    assert len(requests) == 1
    assert deliveries_of(stack, plain) == deliveries_of(stack, undone) == []


def send_email(stack, *values):
    return stack.sql(f"SET ROLE workflow; SELECT core.send_email({arguments_of(values)})")[-1][0]


def refused_email(stack, values):
    return psql(stack, f"SET ROLE workflow; SELECT core.send_email({arguments_of(values)})")


def emails_of(stack, key):
    return stack.sql(
        "SELECT id, address, title, coalesce(body, ''), coalesce(link, '') FROM core.deliveries "
        f"WHERE channel = 'email' AND dedup_key = {literal(key)} ORDER BY id"
    )


@pytest.mark.parametrize("address", BAD_ADDRESSES.values(), ids=BAD_ADDRESSES.keys())
def test_send_email_refuses_invalid_address(stack, address):
    refused = refused_email(stack, (address, KEY, TITLE))

    shown = "NULL" if address is None else quoted(address)
    assert refused.returncode != 0
    assert f"ERROR:  Địa chỉ email {shown} không hợp lệ\n" in refused.stderr


@pytest.mark.parametrize("address", GOOD_ADDRESSES.values(), ids=GOOD_ADDRESSES.keys())
def test_send_email_accepts_valid_address(stack, address):
    key = event_key("dia-chi")

    delivery_id = send_email(stack, address, key, TITLE)

    assert emails_of(stack, key) == [[delivery_id, address, TITLE, "", ""]]


@pytest.mark.parametrize(("values", "message"), INVALID_EMAILS.values(), ids=INVALID_EMAILS.keys())
def test_send_email_refuses_invalid_values_like_notify(stack, values, message):
    refused = refused_email(stack, values)

    assert refused.returncode != 0
    assert f"ERROR:  {message}\n" in refused.stderr


@pytest.mark.parametrize("link", BAD_LINKS.values(), ids=BAD_LINKS.keys())
def test_send_email_refuses_link_outside_system(stack, link):
    refused = refused_email(stack, (ADDRESS, KEY, TITLE, None, link))

    assert refused.returncode != 0
    assert f"ERROR:  Đường dẫn {quoted(link)} không hợp lệ\n" in refused.stderr


def test_email_is_queued_once_for_each_address_and_key(stack):
    key = event_key("da-nhan")
    title, body, link = "Đã nhận yêu cầu YC-001", "Cảm ơn bạn đã gửi yêu cầu", "/tra-cuu/YC-001"

    first = send_email(stack, ADDRESS, key, title, body, link)
    again = send_email(stack, ADDRESS, key, "Tiêu đề khác")
    other = send_email(stack, OTHER_ADDRESS, key, title)

    assert first == again != other
    assert emails_of(stack, key) == [
        [first, ADDRESS, title, body, link],
        [other, OTHER_ADDRESS, title, "", ""],
    ]


def test_email_and_telegram_message_with_same_key_are_both_queued(stack, user):
    key = event_key("hai-kenh")

    telegram_notify(stack, user.id, key)
    send_email(stack, ADDRESS, key, TITLE)
    channels = stack.sql(
        f"SELECT channel FROM core.deliveries WHERE dedup_key = {literal(key)} ORDER BY id"
    )

    assert channels == [["telegram"], ["email"]]


def test_rolled_back_email_is_not_queued(stack):
    key = event_key("huy")

    failed = psql(
        stack,
        f"SET ROLE workflow; SELECT core.send_email({arguments_of([ADDRESS, key, TITLE])}); "
        "SELECT 1 / 0",
    )

    assert "division by zero" in failed.stderr
    assert emails_of(stack, key) == []


def test_only_role_workflow_can_send_email(stack):
    roles = ", ".join(literal(role) for role in [*PUBLISHERS, "workflow"])
    query = (
        f"SELECT role, has_function_privilege(role, {literal(SEND_EMAIL)}, 'EXECUTE'), "
        f"has_function_privilege(role, {literal(CHECK_MESSAGE)}, 'EXECUTE') "
        f"FROM unnest(ARRAY[{roles}]) AS role"
    )

    allowed = {role: tuple(rights) for role, *rights in stack.sql(query)}
    refused = psql(
        stack,
        f"SET ROLE authenticated; SELECT core.send_email({arguments_of([ADDRESS, KEY, TITLE])})",
    )

    assert allowed == {**dict.fromkeys(PUBLISHERS, ("f", "f")), "workflow": ("t", "f")}
    assert "permission denied for function send_email" in refused.stderr


@pytest.mark.parametrize(("channel", "address"), [("email", None), ("telegram", ADDRESS)])
def test_only_email_delivery_has_address(stack, channel, address):
    refused = psql(
        stack,
        "INSERT INTO core.deliveries (channel, dedup_key, title, address) "
        f"VALUES ({literal(channel)}, {literal(event_key('dia-chi'))}, 't', {literal(address)})",
    )

    assert 'violates check constraint "deliveries_address"' in refused.stderr


def test_email_is_skipped_while_smtp_is_not_configured(stack):
    key = event_key("khong-cau-hinh-smtp")

    send_email(stack, ADDRESS, key, TITLE)
    wait_for_status(stack, key, "skipped", timeout=15)

    assert deliveries_of(stack, key) == [["skipped", "0", "", "Chưa cấu hình SMTP"]]
    assert "Chưa cấu hình SMTP nên email" in stack.logs("core")


class MailServer:
    def __init__(self, stack, url):
        self.stack = stack
        self.url = url

    def plan(self, *steps):
        reply = self.stack.call("POST", f"{self.url}/plan", body=list(steps))
        assert reply.status == 200, reply.body

    def sessions(self):
        reply = self.stack.call("GET", f"{self.url}/sessions")
        assert reply.status == 200, reply.body
        return json.loads(reply.body)

    def ready(self):
        try:
            return isinstance(self.sessions(), list)
        except OSError:
            return False

    def delivered(self):
        return [session for session in self.sessions() if session["content"] is not None]

    def received(self, count, timeout=20):
        wait_for(lambda: len(self.delivered()) >= count, timeout)
        return self.delivered()


def commands_of(session):
    return [command for command, _ in session["commands"]]


@pytest.fixture(scope="module")
def mail_server(stack):
    folder = stack.home / SMTP_HOST
    folder.mkdir(mode=0o755, exist_ok=True)
    fake_smtp.make_certificates(folder, SMTP_HOST)
    name = f"{stack.home.name}-smtp"
    script = Path(__file__).with_name("fake_smtp.py")
    image = stack.inspect(stack.container("core"), "{{.Config.Image}}")
    options = ["--detach", "--rm", "--name", name, "--network", stack.network("default")]
    options += ["--network-alias", SMTP_HOST, "--publish", "127.0.0.1::8025"]
    options += ["--volume", f"{script}:/fake_smtp.py:ro", "--volume", f"{folder}:/smtp-gia:ro"]
    arguments = [SMTP_USER, SMTP_PASSWORD, "/smtp-gia/cert.pem", "/smtp-gia/key.pem"]
    stack.run_docker("run", *options, image, "python", "/fake_smtp.py", *arguments)
    override = stack.home / "compose.override.yaml"
    try:
        address = stack.run_docker("port", name, "8025").stdout.split()[0]
        server = MailServer(stack, f"http://{address}")
        wait_for(server.ready, timeout=30)
        override.write_text(
            "services:\n  core:\n    environment:\n      SSL_CERT_FILE: /smtp-gia/ca.pem\n"
            f"    volumes:\n      - ./{SMTP_HOST}/ca.pem:/smtp-gia/ca.pem:ro\n",
            encoding="utf-8",
        )
        settings = {
            "SMTP_HOST": SMTP_HOST,
            "SMTP_PORT": str(fake_smtp.SMTP_PORT),
            "SMTP_USERNAME": SMTP_USER,
            "SMTP_PASSWORD": SMTP_PASSWORD,
            "SMTP_FROM": SMTP_USER,
            "SMTP_FROM_NAME": SMTP_NAME,
        }
        with (stack.home / ".env").open("a", encoding="utf-8") as env:
            env.writelines(f"{key}={value}\n" for key, value in settings.items())
        started = stack.up()
        assert started.returncode == 0, started.stderr
        yield server
    finally:
        override.unlink(missing_ok=True)
        stack.run_docker("rm", "--force", name, check=False)


@pytest.fixture
def mail(mail_server):
    mail_server.plan()
    return mail_server


def test_email_reaches_server_through_starttls_within_two_seconds(stack, mail):
    title, body, link = "Đã nhận yêu cầu YC-001", "Cảm ơn bạn đã gửi yêu cầu", "/tra-cuu/YC-001"
    delays = []

    for count, key in enumerate([event_key("truoc"), event_key("da-nhan")], start=1):
        started = time.time()
        send_email(stack, ADDRESS, key, title, body, link)
        session = mail.received(count)[-1]
        delays.append(session["at"] - started)
        wait_for_status(stack, key, "sent")
    time.sleep(2)

    sent = message_from_string(session["content"], policy=default)
    [sender] = sent["From"].addresses
    assert all(delay < 2 for delay in delays), delays
    assert [command.split(" ")[0] for command in commands_of(session)] == [
        "EHLO",
        "STARTTLS",
        "EHLO",
        "AUTH",
        "MAIL",
        "RCPT",
        "DATA",
        "QUIT",
    ]
    assert [secure for _, secure in session["commands"]][3:] == [True] * 5
    assert session["user"] == SMTP_USER
    assert commands_of(session)[4:6] == [f"MAIL FROM:<{SMTP_USER}>", f"RCPT TO:<{ADDRESS}>"]
    assert (sender.display_name, sender.addr_spec) == (SMTP_NAME, SMTP_USER)
    assert (str(sent["To"]), str(sent["Subject"])) == (ADDRESS, title)
    assert sent.get_content().splitlines() == [body, "", f"{stack.url}{link}"]
    assert deliveries_of(stack, key) == [["sent", "0", sent["Message-ID"], ""]]
    assert len(mail.sessions()) == 2


def test_temporary_error_is_retried_after_five_seconds_and_recipient_gets_one_email(stack, mail):
    key = event_key("loi-451")
    mail.plan({"rcpt": "451 4.3.0 Try again later"})

    send_email(stack, ADDRESS, key, TITLE)
    wait_for_status(stack, key, "sent")
    time.sleep(2)

    first, second = mail.sessions()
    reason = "Máy chủ SMTP trả về mã 451 cho lệnh RCPT TO: 4.3.0 Try again later"
    assert (first["content"], second["content"] is not None) == (None, True)
    assert 5 <= second["started"] - first["started"] < 7
    assert deliveries_of(stack, key)[0][:2] == ["sent", "1"]
    assert f"{reason}. Email sẽ được gửi lại sau 5 giây" in stack.logs("core")


def test_email_refused_by_server_fails_at_once_and_is_logged(stack, mail):
    key = event_key("khong-co-hop-thu")
    mail.plan({"rcpt": "550 5.1.1 The email account does not exist"})

    send_email(stack, ADDRESS, key, TITLE)
    wait_for_status(stack, key, "failed")
    time.sleep(2)

    reason = "Máy chủ SMTP trả về mã 550 cho lệnh RCPT TO: 5.1.1 The email account does not exist"
    assert len(mail.sessions()) == 1
    assert deliveries_of(stack, key) == [["failed", "1", "", reason]]
    assert f"sau 1 lần thử: {reason}" in stack.logs("core")


def test_lost_reply_after_content_is_marked_unknown_and_not_sent_again(stack, mail):
    key = event_key("mat-ket-noi-smtp")
    mail.plan({"content": "drop"})

    send_email(stack, ADDRESS, key, TITLE)
    wait_for_status(stack, key, "unknown")
    time.sleep(2)

    reason = "Mất kết nối khi chờ máy chủ SMTP trả lời: Connection unexpectedly closed"
    [session] = mail.sessions()
    assert session["content"] is not None
    assert deliveries_of(stack, key) == [["unknown", "0", "", reason]]
    assert "Email không được gửi lại để tránh gửi trùng" in stack.logs("core")


def test_server_without_starttls_never_gets_password(stack, mail):
    key = event_key("khong-starttls")
    mail.plan({"no_starttls": True})

    send_email(stack, ADDRESS, key, TITLE)
    wait_for_status(stack, key, "failed")

    [session] = mail.sessions()
    assert [command.split(" ")[0] for command in commands_of(session)] == ["EHLO"]
    assert deliveries_of(stack, key) == [["failed", "1", "", "Máy chủ SMTP không hỗ trợ STARTTLS"]]


def test_each_address_gets_one_email_for_each_key(stack, mail):
    key = event_key("hai-nguoi")

    for address in (ADDRESS, ADDRESS, OTHER_ADDRESS):
        send_email(stack, address, key, TITLE)
    marker = event_key("moc")
    send_email(stack, ADDRESS, marker, "Email mốc")
    sessions = mail.received(3)
    wait_for_status(stack, marker, "sent")
    time.sleep(1)

    recipients = [commands_of(session)[5] for session in mail.sessions()]
    assert recipients == [f"RCPT TO:<{address}>" for address in (ADDRESS, OTHER_ADDRESS, ADDRESS)]
    assert str(message_from_string(sessions[-1]["content"], policy=default)["Subject"]) == (
        "Email mốc"
    )
