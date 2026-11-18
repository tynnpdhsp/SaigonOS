# SPDX-License-Identifier: Apache-2.0
import hashlib
import hmac
import html
import json
import re
import struct
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

import pytest

from saigonos_core.steps import POLL

pytestmark = pytest.mark.integration

COCKPIT = "/operaton/app/cockpit/"
CURRENT_USER = "/operaton/api/admin/auth/user/default"
APPS = {"cockpit": "Operaton Cockpit", "tasklist": "Operaton Tasklist", "admin": "Operaton Admin"}
FLOW = "saigonos operaton"
DENIED = "Chỉ tài khoản quản trị mới vào được trang này."
ADMIN_ONLY = "saigonos-operaton-admin-only"
ADMIN_ONLY_EN = "Only administrator accounts can open this page."
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
TEST_PROCESS = Path(__file__).parent / "processes" / "yeu-cau-thu.bpmn"
TEST_FUNCTIONS = TEST_PROCESS.with_suffix(".sql")
DEADLINE_PROCESS = TEST_PROCESS.with_name("yeu-cau-co-han-thu.bpmn")
TOPIC = "saigonos-function"
STEPS = {
    "nguoi_chay_thu": "thu_nghiem.nguoi_chay",
    "chua_khai_thu": "thu_nghiem.chua_khai",
    "cong_khai_thu": "thu_nghiem.cong_khai",
    "khong_co_ham_thu": "thu_nghiem.khong_co",
    "sai_tham_so_thu": "thu_nghiem.nhan_chuoi",
    "sai_kieu_tra_ve_thu": "thu_nghiem.tra_chuoi",
    "ten_sai_thu": "Thu_Nghiem.Ghi",
    "thieu_ham_thu": None,
    "ghi_initiator_thu": "thu_nghiem.ghi_initiator",
    "loi_lan_dau_thu": "thu_nghiem.loi_lan_dau",
    "luon_loi_thu": "thu_nghiem.luon_loi",
    "doi_role_thu": "thu_nghiem.doi_role",
    "cham_thu": "thu_nghiem.cham",
}
STARTER = "nguoi-gui"
WORKER = "nhan-vien"
MANAGER = "quan-ly"
VIETNAM = timezone(timedelta(hours=7))
FORBIDDEN = {"detail": "Người gọi không có realm role được bắt đầu quy trình này"}
NO_TASKS = {"detail": "Chưa lấy được danh sách việc vì Operaton chưa sẵn sàng"}
TASK_NOT_FOUND = {"detail": "Không tìm thấy việc"}
NOT_CANDIDATE = {"detail": "Người gọi không có realm role nằm trong nhóm ứng viên của việc này"}
TAKEN = {"detail": "Việc đã có người khác nhận"}
NOT_ASSIGNEE = {"detail": "Chỉ người nhận việc mới hoàn thành được việc này"}
TASK_SUSPENDED = {"detail": "Việc đang tạm ngưng"}
INITIATORS = ("initiator", "nguoi_tao")
REQUEST = {"noi_dung": "Máy 12 không lên màn hình"}
RESULT = {"ket_qua": "Đã thay cáp màn hình"}
STEP_FIELDS = {
    "ma": "string",
    "cho": "long",
    "noi_dung": "string",
    "so_luong": "long",
    "khan": "boolean",
    "ghi_chu": "string",
    "han_xu_ly": "date",
}
ROUNDS = 20


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


def realm_text(stack, method, locale, text=None):
    reply = stack.master_login("admin", stack.env["KEYCLOAK_ADMIN_PASSWORD"])
    token = json.loads(reply.body)["access_token"]
    url = f"{stack.keycloak}/admin/realms/saigonos/localization/{locale}"
    if method == "GET":
        return json.loads(stack.call("GET", url, token=token).body).get(ADMIN_ONLY)
    headers = {"Content-Type": "text/plain; charset=utf-8"}
    content = None if text is None else text.encode()
    return stack.call(method, f"{url}/{ADMIN_ONLY}", token=token, headers=headers, content=content)


def run_realm(stack):
    result = stack.compose_result("run", "--rm", "--no-deps", "realm")
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


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


def bpmn(key, name="Quy trình thử", history="P30D", starters=None):
    time_to_live = f' operaton:historyTimeToLive="{history}"' if history else ""
    if starters is not None:
        time_to_live += f' operaton:candidateStarterGroups="{starters}"'
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


def operaton_text(stack, path):
    url = f"http://127.0.0.1:8080/operaton/engine-rest{path}"
    result = stack.exec("operaton", "curl", "--silent", "--user", core_account(stack), url)
    assert result.returncode == 0, result.stderr
    return result.stdout


def operaton_get(stack, path):
    return json.loads(operaton_text(stack, path))


def versions(stack, key):
    definitions = operaton_get(stack, f"/process-definition?key={key}&sortBy=version&sortOrder=asc")
    return [(item["version"], item["resource"], item["name"]) for item in definitions]


def operaton_send(stack, method, path, body):
    url = f"http://127.0.0.1:8080/operaton/engine-rest{path}"
    options = ["--silent", "--output", "/dev/null", "--write-out", "%{http_code}"]
    options += ["--user", core_account(stack), "--header", "Content-Type: application/json"]
    options += ["--request", method, "--data", json.dumps(body)]
    result = stack.exec("operaton", "curl", *options, url)
    return int(result.stdout)


def operaton_post(stack, path, body):
    url = f"http://127.0.0.1:8080/operaton/engine-rest{path}"
    options = ["--silent", "--fail", "--user", core_account(stack)]
    options += ["--header", "Content-Type: application/json", "--data", json.dumps(body)]
    result = stack.exec("operaton", "curl", *options, url)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def started_count(stack, key):
    return operaton_get(stack, f"/history/process-instance/count?processDefinitionKey={key}")[
        "count"
    ]


def variables_of(stack, instance):
    found = operaton_get(stack, f"/process-instance/{instance}/variables")
    return {name: item["value"] for name, item in found.items()}


def start(stack, user, key="yeu_cau_thu", variables=None):
    url = f"{stack.url}/core/processes/{key}/start"
    body = {} if variables is None else {"variables": variables}
    reply = stack.call("POST", url, token=stack.token(user), body=body)
    return reply.status, json.loads(reply.body)


def tasks_of(stack, user, query=""):
    reply = stack.call("GET", f"{stack.url}/core/tasks{query}", token=stack.token(user))
    return reply.status, json.loads(reply.body)


def act(stack, token, task, action, variables=None):
    body = None if variables is None else {"variables": variables}
    reply = stack.call("POST", f"{stack.url}/core/tasks/{task}/{action}", token=token, body=body)
    return reply.status, json.loads(reply.body) if reply.body else None


def task_of(stack, instance):
    [task] = operaton_get(stack, f"/task?processInstanceId={instance}")
    return task["id"]


def new_tasks(stack, starter, count=1):
    token = stack.token(starter)
    url = f"{stack.url}/core/processes/yeu_cau_thu/start"
    instances = []
    for _ in range(count):
        reply = stack.call("POST", url, token=token, body={"variables": REQUEST})
        assert reply.status == 201, reply.body
        instances.append(json.loads(reply.body)["id"])
    found = operaton_get(stack, "/task?processDefinitionKey=yeu_cau_thu")
    tasks = {task["processInstanceId"]: task["id"] for task in found}
    return [tasks[instance] for instance in instances]


def assignees(stack, tasks):
    found = operaton_get(stack, "/task?processDefinitionKey=yeu_cau_thu")
    return {task["id"]: task["assignee"] for task in found if task["id"] in tasks}


def by_status(replies):
    return sorted(replies, key=lambda reply: reply[0])


def together(calls):
    barrier = threading.Barrier(len(calls))

    def run(call):
        barrier.wait()
        return call()

    with ThreadPoolExecutor(len(calls)) as pool:
        return list(pool.map(run, calls))


def through_paused_operaton(stack, calls):
    with ThreadPoolExecutor(len(calls)) as pool:
        stack.compose("pause", "operaton")
        try:
            futures = [pool.submit(call) for call in calls]
            time.sleep(1)
        finally:
            stack.compose("unpause", "operaton")
        return [future.result() for future in futures]


def refused_by_operaton(stack, task):
    lines = stack.logs("operaton").splitlines()
    return any("ENGINE-REST-HTTP500" in line and task in line for line in lines)


def restore_core(stack):
    wait_until_core_account_works(stack)
    stack.compose("restart", "core")
    stack.wait_until_answers("/core/health")


def wait_for(found, message, timeout=30):
    deadline = time.monotonic() + timeout
    while not (value := found()):
        assert time.monotonic() < deadline, message
        time.sleep(0.5)
    return value


def finished(stack, instance):
    def state():
        found = operaton_get(stack, f"/history/process-instance/{instance}")["state"]
        return None if found == "ACTIVE" else found

    return wait_for(state, f"Quy trình {instance} chưa kết thúc")


def incident_of(stack, instance):
    path = f"/incident?processInstanceId={instance}"
    [incident] = wait_for(
        lambda: operaton_get(stack, path), f"Quy trình {instance} chưa có incident"
    )
    return incident


def step_of(stack, instance):
    [step] = operaton_get(stack, f"/external-task?processInstanceId={instance}")
    return step


def failed_step(stack, instance):
    def step():
        found = step_of(stack, instance)
        return found if found["errorMessage"] else None

    return wait_for(step, f"Bước máy của quy trình {instance} chưa báo lỗi")


def written(stack, instance):
    found = operaton_get(stack, f"/history/variable-instance?processInstanceId={instance}")
    return {item["name"]: item["value"] for item in found}


def cancel(stack, instance):
    assert operaton_send(stack, "DELETE", f"/process-instance/{instance}", {}) == 204


def instant(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f%z")


def start_with_deadline(stack, seconds, code=None):
    due = datetime.now(UTC) + timedelta(seconds=seconds)
    due = due.replace(microsecond=due.microsecond // 1000 * 1000)
    variables = REQUEST | {"han_xu_ly": due.isoformat(timespec="milliseconds")}
    if code:
        variables["ma_yeu_cau"] = code
    status, started = start(stack, stack.new_user(role=STARTER), "yeu_cau_co_han_thu", variables)
    assert status == 201, started
    return started["id"], due


def escalated(stack, instance):
    path = f"/task?processInstanceId={instance}&taskDefinitionKey=xu_ly_qua_han"
    [task] = wait_for(
        lambda: operaton_get(stack, path), f"Việc của quy trình {instance} chưa sang nhóm quản lý"
    )
    return task


def in_night_window(moment):
    night = moment.astimezone(VIETNAM).replace(hour=1, minute=0, second=0, microsecond=0)
    return night <= moment <= night + timedelta(hours=4)


def step_bpmn(key, function):
    properties = ""
    if function:
        properties = f"""
      <bpmn:extensionElements>
        <operaton:properties>
          <operaton:property name="function" value="{function}" />
        </operaton:properties>
      </bpmn:extensionElements>"""
    fields = "".join(
        f'<operaton:formField id="{name}" type="{kind}" />' for name, kind in STEP_FIELDS.items()
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:operaton="http://operaton.org/schema/1.0/bpmn"
                  id="{key}_dinh_nghia" targetNamespace="https://saigonos.example/bpmn">
  <bpmn:process id="{key}" isExecutable="true" operaton:historyTimeToLive="P30D"
                operaton:candidateStarterGroups="{STARTER}">
    <bpmn:startEvent id="bat_dau" operaton:initiator="nguoi_tao">
      <bpmn:extensionElements>
        <operaton:formData>{fields}</operaton:formData>
      </bpmn:extensionElements>
    </bpmn:startEvent>
    <bpmn:sequenceFlow id="luong_1" sourceRef="bat_dau" targetRef="buoc_may" />
    <bpmn:serviceTask id="buoc_may" operaton:type="external" operaton:topic="{TOPIC}">{properties}
    </bpmn:serviceTask>
    <bpmn:sequenceFlow id="luong_2" sourceRef="buoc_may" targetRef="ket_thuc" />
    <bpmn:endEvent id="ket_thuc" />
  </bpmn:process>
</bpmn:definitions>
"""


@pytest.fixture(scope="module")
def requests_process(stack):
    stack.add_migration("9101_yeu_cau_thu.sql", TEST_FUNCTIONS.read_text(encoding="utf-8"))
    migrated = stack.compose_result("run", "--rm", "--no-deps", "migrate")
    assert migrated.returncode == 0, migrated.stderr
    with bpmn_files(stack, {TEST_PROCESS.name: TEST_PROCESS.read_text(encoding="utf-8")}):
        code, _, errors = deploy(stack)
    assert code == 0, errors
    return "yeu_cau_thu"


@pytest.fixture(scope="module")
def machine_steps(stack, requests_process):
    files = {f"{key.replace('_', '-')}.bpmn": step_bpmn(key, name) for key, name in STEPS.items()}
    with bpmn_files(stack, files):
        code, _, errors = deploy(stack)
    assert code == 0, errors


@pytest.fixture(scope="module")
def deadline_process(stack, requests_process):
    with bpmn_files(stack, {DEADLINE_PROCESS.name: DEADLINE_PROCESS.read_text(encoding="utf-8")}):
        code, _, errors = deploy(stack)
    assert code == 0, errors
    return "yeu_cau_co_han_thu"


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
    restore_core(stack)


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


def test_realm_service_restores_message_for_users_without_admin_role(stack):
    path = "/authentication/flows/saigonos%20operaton/executions"
    executions = json.loads(stack.admin("GET", path).body)
    deny = next(
        item for item in executions if item.get("providerId") == "deny-access-authenticator"
    )
    config_path = f"/authentication/config/{deny['authenticationConfig']}"
    config = json.loads(stack.admin("GET", config_path).body)
    config["config"]["denyErrorMessage"] = "access-denied"
    assert stack.admin("PUT", config_path, config).status == 204

    lines = run_realm(stack)
    status, _, page, _ = Browser(stack).log_in(stack.new_user())

    assert f"Luồng đăng nhập {FLOW} đã bị thay đổi nên được tạo lại" in lines
    assert (status, DENIED in page) == (401, True)


def test_realm_service_adds_missing_message_and_keeps_edited_one(stack):
    edited = "Trang này dành cho quản trị viên."
    assert realm_text(stack, "PUT", "vi", edited).status == 204
    assert realm_text(stack, "DELETE", "en").status == 204
    try:
        lines = run_realm(stack)
        texts = {locale: realm_text(stack, "GET", locale) for locale in ("vi", "en")}
        status, _, page, _ = Browser(stack).log_in(stack.new_user())
    finally:
        realm_text(stack, "PUT", "vi", DENIED)

    assert f"Đã thêm thông báo {ADMIN_ONLY} (en) vào realm saigonos" in lines
    assert f"Đã thêm thông báo {ADMIN_ONLY} (vi) vào realm saigonos" not in lines
    assert texts == {"vi": edited, "en": ADMIN_ONLY_EN}
    assert (status, edited in page) == (401, True)


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
    ids=["xml-hong", "ten-file-sai", "khong-phai-xml"],
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
        restore_core(stack)

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


def test_user_with_starter_role_starts_process_with_initiator_from_token(stack, requests_process):
    user = stack.new_user(role=STARTER)
    variables = {"noi_dung": "Máy 12 không lên màn hình", "so_luong": 2, "khan": True}

    status, started = start(stack, user, variables=variables)

    assert status == 201, started
    assert (started["process_key"], started["version"]) == (requests_process, 1)
    assert variables_of(stack, started["id"]) == variables | {
        "initiator": user.id,
        "nguoi_tao": user.id,
    }


@pytest.mark.parametrize("name", ["initiator", "nguoi_tao"])
def test_caller_cannot_send_variable_of_initiator(stack, requests_process, name):
    user = stack.new_user(role=STARTER)
    before = started_count(stack, requests_process)

    status, reply = start(stack, user, variables={name: "nguoi-khac"})

    assert status == 422
    assert reply["detail"].startswith(f"Biến {name} do service core ghi bằng mã người gọi.")
    assert started_count(stack, requests_process) == before


@pytest.mark.parametrize(
    "variables",
    [{}, {"noi_dung": ""}, {"noi_dung": " \t\n "}],
    ids=["thieu", "rong", "khoang-trang"],
)
def test_start_without_required_field_is_compliance_error(stack, requests_process, variables):
    before = started_count(stack, requests_process)

    status, reply = start(
        stack, stack.new_user(role=STARTER), variables=variables | {"so_luong": 2}
    )

    assert (status, reply) == (422, {"detail": "LỖI TUÂN THỦ: Phải nhập Nội dung (noi_dung)"})
    assert started_count(stack, requests_process) == before


def test_start_form_gives_variables_types_of_fields(stack, requests_process):
    variables = REQUEST | {"so_luong": 2, "khan": False, "muc_uu_tien": "cao"}

    status, started = start(
        stack,
        stack.new_user(role=STARTER),
        variables=variables | {"han_xu_ly": "2026-11-20T09:00:00+07:00"},
    )

    found = operaton_get(stack, f"/process-instance/{started['id']}/variables")
    assert status == 201
    assert {
        name: (item["type"], item["value"])
        for name, item in found.items()
        if name not in INITIATORS
    } == {
        "noi_dung": ("String", REQUEST["noi_dung"]),
        "so_luong": ("Long", 2),
        "khan": ("Boolean", False),
        "muc_uu_tien": ("String", "cao"),
        "han_xu_ly": ("Date", "2026-11-20T02:00:00.000+0000"),
    }


@pytest.mark.parametrize(
    ("variables", "detail"),
    [
        ({"ghi_chu": "x"}, "Form bắt đầu của quy trình không nhận biến ghi_chu"),
        ({"noi_dung": "x" * 201}, "LỖI TUÂN THỦ: Nội dung (noi_dung) không được dài quá 200 ký tự"),
        ({"so_luong": 0}, "LỖI TUÂN THỦ: Số lượng (so_luong) không được nhỏ hơn 1"),
        ({"so_luong": "2"}, "LỖI TUÂN THỦ: Số lượng (so_luong) phải là số nguyên"),
        ({"khan": "true"}, "LỖI TUÂN THỦ: Khẩn (khan) phải là true hoặc false"),
        (
            {"muc_uu_tien": "vua"},
            "LỖI TUÂN THỦ: Mức ưu tiên (muc_uu_tien) phải là một trong các giá trị cao, thap",
        ),
        (
            {"han_xu_ly": "20/11/2026"},
            "LỖI TUÂN THỦ: Hạn xử lý (han_xu_ly) phải là ngày giờ theo ISO 8601 có múi giờ. "
            "Ví dụ: 2026-11-20T09:00:00+07:00",
        ),
    ],
    ids=[
        "khong-co-trong-form",
        "qua-dai",
        "qua-nho",
        "so-dang-chuoi",
        "chuoi-true",
        "enum",
        "ngay",
    ],
)
def test_start_refuses_values_outside_start_form(stack, requests_process, variables, detail):
    before = started_count(stack, requests_process)

    status, reply = start(stack, stack.new_user(role=STARTER), variables=REQUEST | variables)

    assert (status, reply) == (422, {"detail": detail})
    assert started_count(stack, requests_process) == before


def test_user_without_starter_role_cannot_start_process(stack, requests_process):
    user = stack.new_user(role=WORKER)
    before = started_count(stack, requests_process)

    assert start(stack, user) == (403, FORBIDDEN)
    assert started_count(stack, requests_process) == before


def test_process_without_candidate_starter_groups_cannot_be_started(stack):
    user = stack.new_user(role=STARTER)
    stack.grant_role(user, WORKER)
    with bpmn_files(stack, {"khong-ai-bat-dau.bpmn": bpmn("khong_ai_bat_dau")}):
        assert deploy(stack)[0] == 0

    assert start(stack, user, key="khong_ai_bat_dau") == (403, FORBIDDEN)
    assert started_count(stack, "khong_ai_bat_dau") == 0


def test_start_follows_latest_version_of_process(stack):
    with bpmn_files(stack, {"phien-ban.bpmn": bpmn("phien_ban", starters="nhom-cu")}) as folder:
        first = deploy(stack)
        newer = bpmn("phien_ban", name="Bản mới", starters="nhom-moi, nhom-khac")
        (folder / "phien-ban.bpmn").write_text(newer, encoding="utf-8")
        second = deploy(stack)

    refused = start(stack, stack.new_user(role="nhom-cu"), key="phien_ban")
    status, started = start(stack, stack.new_user(role="nhom-moi"), key="phien_ban")

    assert (first[0], second[0]) == (0, 0)
    assert refused == (403, FORBIDDEN)
    assert (status, started["version"]) == (201, 2)


def test_unknown_process_is_not_found(stack):
    assert start(stack, stack.new_user(role=STARTER), key="khong_co") == (
        404,
        {"detail": "Không tìm thấy quy trình khong_co"},
    )


def test_task_list_shows_own_tasks_and_claimable_tasks_of_caller_only(stack, requests_process):
    starter = stack.new_user(role=STARTER)
    worker = stack.new_user(role=WORKER)
    taker = stack.new_user()
    instances = [start(stack, starter, variables=REQUEST)[1]["id"] for _ in range(3)]
    found = operaton_get(stack, f"/task?processDefinitionKey={requests_process}")
    first, second, third = (
        next(task["id"] for task in found if task["processInstanceId"] == instance)
        for instance in instances
    )
    other_worker = stack.new_user(role=WORKER)

    assert operaton_send(stack, "POST", f"/task/{first}/claim", {"userId": taker.id}) == 204
    assert operaton_send(stack, "POST", f"/task/{second}/claim", {"userId": other_worker.id}) == 204
    seen = {}
    for name, user in {"worker": worker, "taker": taker, "starter": starter}.items():
        status, tasks = tasks_of(stack, user)
        assert status == 200, tasks
        seen[name] = [task for task in tasks if task["process_instance_id"] in instances]
    assert [task["id"] for task in seen["worker"]] == [third]
    assert [(task["id"], task["assignee"]) for task in seen["taker"]] == [(first, taker.id)]
    assert seen["starter"] == []
    assert seen["worker"][0] | {"created": None} == {
        "id": third,
        "name": "Xử lý yêu cầu",
        "description": None,
        "assignee": None,
        "created": None,
        "due": None,
        "priority": 50,
        "task_key": "xu_ly",
        "process_instance_id": instances[2],
        "process_definition_id": found[0]["processDefinitionId"],
        "suspended": False,
    }
    assert len(tasks_of(stack, worker, "?limit=1")[1]) == 1
    assert tasks_of(stack, stack.new_user()) == (200, [])


def test_worker_claims_and_completes_task_until_process_ends(stack, requests_process):
    starter = stack.new_user(role=STARTER)
    worker = stack.new_user(role=WORKER)
    status, started = start(stack, starter, variables={"noi_dung": "Máy 12 không lên màn hình"})
    task = task_of(stack, started["id"])
    token = stack.token(worker)

    claimed = act(stack, token, task, "claim")
    again = act(stack, token, task, "claim")
    listed = [item["assignee"] for item in tasks_of(stack, worker)[1] if item["id"] == task]
    done = act(stack, token, task, "complete", {"ket_qua": "Đã thay cáp màn hình", "so_gio": 2})

    assert status == 201
    assert (claimed, again, listed, done) == ((204, None), (204, None), [worker.id], (204, None))
    assert finished(stack, started["id"]) == "COMPLETED"
    history = operaton_get(stack, f"/history/task?processInstanceId={started['id']}")
    assert [(item["assignee"], item["deleteReason"]) for item in history] == [
        (worker.id, "completed")
    ]
    assert written(stack, started["id"]) == {
        "noi_dung": "Máy 12 không lên màn hình",
        "initiator": starter.id,
        "nguoi_tao": starter.id,
        "ket_qua": "Đã thay cáp màn hình",
        "so_gio": 2,
        "da_cap_nhat": False,
    }
    assert act(stack, token, task, "complete") == (404, TASK_NOT_FOUND)
    assert act(stack, token, task, "claim") == (404, TASK_NOT_FOUND)


def test_two_workers_claiming_same_task_together_get_one_claim(stack, requests_process):
    workers = [stack.new_user(role=WORKER) for _ in range(2)]
    tasks = new_tasks(stack, stack.new_user(role=STARTER), ROUNDS)
    tokens = [stack.token(worker) for worker in workers]

    rounds = [
        together([partial(act, stack, token, task, "claim") for token in tokens]) for task in tasks
    ]

    held = assignees(stack, tasks)
    for task, replies in zip(tasks, rounds, strict=True):
        assert by_status(replies) == [(204, None), (409, TAKEN)]
        winner = workers[[status for status, _ in replies].index(204)]
        assert held[task] == winner.id


def test_claim_refused_inside_operaton_gives_409_to_loser(stack, requests_process):
    workers = [stack.new_user(role=WORKER) for _ in range(2)]
    [task] = new_tasks(stack, stack.new_user(role=STARTER))
    tokens = [stack.token(worker) for worker in workers]

    replies = through_paused_operaton(
        stack, [partial(act, stack, token, task, "claim") for token in tokens]
    )

    assert by_status(replies) == [(204, None), (409, TAKEN)]
    winner = workers[[status for status, _ in replies].index(204)]
    assert assignees(stack, [task]) == {task: winner.id}
    assert refused_by_operaton(stack, task)


def test_same_worker_claiming_twice_together_gets_task(stack, requests_process):
    worker = stack.new_user(role=WORKER)
    [task] = new_tasks(stack, stack.new_user(role=STARTER))
    token = stack.token(worker)

    replies = through_paused_operaton(stack, [partial(act, stack, token, task, "claim")] * 2)

    assert replies == [(204, None), (204, None)]
    assert assignees(stack, [task]) == {task: worker.id}


def test_task_completed_twice_together_is_completed_once(stack, requests_process):
    worker = stack.new_user(role=WORKER)
    [task] = new_tasks(stack, stack.new_user(role=STARTER))
    token = stack.token(worker)
    assert act(stack, token, task, "claim") == (204, None)
    completion = partial(act, stack, token, task, "complete", RESULT)

    replies = through_paused_operaton(stack, [completion] * 2)

    assert by_status(replies) == [(204, None), (404, TASK_NOT_FOUND)]
    [history] = operaton_get(stack, f"/history/task?taskId={task}")
    assert (history["assignee"], history["deleteReason"]) == (worker.id, "completed")


def test_user_outside_candidate_groups_cannot_claim_or_complete(stack, requests_process):
    worker = stack.new_user(role=WORKER)
    outsider = stack.new_user(role=STARTER)
    stack.grant_role(outsider, "quan-ly")
    [task] = new_tasks(stack, outsider)
    token = stack.token(outsider)

    before = act(stack, token, task, "claim"), act(stack, token, task, "complete")
    claimed = act(stack, stack.token(worker), task, "claim")
    after = act(stack, token, task, "claim"), act(stack, token, task, "complete")

    assert before == ((403, NOT_CANDIDATE), (403, NOT_ASSIGNEE))
    assert claimed == (204, None)
    assert after == ((403, NOT_CANDIDATE), (403, NOT_ASSIGNEE))
    assert assignees(stack, [task]) == {task: worker.id}


def test_worker_cannot_take_or_complete_task_claimed_by_another(stack, requests_process):
    first, second = (stack.new_user(role=WORKER) for _ in range(2))
    [task] = new_tasks(stack, stack.new_user(role=STARTER))
    token = stack.token(second)

    claimed = act(stack, stack.token(first), task, "claim")
    taken = act(stack, token, task, "claim")
    refused = act(stack, token, task, "complete", RESULT)

    assert (claimed, taken, refused) == ((204, None), (409, TAKEN), (403, NOT_ASSIGNEE))
    assert assignees(stack, [task]) == {task: first.id}


def test_assignee_cannot_overwrite_initiator_when_completing(stack, requests_process):
    starter = stack.new_user(role=STARTER)
    worker = stack.new_user(role=WORKER)
    _, started = start(stack, starter, variables=REQUEST)
    task = task_of(stack, started["id"])
    token = stack.token(worker)
    assert act(stack, token, task, "claim") == (204, None)

    replies = [act(stack, token, task, "complete", {name: worker.id}) for name in INITIATORS]

    assert [status for status, _ in replies] == [422, 422]
    assert variables_of(stack, started["id"]) == REQUEST | dict.fromkeys(INITIATORS, starter.id)
    assert assignees(stack, [task]) == {task: worker.id}


def test_completion_outside_task_form_keeps_task_with_assignee(stack, requests_process):
    worker = stack.new_user(role=WORKER)
    _, started = start(stack, stack.new_user(role=STARTER), variables=REQUEST)
    instance = started["id"]
    task = task_of(stack, instance)
    token = stack.token(worker)
    assert act(stack, token, task, "claim") == (204, None)
    before = variables_of(stack, instance)
    attempts = [
        ({}, "LỖI TUÂN THỦ: Phải nhập Kết quả (ket_qua)"),
        ({"ket_qua": ""}, "LỖI TUÂN THỦ: Phải nhập Kết quả (ket_qua)"),
        ({"ket_qua": " \t\n "}, "LỖI TUÂN THỦ: Phải nhập Kết quả (ket_qua)"),
        (
            {"ket_qua": "     Đã xong     "},
            "LỖI TUÂN THỦ: Kết quả (ket_qua) phải có ít nhất 10 ký tự",
        ),
        (RESULT | {"so_gio": 1.5}, "LỖI TUÂN THỦ: Số giờ (so_gio) phải là số nguyên"),
        (RESULT | {"noi_dung": "Sửa nội dung"}, "Form của việc không nhận biến noi_dung"),
        (RESULT | {"ma_yeu_cau": "YC-khac"}, "Form của việc không nhận biến ma_yeu_cau"),
    ]

    replies = [act(stack, token, task, "complete", variables) for variables, _ in attempts]

    unfinished = operaton_get(
        stack, f"/history/activity-instance?processInstanceId={instance}&unfinished=true"
    )
    assert replies == [(422, {"detail": detail}) for _, detail in attempts]
    assert assignees(stack, [task]) == {task: worker.id}
    assert variables_of(stack, instance) == before
    assert [item["activityId"] for item in unfinished] == ["xu_ly"]
    assert act(stack, token, task, "complete", RESULT) == (204, None)
    assert finished(stack, instance) == "COMPLETED"


def test_suspended_task_cannot_be_claimed_or_completed(stack, requests_process):
    worker = stack.new_user(role=WORKER)
    _, started = start(stack, stack.new_user(role=STARTER), variables=REQUEST)
    task = task_of(stack, started["id"])
    token = stack.token(worker)
    path = f"/process-instance/{started['id']}/suspended"

    assert operaton_send(stack, "PUT", path, {"suspended": True}) == 204
    refused_claim = act(stack, token, task, "claim")
    assert operaton_send(stack, "PUT", path, {"suspended": False}) == 204
    claimed = act(stack, token, task, "claim")
    assert operaton_send(stack, "PUT", path, {"suspended": True}) == 204
    refused_completion = act(stack, token, task, "complete")
    assert operaton_send(stack, "PUT", path, {"suspended": False}) == 204

    assert refused_claim == (409, TASK_SUSPENDED)
    assert claimed == (204, None)
    assert refused_completion == (409, TASK_SUSPENDED)
    assert act(stack, token, task, "complete", RESULT) == (204, None)


def test_claim_and_complete_of_unknown_task_are_not_found(stack):
    token = stack.token(stack.new_user(role=WORKER))
    task = str(uuid.uuid4())

    assert act(stack, token, task, "claim") == (404, TASK_NOT_FOUND)
    assert act(stack, token, task, "complete") == (404, TASK_NOT_FOUND)


def test_process_runs_to_end_with_machine_step_updating_row(stack, requests_process):
    code = f"YC-{uuid.uuid4().hex[:8]}"
    stack.sql(f"INSERT INTO thu_nghiem.yeu_cau (ma) VALUES ('{code}')")
    worker = stack.new_user(role=WORKER)
    variables = REQUEST | {"ma_yeu_cau": code}
    status, started = start(stack, stack.new_user(role=STARTER), variables=variables)
    instance = started["id"]
    task = task_of(stack, instance)
    token = stack.token(worker)

    claimed = act(stack, token, task, "claim")
    done = act(stack, token, task, "complete", RESULT)
    state = finished(stack, instance)

    assert (status, claimed, done, state) == (201, (204, None), (204, None), "COMPLETED")
    assert stack.sql(f"SELECT trang_thai, ket_qua FROM thu_nghiem.yeu_cau WHERE ma = '{code}'") == [
        ["da_xu_ly", "Đã thay cáp màn hình"]
    ]
    assert stack.sql(
        "SELECT operation, db_role, actor FROM core.audit_log WHERE table_schema = 'thu_nghiem' "
        f"AND coalesce(new_row, old_row) ->> 'ma' = '{code}' ORDER BY id"
    ) == [["INSERT", "postgres", ""], ["UPDATE", "workflow", ""]]
    assert written(stack, instance)["da_cap_nhat"] is True
    assert stack.sql(
        f"SELECT activity_id, function FROM core.step_runs WHERE process_instance_id = '{instance}'"
    ) == [["ghi_ket_qua", "thu_nghiem.ghi_ket_qua"]]


def test_function_gets_variables_and_runs_as_workflow(stack, machine_steps):
    starter = stack.new_user(role=STARTER)
    variables = {"noi_dung": "Máy 12", "so_luong": 2, "khan": True, "ghi_chu": None}
    due = {"han_xu_ly": "2026-11-20T09:00:00+07:00"}

    _, started = start(stack, starter, "nguoi_chay_thu", variables | due)
    state = finished(stack, started["id"])

    found = written(stack, started["id"])
    assert state == "COMPLETED"
    assert (found["vai_tro"], found["role"]) == ("workflow", "workflow")
    assert json.loads(found["bien"]) == variables | dict.fromkeys(INITIATORS, starter.id) | {
        "han_xu_ly": "2026-11-20T02:00:00.000+0000"
    }


@pytest.mark.parametrize(
    ("key", "message"),
    [
        ("chua_khai_thu", "Hàm thu_nghiem.chua_khai(jsonb) chưa được khai báo cho quy trình."),
        ("cong_khai_thu", "Hàm thu_nghiem.cong_khai(jsonb) chưa được khai báo cho quy trình."),
        ("khong_co_ham_thu", "Không có hàm thu_nghiem.khong_co"),
        ("sai_tham_so_thu", "Hàm thu_nghiem.nhan_chuoi phải nhận đúng một tham số kiểu jsonb"),
        ("sai_kieu_tra_ve_thu", "Hàm thu_nghiem.tra_chuoi(jsonb) phải trả về một giá trị kiểu"),
        ("ten_sai_thu", "Tên hàm Thu_Nghiem.Ghi không hợp lệ."),
        ("thieu_ham_thu", "Bước máy thiếu thuộc tính function"),
        ("ghi_initiator_thu", "Hàm thu_nghiem.ghi_initiator không được ghi biến initiator."),
    ],
    ids=[
        "chua-khai-bao",
        "cap-cho-public",
        "khong-co-ham",
        "sai-kieu-tham-so",
        "sai-kieu-tra-ve",
        "ten-sai",
        "thieu-function",
        "ghi-initiator",
    ],
)
def test_step_that_cannot_run_becomes_incident(stack, machine_steps, key, message):
    code = uuid.uuid4().hex

    _, started = start(stack, stack.new_user(role=STARTER), key, {"ma": code})
    incident = incident_of(stack, started["id"])

    assert incident["incidentType"] == "failedExternalTask"
    assert message in incident["incidentMessage"]
    assert stack.sql(f"SELECT count(*) FROM thu_nghiem.lan_chay WHERE ma = '{code}'") == [["0"]]
    cancel(stack, started["id"])


def test_failing_function_is_tried_again_after_delay(stack, machine_steps):
    _, started = start(stack, stack.new_user(role=STARTER), "loi_lan_dau_thu")
    instance = started["id"]

    state = finished(stack, instance)

    log = operaton_get(
        stack,
        f"/history/external-task-log?processInstanceId={instance}&sortBy=timestamp&sortOrder=asc",
    )
    failure = next(item for item in log if item["failureLog"])
    success = next(item for item in log if item["successLog"])
    assert state == "COMPLETED"
    assert written(stack, instance)["lan_goi"] == 2
    assert failure["errorMessage"] == "Hàm thu_nghiem.loi_lan_dau báo lỗi: Lỗi thử ở lần gọi đầu"
    assert instant(success["timestamp"]) - instant(failure["timestamp"]) >= timedelta(seconds=5)


def test_function_failing_every_time_becomes_incident(stack, machine_steps):
    _, started = start(stack, stack.new_user(role=STARTER), "luon_loi_thu")
    instance = started["id"]
    step = failed_step(stack, instance)

    assert (
        operaton_send(stack, "PUT", f"/external-task/{step['id']}/retries", {"retries": 1}) == 204
    )
    incident = incident_of(stack, instance)
    details = operaton_text(stack, f"/external-task/{step['id']}/errorDetails")

    assert step["retries"] == 3
    assert step["errorMessage"] == "Hàm thu_nghiem.luon_loi báo lỗi: Không đủ dữ liệu để xử lý"
    assert incident["incidentMessage"] == step["errorMessage"]
    assert details.splitlines()[:3] == [
        "SQLSTATE P0001: Không đủ dữ liệu để xử lý",
        "Kiểm tra biến ma_yeu_cau",
        "PL/pgSQL function thu_nghiem.luon_loi(jsonb) line 3 at RAISE",
    ]
    cancel(stack, instance)


def test_function_cannot_change_role_of_session(stack, machine_steps):
    _, started = start(stack, stack.new_user(role=STARTER), "doi_role_thu")

    step = failed_step(stack, started["id"])

    assert step["errorMessage"] == (
        'Hàm thu_nghiem.doi_role báo lỗi: cannot set parameter "role" '
        "within security-definer function"
    )
    cancel(stack, started["id"])


def test_function_runs_once_when_core_dies_before_reporting(stack, machine_steps):
    code = uuid.uuid4().hex
    _, started = start(stack, stack.new_user(role=STARTER), "cham_thu", {"ma": code, "cho": 5})
    instance = started["id"]
    sleeping = (
        "SELECT count(*) FROM pg_stat_activity "
        "WHERE usename = 'core_service' AND wait_event = 'PgSleep'"
    )
    wait_for(lambda: stack.sql(sleeping) != [["0"]], "Hàm của bước máy chưa chạy")
    step = step_of(stack, instance)
    lock = {"topicName": TOPIC, "lockDuration": 600000, "processInstanceId": instance}
    taken = {"workerId": "kiem-thu", "maxTasks": 1, "topics": [lock]}

    assert operaton_send(stack, "POST", f"/external-task/{step['id']}/unlock", {}) == 204
    assert operaton_send(stack, "POST", "/external-task/fetchAndLock", taken) == 200
    assert step_of(stack, instance)["workerId"] == "kiem-thu"
    refused = f"Chưa báo được Operaton là bước máy {step['id']} đã xong"
    wait_for(lambda: refused in stack.logs("core"), "Service core chưa báo Operaton")
    container = stack.container("core")
    restarts = int(stack.inspect(container, "{{.RestartCount}}"))
    stack.kill_process(process_id(stack, container, "uvicorn"))
    killed = time.monotonic()
    restarted = str(restarts + 1)
    wait_for(
        lambda: stack.inspect(container, "{{.RestartCount}}") == restarted,
        "Service core chưa khởi động lại",
    )
    stack.wait_until_answers("/core/health")
    # Lời gọi long polling của tiến trình đã chết vẫn chờ trong Operaton tới hết thời gian chờ
    time.sleep(max(killed + POLL + 1 - time.monotonic(), 0))
    assert operaton_send(stack, "POST", f"/external-task/{step['id']}/unlock", {}) == 204

    state = finished(stack, instance)

    assert state == "COMPLETED"
    assert stack.sql(f"SELECT count(*) FROM thu_nghiem.lan_chay WHERE ma = '{code}'") == [["1"]]
    assert written(stack, instance)["so_lan"] == 1


def test_process_with_deadline_cannot_start_without_deadline(stack, deadline_process):
    before = started_count(stack, deadline_process)

    status, reply = start(stack, stack.new_user(role=STARTER), deadline_process, REQUEST)

    assert (status, reply) == (422, {"detail": "LỖI TUÂN THỦ: Phải nhập Hạn xử lý (han_xu_ly)"})
    assert started_count(stack, deadline_process) == before


def test_overdue_task_moves_to_managers_within_seconds(stack, deadline_process):
    worker = stack.new_user(role=WORKER)
    manager = stack.new_user(role=MANAGER)
    began = time.monotonic()
    instance, due = start_with_deadline(stack, 10)
    [task] = operaton_get(stack, f"/task?processInstanceId={instance}")

    moved = escalated(stack, instance)
    elapsed = time.monotonic() - began

    path = f"/history/task?processInstanceId={instance}&taskDefinitionKey=xu_ly"
    seen = {
        name: [
            item["id"]
            for item in tasks_of(stack, user)[1]
            if item["process_instance_id"] == instance
        ]
        for name, user in {"worker": worker, "manager": manager}.items()
    }
    assert (task["taskDefinitionKey"], instant(task["due"])) == ("xu_ly", due)
    assert elapsed < 15
    assert instant(moved["created"]) >= due
    assert [(item["id"], item["deleteReason"]) for item in operaton_get(stack, path)] == [
        (task["id"], "deleted")
    ]
    assert seen == {"worker": [], "manager": [moved["id"]]}
    cancel(stack, instance)


def test_assignee_loses_overdue_task_and_manager_finishes_process(stack, deadline_process):
    code = f"YC-{uuid.uuid4().hex[:8]}"
    stack.sql(f"INSERT INTO thu_nghiem.yeu_cau (ma) VALUES ('{code}')")
    worker = stack.new_user(role=WORKER)
    manager = stack.new_user(role=MANAGER)
    instance, _ = start_with_deadline(stack, 5, code)
    task = task_of(stack, instance)
    token = stack.token(worker)
    claimed = act(stack, token, task, "claim")

    moved = escalated(stack, instance)["id"]
    boss = stack.token(manager)
    late = act(stack, token, task, "complete", RESULT)
    taken = act(stack, token, moved, "claim")
    handled = (
        act(stack, boss, moved, "claim"),
        act(stack, boss, moved, "complete", {"ket_qua": "Quản lý đã thay màn hình"}),
    )

    history = operaton_get(
        stack, f"/history/task?processInstanceId={instance}&sortBy=startTime&sortOrder=asc"
    )
    assert claimed == (204, None)
    assert late == (404, TASK_NOT_FOUND)
    assert taken == (403, NOT_CANDIDATE)
    assert handled == ((204, None), (204, None))
    assert finished(stack, instance) == "COMPLETED"
    assert stack.sql(f"SELECT trang_thai, ket_qua FROM thu_nghiem.yeu_cau WHERE ma = '{code}'") == [
        ["da_xu_ly", "Quản lý đã thay màn hình"]
    ]
    assert [
        (item["taskDefinitionKey"], item["assignee"], item["deleteReason"]) for item in history
    ] == [
        ("xu_ly", worker.id, "deleted"),
        ("xu_ly_qua_han", manager.id, "completed"),
    ]


def test_task_completed_before_deadline_removes_timer(stack, deadline_process):
    worker = stack.new_user(role=WORKER)
    instance, due = start_with_deadline(stack, 60)
    timers = operaton_get(stack, f"/job?processInstanceId={instance}&timers=true")
    task = task_of(stack, instance)
    token = stack.token(worker)

    done = act(stack, token, task, "claim"), act(stack, token, task, "complete", RESULT)

    history = operaton_get(stack, f"/history/task?processInstanceId={instance}")
    assert done == ((204, None), (204, None))
    assert [instant(job["dueDate"]) for job in timers] == [due]
    assert finished(stack, instance) == "COMPLETED"
    assert operaton_get(stack, f"/job?processInstanceId={instance}") == []
    assert [item["taskDefinitionKey"] for item in history] == ["xu_ly"]


def test_deadline_passed_while_operaton_was_stopped_fires_once_it_starts(stack, deadline_process):
    closed = "ENGINE-00007 Process Engine default closed"
    before = stack.logs("operaton").count(closed)
    instance, due = start_with_deadline(stack, 5)
    container = stack.container("operaton")

    assert stack.compose_result("stop", "operaton").returncode == 0
    stopped = stack.inspect(container, "{{.State.Status}} {{.State.ExitCode}}")
    time.sleep(max((due - datetime.now(UTC)).total_seconds(), 0) + 2)
    assert stack.compose_result("start", "operaton").returncode == 0
    deadline = time.monotonic() + 180
    while stack.inspect(container, "{{.State.Health.Status}}") != "healthy":
        assert time.monotonic() < deadline, "Operaton chưa khởi động lại"
        time.sleep(1)
    back = time.monotonic()
    moved = escalated(stack, instance)

    assert stopped == "exited 130"
    assert stack.logs("operaton").count(closed) == before + 1
    assert time.monotonic() - back < 5
    assert instant(moved["created"]) > due + timedelta(seconds=2)
    wait_until_core_account_works(stack)
    cancel(stack, instance)


def test_history_cleanup_is_scheduled_every_night_in_vietnam(stack):
    window = operaton_get(stack, "/history/cleanup/configuration")
    begin, end = (instant(window[name]) for name in ("batchWindowStartTime", "batchWindowEndTime"))
    [job] = operaton_get(stack, "/history/cleanup/jobs")

    assert window["enabled"] is True
    assert begin.astimezone(VIETNAM).strftime("%H:%M") == "01:00"
    assert end - begin == timedelta(hours=4)
    assert in_night_window(instant(job["dueDate"]))


def test_history_cleanup_removes_only_history_past_time_to_live(stack):
    files = {
        "het-han-ngay.bpmn": bpmn("het_han_ngay", history="P0D"),
        "giu-lai.bpmn": bpmn("giu_lai"),
    }
    with bpmn_files(stack, files):
        assert deploy(stack)[0] == 0
    expired, kept = (
        operaton_post(stack, f"/process-definition/key/{key}/start", {})["id"]
        for key in ("het_han_ngay", "giu_lai")
    )

    def history(instance):
        return operaton_get(stack, f"/history/process-instance?processInstanceId={instance}")

    [old], [new] = history(expired), history(kept)
    operaton_post(stack, "/history/cleanup?immediatelyDue=true", {})
    wait_for(lambda: history(expired) == [], "Operaton chưa xóa lịch sử đã hết hạn")

    [job] = wait_for(
        lambda: [
            job
            for job in operaton_get(stack, "/history/cleanup/jobs")
            if in_night_window(instant(job["dueDate"]))
        ],
        "Việc dọn lịch sử chưa được hẹn lại vào ban đêm",
    )
    assert instant(old["removalTime"]) == instant(old["endTime"])
    assert instant(new["removalTime"]) - instant(new["endTime"]) == timedelta(days=30)
    assert [item["id"] for item in history(kept)] == [kept]
    assert job["exceptionMessage"] is None


def test_core_answers_503_while_operaton_is_unreachable(stack):
    user = stack.new_user(role=WORKER)
    network = stack.network("default")
    container = stack.container("operaton")

    stack.run_docker("network", "disconnect", network, container)
    try:
        unreachable = tasks_of(stack, user)
    finally:
        stack.run_docker("network", "connect", "--alias", "operaton", network, container)

    assert unreachable == (503, NO_TASKS)
    assert tasks_of(stack, user)[0] == 200


def test_core_stops_calling_operaton_while_it_refuses_account_of_core(stack):
    token = stack.token(stack.new_user(role=WORKER))
    url = f"{stack.url}/core/tasks"
    refusal = "Service core ngừng gọi Operaton trong 60 giây"
    before = stack.logs("core").count(refusal)

    assert rest_status(stack, "core:sai-mat-khau") == 401
    replies = [stack.call("GET", url, token=token) for _ in range(3)]
    refusals = stack.logs("core").count(refusal) - before
    wait_until_core_account_works(stack)
    paused = stack.call("GET", url, token=token)
    stack.compose("restart", "core")
    stack.wait_until_answers("/core/health")

    assert [reply.status for reply in replies] == [503, 503, 503]
    assert all(json.loads(reply.body) == NO_TASKS for reply in replies)
    assert refusals == 1
    assert paused.status == 503
    assert stack.call("GET", url, token=token).status == 200


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
