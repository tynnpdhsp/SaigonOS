# SPDX-License-Identifier: Apache-2.0
import copy
import json
import re
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from urllib.parse import parse_qs, unquote

import pytest

from saigonos_core.app_database import ApplyError
from saigonos_core.app_keycloak import (
    CLIENT_CREATED,
    CLIENT_REMOVED,
    CLIENT_UPDATED,
    DEFAULT_SCOPES,
    DESCRIPTION,
    OWNER,
    ROLE_CREATED,
    ROLE_REMOVED,
    ROLE_UPDATED,
    Keycloak,
    apply_keycloak,
    check_names,
    differs,
    remove_keycloak,
)
from saigonos_core.manifest import Manifest

SITE = "https://dx.example.com"
DATA = {
    "name": "nghi-phep",
    "title": "Nghỉ phép",
    "version": "0.1.0",
    "roles": [
        {"name": "nghi-phep.nhan-vien", "description": "Gửi đơn và xem đơn của mình"},
        {"name": "nghi-phep.quan-ly", "description": "Duyệt đơn của nhân viên"},
    ],
}
ROLES = [role["name"] for role in DATA["roles"]]
REALM_DEFAULTS = ["acr", "basic", "email", "profile", "roles", "web-origins"]
REALM_OPTIONAL = ["address", "microprofile-jwt", "offline_access", "organization", "phone"]
CLIENT = r"/clients/(?P<client>[^/?]+)"
ROLE = r"/roles/(?P<role>[^/?]+)"
SCOPES = rf"{CLIENT}/(?P<kind>default|optional)-client-scopes"
ROUTES = [
    ("GET", r"/clients\?clientId=(?P<client_id>[^&]+)", "find_clients"),
    ("POST", r"/clients", "create_client"),
    ("PUT", CLIENT, "update_client"),
    ("DELETE", CLIENT, "delete_client"),
    ("GET", r"/roles\?search=(?P<search>[^&]+)&briefRepresentation=false", "search_roles"),
    ("DELETE", ROLE, "delete_role"),
    ("GET", rf"{CLIENT}/protocol-mappers/models", "mappers_of"),
    ("POST", rf"{CLIENT}/protocol-mappers/models", "add_mapper"),
    ("DELETE", rf"{CLIENT}/protocol-mappers/models/(?P<mapper>[^/]+)", "remove_mapper"),
    ("GET", rf"{CLIENT}/scope-mappings", "scope_mappings"),
    ("POST", rf"{CLIENT}/scope-mappings/realm", "add_realm_scope"),
    ("DELETE", rf"{CLIENT}/scope-mappings/realm", "remove_realm_scope"),
    ("POST", rf"{CLIENT}/scope-mappings/clients/(?P<other>[^/]+)", "add_client_scope"),
    ("DELETE", rf"{CLIENT}/scope-mappings/clients/(?P<other>[^/]+)", "remove_client_scope"),
    ("GET", SCOPES, "scopes_of"),
    ("PUT", rf"{SCOPES}/(?P<scope>[^/]+)", "assign_scope"),
    ("DELETE", rf"{SCOPES}/(?P<scope>[^/]+)", "unassign_scope"),
    ("GET", r"/client-scopes", "realm_scopes"),
    ("GET", ROLE, "find_role"),
    ("POST", r"/roles", "create_role"),
    ("PUT", ROLE, "update_role"),
    ("GET", rf"{ROLE}/composites", "composites_of"),
    ("POST", rf"{ROLE}/composites", "add_composites"),
    ("DELETE", rf"{ROLE}/composites", "remove_composites"),
]


class Missing(Exception):
    pass


class FakeKeycloak:
    def __init__(self):
        self.calls = []
        self.clients = {}
        self.roles = {}
        self.composites = {}
        self.mappers = {}
        self.realm_scope = {}
        self.client_scope = {}
        self.assigned = {}
        self.scopes = {name: f"scope-{name}" for name in REALM_DEFAULTS + REALM_OPTIONAL}
        self.realm_defaults = list(REALM_DEFAULTS)
        self.count = 0
        for name in ("authenticated", "admin", "offline_access"):
            self.create_role({"name": name})

    def new_id(self, kind):
        self.count += 1
        return f"{kind}-{self.count}"

    def call(self, method, path, body=None, missing_ok=False):
        self.calls.append((method, path))
        matches = (
            (handler, re.fullmatch(pattern, path))
            for verb, pattern, handler in ROUTES
            if verb == method
        )
        handler, found = next(((name, found) for name, found in matches if found), (None, None))
        if found is None:
            raise AssertionError(f"Keycloak giả chưa có lời gọi {method} {path}")
        params = {key: unquote(value) for key, value in found.groupdict().items()}
        try:
            return copy.deepcopy(getattr(self, handler)(copy.deepcopy(body), **params))
        except Missing as error:
            if missing_ok:
                return None
            raise ApplyError(
                f"Keycloak trả về mã 404 cho lời gọi {method} {path}: {error}."
            ) from None

    @property
    def writes(self):
        return [call for call in self.calls if call[0] != "GET"]

    def client_named(self, client_id):
        return next(rep for rep in self.clients.values() if rep["clientId"] == client_id)

    def role_by_id(self, role_id):
        return next(rep for rep in self.roles.values() if rep["id"] == role_id)

    def find_clients(self, body, client_id):
        return [rep for rep in self.clients.values() if rep["clientId"] == client_id]

    def create_client(self, body):
        client = self.new_id("client")
        rep = {
            "id": client,
            "enabled": True,
            "publicClient": False,
            "standardFlowEnabled": True,
            "directAccessGrantsEnabled": False,
            "fullScopeAllowed": True,
            "frontchannelLogout": False,
            "redirectUris": [],
            "webOrigins": [],
            "authenticationFlowBindingOverrides": {},
        } | body
        rep["attributes"] = {"realm_client": "false"} | body.get("attributes", {})
        rep.setdefault("adminUrl", rep.get("rootUrl"))
        self.clients[client] = rep
        self.mappers[client] = []
        self.realm_scope[client] = []
        self.client_scope[client] = {}
        self.assigned[client] = {
            "default": list(self.realm_defaults),
            "optional": list(REALM_OPTIONAL),
        }

    def delete_client(self, body, client):
        if client not in self.clients:
            raise Missing("Could not find client")
        del self.clients[client]

    def search_roles(self, body, search):
        return [rep for name, rep in self.roles.items() if search.lower() in name.lower()]

    def delete_role(self, body, role):
        if role not in self.roles:
            raise Missing("Could not find role")
        del self.roles[role]

    def update_client(self, body, client):
        rep = self.clients[client]
        for key, value in body.items():
            if key == "attributes":
                rep[key].update(value)
            elif key == "authenticationFlowBindingOverrides":
                for flow, flow_id in value.items():
                    if flow_id:
                        rep[key][flow] = flow_id
                    else:
                        rep[key].pop(flow, None)
            else:
                rep[key] = value

    def mappers_of(self, body, client):
        return self.mappers[client]

    def add_mapper(self, body, client):
        self.mappers[client].append(body | {"id": self.new_id("mapper")})

    def remove_mapper(self, body, client, mapper):
        self.mappers[client] = [item for item in self.mappers[client] if item["id"] != mapper]

    def scope_mappings(self, body, client):
        mappings = {}
        if self.realm_scope[client]:
            mappings["realmMappings"] = [self.roles[name] for name in self.realm_scope[client]]
        if self.client_scope[client]:
            mappings["clientMappings"] = self.client_scope[client]
        return mappings

    def add_realm_scope(self, body, client):
        for role in body:
            name = self.role_by_id(role["id"])["name"]
            if name not in self.realm_scope[client]:
                self.realm_scope[client].append(name)

    def remove_realm_scope(self, body, client):
        names = {self.role_by_id(role["id"])["name"] for role in body}
        self.realm_scope[client] = [name for name in self.realm_scope[client] if name not in names]

    def add_client_scope(self, body, client, other):
        entry = {"id": other, "client": f"client-{other}", "mappings": []}
        self.client_scope[client].setdefault(other, entry)["mappings"] += body

    def remove_client_scope(self, body, client, other):
        removed = {role["id"] for role in body}
        entry = self.client_scope[client][other]
        entry["mappings"] = [role for role in entry["mappings"] if role["id"] not in removed]
        if not entry["mappings"]:
            del self.client_scope[client][other]

    def scope_name(self, scope):
        return next(name for name, scope_id in self.scopes.items() if scope_id == scope)

    def scopes_of(self, body, client, kind):
        return [{"id": self.scopes[name], "name": name} for name in self.assigned[client][kind]]

    def assign_scope(self, body, client, kind, scope):
        if self.scope_name(scope) not in self.assigned[client][kind]:
            self.assigned[client][kind].append(self.scope_name(scope))

    def unassign_scope(self, body, client, kind, scope):
        self.assigned[client][kind].remove(self.scope_name(scope))

    def realm_scopes(self, body):
        return [{"id": scope_id, "name": name} for name, scope_id in self.scopes.items()]

    def find_role(self, body, role):
        if role not in self.roles:
            raise Missing("Could not find role")
        return self.roles[role]

    def create_role(self, body):
        self.roles[body["name"]] = {
            "id": self.new_id("role"),
            "name": body["name"],
            "description": body.get("description"),
            "composite": False,
            "clientRole": False,
            "attributes": body.get("attributes") or {},
        }
        self.composites[body["name"]] = []

    def update_role(self, body, role):
        self.roles[role]["description"] = body.get("description")
        if body.get("attributes") is not None:
            self.roles[role]["attributes"] = body["attributes"]

    def composites_of(self, body, role):
        return [self.roles[name] for name in self.composites[role]]

    def add_composites(self, body, role):
        self.composites[role] += [self.role_by_id(item["id"])["name"] for item in body]
        self.roles[role]["composite"] = bool(self.composites[role])

    def remove_composites(self, body, role):
        removed = {self.role_by_id(item["id"])["name"] for item in body}
        self.composites[role] = [name for name in self.composites[role] if name not in removed]
        self.roles[role]["composite"] = bool(self.composites[role])

    def state(self, app):
        client = self.client_named(app)
        key = client["id"]
        roles = {name: rep for name, rep in self.roles.items() if name.startswith(f"{app}.")}
        return copy.deepcopy(
            {
                "client": client,
                "mappers": self.mappers[key],
                "realm_scope": sorted(self.realm_scope[key]),
                "client_scope": self.client_scope[key],
                "default": sorted(self.assigned[key]["default"]),
                "optional": sorted(self.assigned[key]["optional"]),
                "roles": roles,
                "composites": {name: self.composites[name] for name in roles},
            }
        )


@pytest.fixture
def keycloak():
    return FakeKeycloak()


def manifest(**changes):
    return Manifest.model_validate(DATA | changes)


def run(keycloak, data=None, site=SITE):
    said = []
    changed = apply_keycloak(keycloak, data or manifest(), site, said.append)
    return changed, said


def plugged(keycloak):
    run(keycloak)
    keycloak.calls.clear()
    return keycloak.client_named("nghi-phep")["id"], keycloak.state("nghi-phep")


def failure(action):
    with pytest.raises(ApplyError) as raised:
        action()
    return str(raised.value)


def test_first_apply_creates_roles_and_public_client(keycloak):
    changed, said = run(keycloak)

    client = keycloak.client_named("nghi-phep")
    state = keycloak.state("nghi-phep")
    assert changed is True
    assert said == [
        ROLE_CREATED.format(role="nghi-phep.nhan-vien"),
        ROLE_CREATED.format(role="nghi-phep.quan-ly"),
        CLIENT_CREATED.format(client="nghi-phep"),
    ]
    assert {
        key: client[key] for key in ("name", "description", "rootUrl", "baseUrl", "adminUrl")
    } == {
        "name": "Nghỉ phép",
        "description": DESCRIPTION,
        "rootUrl": SITE,
        "baseUrl": "/apps/nghi-phep/",
        "adminUrl": "",
    }
    assert client["publicClient"] is client["standardFlowEnabled"] is True
    assert not any(
        client[key]
        for key in (
            "implicitFlowEnabled",
            "directAccessGrantsEnabled",
            "serviceAccountsEnabled",
            "fullScopeAllowed",
            "bearerOnly",
            "consentRequired",
        )
    )
    assert client["redirectUris"] == [f"{SITE}/apps/nghi-phep/*"]
    assert client["webOrigins"] == ["+"]
    assert client["attributes"] == {
        "realm_client": "false",
        OWNER: "nghi-phep",
        "pkce.code.challenge.method": "S256",
        "post.logout.redirect.uris": "+",
        "oauth2.device.authorization.grant.enabled": "false",
        "oidc.ciba.grant.enabled": "false",
        "standard.token.exchange.enabled": "false",
    }
    assert state["realm_scope"] == ["authenticated", *ROLES]
    assert (state["client_scope"], state["mappers"]) == ({}, [])
    assert (state["default"], state["optional"]) == (sorted(DEFAULT_SCOPES), [])
    assert {
        name: (role["description"], role["attributes"]) for name, role in state["roles"].items()
    } == {role["name"]: (role["description"], {OWNER: ["nghi-phep"]}) for role in DATA["roles"]}


def test_apply_again_changes_nothing(keycloak):
    _, state = plugged(keycloak)

    changed, said = run(keycloak)

    assert (changed, said) == (False, [])
    assert keycloak.writes == []
    assert keycloak.state("nghi-phep") == state


def by_hand(**settings):
    return lambda keycloak, client: keycloak.call("PUT", f"/clients/{client}", settings)


def add_scope(kind, name):
    return lambda keycloak, client: keycloak.call(
        "PUT", f"/clients/{client}/{kind}-client-scopes/{keycloak.scopes[name]}"
    )


def role_scope(method, name):
    return lambda keycloak, client: keycloak.call(
        method, f"/clients/{client}/scope-mappings/realm", [keycloak.roles[name]]
    )


EDITS = {
    "tat-client": by_hand(enabled=False),
    "doi-sang-confidential": by_hand(publicClient=False),
    "bat-password-grant": by_hand(directAccessGrantsEnabled=True),
    "bat-implicit": by_hand(implicitFlowEnabled=True),
    "bat-service-account": by_hand(serviceAccountsEnabled=True),
    "bat-authorization": by_hand(authorizationServicesEnabled=True),
    "bat-consent": by_hand(consentRequired=True),
    "bat-full-scope": by_hand(fullScopeAllowed=True),
    "them-redirect": by_hand(redirectUris=[f"{SITE}/apps/nghi-phep/*", "*"]),
    "them-web-origin": by_hand(webOrigins=["*"]),
    "dat-admin-url": by_hand(adminUrl="https://evil.example.com"),
    "doi-ten": by_hand(name="Tên khác", description=None),
    "pkce-plain": by_hand(attributes={"pkce.code.challenge.method": "plain"}),
    "bat-device-grant": by_hand(attributes={"oauth2.device.authorization.grant.enabled": "true"}),
    "doi-luong-dang-nhap": by_hand(authenticationFlowBindingOverrides={"browser": "flow-1"}),
    "them-mapper": lambda keycloak, client: keycloak.call(
        "POST",
        f"/clients/{client}/protocol-mappers/models",
        {"name": "gia", "protocolMapper": "oidc-hardcoded-claim-mapper"},
    ),
    "them-role-admin": role_scope("POST", "admin"),
    "bo-role-cua-ung-dung": role_scope("DELETE", "nghi-phep.quan-ly"),
    "them-client-role": lambda keycloak, client: keycloak.call(
        "POST",
        f"/clients/{client}/scope-mappings/clients/realm-management",
        [{"id": "realm-admin"}],
    ),
    "them-optional-scope": add_scope("optional", "offline_access"),
    "them-default-scope": add_scope("default", "microprofile-jwt"),
    "bo-default-scope": lambda keycloak, client: keycloak.call(
        "DELETE", f"/clients/{client}/default-client-scopes/{keycloak.scopes['profile']}"
    ),
}


@pytest.mark.parametrize("edit", list(EDITS))
def test_client_edited_by_hand_is_put_back(keycloak, edit):
    client, state = plugged(keycloak)
    EDITS[edit](keycloak, client)
    assert keycloak.state("nghi-phep") != state

    changed, said = run(keycloak)

    assert (changed, said) == (True, [CLIENT_UPDATED.format(client="nghi-phep")])
    assert keycloak.state("nghi-phep") == state
    assert run(keycloak) == (False, [])


def test_scope_moved_from_default_to_optional_comes_back_as_default(keycloak):
    client, state = plugged(keycloak)
    add_scope("optional", "profile")(keycloak, client)
    keycloak.call("DELETE", f"/clients/{client}/default-client-scopes/{keycloak.scopes['profile']}")

    run(keycloak)

    assert keycloak.state("nghi-phep") == state


@pytest.mark.parametrize(
    ("description", "composites"),
    [("Sửa tay", []), (None, ["admin"]), ("Sửa tay", ["admin", "offline_access"])],
    ids=["mo-ta", "composite", "ca-hai"],
)
def test_role_edited_by_hand_is_put_back_and_keeps_other_attributes(
    keycloak, description, composites
):
    _, state = plugged(keycloak)
    path = "/roles/nghi-phep.quan-ly"
    if description:
        keycloak.call("PUT", path, {"name": "nghi-phep.quan-ly", "description": description})
    keycloak.call("POST", f"{path}/composites", [keycloak.roles[name] for name in composites])
    attributes = {OWNER: ["nghi-phep"], "ghi-chu": ["của quản trị viên"]}
    keycloak.roles["nghi-phep.quan-ly"]["attributes"] = attributes

    changed, said = run(keycloak)

    state["roles"]["nghi-phep.quan-ly"]["attributes"] = attributes
    assert (changed, said) == (True, [ROLE_UPDATED.format(role="nghi-phep.quan-ly")])
    assert keycloak.state("nghi-phep") == state


def test_role_left_out_of_manifest_is_kept_but_leaves_scope_of_client(keycloak):
    plugged(keycloak)

    changed, said = run(keycloak, manifest(roles=DATA["roles"][:1]))

    assert (changed, said) == (True, [CLIENT_UPDATED.format(client="nghi-phep")])
    assert keycloak.state("nghi-phep")["realm_scope"] == ["authenticated", "nghi-phep.nhan-vien"]
    assert "nghi-phep.quan-ly" in keycloak.roles


def test_new_title_updates_client(keycloak):
    plugged(keycloak)

    changed, said = run(keycloak, manifest(title="Nghỉ phép năm"))

    assert (changed, said) == (True, [CLIENT_UPDATED.format(client="nghi-phep")])
    assert keycloak.client_named("nghi-phep")["name"] == "Nghỉ phép năm"


def test_new_address_updates_addresses_of_client(keycloak):
    plugged(keycloak)

    changed, said = run(keycloak, site="https://moi.example.com/")

    client = keycloak.client_named("nghi-phep")
    assert (changed, said) == (True, [CLIENT_UPDATED.format(client="nghi-phep")])
    assert client["rootUrl"] == "https://moi.example.com"
    assert client["redirectUris"] == ["https://moi.example.com/apps/nghi-phep/*"]
    assert run(keycloak, site="https://moi.example.com") == (False, [])


def test_check_names_lists_every_name_not_made_for_app(keycloak):
    keycloak.call("POST", "/clients", {"clientId": "nghi-phep"})
    keycloak.create_role({"name": "nghi-phep.nhan-vien"})
    keycloak.create_role({"name": "nghi-phep.quan-ly", "attributes": {OWNER: ["don-tu"]}})

    message = failure(lambda: check_names(keycloak, manifest()))

    assert message == (
        "Client nghi-phep, realm role nghi-phep.nhan-vien và realm role nghi-phep.quan-ly "
        "đã có trong Keycloak nhưng không do SaigonOS tạo cho ứng dụng nghi-phep. "
        "Hãy đặt tên khác cho ứng dụng."
    )
    assert keycloak.writes == [("POST", "/clients")]


def test_check_names_reports_single_name(keycloak):
    keycloak.create_role({"name": "nghi-phep.quan-ly", "attributes": {OWNER: ["nghi-phep", "x"]}})

    message = failure(lambda: check_names(keycloak, manifest()))

    assert message.startswith("Realm role nghi-phep.quan-ly đã có trong Keycloak nhưng")


def test_check_names_passes_for_missing_names_and_names_of_app(keycloak):
    check_names(keycloak, manifest())
    plugged(keycloak)

    check_names(keycloak, manifest())

    assert keycloak.writes == []


def test_apply_stops_at_client_taken_after_check(keycloak):
    keycloak.call("POST", "/clients", {"clientId": "nghi-phep", "directAccessGrantsEnabled": True})
    before = keycloak.client_named("nghi-phep")

    message = failure(lambda: run(keycloak))

    assert message.startswith("Client nghi-phep đã có trong Keycloak nhưng không do SaigonOS tạo")
    assert keycloak.client_named("nghi-phep") == before


def test_apply_stops_at_role_taken_after_check(keycloak):
    keycloak.create_role({"name": "nghi-phep.quan-ly", "description": "Của người khác"})

    message = failure(lambda: run(keycloak))

    assert message.startswith("Realm role nghi-phep.quan-ly đã có trong Keycloak nhưng")
    assert keycloak.roles["nghi-phep.quan-ly"]["description"] == "Của người khác"
    assert keycloak.clients == {}


def test_realm_without_role_authenticated_is_reported_before_any_change(keycloak):
    del keycloak.roles["authenticated"]

    message = failure(lambda: run(keycloak))

    assert message == "Realm saigonos không có realm role authenticated."
    assert keycloak.writes == []


def test_realm_without_client_scope_is_reported(keycloak):
    del keycloak.scopes["acr"]
    keycloak.realm_defaults.remove("acr")

    message = failure(lambda: run(keycloak))

    assert message == "Realm saigonos không có client scope acr."


def test_differs_compares_lists_as_sets_and_missing_text_as_empty():
    assert not differs({"a": ["x", "y"], "b": None, "c": {}}, {"a": ["y", "x"], "b": ""})
    assert differs({"a": ["x"]}, {"a": ["x", "y"]})
    assert differs({"a": "x"}, {"a": ["x"]})
    assert differs(None, {"a": True})
    assert not differs({"a": None}, {"a": False})


def removed(keycloak, purge):
    said = []
    changed = remove_keycloak(keycloak, "nghi-phep", purge, said.append)
    return changed, said


def test_remove_deletes_client_and_keeps_roles(keycloak):
    run(keycloak)

    assert removed(keycloak, False) == (True, [CLIENT_REMOVED.format(client="nghi-phep")])
    assert removed(keycloak, False) == (False, [])
    assert keycloak.find_clients(None, "nghi-phep") == []
    assert set(ROLES) <= set(keycloak.roles)


def test_purge_deletes_every_role_owned_by_app(keycloak):
    run(keycloak)
    run(keycloak, manifest(roles=DATA["roles"][:1]))
    keycloak.create_role({"name": "nghi-phep.tu-tao"})
    keycloak.create_role({"name": "nghi-phep-khac.quan-ly", "attributes": {OWNER: ["nghi-phep"]}})

    changed, said = removed(keycloak, True)

    assert changed is True
    assert said == [
        CLIENT_REMOVED.format(client="nghi-phep"),
        *(ROLE_REMOVED.format(role=role) for role in sorted(ROLES)),
    ]
    assert {"nghi-phep.tu-tao", "nghi-phep-khac.quan-ly"} <= set(keycloak.roles)
    assert not set(ROLES) & set(keycloak.roles)


def test_remove_leaves_client_made_by_hand(keycloak):
    keycloak.create_client({"clientId": "nghi-phep"})

    assert removed(keycloak, False) == (False, [])
    assert keycloak.find_clients(None, "nghi-phep") != []


@pytest.fixture
def server():
    state = SimpleNamespace(requests=[], logins=[], replies=[], tokens=0)

    class Handler(BaseHTTPRequestHandler):
        def answer(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            state.requests.append((self.command, self.path, self.headers, body))
            if self.path.endswith("/openid-connect/token"):
                state.tokens += 1
                default = (200, {"access_token": f"token-{state.tokens}"})
                status, data = state.logins.pop(0) if state.logins else default
            else:
                status, data = state.replies.pop(0) if state.replies else (200, {"ok": True})
            content = data if isinstance(data, bytes) else json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        do_GET = do_POST = do_PUT = do_DELETE = answer

        def log_message(self, *details):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    state.url = f"http://127.0.0.1:{httpd.server_port}/auth"
    yield state
    httpd.shutdown()
    httpd.server_close()


def admin(server):
    return Keycloak(server.url, "admin", "mat-khau-quan-tri")


def test_first_call_logs_in_to_master_and_sends_access_token(server):
    keycloak = admin(server)

    data = keycloak.call("GET", "/roles/nghi-phep.quan-ly")

    [(login, login_path, login_headers, form), (method, path, headers, body)] = server.requests
    assert data == {"ok": True}
    assert (login, login_path) == ("POST", "/auth/realms/master/protocol/openid-connect/token")
    assert login_headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert parse_qs(form.decode()) == {
        "grant_type": ["password"],
        "client_id": ["admin-cli"],
        "username": ["admin"],
        "password": ["mat-khau-quan-tri"],
    }
    assert (method, path, body) == (
        "GET",
        "/auth/admin/realms/saigonos/roles/nghi-phep.quan-ly",
        b"",
    )
    assert headers["Authorization"] == "Bearer token-1"
    assert headers["Accept"] == "application/json"
    assert "Content-Type" not in headers


def test_body_is_sent_as_json_and_empty_reply_gives_none(server):
    server.replies.append((204, b""))

    data = admin(server).call(
        "POST", "/roles", {"name": "nghi-phep.quan-ly", "description": "Duyệt"}
    )

    _, path, headers, body = server.requests[-1]
    assert data is None
    assert path == "/auth/admin/realms/saigonos/roles"
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body) == {"name": "nghi-phep.quan-ly", "description": "Duyệt"}


def test_access_token_is_reused_and_renewed_once_after_401(server):
    keycloak = admin(server)
    keycloak.call("GET", "/roles/a")
    server.replies.append((401, {"error": "HTTP 401 Unauthorized"}))

    data = keycloak.call("GET", "/roles/b")

    paths = [request[1].rsplit("/", 1)[-1] for request in server.requests]
    assert data == {"ok": True}
    assert paths == ["token", "a", "b", "token", "b"]
    assert server.requests[-1][2]["Authorization"] == "Bearer token-2"


def test_second_401_is_reported(server):
    server.replies += [(401, {"error": "HTTP 401 Unauthorized"})] * 2

    message = failure(lambda: admin(server).call("PUT", "/clients/x", {"enabled": True}))

    assert message == "Keycloak trả về mã 401 cho lời gọi PUT /clients/x: HTTP 401 Unauthorized."


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        (
            (401, {"error": "invalid_grant", "error_description": "Invalid user credentials"}),
            ": Invalid user credentials.",
        ),
        ((200, {"token_type": "Bearer"}), ': {"token_type": "Bearer"}.'),
        ((502, b"<html>Bad Gateway</html>"), ": <html>Bad Gateway</html>."),
    ],
    ids=["sai-mat-khau", "thieu-token", "khong-phai-json"],
)
def test_refused_login_points_to_admin_password(server, reply, reason):
    server.logins.append(reply)

    message = failure(lambda: admin(server).call("GET", "/roles/a"))

    assert message == (
        f"Không đăng nhập được realm master của Keycloak{reason} Mật khẩu của tài khoản admin "
        "phải trùng giá trị KEYCLOAK_ADMIN_PASSWORD trong file .env."
    )


def test_missing_item_gives_none_only_when_allowed(server):
    server.replies += [(404, {"error": "Could not find role"})] * 2
    keycloak = admin(server)

    found = keycloak.call("GET", "/roles/a", missing_ok=True)
    message = failure(lambda: keycloak.call("GET", "/roles/a"))

    assert found is None
    assert message == "Keycloak trả về mã 404 cho lời gọi GET /roles/a: Could not find role."


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        (
            (409, {"errorMessage": "Client nghi-phep already exists."}),
            ": Client nghi-phep already exists.",
        ),
        ((500, b""), "."),
    ],
    ids=["co-thong-bao", "khong-co-noi-dung"],
)
def test_refused_call_is_reported_with_status(server, reply, reason):
    server.replies.append(reply)

    message = failure(lambda: admin(server).call("POST", "/clients", {"clientId": "nghi-phep"}))

    assert message == f"Keycloak trả về mã {reply[0]} cho lời gọi POST /clients{reason}"


def test_unreachable_keycloak_asks_to_start_system():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    message = failure(
        lambda: Keycloak(f"http://127.0.0.1:{port}/auth", "admin", "x").call("GET", "/roles/a")
    )

    assert message.startswith("Không kết nối được Keycloak: ")
    assert message.endswith(". Hãy khởi động hệ thống bằng lệnh saigonos up rồi chạy lại.")
