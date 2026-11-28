# SPDX-License-Identifier: Apache-2.0
import json
from collections.abc import Callable
from http.client import HTTPConnection, HTTPException
from typing import Any, NamedTuple, Protocol
from urllib.parse import quote, urlencode, urlsplit

from saigonos_core.app_database import ApplyError
from saigonos_core.manifest import Manifest, Role

REALM = "saigonos"
OWNER = "saigonos.app"
SIGNED_IN = "authenticated"
DEFAULT_SCOPES = ("acr", "basic", "email", "profile", "roles", "web-origins")
TIMEOUT = 30
DESCRIPTION = (
    "Do lệnh apply của SaigonOS tạo theo bản khai báo của ứng dụng. "
    "Mọi thay đổi trên client này bị đặt lại khi cài đặt lại ứng dụng."
)
ROLE_CREATED = "Đã tạo realm role {role}."
ROLE_UPDATED = "Đã cập nhật realm role {role}."
CLIENT_CREATED = "Đã tạo client {client}."
CLIENT_UPDATED = "Đã cập nhật client {client}."
CLIENT_REMOVED = "Đã gỡ client {client}."
ROLE_REMOVED = "Đã xóa realm role {role}."


class Reply(NamedTuple):
    status: int
    data: Any


class AdminApi(Protocol):
    def call(self, method: str, path: str, body: Any = None, missing_ok: bool = False) -> Any: ...


def explained(text: str, data: Any) -> str:
    message = "" if data is None else str(data)
    if isinstance(data, dict):
        found = (data.get(key) for key in ("errorMessage", "error_description", "error"))
        whole = json.dumps(data, ensure_ascii=False)
        message = next((value for value in found if isinstance(value, str)), whole)
    message = message.strip().rstrip(".")
    return f"{text}: {message}." if message else f"{text}."


class Keycloak:
    def __init__(self, url: str, username: str, password: str, timeout: float = TIMEOUT) -> None:
        parts = urlsplit(url)
        self.host = parts.hostname or ""
        self.port = parts.port
        self.base = parts.path.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self.token: str | None = None

    def send(self, method: str, path: str, payload: bytes | None, kind: str | None) -> Reply:
        headers = {"Accept": "application/json"}
        if kind is not None:
            headers["Content-Type"] = kind
        if self.token is not None:
            headers["Authorization"] = f"Bearer {self.token}"
        connection = HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            connection.request(method, self.base + path, body=payload, headers=headers)
            response = connection.getresponse()
            content = response.read()
        except (OSError, HTTPException) as error:
            raise ApplyError(
                f"Không kết nối được Keycloak: {error}. "
                "Hãy khởi động hệ thống bằng lệnh saigonos up rồi chạy lại."
            ) from error
        finally:
            connection.close()
        try:
            data = json.loads(content) if content else None
        except ValueError:
            data = content.decode(errors="replace")
        return Reply(response.status, data)

    def log_in(self) -> None:
        self.token = None
        form = urlencode(
            {
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": self.username,
                "password": self.password,
            }
        )
        path = "/realms/master/protocol/openid-connect/token"
        reply = self.send("POST", path, form.encode(), "application/x-www-form-urlencoded")
        token = reply.data.get("access_token") if isinstance(reply.data, dict) else None
        if reply.status != 200 or not isinstance(token, str):
            refused = explained("Không đăng nhập được realm master của Keycloak", reply.data)
            raise ApplyError(
                f"{refused} Mật khẩu của tài khoản admin phải trùng giá trị "
                "KEYCLOAK_ADMIN_PASSWORD trong file .env."
            )
        self.token = token

    def call(self, method: str, path: str, body: Any = None, missing_ok: bool = False) -> Any:
        payload = None if body is None else json.dumps(body).encode()
        kind = None if body is None else "application/json"
        target = f"/admin/realms/{REALM}{path}"
        if self.token is None:
            self.log_in()
        reply = self.send(method, target, payload, kind)
        if reply.status == 401:
            self.log_in()
            reply = self.send(method, target, payload, kind)
        if missing_ok and reply.status == 404:
            return None
        if reply.status >= 300:
            text = f"Keycloak trả về mã {reply.status} cho lời gọi {method} {path}"
            raise ApplyError(explained(text, reply.data))
        return reply.data


def segment(value: str) -> str:
    return quote(value, safe="")


def owned(item: dict[str, Any], app: str) -> bool:
    return (item.get("attributes") or {}).get(OWNER) in (app, [app])


def conflict(names: list[str], app: str) -> ApplyError:
    listed = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} và {names[-1]}"
    return ApplyError(
        f"{listed[0].upper()}{listed[1:]} đã có trong Keycloak nhưng không do SaigonOS tạo "
        f"cho ứng dụng {app}. Hãy đặt tên khác cho ứng dụng."
    )


def find_client(keycloak: AdminApi, app: str) -> dict[str, Any] | None:
    clients = keycloak.call("GET", f"/clients?{urlencode({'clientId': app})}")
    return next((client for client in clients if client.get("clientId") == app), None)


def find_role(keycloak: AdminApi, name: str) -> dict[str, Any] | None:
    return keycloak.call("GET", f"/roles/{segment(name)}", missing_ok=True)


def check_names(keycloak: AdminApi, manifest: Manifest) -> None:
    names = []
    client = find_client(keycloak, manifest.name)
    if client is not None and not owned(client, manifest.name):
        names.append(f"client {manifest.name}")
    for role in manifest.roles:
        found = find_role(keycloak, role.name)
        if found is not None and not owned(found, manifest.name):
            names.append(f"realm role {role.name}")
    if names:
        raise conflict(names, manifest.name)


def sync_role(
    keycloak: AdminApi, app: str, role: Role, say: Callable[[str], None]
) -> tuple[dict[str, Any], bool]:
    path = f"/roles/{segment(role.name)}"
    current = keycloak.call("GET", path, missing_ok=True)
    if current is None:
        created = {"name": role.name, "description": role.description, "attributes": {OWNER: [app]}}
        keycloak.call("POST", "/roles", created)
        say(ROLE_CREATED.format(role=role.name))
        return keycloak.call("GET", path), True
    if not owned(current, app):
        raise conflict([f"realm role {role.name}"], app)
    changed = False
    if current.get("description") != role.description:
        keycloak.call("PUT", path, {"name": role.name, "description": role.description})
        changed = True
    if current.get("composite"):
        keycloak.call("DELETE", f"{path}/composites", keycloak.call("GET", f"{path}/composites"))
        changed = True
    if changed:
        say(ROLE_UPDATED.format(role=role.name))
    return current, changed


def wanted_client(manifest: Manifest, site_url: str) -> dict[str, Any]:
    path = f"/apps/{manifest.name}/"
    return {
        "clientId": manifest.name,
        "name": manifest.title,
        "description": DESCRIPTION,
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": True,
        "bearerOnly": False,
        "consentRequired": False,
        "standardFlowEnabled": True,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "authorizationServicesEnabled": False,
        "fullScopeAllowed": False,
        "rootUrl": site_url,
        "baseUrl": path,
        "adminUrl": "",
        "redirectUris": [f"{site_url}{path}*"],
        "webOrigins": ["+"],
        "attributes": {
            OWNER: manifest.name,
            "pkce.code.challenge.method": "S256",
            "post.logout.redirect.uris": "+",
            "oauth2.device.authorization.grant.enabled": "false",
            "oidc.ciba.grant.enabled": "false",
            "standard.token.exchange.enabled": "false",
        },
    }


def differs(current: Any, wanted: Any) -> bool:
    if isinstance(wanted, dict):
        found = current if isinstance(current, dict) else {}
        return any(differs(found.get(key), value) for key, value in wanted.items())
    if isinstance(wanted, list):
        return not isinstance(current, list) or sorted(current) != sorted(wanted)
    if isinstance(wanted, bool):
        return bool(current) is not wanted
    return (current or "") != wanted


def sync_settings(keycloak: AdminApi, client: dict[str, Any], wanted: dict[str, Any]) -> bool:
    flows = client.get("authenticationFlowBindingOverrides") or {}
    overrides = {flow: "" for flow, value in flows.items() if value}
    if not overrides and not differs(client, wanted):
        return False
    body = wanted | ({"authenticationFlowBindingOverrides": overrides} if overrides else {})
    keycloak.call("PUT", f"/clients/{segment(client['id'])}", body)
    return True


def sync_mappers(keycloak: AdminApi, base: str) -> bool:
    mappers = keycloak.call("GET", f"{base}/protocol-mappers/models")
    for mapper in mappers:
        keycloak.call("DELETE", f"{base}/protocol-mappers/models/{segment(mapper['id'])}")
    return bool(mappers)


def brief(role: dict[str, Any]) -> dict[str, Any]:
    return {"id": role["id"], "name": role["name"]}


def sync_scope_mappings(keycloak: AdminApi, base: str, roles: dict[str, dict[str, Any]]) -> bool:
    mappings = keycloak.call("GET", f"{base}/scope-mappings") or {}
    current = {role["name"]: role for role in mappings.get("realmMappings") or []}
    extra = [brief(role) for name, role in current.items() if name not in roles]
    missing = [brief(role) for name, role in roles.items() if name not in current]
    if extra:
        keycloak.call("DELETE", f"{base}/scope-mappings/realm", extra)
    if missing:
        keycloak.call("POST", f"{base}/scope-mappings/realm", missing)
    others = list((mappings.get("clientMappings") or {}).values())
    for other in others:
        path = f"{base}/scope-mappings/clients/{segment(other['id'])}"
        keycloak.call("DELETE", path, other["mappings"])
    return bool(extra or missing or others)


def sync_client_scopes(keycloak: AdminApi, base: str) -> bool:
    defaults = keycloak.call("GET", f"{base}/default-client-scopes")
    optional = keycloak.call("GET", f"{base}/optional-client-scopes")
    names = {scope["name"] for scope in defaults}
    extra = [scope for scope in defaults if scope["name"] not in DEFAULT_SCOPES]
    missing = [name for name in DEFAULT_SCOPES if name not in names]
    for scope in optional:
        keycloak.call("DELETE", f"{base}/optional-client-scopes/{segment(scope['id'])}")
    for scope in extra:
        keycloak.call("DELETE", f"{base}/default-client-scopes/{segment(scope['id'])}")
    if missing:
        scopes = {scope["name"]: scope["id"] for scope in keycloak.call("GET", "/client-scopes")}
        absent = [name for name in missing if name not in scopes]
        if absent:
            raise ApplyError(f"Realm {REALM} không có client scope {', '.join(absent)}.")
        for name in missing:
            keycloak.call("PUT", f"{base}/default-client-scopes/{segment(scopes[name])}")
    return bool(optional or extra or missing)


def sync_client(
    keycloak: AdminApi,
    manifest: Manifest,
    site_url: str,
    roles: dict[str, dict[str, Any]],
    say: Callable[[str], None],
) -> bool:
    wanted = wanted_client(manifest, site_url)
    client = find_client(keycloak, manifest.name)
    created = client is None
    if client is None:
        keycloak.call("POST", "/clients", wanted)
        client = find_client(keycloak, manifest.name) or {}
    elif not owned(client, manifest.name):
        raise conflict([f"client {manifest.name}"], manifest.name)
    base = f"/clients/{segment(client['id'])}"
    changed = sync_settings(keycloak, client, wanted)
    changed = sync_mappers(keycloak, base) or changed
    changed = sync_scope_mappings(keycloak, base, roles) or changed
    changed = sync_client_scopes(keycloak, base) or changed
    if created:
        say(CLIENT_CREATED.format(client=manifest.name))
    elif changed:
        say(CLIENT_UPDATED.format(client=manifest.name))
    return created or changed


def apply_keycloak(
    keycloak: AdminApi, manifest: Manifest, site_url: str, say: Callable[[str], None]
) -> bool:
    signed_in = find_role(keycloak, SIGNED_IN)
    if signed_in is None:
        raise ApplyError(f"Realm {REALM} không có realm role {SIGNED_IN}.")
    roles = {SIGNED_IN: signed_in}
    changed = False
    for role in manifest.roles:
        roles[role.name], role_changed = sync_role(keycloak, manifest.name, role, say)
        changed = role_changed or changed
    return sync_client(keycloak, manifest, site_url.rstrip("/"), roles, say) or changed


def roles_of(keycloak: AdminApi, app: str) -> list[dict[str, Any]]:
    query = urlencode({"search": f"{app}.", "briefRepresentation": "false"})
    found = keycloak.call("GET", f"/roles?{query}")
    return [
        role for role in found if role.get("name", "").startswith(f"{app}.") and owned(role, app)
    ]


def remove_keycloak(keycloak: AdminApi, app: str, purge: bool, say: Callable[[str], None]) -> bool:
    changed = False
    client = find_client(keycloak, app)
    if client is not None and owned(client, app):
        keycloak.call("DELETE", f"/clients/{segment(client['id'])}")
        say(CLIENT_REMOVED.format(client=app))
        changed = True
    if purge:
        for role in sorted(roles_of(keycloak, app), key=lambda role: role["name"]):
            keycloak.call("DELETE", f"/roles/{segment(role['name'])}")
            say(ROLE_REMOVED.format(role=role["name"]))
            changed = True
    return changed
