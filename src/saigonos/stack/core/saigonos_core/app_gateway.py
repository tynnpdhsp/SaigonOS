# SPDX-License-Identifier: Apache-2.0
import json
from collections.abc import Callable
from http.client import HTTPConnection, HTTPException
from typing import Any, Protocol
from urllib.parse import urlsplit

from saigonos_core.app_database import ApplyError, schema_of
from saigonos_core.manifest import Manifest

OWNER = "saigonos.app"
ACCESS = "saigonos.access."
PREFIX = "app-"
TIMEOUT = 30
UPSTREAM = {"type": "roundrobin", "nodes": {"postgrest:3000": 1}}
ACCESS_TOKEN = {
    "_meta": {"filter": [["http_authorization", "~~", "."]]},
    "client_id": "apisix",
    "discovery": "http://keycloak:8080/auth/realms/saigonos/.well-known/openid-configuration",
    "realm": "saigonos",
    "bearer_only": True,
    "use_jwks": True,
    "iat_slack": 0,
}
RATE_LIMIT = {
    "count": 300,
    "time_window": 10,
    "key_type": "var",
    "key": "remote_addr",
    "rejected_code": 429,
    "rejected_msg": "Gọi API quá nhiều lần, vui lòng thử lại sau",
}
POLICY = {
    "_meta": {"priority": 1000},
    "host": "http://opa:8181",
    "policy": "saigonos/apps/decision",
    "with_route": True,
}
STAMPS = ("create_time", "update_time")
ROUTE_CREATED = "Đã tạo route {route}."
ROUTE_UPDATED = "Đã cập nhật route {route}."
ROUTE_REMOVED = "Đã gỡ route {route}."


class AdminApi(Protocol):
    def call(self, method: str, path: str, body: Any = None, missing_ok: bool = False) -> Any: ...


class Apisix:
    def __init__(self, url: str, key: str, timeout: float = TIMEOUT) -> None:
        parts = urlsplit(url)
        self.host = parts.hostname or ""
        self.port = parts.port
        self.base = parts.path.rstrip("/")
        self.key = key
        self.timeout = timeout

    def call(self, method: str, path: str, body: Any = None, missing_ok: bool = False) -> Any:
        headers = {"Accept": "application/json", "X-API-KEY": self.key}
        payload = None
        if body is not None:
            payload = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        connection = HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            connection.request(method, f"{self.base}/apisix/admin{path}", payload, headers)
            response = connection.getresponse()
            content = response.read()
        except (OSError, HTTPException) as error:
            raise ApplyError(
                f"Không kết nối được Admin API của APISIX: {error}. "
                "Hãy khởi động hệ thống bằng lệnh saigonos up rồi chạy lại."
            ) from error
        finally:
            connection.close()
        try:
            data = json.loads(content) if content else None
        except ValueError:
            data = content.decode(errors="replace")
        if missing_ok and response.status == 404:
            return None
        if response.status >= 300:
            found = data.get("error_msg") or data.get("message") if isinstance(data, dict) else data
            reason = str(found or "").strip().rstrip(".")
            text = f"APISIX trả về mã {response.status} cho lời gọi {method} {path}"
            raise ApplyError(f"{text}: {reason}." if reason else f"{text}.")
        return data


def route_of(app: str) -> str:
    return f"{PREFIX}{app}"


def wanted_route(manifest: Manifest) -> dict[str, Any]:
    app = manifest.name
    schema = schema_of(app)
    labels = {OWNER: app}
    labels |= {f"{ACCESS}{index}": rule.label() for index, rule in enumerate(manifest.access, 1)}
    route = {
        "name": route_of(app),
        "desc": (
            f"PostgREST: API của ứng dụng {app}, tự đặt header Accept-Profile và "
            f"Content-Profile là {schema}. Do lệnh apply của SaigonOS tạo theo bản khai, "
            "mọi thay đổi trên route này bị đặt lại khi cài đặt lại ứng dụng"
        ),
        "uris": [f"/apps/{app}/api", f"/apps/{app}/api/*"],
        "labels": labels,
        "status": 1,
        "priority": 0,
        "plugins": {
            "openid-connect": ACCESS_TOKEN,
            "limit-count": RATE_LIMIT,
            "proxy-rewrite": {
                "regex_uri": [f"^/apps/{app}/api/?(.*)$", "/$1"],
                "headers": {"set": {"Accept-Profile": schema, "Content-Profile": schema}},
            },
            "response-rewrite": {
                "vars": [["uri", "~~", f"^/apps/{app}/api/?$"]],
                "filters": [
                    {
                        "regex": '"basePath"\\s*:\\s*"/api"',
                        "scope": "once",
                        "replace": f'"basePath":"/apps/{app}/api"',
                    }
                ],
            },
        },
        "upstream": UPSTREAM,
    }
    if manifest.access:
        route["plugins"]["opa"] = POLICY
    return route


def stored(reply: Any) -> dict[str, Any] | None:
    value = reply.get("value") if isinstance(reply, dict) else None
    if not isinstance(value, dict):
        return None
    return {key: item for key, item in value.items() if key not in STAMPS}


def find_route(apisix: AdminApi, app: str) -> dict[str, Any] | None:
    return stored(apisix.call("GET", f"/routes/{route_of(app)}", missing_ok=True))


def owned(route: dict[str, Any], app: str) -> bool:
    return (route.get("labels") or {}).get(OWNER) == app


def conflict(app: str) -> ApplyError:
    return ApplyError(
        f"Route {route_of(app)} đã có trong APISIX nhưng không do SaigonOS tạo "
        f"cho ứng dụng {app}. Hãy đặt tên khác cho ứng dụng."
    )


def check_route(apisix: AdminApi, manifest: Manifest) -> None:
    route = find_route(apisix, manifest.name)
    if route is not None and not owned(route, manifest.name):
        raise conflict(manifest.name)


def apply_gateway(apisix: AdminApi, manifest: Manifest, say: Callable[[str], None]) -> bool:
    app = manifest.name
    current = find_route(apisix, app)
    if current is not None and not owned(current, app):
        raise conflict(app)
    saved = stored(apisix.call("PUT", f"/routes/{route_of(app)}", wanted_route(manifest)))
    if current is None:
        say(ROUTE_CREATED.format(route=route_of(app)))
        return True
    if saved != current:
        say(ROUTE_UPDATED.format(route=route_of(app)))
        return True
    return False


def remove_gateway(apisix: AdminApi, app: str, say: Callable[[str], None]) -> bool:
    current = find_route(apisix, app)
    if current is None or not owned(current, app):
        return False
    apisix.call("DELETE", f"/routes/{route_of(app)}", missing_ok=True)
    say(ROUTE_REMOVED.format(route=route_of(app)))
    return True
