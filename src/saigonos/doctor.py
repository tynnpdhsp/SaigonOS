# SPDX-License-Identifier: Apache-2.0
import base64
import hashlib
import json
import secrets
import ssl
import time
from collections.abc import Callable
from functools import partial
from http.client import HTTPConnection, HTTPException, HTTPMessage, HTTPSConnection
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import parse_qs, urlsplit

from saigonos import compose
from saigonos.apps import AppFolderError, app_folders, read_manifest
from saigonos.home import APPS_FOLDER, parse_env, read_env_lines

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
WAF_PROBE_PATH = "/api/?kiem_tra=%3Cscript%3Ealert(1)%3C%2Fscript%3E"
WAF_CODE = "SGN04"
APP_RULES_CODE = "SGN03"
WAF_NAME = "Tường lửa"
WAF_MODES = ("block", "detect")
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
INVALID_AUTHORIZATION = {"Authorization": "Bearer khong-hop-le"}
CADDY = "caddy"
GRAFANA = "grafana"
PROMETHEUS = "prometheus"
GRAFANA_HEALTH_PATH = "/grafana/api/health"
TARGETS_URL = "http://127.0.0.1:9090/api/v1/targets?state=active"
TARGETS_WAIT = 30
TARGETS_POLL = 2
MONITORING_NAME = "Giám sát"
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
    containers = compose.containers(home)
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
    target = f"{parts.path}?{parts.query}" if parts.query else parts.path
    try:
        connection.request("GET", target, headers=headers or {})
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
        return False, (
            f"Centrifugo từ chối kết nối từ trang {url}. "
            "Hãy chạy lệnh saigonos init rồi saigonos up để Centrifugo nhận địa chỉ này"
        )
    if status != 101:
        return False, f"lời gọi {REALTIME_PATH} nhận mã {status}, đúng ra là 101"
    if not accepted:
        return False, "API Gateway không trả lời đúng giao thức WebSocket"
    if api != 404:
        return False, f"API của Centrifugo nhận mã {api} qua API Gateway, đúng ra là 404"
    return True, "Centrifugo nhận kết nối WebSocket, API của Centrifugo bị chặn"


def waf_state(mode: str, status: int, body: bytes) -> tuple[bool, str]:
    if mode not in WAF_MODES:
        return False, f"SAIGONOS_WAF_MODE trong file .env là {mode}, chỉ dùng block hoặc detect"
    try:
        code = json.loads(body).get("code")
    except (ValueError, AttributeError):
        code = None
    blocked = status == 403 and code == WAF_CODE
    if mode == "detect" and blocked:
        return False, "SAIGONOS_WAF_MODE là detect nhưng lời gọi vẫn bị chặn. Hãy chạy saigonos up"
    if mode == "detect":
        return True, "chế độ chỉ ghi log, lời gọi có dấu hiệu tấn công không bị chặn"
    if not blocked:
        return False, (
            f"lời gọi có dấu hiệu tấn công nhận mã {status}, đúng ra là 403 với mã {WAF_CODE}"
        )
    return True, "API Gateway chặn lời gọi có dấu hiệu tấn công"


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


def waf_check(url: str, certificate: str | None, mode: str) -> tuple[bool, str]:
    reply = fetch(f"{url}{WAF_PROBE_PATH}", certificate)
    return waf_state(mode, reply.status, reply.body)


def gateway_checks(
    url: str, certificate: str | None = None, waf_mode: str = "block"
) -> list[Check]:
    checks = []
    for name, probe in [*PROBES, (WAF_NAME, partial(waf_check, mode=waf_mode))]:
        try:
            checks.append(Check(name, *probe(url, certificate)))
        except (OSError, HTTPException) as error:
            checks.append(Check(name, False, f"không kết nối được tới {url}: {error}"))
    return checks


def prometheus_targets(home: Path) -> list[dict[str, Any]] | None:
    try:
        output = compose.capture(
            home, "exec", "-T", PROMETHEUS, "wget", "-q", "-O", "-", TARGETS_URL
        )
        targets = json.loads(output)["data"]["activeTargets"]
    except (compose.ComposeError, ValueError, KeyError, TypeError):
        return None
    return targets if isinstance(targets, list) else None


def first_scrape_done(targets: list[dict[str, Any]] | None) -> bool:
    if targets is None:
        return True
    return bool(targets) and all(target.get("health") != "unknown" for target in targets)


def settled_targets(home: Path) -> list[dict[str, Any]] | None:
    deadline = time.monotonic() + TARGETS_WAIT
    targets = prometheus_targets(home)
    while not first_scrape_done(targets) and time.monotonic() < deadline:
        time.sleep(TARGETS_POLL)
        targets = prometheus_targets(home)
    return targets


def jobs(targets: list[dict[str, Any]], wanted: Callable[[Any], bool]) -> str:
    return ", ".join(
        sorted(
            str(target.get("labels", {}).get("job"))
            for target in targets
            if wanted(target.get("health"))
        )
    )


def monitoring_state(
    status: int, body: bytes, targets: list[dict[str, Any]] | None
) -> tuple[bool, str]:
    try:
        database = json.loads(body).get("database")
    except (ValueError, AttributeError):
        database = None
    if status != 200 or database != "ok":
        return False, f"lời gọi {GRAFANA_HEALTH_PATH} nhận mã {status}, đúng ra là 200"
    if targets is None:
        return False, "không đọc được danh sách target của Prometheus"
    if not targets:
        return False, "Prometheus chưa có target nào"
    if down := jobs(targets, lambda health: health == "down"):
        return False, f"Prometheus không đọc được metrics của {down}"
    if waiting := jobs(targets, lambda health: health != "up"):
        return False, f"Prometheus chưa đọc lần nào metrics của {waiting}"
    return True, f"Grafana trả lời tại /grafana/, Prometheus đọc metrics của {len(targets)} target"


def monitoring_check(home: Path, url: str, certificate: str | None) -> Check:
    try:
        reply = fetch(f"{url}{GRAFANA_HEALTH_PATH}", certificate)
    except (OSError, HTTPException) as error:
        return Check(MONITORING_NAME, False, f"không kết nối được tới {url}: {error}")
    return Check(
        MONITORING_NAME, *monitoring_state(reply.status, reply.body, settled_targets(home))
    )


def error_code(body: bytes) -> str | None:
    try:
        code = json.loads(body).get("code")
    except (ValueError, AttributeError):
        return None
    return code if isinstance(code, str) else None


def app_state(name: str, api: int, page: int | None, code: str | None = None) -> tuple[bool, str]:
    api_path, page_path = f"/apps/{name}/api/", f"/apps/{name}/"
    guarded = api in (401, 403) and code == APP_RULES_CODE
    if api != 200 and not guarded:
        return False, f"lời gọi {api_path} nhận mã {api}, đúng ra là 200"
    if page is not None and page != 200:
        return False, f"lời gọi {page_path} nhận mã {page}, đúng ra là 200"
    if guarded:
        where = page_path if page is not None else api_path
        return True, f"ứng dụng trả lời tại {where}, API đòi đăng nhập theo luật truy cập"
    if page is None:
        return True, f"API của ứng dụng trả lời tại {api_path}"
    return True, f"API và giao diện của ứng dụng trả lời tại {page_path}"


def app_checks(home: Path, url: str, certificate: str | None = None) -> list[Check]:
    checks = []
    for folder in app_folders(home / APPS_FOLDER):
        name = f"Ứng dụng {folder.name}"
        try:
            manifest = read_manifest(folder)
        except (OSError, ValueError, AppFolderError):
            checks.append(Check(name, False, "không đọc được bản khai báo trong thư mục apps"))
            continue
        try:
            reply = fetch(f"{url}/apps/{folder.name}/api/", certificate)
            page = None
            if manifest.get("ui"):
                page = fetch(f"{url}/apps/{folder.name}/", certificate).status
        except (OSError, HTTPException) as error:
            checks.append(Check(name, False, f"không kết nối được tới {url}: {error}"))
            continue
        code = error_code(reply.body)
        checks.append(Check(name, *app_state(folder.name, reply.status, page, code)))
    return checks


def run_checks(home: Path, url: str) -> list[Check]:
    services = service_checks(home)
    certificate = None
    if any(check.name == CADDY for check in services):
        certificate = caddy_root_certificate(home)
    waf_mode = parse_env(read_env_lines(home)).get("SAIGONOS_WAF_MODE") or "block"
    gateway = gateway_checks(url, certificate, waf_mode)
    if any(check.name == GRAFANA for check in services):
        gateway.append(monitoring_check(home, url, certificate))
    return [*services, *gateway, *app_checks(home, url, certificate)]
