# SPDX-License-Identifier: Apache-2.0
import base64
import hashlib
import json
import secrets
import ssl
from http.client import HTTPConnection, HTTPException, HTTPMessage, HTTPSConnection
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import parse_qs, urlsplit

from saigonos import compose

REALM_PATH = "/auth/realms/saigonos"
TOKEN_PATH = f"{REALM_PATH}/protocol/openid-connect/token"
DISCOVERY_PATH = f"{REALM_PATH}/.well-known/openid-configuration"
API_PATH = "/api/"
CORE_HEALTH_PATH = "/core/health"
CORE_USER_PATH = "/core/me"
AUTHORIZATION_PATH = f"{REALM_PATH}/protocol/openid-connect/auth"
OPERATON_LOGIN_PATH = "/operaton/oauth2/authorization/operaton"
OPERATON_CALLBACK_PATH = "/operaton/login/oauth2/code/operaton"
OPERATON_REST_PATH = "/operaton/engine-rest/version"
REALTIME_PATH = "/realtime/connection/websocket"
REALTIME_API_PATH = "/realtime/api"
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
INVALID_AUTHORIZATION = {"Authorization": "Bearer khong-hop-le"}
CADDY = "caddy"
CADDY_ROOT_CERTIFICATE = "/data/caddy/pki/authorities/local/root.crt"
TIMEOUT = 5
STOPPED_STATES = {
    "created": "đã tạo nhưng chưa chạy",
    "restarting": "đang khởi động lại",
    "paused": "đang tạm dừng",
}


class Check(NamedTuple):
    name: str
    ok: bool
    detail: str


class Reply(NamedTuple):
    status: int
    body: bytes
    headers: HTTPMessage


def service_state(service: dict[str, Any], container: dict[str, Any] | None) -> tuple[bool, str]:
    if container is None:
        return False, "chưa được tạo"
    state = container.get("State")
    health = container.get("Health")
    exit_code = container.get("ExitCode")
    if service.get("restart", "no") == "no":
        if state == "exited":
            done = exit_code == 0
            return done, "đã chạy xong" if done else f"kết thúc với mã lỗi {exit_code}"
        return False, "chưa chạy xong"
    if state == "exited":
        return False, f"đã dừng với mã thoát {exit_code}"
    if state != "running":
        return False, STOPPED_STATES.get(state, f"không chạy, trạng thái {state}")
    if health == "starting":
        return False, "đang khởi động"
    if health == "unhealthy":
        return False, "healthcheck báo lỗi"
    return True, "đang chạy"


def service_checks(home: Path) -> list[Check]:
    services = json.loads(compose.capture(home, "config", "--format", "json"))["services"]
    output = compose.capture(home, "ps", "--all", "--format", "json").strip()
    if output.startswith("["):
        rows = json.loads(output)
    else:
        rows = [json.loads(line) for line in output.splitlines()]
    containers = {row["Service"]: row for row in rows}
    return [
        Check(name, *service_state(service, containers.get(name)))
        for name, service in services.items()
    ]


def caddy_root_certificate(home: Path) -> str | None:
    try:
        return compose.capture(home, "exec", "-T", CADDY, "cat", CADDY_ROOT_CERTIFICATE) or None
    except compose.ComposeError:
        return None


def fetch(url: str, certificate: str | None = None, headers: dict[str, str] | None = None) -> Reply:
    parts = urlsplit(url)
    connection: HTTPConnection
    if parts.scheme == "https":
        context = ssl.create_default_context()
        if certificate:
            context.load_verify_locations(cadata=certificate)
        connection = HTTPSConnection(parts.netloc, timeout=TIMEOUT, context=context)
    else:
        connection = HTTPConnection(parts.netloc, timeout=TIMEOUT)
    try:
        connection.request("GET", parts.path, headers=headers or {})
        response = connection.getresponse()
        return Reply(response.status, response.read(), response.headers)
    finally:
        connection.close()


def login_state(url: str, status: int, body: bytes) -> tuple[bool, str]:
    if status != 200:
        return False, f"Keycloak trả về mã {status}"
    try:
        discovery = json.loads(body)
        issuer, token_endpoint = discovery.get("issuer"), discovery.get("token_endpoint")
    except (ValueError, AttributeError):
        issuer = token_endpoint = None
    if issuer != f"{url}{REALM_PATH}":
        return False, f"Keycloak dùng địa chỉ {issuer}, khác với SAIGONOS_URL trong file .env"
    if token_endpoint != f"{url}{TOKEN_PATH}":
        seen = str(token_endpoint).removesuffix(TOKEN_PATH)
        return False, (
            f"Keycloak nhận lời gọi qua địa chỉ {seen}, khác với SAIGONOS_URL trong file .env. "
            "Hãy kiểm tra header X-Forwarded-Proto, X-Forwarded-Host và X-Forwarded-Port "
            "của reverse proxy"
        )
    return True, f"Keycloak trả lời tại {url}/auth"


def api_state(anonymous: int, invalid: int) -> tuple[bool, str]:
    if anonymous != 200:
        return False, f"lời gọi không có access token nhận mã {anonymous}, đúng ra là 200"
    if invalid != 401:
        return False, f"lời gọi có access token không hợp lệ nhận mã {invalid}, đúng ra là 401"
    return True, "PostgREST trả lời, access token không hợp lệ bị từ chối"


def core_state(health: int, invalid: int) -> tuple[bool, str]:
    if health != 200:
        return False, f"lời gọi {CORE_HEALTH_PATH} nhận mã {health}, đúng ra là 200"
    if invalid != 401:
        return False, f"lời gọi có access token không hợp lệ nhận mã {invalid}, đúng ra là 401"
    return True, "service core trả lời, access token không hợp lệ bị từ chối"


def operaton_state(url: str, status: int, location: str | None, rest: int) -> tuple[bool, str]:
    if status != 302:
        return False, f"lời gọi {OPERATON_LOGIN_PATH} nhận mã {status}, đúng ra là 302"
    if not location:
        return False, "Operaton không cho biết địa chỉ của trang đăng nhập"
    parts = urlsplit(location)
    target = f"{parts.scheme}://{parts.netloc}{parts.path}"
    if target != f"{url}{AUTHORIZATION_PATH}":
        return (
            False,
            f"Operaton chuyển người dùng tới {target}, không phải trang đăng nhập của Keycloak",
        )
    redirect = parse_qs(parts.query).get("redirect_uri", [""])[0]
    if redirect != f"{url}{OPERATON_CALLBACK_PATH}":
        seen = redirect.removesuffix(OPERATON_CALLBACK_PATH)
        return False, (
            f"Operaton nhận lời gọi qua địa chỉ {seen}, khác với SAIGONOS_URL trong file .env. "
            "Hãy kiểm tra header X-Forwarded-Proto, X-Forwarded-Host và X-Forwarded-Port "
            "của reverse proxy"
        )
    if rest != 404:
        return False, f"REST của Operaton nhận mã {rest} qua API Gateway, đúng ra là 404"
    return True, "Operaton chuyển tới trang đăng nhập, REST của Operaton bị chặn"


def realtime_state(url: str, status: int, accepted: bool, api: int) -> tuple[bool, str]:
    if status == 400:
        return False, (
            "Centrifugo không nhận được yêu cầu kết nối WebSocket. "
            "Hãy kiểm tra header Upgrade và Connection của reverse proxy"
        )
    if status == 403:
        return False, f"Centrifugo từ chối kết nối từ trang {url}, khác với SAIGONOS_URL đang dùng"
    if status != 101:
        return False, f"lời gọi {REALTIME_PATH} nhận mã {status}, đúng ra là 101"
    if not accepted:
        return False, "API Gateway không trả lời đúng giao thức WebSocket"
    if api != 404:
        return False, f"API của Centrifugo nhận mã {api} qua API Gateway, đúng ra là 404"
    return True, "Centrifugo nhận kết nối WebSocket, API của Centrifugo bị chặn"


def websocket_accept(key: str) -> str:
    digest = hashlib.sha1(f"{key}{WEBSOCKET_GUID}".encode(), usedforsecurity=False).digest()
    return base64.b64encode(digest).decode()


def login_check(url: str, certificate: str | None) -> tuple[bool, str]:
    reply = fetch(f"{url}{DISCOVERY_PATH}", certificate)
    return login_state(url, reply.status, reply.body)


def api_check(url: str, certificate: str | None) -> tuple[bool, str]:
    anonymous = fetch(f"{url}{API_PATH}", certificate)
    invalid = fetch(f"{url}{API_PATH}", certificate, INVALID_AUTHORIZATION)
    return api_state(anonymous.status, invalid.status)


def core_check(url: str, certificate: str | None) -> tuple[bool, str]:
    health = fetch(f"{url}{CORE_HEALTH_PATH}", certificate)
    invalid = fetch(f"{url}{CORE_USER_PATH}", certificate, INVALID_AUTHORIZATION)
    return core_state(health.status, invalid.status)


def operaton_check(url: str, certificate: str | None) -> tuple[bool, str]:
    login = fetch(f"{url}{OPERATON_LOGIN_PATH}", certificate)
    rest = fetch(f"{url}{OPERATON_REST_PATH}", certificate)
    return operaton_state(url, login.status, login.headers.get("Location"), rest.status)


def realtime_check(url: str, certificate: str | None) -> tuple[bool, str]:
    key = base64.b64encode(secrets.token_bytes(16)).decode()
    headers = {
        "Upgrade": "websocket",
        "Connection": "Upgrade",
        "Sec-WebSocket-Key": key,
        "Sec-WebSocket-Version": "13",
        "Origin": url,
    }
    handshake = fetch(f"{url}{REALTIME_PATH}", certificate, headers)
    accepted = handshake.headers.get("Sec-WebSocket-Accept") == websocket_accept(key)
    api = fetch(f"{url}{REALTIME_API_PATH}", certificate)
    return realtime_state(url, handshake.status, accepted, api.status)


PROBES = (
    ("Đăng nhập", login_check),
    ("API", api_check),
    ("Core API", core_check),
    ("Operaton", operaton_check),
    ("Centrifugo", realtime_check),
)


def gateway_checks(url: str, certificate: str | None = None) -> list[Check]:
    checks = []
    for name, probe in PROBES:
        try:
            checks.append(Check(name, *probe(url, certificate)))
        except (OSError, HTTPException) as error:
            checks.append(Check(name, False, f"không kết nối được tới {url}: {error}"))
    return checks


def run_checks(home: Path, url: str) -> list[Check]:
    services = service_checks(home)
    certificate = None
    if any(check.name == CADDY for check in services):
        certificate = caddy_root_certificate(home)
    return [*services, *gateway_checks(url, certificate)]
