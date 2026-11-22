# SPDX-License-Identifier: Apache-2.0
import copy
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from threading import Thread
from types import SimpleNamespace

import pytest

from saigonos_core.app_database import ApplyError
from saigonos_core.app_gateway import (
    OWNER,
    PREFIX,
    ROUTE_CREATED,
    ROUTE_UPDATED,
    UNCHANGED,
    Apisix,
    apply_gateway,
    check_route,
    wanted_route,
)
from saigonos_core.manifest import Manifest

ROUTES = files("saigonos") / "stack" / "config" / "apisix" / "routes"
MANIFEST = Manifest.model_validate(
    {
        "name": "nghi-phep",
        "title": "Nghỉ phép",
        "version": "0.1.0",
        "roles": [{"name": "nghi-phep.nhan-vien", "description": "Gửi đơn"}],
    }
)
ROUTE = "/routes/app-nghi-phep"
DEFAULTS = {
    "limit-count": {"policy": "local", "allow_degradation": False},
    "openid-connect": {"ssl_verify": False, "timeout": 3},
    "proxy-rewrite": {"use_real_request_uri_unsafe": False},
}


class FakeApisix:
    def __init__(self):
        self.calls = []
        self.routes = {}
        self.clock = 0

    def tick(self):
        self.clock += 1
        return self.clock

    def call(self, method, path, body=None, missing_ok=False):
        self.calls.append((method, path))
        route = path.removeprefix("/routes/")
        if method == "GET":
            if route not in self.routes:
                if missing_ok:
                    return None
                raise ApplyError("APISIX trả về mã 404")
            return {"key": f"/apisix/routes/{route}", "value": copy.deepcopy(self.routes[route])}
        assert method == "PUT"
        value = copy.deepcopy(body)
        for plugin, defaults in DEFAULTS.items():
            if plugin in value.get("plugins", {}):
                value["plugins"][plugin] = defaults | value["plugins"][plugin]
        created = self.routes.get(route, {}).get("create_time", self.tick())
        value |= {"id": route, "create_time": created, "update_time": self.tick()}
        self.routes[route] = value
        return {"key": f"/apisix/routes/{route}", "value": copy.deepcopy(value)}


@pytest.fixture
def apisix():
    return FakeApisix()


def said(apisix, manifest=MANIFEST):
    lines = []
    changed = apply_gateway(apisix, manifest, lines.append)
    return changed, lines


def failure(action):
    with pytest.raises(ApplyError) as raised:
        action()
    return str(raised.value)


def test_first_apply_creates_route_for_api_of_app(apisix):
    changed, lines = said(apisix)

    route = apisix.routes["app-nghi-phep"]
    rewrite = route["plugins"]["proxy-rewrite"]
    assert (changed, lines) == (True, [ROUTE_CREATED.format(route="app-nghi-phep")])
    assert route["uris"] == ["/apps/nghi-phep/api", "/apps/nghi-phep/api/*"]
    assert route["labels"] == {OWNER: "nghi-phep"}
    assert (route["status"], route["priority"]) == (1, 0)
    assert rewrite["regex_uri"] == ["^/apps/nghi-phep/api/?(.*)$", "/$1"]
    assert rewrite["headers"] == {
        "set": {"Accept-Profile": "nghi_phep", "Content-Profile": "nghi_phep"}
    }
    assert route["upstream"] == {"type": "roundrobin", "nodes": {"postgrest:3000": 1}}
    assert apisix.calls == [("GET", ROUTE), ("PUT", ROUTE)]


def test_route_checks_token_and_limits_calls_like_api_route():
    api = json.loads((ROUTES / "api.json").read_text())
    plugins = wanted_route(MANIFEST)["plugins"]

    assert set(plugins) == set(api["plugins"])
    for name in ("openid-connect", "limit-count"):
        assert plugins[name] == api["plugins"][name]


def test_apply_again_changes_nothing(apisix):
    said(apisix)

    changed, lines = said(apisix)

    assert (changed, lines) == (False, [UNCHANGED])


@pytest.mark.parametrize(
    "edit",
    [
        lambda route: route["plugins"].pop("openid-connect"),
        lambda route: route["plugins"].update({"key-auth": {}}),
        lambda route: route["plugins"]["limit-count"].update({"count": 100000}),
        lambda route: route["plugins"]["limit-count"].update({"allow_degradation": True}),
        lambda route: route["plugins"]["proxy-rewrite"]["headers"]["set"].update(
            {"Accept-Profile": "core"}
        ),
        lambda route: route.update({"uris": ["/apps/nghi-phep/api/*", "/khac/*"]}),
        lambda route: route.update({"status": 0}),
        lambda route: route.update({"methods": ["GET"]}),
        lambda route: route["upstream"]["nodes"].update({"core:8000": 1}),
    ],
    ids=[
        "bo-kiem-tra-token",
        "them-plugin",
        "doi-gioi-han",
        "doi-gia-tri-mac-dinh",
        "doi-schema",
        "them-dia-chi",
        "tat-route",
        "gioi-han-phuong-thuc",
        "them-upstream",
    ],
)
def test_route_edited_by_hand_is_put_back(apisix, edit):
    said(apisix)
    first = copy.deepcopy(apisix.routes["app-nghi-phep"])
    edit(apisix.routes["app-nghi-phep"])

    changed, lines = said(apisix)

    restored = apisix.routes["app-nghi-phep"]
    assert (changed, lines) == (True, [ROUTE_UPDATED.format(route="app-nghi-phep")])
    assert {key: value for key, value in restored.items() if key != "update_time"} == {
        key: value for key, value in first.items() if key != "update_time"
    }


@pytest.mark.parametrize("labels", [None, {}, {OWNER: "nghi-phep-khac"}])
def test_route_not_made_for_app_is_not_taken_over(apisix, labels):
    apisix.routes["app-nghi-phep"] = {"uris": ["/khac/*"]} | (
        {} if labels is None else {"labels": labels}
    )
    expected = (
        "Route app-nghi-phep đã có trong APISIX nhưng không do SaigonOS tạo "
        "cho ứng dụng nghi-phep. Hãy đặt tên khác cho ứng dụng."
    )

    checked = failure(lambda: check_route(apisix, MANIFEST))
    applied = failure(lambda: said(apisix))

    assert checked == applied == expected
    assert ("PUT", ROUTE) not in apisix.calls
    assert apisix.routes["app-nghi-phep"]["uris"] == ["/khac/*"]


def test_check_route_passes_for_missing_route_and_route_of_app(apisix):
    check_route(apisix, MANIFEST)
    said(apisix)

    check_route(apisix, MANIFEST)

    assert apisix.calls.count(("GET", ROUTE)) == 3


def test_route_ids_of_core_never_start_with_prefix_of_apps():
    names = [path.name.removesuffix(".json") for path in ROUTES.iterdir()]

    assert names
    assert not [name for name in names if name.startswith(PREFIX)]


@pytest.fixture
def server():
    state = SimpleNamespace(requests=[], replies=[])

    class Handler(BaseHTTPRequestHandler):
        def answer(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            state.requests.append((self.command, self.path, self.headers, body))
            status, data = state.replies.pop(0) if state.replies else (200, {"value": {}})
            content = data if isinstance(data, bytes) else json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        do_GET = do_PUT = answer

        def log_message(self, *details):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    state.url = f"http://127.0.0.1:{httpd.server_port}"
    yield state
    httpd.shutdown()
    httpd.server_close()


def admin(server):
    return Apisix(server.url, "khoa-quan-tri")


def test_call_sends_admin_key_and_json_body(server):
    data = admin(server).call("PUT", "/routes/app-x", {"uris": ["/apps/x/api/*"]})

    [(method, path, headers, body)] = server.requests
    assert data == {"value": {}}
    assert (method, path) == ("PUT", "/apisix/admin/routes/app-x")
    assert headers["X-API-KEY"] == "khoa-quan-tri"
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body) == {"uris": ["/apps/x/api/*"]}


def test_get_sends_no_body(server):
    admin(server).call("GET", "/routes/app-x")

    [(method, _, headers, body)] = server.requests
    assert (method, body) == ("GET", b"")
    assert "Content-Type" not in headers


def test_missing_route_gives_none_only_when_allowed(server):
    server.replies += [(404, {"message": "Key not found"})] * 2
    apisix = admin(server)

    found = apisix.call("GET", "/routes/app-x", missing_ok=True)
    message = failure(lambda: apisix.call("GET", "/routes/app-x"))

    assert found is None
    assert message == "APISIX trả về mã 404 cho lời gọi GET /routes/app-x: Key not found."


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        ((400, {"error_msg": "invalid configuration: uris"}), ": invalid configuration: uris."),
        ((401, {"message": "failed to check token"}), ": failed to check token."),
        ((502, b"<html>Bad Gateway</html>"), ": <html>Bad Gateway</html>."),
        ((500, b""), "."),
    ],
    ids=["cau-hinh-sai", "sai-khoa", "khong-phai-json", "khong-co-noi-dung"],
)
def test_refused_call_is_reported_with_status(server, reply, reason):
    server.replies.append(reply)

    message = failure(lambda: admin(server).call("PUT", "/routes/app-x", {}))

    assert message == f"APISIX trả về mã {reply[0]} cho lời gọi PUT /routes/app-x{reason}"


def test_unreachable_apisix_asks_to_start_system():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    message = failure(lambda: Apisix(f"http://127.0.0.1:{port}", "x").call("GET", "/routes/a"))

    assert message.startswith("Không kết nối được Admin API của APISIX: ")
    assert message.endswith(". Hãy khởi động hệ thống bằng lệnh saigonos up rồi chạy lại.")
