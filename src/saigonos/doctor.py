# SPDX-License-Identifier: Apache-2.0
import json
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urlsplit

from saigonos import compose

REALM_PATH = "/auth/realms/saigonos"
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
        return False, "không đạt kiểm tra sức khỏe"
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


def fetch(url: str) -> tuple[int, bytes]:
    parts = urlsplit(url)
    connection_type = HTTPSConnection if parts.scheme == "https" else HTTPConnection
    connection = connection_type(parts.netloc, timeout=TIMEOUT)
    try:
        connection.request("GET", parts.path)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def login_state(url: str, status: int, body: bytes) -> tuple[bool, str]:
    if status != 200:
        return False, f"Keycloak trả về mã {status}"
    try:
        issuer = json.loads(body).get("issuer")
    except (ValueError, AttributeError):
        issuer = None
    if issuer != f"{url}{REALM_PATH}":
        return False, f"Keycloak dùng địa chỉ {issuer}, khác với SAIGONOS_URL trong file .env"
    return True, f"Keycloak trả lời tại {url}/auth"


def api_state(url: str, status: int, body: bytes) -> tuple[bool, str]:
    if status != 401:
        return False, f"lời gọi không có access token nhận mã {status}, đúng ra là 401"
    return True, "lời gọi không có access token bị từ chối"


PROBES = (
    ("Đăng nhập", f"{REALM_PATH}/.well-known/openid-configuration", login_state),
    ("API", "/api/", api_state),
)


def gateway_checks(url: str) -> list[Check]:
    checks = []
    for name, path, state in PROBES:
        try:
            status, body = fetch(f"{url}{path}")
        except (OSError, HTTPException) as error:
            checks.append(Check(name, False, f"không kết nối được tới {url}: {error}"))
        else:
            checks.append(Check(name, *state(url, status, body)))
    return checks
