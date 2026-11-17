# SPDX-License-Identifier: Apache-2.0
import hashlib
import hmac
import html
import json
import re
import struct
import time
from contextlib import contextmanager
from urllib.parse import parse_qs, urljoin, urlsplit

import pytest

pytestmark = pytest.mark.integration

COCKPIT = "/operaton/app/cockpit/"
CURRENT_USER = "/operaton/api/admin/auth/user/default"
APPS = {"cockpit": "Operaton Cockpit", "tasklist": "Operaton Tasklist", "admin": "Operaton Admin"}
FLOW = "saigonos operaton"
DENIED = "Truy cập bị từ chối"
CLOSED_PATHS = {
    "/operaton/engine-rest/version": 404,
    "/operaton/engine-rest/engine": 404,
    "/operaton/health": 404,
    "/operaton/login": 404,
    "/operaton/logout/connect/back-channel/operaton": 404,
    "/operaton/securityFilterRules.json": 404,
    "/operaton/app/..;/engine-rest/version": 404,
    "/operaton/app/%2e%2e;/engine-rest/version": 404,
    "/operaton/engine-rest;x=1/version": 404,
    "/operaton/app/;/../../engine-rest/version": 404,
    "/operaton/app/%3b/../../engine-rest/version": 404,
    "/operaton/app/%2e%2e/engine-rest/version": 404,
    "//operaton//app/../engine-rest/version": 404,
    "/operaton/api/../engine-rest/version": 404,
}
REDIRECTS = {301, 302, 303, 307}


def totp(secret, step=0):
    counter = struct.pack(">Q", int(time.time() // 30) + step)
    digest = hmac.new(secret.encode(), counter, hashlib.sha1).digest()
    offset = digest[-1] & 15
    code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{code % 1_000_000:06d}"


def form_action(page):
    return html.unescape(re.search(r'action="([^"]+)"', page)[1])


class Browser:
    def __init__(self, stack):
        self.stack = stack
        self.cookies = {}
        self.trail = []

    def open(self, method, url, form=None):
        if url.startswith("/"):
            url = f"{self.stack.url}{url}"
        for _ in range(15):
            cookies = "; ".join(f"{name}={value}" for name, value in self.cookies.items())
            reply = self.stack.call(method, url, form=form, headers={"Cookie": cookies})
            for cookie in reply.headers.get_all("Set-Cookie", []):
                name, value = cookie.split(";", 1)[0].split("=", 1)
                if value:
                    self.cookies[name] = value
                else:
                    self.cookies.pop(name, None)
            self.trail.append((reply.status, url))
            if reply.status not in REDIRECTS:
                return reply.status, url, reply.body.decode(errors="replace")
            url = urljoin(url, reply.headers["Location"])
            method, form = "GET", None
        raise AssertionError(f"Quá nhiều lần chuyển hướng: {self.trail}")

    def log_in(self, user, otp=None):
        status, url, page = self.open("GET", COCKPIT)
        assert "/auth/realms/saigonos/" in url, url
        form = {"username": user.name, "password": user.password}
        status, url, page = self.open("POST", form_action(page), form)
        if "totpSecret" in page:
            otp = html.unescape(re.search(r'name="totpSecret" value="([^"]+)"', page)[1])
            form = {"totpSecret": otp, "totp": totp(otp), "userLabel": "thu"}
            status, url, page = self.open("POST", form_action(page), form)
        elif 'name="otp"' in page:
            status, url, page = self.open("POST", form_action(page), {"otp": totp(otp, 1)})
        return status, url, page, otp

    def current_user(self):
        status, url, body = self.open("GET", CURRENT_USER)
        return json.loads(body) if status == 200 and url.endswith(CURRENT_USER) else None


def operaton_client(stack):
    clients = json.loads(stack.admin("GET", "/clients?clientId=operaton").body)
    assert len(clients) == 1
    return clients[0]


def rest_status(stack, user=None):
    options = ["--silent", "--output", "/dev/null", "--write-out", "%{http_code}"]
    if user:
        options += ["--user", user]
    url = "http://127.0.0.1:8080/operaton/engine-rest/version"
    result = stack.exec("operaton", "curl", *options, url)
    return int(result.stdout)


def process_id(stack, container, name):
    rows = stack.run_docker("top", container, "-eo", "pid,comm").stdout.splitlines()[1:]
    return next(pid for pid, command in (row.split() for row in rows) if command == name)


def core_account(stack):
    return f"core:{stack.env['CORE_OPERATON_PASSWORD']}"


def wait_until_core_account_works(stack, timeout=30):
    deadline = time.monotonic() + timeout
    while rest_status(stack, core_account(stack)) != 200:
        assert time.monotonic() < deadline, "Tài khoản core bị khóa quá lâu"
        time.sleep(1)


def bpmn(key, name="Quy trình thử", history=True):
    time_to_live = ' operaton:historyTimeToLive="P30D"' if history else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:operaton="http://operaton.org/schema/1.0/bpmn"
                  id="{key}_dinh_nghia" targetNamespace="https://saigonos.example/bpmn">
  <bpmn:process id="{key}" name="{name}" isExecutable="true"{time_to_live}>
    <bpmn:startEvent id="bat_dau" />
    <bpmn:sequenceFlow id="luong_1" sourceRef="bat_dau" targetRef="ket_thuc" />
    <bpmn:endEvent id="ket_thuc" />
  </bpmn:process>
</bpmn:definitions>
"""


@contextmanager
def bpmn_files(stack, files):
    folder = stack.home / "config" / "operaton" / "processes"
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    try:
        yield folder
    finally:
        for name in files:
            (folder / name).unlink(missing_ok=True)


def deploy(stack, *options):
    result = stack.compose_result("run", "--rm", "--no-deps", *options, "processes")
    return result.returncode, result.stdout.splitlines(), result.stderr


def operaton_get(stack, path):
    url = f"http://127.0.0.1:8080/operaton/engine-rest{path}"
    result = stack.exec("operaton", "curl", "--silent", "--user", core_account(stack), url)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def versions(stack, key):
    definitions = operaton_get(stack, f"/process-definition?key={key}&sortBy=version&sortOrder=asc")
    return [(item["version"], item["resource"], item["name"]) for item in definitions]


def test_operaton_runs_on_own_database(stack):
    tables = stack.sql(
        "SELECT count(*) FROM pg_database WHERE datname = 'operaton' "
        "AND pg_get_userbyid(datdba) = 'operaton'"
    )
    options = ["psql", "--username=operaton", "--no-psqlrc", "--tuples-only", "--no-align"]
    engine = stack.exec(
        "postgres", *options, "--dbname=operaton", "--command=SELECT 1 FROM act_ge_property LIMIT 1"
    )

    assert tables == [["1"]]
    assert engine.returncode == 0, engine.stderr
    for database in ("saigonos", "keycloak"):
        refused = stack.exec("postgres", *options, f"--dbname={database}", "--command=SELECT 1")
        assert refused.returncode != 0
        assert f'permission denied for database "{database}"' in refused.stderr


def test_admin_with_otp_opens_cockpit_tasklist_and_admin(stack):
    admin = stack.new_user(role="admin")
    browser = Browser(stack)

    status, url, page, otp = browser.log_in(admin)

    assert otp
    assert (status, url) == (200, f"{stack.url}/operaton/app/cockpit/default/")
    assert browser.current_user() == {
        "userId": admin.id,
        "authorizedApps": ["admin", "tasklist", "welcome", "cockpit"],
    }
    for app, title in APPS.items():
        status, url, page = browser.open("GET", f"/operaton/app/{app}/default/")
        assert (status, url) == (200, f"{stack.url}/operaton/app/{app}/default/")
        assert f"<title>{title}</title>" in page
    for path in ("/operaton/lib/deps.js", "/operaton/favicon.ico"):
        assert browser.open("GET", path)[0] == 200


def test_admin_types_otp_code_at_next_login(stack):
    admin = stack.new_user(role="admin")
    _, _, _, otp = Browser(stack).log_in(admin)
    browser = Browser(stack)
    _, _, page = browser.open("GET", COCKPIT)
    form = {"username": admin.name, "password": admin.password}

    _, _, page = browser.open("POST", form_action(page), form)
    asked = 'name="otp"' in page
    status, url, _ = browser.open("POST", form_action(page), {"otp": totp(otp, 1)})

    assert asked
    assert (status, url) == (200, f"{stack.url}/operaton/app/cockpit/default/")
    assert browser.current_user()["userId"] == admin.id


def test_user_without_admin_role_gets_no_session_of_operaton(stack):
    user = stack.new_user()
    browser = Browser(stack)

    status, _, page, _ = browser.log_in(user)
    _, url, _ = browser.open("GET", CURRENT_USER)

    assert status == 401
    assert DENIED in page
    assert url.startswith(f"{stack.url}/auth/realms/saigonos/protocol/openid-connect/auth?")
    assert browser.current_user() is None


def test_logout_ends_session_of_operaton(stack):
    browser = Browser(stack)
    browser.log_in(stack.new_user(role="admin"))
    start = len(browser.trail)

    _, url, _ = browser.open("GET", "/logout")

    assert browser.trail[start] == (302, f"{stack.url}/logout")
    assert url.startswith(f"{stack.url}/auth/realms/saigonos/protocol/openid-connect/auth?")
    assert browser.current_user() is None


def test_login_of_operaton_asks_password_despite_session_of_keycloak(stack):
    browser = Browser(stack)
    browser.log_in(stack.new_user(role="admin"))
    browser.open("GET", "/logout")

    _, _, page = browser.open("GET", COCKPIT)

    assert "KEYCLOAK_IDENTITY" in browser.cookies
    assert 'name="password"' in page
    assert browser.current_user() is None


def test_disabled_admin_loses_session_of_operaton_at_next_call(stack):
    admin = stack.new_user(role="admin")
    browser = Browser(stack)
    browser.log_in(admin)
    assert browser.current_user()["userId"] == admin.id

    assert stack.admin("PUT", f"/users/{admin.id}", {"enabled": False}).status == 204

    assert browser.current_user() is None


@pytest.mark.parametrize(("path", "status"), CLOSED_PATHS.items())
def test_gateway_does_not_open_rest_of_operaton(stack, path, status):
    assert stack.call("GET", f"{stack.url}{path}").status == status


def test_rest_of_operaton_needs_account_of_core(stack):
    account = core_account(stack)

    assert rest_status(stack) == 401
    assert rest_status(stack, account) == 200
    assert rest_status(stack, "core:sai-mat-khau") == 401
    assert rest_status(stack, account) == 401
    wait_until_core_account_works(stack)


def test_operaton_sends_login_to_keycloak_at_saigonos_url(stack):
    reply = stack.call("GET", f"{stack.url}/operaton/oauth2/authorization/operaton")
    location = urlsplit(reply.headers["Location"])
    query = parse_qs(location.query)

    assert reply.status == 302
    assert f"{location.scheme}://{location.netloc}{location.path}" == (
        f"{stack.url}/auth/realms/saigonos/protocol/openid-connect/auth"
    )
    assert query["redirect_uri"] == [f"{stack.url}/operaton/login/oauth2/code/operaton"]
    assert query["code_challenge_method"] == ["S256"]


def test_client_of_operaton_allows_only_login_through_browser(stack):
    client = operaton_client(stack)
    flows = json.loads(stack.admin("GET", "/authentication/flows").body)
    flow = next(flow for flow in flows if flow["alias"] == FLOW)
    form = {
        "grant_type": "password",
        "client_id": "operaton",
        "client_secret": stack.env["OPERATON_CLIENT_SECRET"],
        "username": "admin",
        "password": "khong-dung",
    }
    token = f"{stack.url}/auth/realms/saigonos/protocol/openid-connect/token"

    assert client["publicClient"] is False
    assert client["directAccessGrantsEnabled"] is False
    assert client["implicitFlowEnabled"] is False
    assert client["serviceAccountsEnabled"] is False
    assert client["redirectUris"] == [f"{stack.url}/operaton/login/oauth2/code/operaton"]
    assert client["attributes"]["pkce.code.challenge.method"] == "S256"
    assert client["authenticationFlowBindingOverrides"] == {"browser": flow["id"]}
    assert json.loads(stack.call("POST", token, form=form).body)["error"] == "unauthorized_client"


def test_realm_service_restores_login_flow_and_client_of_operaton(stack):
    executions = json.loads(
        stack.admin("GET", "/authentication/flows/saigonos%20operaton/executions").body
    )
    denial = next(execution for execution in executions if execution.get("authenticationFlow"))
    denial["requirement"] = "DISABLED"
    path = "/authentication/flows/saigonos%20operaton/executions"
    assert stack.admin("PUT", path, denial).status == 204
    client = operaton_client(stack)
    changes = {"directAccessGrantsEnabled": True, "redirectUris": ["*"]}
    assert stack.admin("PUT", f"/clients/{client['id']}", changes).status == 204

    first = stack.up()
    repaired = stack.logs("realm").splitlines()[-3:]
    second = stack.up()

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert repaired == [
        f"Luồng đăng nhập {FLOW} đã bị thay đổi nên được tạo lại",
        f"Đã tạo luồng đăng nhập {FLOW} của realm saigonos",
        "Đã cập nhật client operaton của realm saigonos",
    ]
    assert stack.logs("realm").splitlines()[-1] == "Realm saigonos không cần thay đổi"
    restored = operaton_client(stack)
    assert restored["enabled"] is True
    assert restored["directAccessGrantsEnabled"] is False
    assert restored["redirectUris"] == [f"{stack.url}/operaton/login/oauth2/code/operaton"]
    status, _, page, _ = Browser(stack).log_in(stack.new_user())
    assert (status, DENIED in page) == (401, True)


def test_processes_service_reports_empty_folder(stack):
    folder = stack.home / "config" / "operaton" / "processes"

    code, lines, _ = deploy(stack)

    assert folder.is_dir()
    assert sorted(folder.iterdir()) == []
    assert (code, lines) == (0, ["Không có file BPMN nào"])
    assert "Không có file BPMN nào" in stack.logs("processes").splitlines()


def test_bpmn_file_is_deployed_once_and_again_after_change(stack):
    with bpmn_files(stack, {"thu-nghiem.bpmn": bpmn("thu_nghiem")}) as folder:
        first = deploy(stack)
        second = deploy(stack)
        (folder / "thu-nghiem.bpmn").write_text(
            bpmn("thu_nghiem", name="Quy trình đã sửa"), encoding="utf-8"
        )
        third = deploy(stack)

    deployments = operaton_get(
        stack, "/deployment?name=thu-nghiem.bpmn&sortBy=deploymentTime&sortOrder=asc"
    )
    assert first[:2] == (
        0,
        ["Đã triển khai file thu-nghiem.bpmn: quy trình thu_nghiem, phiên bản 1"],
    )
    assert second[:2] == (0, ["File thu-nghiem.bpmn không thay đổi"])
    assert third[:2] == (
        0,
        ["Đã triển khai file thu-nghiem.bpmn: quy trình thu_nghiem, phiên bản 2"],
    )
    assert versions(stack, "thu_nghiem") == [
        (1, "thu-nghiem.bpmn", "Quy trình thử"),
        (2, "thu-nghiem.bpmn", "Quy trình đã sửa"),
    ]
    assert [(item["name"], item["source"]) for item in deployments] == [
        ("thu-nghiem.bpmn", "saigonos"),
        ("thu-nghiem.bpmn", "saigonos"),
    ]


def test_bpmn_file_without_history_time_to_live_stops_up_until_removed(stack):
    with bpmn_files(stack, {"thieu-ttl.bpmn": bpmn("thieu_ttl", history=False)}):
        failed = stack.up()
        log = stack.logs("processes")
    recovered = stack.up()

    assert failed.returncode != 0
    assert 'service "processes" didn\'t complete successfully' in failed.stderr
    assert "Không triển khai được file thieu-ttl.bpmn: ENGINE-09005" in log
    assert "History Time To Live (TTL) cannot be null" in log
    assert recovered.returncode == 0, recovered.stderr
    assert versions(stack, "thieu_ttl") == []


@pytest.mark.parametrize(
    ("name", "text", "message"),
    [
        (
            "hong.bpmn",
            bpmn("hong")[:200],
            "Không triển khai được file hong.bpmn: ENGINE-09003 Could not parse 'hong.bpmn'.",
        ),
        (
            "quy trình.bpmn",
            bpmn("ten_sai"),
            "Tên file quy trình.bpmn không hợp lệ.",
        ),
        (
            "khong-phai-xml.bpmn",
            "Đây không phải là BPMN",
            "Không triển khai được file khong-phai-xml.bpmn: ENGINE-09003",
        ),
    ],
)
def test_broken_bpmn_file_is_reported_by_name(stack, name, text, message):
    with bpmn_files(stack, {name: text}):
        code, lines, errors = deploy(stack)

    assert code == 1
    assert lines == []
    assert message in errors


def test_bpmn_file_cannot_take_process_of_another_file(stack):
    with bpmn_files(stack, {"chu-quy-trinh.bpmn": bpmn("dung_chung")}):
        owner = deploy(stack)
        intruder = {"file-moi.bpmn": bpmn("dung_chung", name="Bản chiếm quy trình")}
        with bpmn_files(stack, intruder):
            code, lines, errors = deploy(stack)

    assert owner[0] == 0
    assert code == 1
    assert lines == [
        "File chu-quy-trinh.bpmn không thay đổi",
        "Đã triển khai file file-moi.bpmn: quy trình dung_chung, phiên bản 2",
        "Đã gỡ bản triển khai mới của file file-moi.bpmn",
    ]
    assert (
        "Quy trình dung_chung được khai báo trong nhiều file: chu-quy-trinh.bpmn, file-moi.bpmn. "
        "Mỗi quy trình chỉ được khai báo trong một file."
    ) in errors
    assert versions(stack, "dung_chung") == [(1, "chu-quy-trinh.bpmn", "Quy trình thử")]


def test_two_new_files_with_same_process_deploy_nothing(stack):
    files = {"ban-a.bpmn": bpmn("hai_ban"), "ban-b.bpmn": bpmn("hai_ban", name="Bản B")}
    with bpmn_files(stack, files):
        code, lines, errors = deploy(stack)

    assert code == 1
    assert lines == [
        "Đã triển khai file ban-a.bpmn: quy trình hai_ban, phiên bản 1",
        "Đã triển khai file ban-b.bpmn: quy trình hai_ban, phiên bản 2",
        "Đã gỡ bản triển khai mới của file ban-a.bpmn",
        "Đã gỡ bản triển khai mới của file ban-b.bpmn",
    ]
    assert "Quy trình hai_ban được khai báo trong nhiều file: ban-a.bpmn, ban-b.bpmn." in errors
    assert versions(stack, "hai_ban") == []


def test_wrong_password_of_core_costs_one_login_attempt(stack):
    files = {"mat-khau-mot.bpmn": bpmn("mat_khau_mot"), "mat-khau-hai.bpmn": bpmn("mat_khau_hai")}
    query = "--command=SELECT attempts_ FROM act_id_user WHERE id_ = 'core'"
    options = ["psql", "--username=postgres", "--dbname=operaton", "--tuples-only", "--no-align"]
    with bpmn_files(stack, files):
        code, lines, errors = deploy(stack, "--env", "CORE_OPERATON_PASSWORD=sai-mat-khau")
        attempts = stack.exec("postgres", *options, query).stdout.strip()
        wait_until_core_account_works(stack)

    assert code == 1
    assert lines == []
    assert "Operaton từ chối tài khoản core." in errors
    assert attempts == "1"
    assert versions(stack, "mat_khau_mot") == []


def test_removed_bpmn_file_keeps_its_process(stack):
    with bpmn_files(stack, {"go-bo.bpmn": bpmn("go_bo")}):
        deployed = deploy(stack)
    code, lines, _ = deploy(stack)

    assert deployed[0] == 0
    assert (code, lines) == (0, ["Không có file BPMN nào"])
    assert versions(stack, "go_bo") == [(1, "go-bo.bpmn", "Quy trình thử")]


def test_killed_operaton_restarts_by_itself(stack):
    container = stack.container("operaton")
    restarts = int(stack.inspect(container, "{{.RestartCount}}"))
    state = "{{.RestartCount}} {{.State.Health.Status}}"

    stack.kill_process(process_id(stack, container, "java"))

    deadline = time.monotonic() + 180
    while stack.inspect(container, state) != f"{restarts + 1} healthy":
        assert time.monotonic() < deadline, "Operaton chưa khởi động lại"
        time.sleep(1)
    assert rest_status(stack, core_account(stack)) == 200
