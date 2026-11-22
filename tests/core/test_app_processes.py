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
    ACTIVATED,
    DELETED,
    DEPLOYED,
    REFUSED,
    SUSPENDED,
    Operaton,
    activate_processes,
    apply_processes,
    check_operaton,
    delete_processes,
    suspend_processes,
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

        do_GET = do_POST = do_PUT = do_DELETE = answer

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

    assert (changed, said) == (False, [])


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


def definitions(*items):
    return 200, [
        {"id": f"{key}:{version}:id", "key": key, "suspended": suspended, "tenantId": tenant}
        for key, version, suspended, tenant in items
    ]


def test_suspend_stops_every_active_version_of_app_with_its_instances(server):
    server.replies += [
        definitions(
            ("nghi_phep.duyet", 1, False, "nghi-phep"),
            ("nghi_phep.duyet", 2, False, "nghi-phep"),
            ("nghi_phep.bao_cao", 1, True, "nghi-phep"),
            ("khac.duyet", 1, False, "khac"),
        ),
        (204, b""),
        (204, b""),
    ]
    said = []

    changed = suspend_processes(engine(server), "nghi-phep", said.append)

    assert changed is True
    assert said == [SUSPENDED.format(key="nghi_phep.duyet")]
    listed, *updates = [(method, path, body) for method, path, _, body in server.requests]
    assert listed[:2] == ("GET", "/operaton/engine-rest/process-definition?tenantIdIn=nghi-phep")
    assert [(method, path) for method, path, _ in updates] == [
        ("PUT", "/operaton/engine-rest/process-definition/nghi_phep.duyet:1:id/suspended"),
        ("PUT", "/operaton/engine-rest/process-definition/nghi_phep.duyet:2:id/suspended"),
    ]
    assert {json.loads(body)["includeProcessInstances"] for _, _, body in updates} == {True}
    assert {json.loads(body)["suspended"] for _, _, body in updates} == {True}


def test_activate_resumes_suspended_versions(server):
    server.replies += [definitions(("nghi_phep.duyet", 1, True, "nghi-phep")), (204, b"")]
    said = []

    assert activate_processes(engine(server), "nghi-phep", said.append) is True
    assert said == [ACTIVATED.format(key="nghi_phep.duyet")]
    assert json.loads(server.requests[1][3]) == {
        "suspended": False,
        "includeProcessInstances": True,
    }


def test_nothing_to_suspend_says_nothing(server):
    server.replies.append(definitions(("nghi_phep.duyet", 1, True, "nghi-phep")))
    said = []

    assert suspend_processes(engine(server), "nghi-phep", said.append) is False
    assert said == []


def test_delete_removes_deployments_of_app_with_cascade(server):
    deployments = [
        {"id": "trien-khai-1", "name": "duyet.bpmn", "tenantId": "nghi-phep"},
        {"id": "trien-khai-2", "name": "duyet.bpmn", "tenantId": "nghi-phep"},
        {"id": "khac", "name": "khac.bpmn", "tenantId": "khac"},
    ]
    server.replies += [(200, deployments), (204, b""), (404, {"message": "Deployment not found"})]
    said = []

    changed = delete_processes(engine(server), "nghi-phep", said.append)

    assert changed is True
    assert said == [DELETED.format(count=2)]
    assert [(method, path) for method, path, *_ in server.requests[1:]] == [
        ("DELETE", "/operaton/engine-rest/deployment/trien-khai-1?cascade=true"),
        ("DELETE", "/operaton/engine-rest/deployment/trien-khai-2?cascade=true"),
    ]


def test_refused_change_of_process_stops_removal(server):
    server.replies += [
        definitions(("nghi_phep.duyet", 1, False, "nghi-phep")),
        (500, {"message": "ENGINE-01009 Error"}),
    ]

    with pytest.raises(ApplyError) as error:
        suspend_processes(engine(server), "nghi-phep", print)

    assert str(error.value) == (
        "Operaton không đổi được trạng thái của quy trình nghi_phep.duyet: ENGINE-01009 Error."
    )


def test_listing_error_is_reported(server):
    server.replies.append((500, {"message": "ENGINE-03004 Error"}))

    with pytest.raises(ApplyError) as error:
        delete_processes(engine(server), "nghi-phep", print)

    assert str(error.value) == (
        "Operaton trả về mã 500 cho lời gọi GET /deployment: ENGINE-03004 Error."
    )


def test_refused_deletion_stops_purge(server):
    deployment = {"id": "trien-khai-1", "name": "duyet.bpmn", "tenantId": "nghi-phep"}
    server.replies += [(200, [deployment]), (500, {"message": "ENGINE-03028 Error"})]

    with pytest.raises(ApplyError) as error:
        delete_processes(engine(server), "nghi-phep", print)

    assert str(error.value) == (
        "Operaton không xóa được bản triển khai duyet.bpmn: ENGINE-03028 Error."
    )
