# SPDX-License-Identifier: Apache-2.0
import base64
import hashlib
import hmac
import json
import re
import secrets
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

pytestmark = pytest.mark.integration

LOGIN_NEEDED = {"detail": "Lời gọi này cần access token của người dùng đã đăng nhập"}
INVALID = {"detail": "Access token không hợp lệ"}
REALM_PATH = "/auth/realms/saigonos/protocol/openid-connect"
KEYS_COOLDOWN = 1
SHORT_LIFESPAN = 5
PIN = r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)"
ALLOWED = "chỉ dành cho người đã đăng nhập"
CALL = """
import json, sys, urllib.error, urllib.request
request = urllib.request.Request(sys.argv[1], headers=json.loads(sys.argv[2]))
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        status, body = response.status, response.read()
except urllib.error.HTTPError as error:
    status, body = error.code, error.read()
print(json.dumps({"status": status, "body": body.decode()}))
"""
CONNECT = "import socket, sys; socket.create_connection((sys.argv[1], int(sys.argv[2])), 3)"
NESTED = """\
CREATE FUNCTION api.{name}_closed() RETURNS text
LANGUAGE sql STABLE
RETURN '{allowed}';
GRANT EXECUTE ON FUNCTION api.{name}_closed TO authenticated;
CREATE FUNCTION api.{name}_nested() RETURNS text
LANGUAGE plpgsql STABLE
AS $$ BEGIN RETURN api.{name}_closed(); END $$;
GRANT EXECUTE ON FUNCTION api.{name}_nested TO anon, authenticated;
"""
PLANS = """
import asyncio, json, sys
from asyncpg import InsufficientPrivilegeError
from saigonos_core.callers import caller_of
from saigonos_core.database import Database

async def main(name):
    database = Database(max_size=1)
    await database.open()
    user = caller_of({"sub": "nguoi-dung", "realm_access": {"roles": ["authenticated"]}})
    results = []
    for caller in [user, user, user, caller_of(None)]:
        try:
            async with database.session(caller) as connection:
                results.append(await connection.fetchval(f"SELECT api.{name}_nested()"))
        except InsufficientPrivilegeError as error:
            results.append(error.sqlstate)
    await database.close()
    print(json.dumps(results, ensure_ascii=False))

asyncio.run(main(sys.argv[1]))
"""


def segment(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def decode(part):
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def header_of(token):
    return decode(token.split(".")[0])


def claims_of(token):
    return decode(token.split(".")[1])


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def wait_for(condition, timeout=60):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "Hết thời gian chờ"
        time.sleep(0.5)


def direct(stack, path, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    url = f"http://127.0.0.1:8000{path}"
    result = stack.exec("core", "python", "-c", CALL, url, json.dumps(headers))
    assert result.returncode == 0, result.stderr
    reply = json.loads(result.stdout)
    return reply["status"], json.loads(reply["body"])


def core(stack, path, token=None, headers=None):
    return stack.call("GET", f"{stack.url}/core{path}", token=token, headers=headers)


def add_client(stack, client_id, attributes):
    client = {
        "clientId": client_id,
        "publicClient": True,
        "directAccessGrantsEnabled": True,
        "standardFlowEnabled": False,
        "attributes": attributes,
    }
    reply = stack.admin("POST", "/clients", client)
    assert reply.status == 201, reply.body


def grant(stack, user, client="kiem-thu", scope="profile"):
    form = {
        "grant_type": "password",
        "client_id": client,
        "username": user.name,
        "password": user.password,
        "scope": scope,
    }
    reply = stack.call("POST", f"{stack.url}{REALM_PATH}/token", form=form)
    assert reply.status == 200, reply.body
    return json.loads(reply.body)


def forged_tokens(stack, user):
    token = stack.token(user)
    kid = header_of(token)["kid"]
    keys = json.loads(stack.call("GET", f"{stack.url}{REALM_PATH}/certs").body)["keys"]
    public_key = RSAAlgorithm.from_jwk(next(key for key in keys if key["kid"] == kid))
    pem = public_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    content = f"{segment(json.dumps({'alg': 'HS256', 'typ': 'JWT', 'kid': kid}).encode())}."
    content += token.split(".")[1]
    stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return stack.forged_tokens(user) | {
        "ký bằng khóa khác": jwt.encode(
            claims_of(token), stranger, algorithm="RS256", headers={"kid": kid}
        ),
        "ký HS256 bằng khóa công khai": (
            f"{content}.{segment(hmac.new(pem, content.encode(), hashlib.sha256).digest())}"
        ),
    }


@pytest.fixture(scope="module")
def nested(stack):
    name = f"plan_{secrets.token_hex(4)}"
    stack.add_migration(f"9008_{name}.sql", NESTED.format(name=name, allowed=ALLOWED))
    started = stack.saigonos("up")
    assert started.returncode == 0, started.stderr
    return name


def test_doctor_reports_core_service(stack):
    result = stack.saigonos("doctor")

    assert result.returncode == 0, result.stdout
    assert re.search(r"BÌNH THƯỜNG\s+core\s+đang chạy", result.stdout)
    assert re.search(r"BÌNH THƯỜNG\s+Core API\s+service core trả lời", result.stdout)


def test_core_image_is_built_on_host_with_locked_libraries(stack):
    service = json.loads(stack.compose("config", "--format", "json"))["services"]["core"]
    lock = (stack.home / "core" / "requirements.txt").read_text(encoding="utf-8")
    frozen = stack.exec("core", "pip", "freeze").stdout

    locked = {normalize(name): version for name, version in re.findall(PIN, lock, re.M)}
    installed = {normalize(name): version for name, version in re.findall(PIN, frozen, re.M)}

    assert service["build"]["context"] == str(stack.home / "core")
    assert service["pull_policy"] == "build"
    assert installed == locked


def test_core_runs_as_unprivileged_user_without_port_on_host(stack):
    service = json.loads(stack.compose("config", "--format", "json"))["services"]["core"]

    assert stack.exec("core", "id", "-un").stdout.strip() == "nobody"
    assert "ports" not in service


def test_core_connects_to_database_with_own_role(stack):
    sessions = (
        "SELECT DISTINCT usename FROM pg_stat_activity WHERE application_name = 'saigonos-core'"
    )
    attributes = (
        "SELECT rolinherit, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'core_service'"
    )

    assert stack.sql(sessions) == [["core_service"]]
    assert stack.sql(attributes) == [["f", "f", "f"]]


@pytest.mark.parametrize(("host", "port"), [("seaweedfs", 8333), ("clamav", 3310)])
def test_core_reaches_storage_and_scanner(stack, host, port):
    assert stack.exec("core", "python", "-c", CONNECT, host, str(port)).returncode == 0


def test_core_answers_through_gateway_without_token(stack):
    reply = core(stack, "/health")

    assert (reply.status, json.loads(reply.body)) == (200, {"status": "ok"})


def test_core_needs_token_of_logged_in_user(stack):
    roleless = stack.new_user()
    stack.revoke_roles(roleless)
    token = stack.token(roleless)

    without = core(stack, "/me")
    with_roleless = core(stack, "/me", token)

    assert (without.status, json.loads(without.body)) == (401, LOGIN_NEEDED)
    assert (with_roleless.status, json.loads(with_roleless.body)) == (401, LOGIN_NEEDED)
    assert direct(stack, "/me", token) == (401, LOGIN_NEEDED)


def test_core_queries_database_as_caller(stack):
    user = stack.new_user(unit="khoa-a")

    reply = core(stack, "/me", stack.token(user))

    assert reply.status == 200
    assert json.loads(reply.body) == {"uid": user.id, "unit": "khoa-a", "role": "authenticated"}


def test_gateway_rejects_forged_token_before_core(stack):
    forged = forged_tokens(stack, stack.new_user())

    replies = {name: core(stack, "/me", token) for name, token in forged.items()}

    assert {name: reply.status for name, reply in replies.items()} == dict.fromkeys(forged, 401)
    assert {reply.headers.get_content_type() for reply in replies.values()} == {"text/html"}


def test_core_rejects_forged_token_called_directly(stack):
    user = stack.new_user()
    id_token = grant(stack, user, scope="openid profile")["id_token"]
    forged = forged_tokens(stack, user) | {"ID token": id_token}

    replies = {name: direct(stack, "/me", token) for name, token in forged.items()}

    assert direct(stack, "/me", stack.token(user))[0] == 200
    assert replies == dict.fromkeys(forged, (401, INVALID))


def test_core_rejects_expired_token_by_itself(stack):
    user = stack.new_user()
    add_client(stack, "kiem-thu-ngan", {"access.token.lifespan": str(SHORT_LIFESPAN)})
    token = grant(stack, user, client="kiem-thu-ngan")["access_token"]
    claims = claims_of(token)

    fresh = direct(stack, "/me", token)[0]
    time.sleep(max(0, claims["exp"] - time.time()) + 1)

    assert claims["exp"] - claims["iat"] == SHORT_LIFESPAN
    assert fresh == 200
    assert direct(stack, "/me", token) == (401, INVALID)
    assert core(stack, "/me", token).status == 401


def test_anon_cannot_reuse_query_plan_made_for_user(stack, nested):
    result = stack.exec("core", "python", "-c", PLANS, nested)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [ALLOWED] * 3 + ["42501"]


def test_core_api_document_gives_saigonos_url(stack):
    reply = core(stack, "/openapi.json")
    document = json.loads(reply.body)

    assert reply.status == 200
    assert document["servers"] == [{"url": f"{stack.url}/core"}]
    assert {"/health", "/me"} <= set(document["paths"])


def test_rate_limit_counts_calls_to_core(stack):
    def remaining():
        reply = core(stack, "/health", headers={"X-Forwarded-For": "203.0.113.10"})
        assert reply.status == 200, reply.body
        return int(reply.headers["X-RateLimit-Remaining"])

    assert [remaining(), remaining()] == [299, 298]


def test_core_accepts_token_signed_with_new_key(stack):
    user = stack.new_user()
    old = stack.token(user)
    assert direct(stack, "/me", old)[0] == 200
    time.sleep(KEYS_COOLDOWN + 0.1)

    stack.rotate_keys()
    token = stack.token(user)

    assert header_of(token)["kid"] != header_of(old)["kid"]
    assert direct(stack, "/me", token)[0] == 200
    assert core(stack, "/me", token).status == 200


def test_killed_core_restarts_by_itself(stack):
    container = stack.container("core")
    restarts = int(stack.inspect(container, "{{.RestartCount}}"))
    state = "{{.RestartCount}} {{.State.Health.Status}}"

    stack.kill(container)

    wait_for(lambda: stack.inspect(container, state) == f"{restarts + 1} healthy", 120)
    assert core(stack, "/health").status == 200


def test_core_reconnects_after_database_restart(stack):
    user = stack.new_user()

    result = stack.compose_result("restart", "postgres")
    wait_for(lambda: core(stack, "/health").status == 200)
    wait_for(lambda: stack.login(user).status == 200)

    assert result.returncode == 0, result.stderr
    assert core(stack, "/me", stack.token(user)).status == 200
