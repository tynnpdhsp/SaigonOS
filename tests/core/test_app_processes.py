# SPDX-License-Identifier: Apache-2.0
import base64
import json
import socket
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace

import pytest

from saigonos_core.app_database import ApplyError
from saigonos_core.app_processes import (
    DEPLOYED,
    REFUSED,
    UNCHANGED,
    Operaton,
    apply_processes,
    check_operaton,
)
from saigonos_core.manifest import Manifest

MANIFEST = Manifest.model_validate(
    {
        "name": "nghi-phep",
        "title": "Nghỉ phép",
        "version": "0.1.0",
        "roles": [{"name": "nghi-phep.quan-ly", "description": "Duyệt đơn"}],
        "processes": "quy-trinh/",
    }
)
CREATED = "/operaton/engine-rest/deployment/create"


@pytest.fixture
def server():
    state = SimpleNamespace(requests=[], replies=[])

    class Handler(BaseHTTPRequestHandler):
        def answer(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            state.requests.append((self.command, self.path, self.headers, body))
            status, data = state.replies.pop(0) if state.replies else (200, {"version": "2.2.1"})
            content = data if isinstance(data, bytes) else json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        do_GET = do_POST = answer

        def log_message(self, *details):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    state.url = f"http://127.0.0.1:{httpd.server_port}/operaton/engine-rest"
    yield state
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def app(tmp_path):
    folder = tmp_path / "quy-trinh"
    folder.mkdir()
    for name in ("duyet.bpmn", "bao-cao.bpmn"):
        (folder / name).write_text(f"<{name}/>", encoding="utf-8")
    (folder / "ghi-chu.txt").write_text("không triển khai", encoding="utf-8")
    return tmp_path


def engine(server):
    return Operaton(server.url, "mat-khau-tai-khoan-core")


def deployed(*definitions):
    found = {
        f"{key}:{version}:id": {"key": key, "version": version} for key, version in definitions
    }
    return 200, {"id": "ban-trien-khai", "deployedProcessDefinitions": found}


def form_of(headers, body):
    head = f"Content-Type: {headers['Content-Type']}\r\n\r\n".encode()
    message = BytesParser(policy=default).parsebytes(head + body)
    fields = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        fields[name] = (part.get_filename(), part.get_payload(decode=True))
    return fields


def test_each_bpmn_file_is_deployed_into_tenant_of_app(server, app):
    server.replies += [deployed(), deployed(("nghi_phep.duyet", 1))]
    said = []

    changed = apply_processes(engine(server), MANIFEST, app, said.append)

    assert changed is True
    assert said == [DEPLOYED.format(file="duyet.bpmn", key="nghi_phep.duyet", version=1)]
    assert [(method, path) for method, path, *_ in server.requests] == [("POST", CREATED)] * 2
    _, _, headers, body = server.requests[1]
    account = base64.b64decode(headers["Authorization"].removeprefix("Basic ")).decode()
    assert account == "core:mat-khau-tai-khoan-core"
    assert form_of(headers, body) == {
        "deployment-name": (None, b"duyet.bpmn"),
        "deployment-source": (None, b"app:nghi-phep"),
        "tenant-id": (None, b"nghi-phep"),
        "enable-duplicate-filtering": (None, b"true"),
        "deploy-changed-only": (None, b"true"),
        "data": ("duyet.bpmn", b"<duyet.bpmn/>"),
    }


def test_definitions_of_one_file_are_listed_by_key(server, app):
    (app / "quy-trinh" / "duyet.bpmn").unlink()
    server.replies.append(deployed(("nghi_phep.tong_hop", 3), ("nghi_phep.bao_cao", 2)))
    said = []

    apply_processes(engine(server), MANIFEST, app, said.append)

    assert said == [
        DEPLOYED.format(file="bao-cao.bpmn", key="nghi_phep.bao_cao", version=2),
        DEPLOYED.format(file="bao-cao.bpmn", key="nghi_phep.tong_hop", version=3),
    ]


@pytest.mark.parametrize(
    "reply",
    [(200, {"id": "cu", "deployedProcessDefinitions": None}), deployed()],
    ids=["khong-thay-doi", "khong-co-quy-trinh-chay-duoc"],
)
def test_unchanged_files_give_one_line(server, app, reply):
    server.replies += [reply, reply]
    said = []

    changed = apply_processes(engine(server), MANIFEST, app, said.append)

    assert (changed, said) == (False, [UNCHANGED])


def test_app_without_processes_does_not_call_operaton(server, app):
    manifest = MANIFEST.model_copy(update={"processes": None})

    assert apply_processes(engine(server), manifest, app, print) is False
    assert server.requests == []


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        (
            (400, {"message": "ENGINE-09005 Could not parse BPMN process."}),
            "Operaton không triển khai được file bao-cao.bpmn: "
            "ENGINE-09005 Could not parse BPMN process.",
        ),
        ((500, b""), "Operaton không triển khai được file bao-cao.bpmn."),
        (
            (502, b"<html>Bad Gateway</html>"),
            "Operaton không triển khai được file bao-cao.bpmn: <html>Bad Gateway</html>.",
        ),
        ((401, {"message": "Unauthorized"}), REFUSED),
    ],
    ids=["file-sai", "khong-co-noi-dung", "khong-phai-json", "sai-mat-khau"],
)
def test_refused_deployment_stops_apply(server, app, reply, message):
    server.replies.append(reply)

    with pytest.raises(ApplyError) as error:
        apply_processes(engine(server), MANIFEST, app, print)

    assert str(error.value) == message
    assert len(server.requests) == 1


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        ((200, {"version": "2.2.1"}), None),
        ((401, b""), REFUSED),
        (
            (503, {"message": "Service Unavailable"}),
            "REST API của Operaton trả về mã 503: Service Unavailable.",
        ),
    ],
    ids=["dat", "sai-mat-khau", "chua-san-sang"],
)
def test_check_asks_operaton_for_its_version(server, reply, message):
    server.replies.append(reply)

    try:
        check_operaton(engine(server))
    except ApplyError as error:
        found = str(error)
    else:
        found = None

    assert server.requests[0][:2] == ("GET", "/operaton/engine-rest/version")
    assert found == message


def test_unreachable_operaton_asks_to_start_system():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    with pytest.raises(ApplyError) as error:
        check_operaton(Operaton(f"http://127.0.0.1:{port}/operaton/engine-rest", "x"))

    assert str(error.value).startswith("Không kết nối được REST API của Operaton: ")
    assert str(error.value).endswith(". Hãy khởi động hệ thống bằng lệnh saigonos up rồi chạy lại.")
