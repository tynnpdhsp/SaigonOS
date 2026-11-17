# SPDX-License-Identifier: Apache-2.0
import json
import ssl
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urlsplit

from saigonos import compose

REALM_PATH = "/auth/realms/saigonos"
TOKEN_PATH = f"{REALM_PATH}/protocol/openid-connect/token"
DISCOVERY_PATH = f"{REALM_PATH}/.well-known/openid-configuration"
API_PATH = "/api/"
CORE_HEALTH_PATH = "/core/health"
CORE_USER_PATH = "/core/me"
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


def fetch(
    url: str, certificate: str | None = None, headers: dict[str, str] | None = None
) -> tuple[int, bytes]:
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
        return response.status, response.read()
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


def login_check(url: str, certificate: str | None) -> tuple[bool, str]:
    status, body = fetch(f"{url}{DISCOVERY_PATH}", certificate)
    return login_state(url, status, body)


def api_check(url: str, certificate: str | None) -> tuple[bool, str]:
    anonymous, _ = fetch(f"{url}{API_PATH}", certificate)
    invalid, _ = fetch(f"{url}{API_PATH}", certificate, INVALID_AUTHORIZATION)
    return api_state(anonymous, invalid)


def core_check(url: str, certificate: str | None) -> tuple[bool, str]:
    health, _ = fetch(f"{url}{CORE_HEALTH_PATH}", certificate)
    invalid, _ = fetch(f"{url}{CORE_USER_PATH}", certificate, INVALID_AUTHORIZATION)
    return core_state(health, invalid)


PROBES = (("Đăng nhập", login_check), ("API", api_check), ("Core API", core_check))


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
