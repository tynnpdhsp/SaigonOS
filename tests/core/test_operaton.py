# SPDX-License-Identifier: Apache-2.0
import base64
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from saigonos_core.operaton import (
    MAX_REFUSALS,
    PAUSE,
    Operaton,
    OperatonError,
    OperatonUnavailableError,
)

PREFIX = "/operaton/engine-rest"
CORE_LOGIN = "mat-khau-cua-core"
PAUSED = "Service core đang tạm ngừng gọi Operaton"
STOPPED = "Service core đã ngừng gọi Operaton"
REFUSED = "Operaton từ chối tài khoản core. Service core ngừng gọi Operaton trong 60 giây."


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Server:
    def __init__(self):
        self.requests = []
        self.replies = {}
        self.default = (200, b"{}")
        self.gate = None

    def reply(self, method, path, status, data=None):
        content = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.replies[method, f"{PREFIX}{path}"] = (status, b"" if data is None else content)

    def refuse(self):
        self.replies.clear()
        self.default = (401, b"")

    def accept(self):
        self.default = (200, b"{}")


@pytest.fixture
def server():
    state = Server()

    class Handler(BaseHTTPRequestHandler):
        def answer(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""
            state.requests.append((self.command, self.path, self.headers, body))
            if state.gate is not None:
                state.gate.wait(5)
            status, content = state.replies.get((self.command, self.path), state.default)
            self.send_response(status)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        do_GET = do_POST = answer

        def log_message(self, format, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.url = f"http://127.0.0.1:{httpd.server_port}{PREFIX}"
    threading.Thread(
        target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    ).start()
    yield state
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def operaton(server, clock):
    return Operaton(server.url, CORE_LOGIN, clock=clock)


def refusals_logged(caplog):
    return [record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING]


def test_call_signs_in_as_core_and_sends_json(server, operaton):
    server.reply("POST", "/process-definition/yeu_cau:2:abc/submit-form", 200, {"id": "pi-1"})
    variables = {"initiator": {"value": "nguoi-dung", "type": "String"}}

    started = operaton.submit_start_form("yeu_cau:2:abc", variables)

    [(method, path, headers, body)] = server.requests
    assert started == {"id": "pi-1"}
    assert (method, path) == ("POST", f"{PREFIX}/process-definition/yeu_cau:2:abc/submit-form")
    assert headers["Authorization"] == "Basic " + base64.b64encode(
        f"core:{CORE_LOGIN}".encode()
    ).decode("ascii")
    assert headers["Content-Type"] == "application/json"
    assert headers["Accept"] == "application/json"
    assert json.loads(body) == {"variables": variables}


def test_path_segment_cannot_leave_its_place(server, operaton):
    server.reply("GET", "/process-definition/key/a%2F..%2Fb%3Fc", 404, {"message": "Không có"})

    assert operaton.latest_definition("a/../b?c") is None
    assert server.requests[0][1] == f"{PREFIX}/process-definition/key/a%2F..%2Fb%3Fc"


def test_latest_definition_is_none_for_unknown_key(server, operaton):
    definition = {"id": "yeu_cau:1:abc", "key": "yeu_cau", "version": 1, "suspended": False}
    server.reply("GET", "/process-definition/key/yeu_cau", 200, definition)
    server.reply("GET", "/process-definition/key/khong_co", 404, {"message": "No matching"})

    assert operaton.latest_definition("yeu_cau") == definition
    assert operaton.latest_definition("khong_co") is None


def test_definition_xml_returns_bpmn_of_definition(server, operaton):
    server.reply(
        "GET", "/process-definition/yeu_cau:1:abc/xml", 200, {"bpmn20Xml": "<definitions />"}
    )

    assert operaton.definition_xml("yeu_cau:1:abc") == "<definitions />"


def test_tasks_send_query_with_paging(server, operaton):
    server.reply("POST", "/task?firstResult=10&maxResults=20", 200, [{"id": "t-1"}])
    query = {"assignee": "nguoi-dung"}

    tasks = operaton.tasks(query, 10, 20)

    assert tasks == [{"id": "t-1"}]
    assert json.loads(server.requests[0][3]) == query


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"type": "RestException", "message": "ENGINE-03043 suspended"}, "ENGINE-03043 suspended"),
        (b"<html>Internal error</html>", "<html>Internal error</html>"),
    ],
)
def test_unexpected_status_raises_error_with_message_of_operaton(server, operaton, data, message):
    server.reply("GET", "/process-definition/key/yeu_cau", 500, data)

    with pytest.raises(OperatonError) as raised:
        operaton.latest_definition("yeu_cau")

    assert raised.value.status == 500
    assert str(raised.value) == f"Operaton trả về mã 500: {message}"


def test_unreachable_operaton_is_unavailable(clock):
    operaton = Operaton("http://127.0.0.1:9/operaton/engine-rest", CORE_LOGIN, clock=clock)

    with pytest.raises(OperatonUnavailableError, match="Không kết nối được Operaton"):
        operaton.latest_definition("yeu_cau")


def test_refusal_pauses_calls_without_contacting_operaton(server, operaton, clock, caplog):
    server.refuse()

    with pytest.raises(OperatonUnavailableError, match="Operaton từ chối tài khoản core"):
        operaton.latest_definition("yeu_cau")
    clock.now += PAUSE - 1
    with pytest.raises(OperatonUnavailableError, match=PAUSED):
        operaton.latest_definition("yeu_cau")
    sent_while_paused = len(server.requests)
    server.accept()
    clock.now += 1
    operaton.tasks({}, 0, 1)

    assert sent_while_paused == 1
    assert len(server.requests) == 2
    assert refusals_logged(caplog) == [
        f"{REFUSED} Hãy kiểm tra giá trị CORE_OPERATON_PASSWORD trong file .env"
    ]


def test_core_stops_calling_operaton_after_refusals_in_a_row(server, operaton, clock, caplog):
    server.refuse()
    for _ in range(MAX_REFUSALS):
        with pytest.raises(OperatonUnavailableError):
            operaton.latest_definition("yeu_cau")
        clock.now += PAUSE
    server.accept()
    clock.now += 24 * 3600

    with pytest.raises(OperatonUnavailableError, match=STOPPED):
        operaton.tasks({}, 0, 1)

    assert len(server.requests) == MAX_REFUSALS
    assert refusals_logged(caplog)[-1] == (
        "Operaton từ chối tài khoản core 5 lần liên tiếp. "
        "Service core ngừng gọi Operaton cho tới khi khởi động lại. "
        "Hãy khôi phục giá trị đúng của CORE_OPERATON_PASSWORD trong file .env rồi chạy saigonos up"
    )


def test_accepted_call_resets_count_of_refusals(server, operaton, clock):
    for _ in range(2):
        server.refuse()
        for _ in range(MAX_REFUSALS - 1):
            with pytest.raises(OperatonUnavailableError):
                operaton.latest_definition("yeu_cau")
            clock.now += PAUSE
        server.accept()
        operaton.tasks({}, 0, 1)

    assert len(server.requests) == 2 * MAX_REFUSALS


def test_refusals_of_calls_sent_together_count_once(server, operaton, clock, caplog):
    server.refuse()
    server.gate = threading.Event()
    calls = 4

    with ThreadPoolExecutor(calls) as pool:
        futures = [pool.submit(operaton.tasks, {}, 0, 1) for _ in range(calls)]
        deadline = time.monotonic() + 5
        while len(server.requests) < calls:
            assert time.monotonic() < deadline, "Các lời gọi chưa tới Operaton"
            time.sleep(0.01)
        server.gate.set()
        errors = [future.exception() for future in futures]
    for _ in range(MAX_REFUSALS - 1):
        clock.now += PAUSE
        with pytest.raises(OperatonUnavailableError):
            operaton.latest_definition("yeu_cau")

    assert all(isinstance(error, OperatonUnavailableError) for error in errors)
    assert len(server.requests) == calls + MAX_REFUSALS - 1
    assert len(refusals_logged(caplog)) == MAX_REFUSALS
    assert "khởi động lại" in refusals_logged(caplog)[-1]
