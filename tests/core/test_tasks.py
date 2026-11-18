# SPDX-License-Identifier: Apache-2.0
import json
import logging
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from saigonos_core.callers import caller_of
from saigonos_core.main import create_app
from saigonos_core.operaton import OperatonError, OperatonUnavailableError
from saigonos_core.tasks import SORTING, query_of

WORKER = "nhan-vien"
NOT_FOUND = {"detail": "Không tìm thấy việc"}
NOT_CANDIDATE = {"detail": "Người gọi không có realm role nằm trong nhóm ứng viên của việc này"}
TAKEN = {"detail": "Việc đã có người khác nhận"}
NOT_ASSIGNEE = {"detail": "Chỉ người nhận việc mới hoàn thành được việc này"}
SUSPENDED = {"detail": "Việc đang tạm ngưng"}
LOCKED = "ENGINE-03005 Entity was updated by another transaction concurrently."
PROCESS = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:operaton="http://operaton.org/schema/1.0/bpmn"
                  id="dinh_nghia" targetNamespace="https://dx.example.com/bpmn">
  <bpmn:process id="yeu_cau" isExecutable="true" operaton:candidateStarterGroups="nguoi-gui">
    <bpmn:startEvent id="bat_dau" operaton:initiator="nguoi_tao" />
    <bpmn:userTask id="xu_ly" operaton:candidateGroups="nhan-vien" />
  </bpmn:process>
</bpmn:definitions>
"""
FOUND = {
    "id": "viec-1",
    "name": "Xử lý yêu cầu",
    "assignee": None,
    "owner": None,
    "created": "2026-11-18T02:38:56.251+0000",
    "lastUpdated": None,
    "due": "2026-11-20T09:00:00.000+0700",
    "followUp": None,
    "delegationState": None,
    "description": "Kiểm tra máy và ghi kết quả",
    "executionId": "thuc-thi-1",
    "parentTaskId": None,
    "priority": 50,
    "processDefinitionId": "yeu_cau:1:0001",
    "processInstanceId": "quy-trinh-1",
    "taskDefinitionKey": "xu_ly",
    "suspended": False,
    "formKey": None,
    "tenantId": None,
}


class IdleDatabase:
    async def open(self):
        pass

    async def close(self):
        pass


@pytest.fixture
def client(settings, scans, operaton):
    app = create_app(settings, IdleDatabase(), scans=scans, operaton=operaton)
    with TestClient(app) as client:
        yield client


def bearer(realm, *roles):
    token = realm.token(realm_access={"roles": ["authenticated", *roles]})
    return {"Authorization": f"Bearer {token}"}


def claim(client, headers, task_id="viec-1"):
    return client.post(f"/tasks/{task_id}/claim", headers=headers)


def complete(client, headers, task_id="viec-1", variables=None):
    body = None if variables is None else {"variables": variables}
    return client.post(f"/tasks/{task_id}/complete", headers=headers, json=body)


@pytest.fixture
def assigned(operaton, realm):
    operaton.deploy("yeu_cau", PROCESS)
    operaton.add_task(assignee=realm.subject)


def test_tasks_ask_operaton_for_own_and_claimable_tasks_only(client, operaton, realm):
    reply = client.get("/tasks", headers=bearer(realm, "nhan-vien", "a,b"))

    assert (reply.status_code, reply.json()) == (200, [])
    assert operaton.queries == [
        (
            {
                "orQueries": [
                    {
                        "assignee": realm.subject,
                        "candidateGroups": ["a,b", "authenticated", "nhan-vien"],
                    }
                ],
                "sorting": SORTING,
            },
            0,
            50,
        )
    ]


def test_caller_without_realm_roles_asks_only_for_own_tasks():
    caller = caller_of({"sub": "nguoi-dung", "realm_access": {"roles": []}})

    assert query_of(caller) == {"assignee": "nguoi-dung", "sorting": SORTING}


def test_task_fields_come_from_operaton(client, operaton, realm):
    operaton.found = [FOUND, FOUND | {"id": "viec-2", "assignee": realm.subject, "due": None}]

    reply = client.get("/tasks", headers=bearer(realm))

    first, second = reply.json()
    assert reply.status_code == 200
    assert first == {
        "id": "viec-1",
        "name": "Xử lý yêu cầu",
        "description": "Kiểm tra máy và ghi kết quả",
        "assignee": None,
        "created": "2026-11-18T02:38:56.251000Z",
        "due": "2026-11-20T09:00:00+07:00",
        "priority": 50,
        "task_key": "xu_ly",
        "process_instance_id": "quy-trinh-1",
        "process_definition_id": "yeu_cau:1:0001",
        "suspended": False,
    }
    assert (second["assignee"], second["due"]) == (realm.subject, None)
    assert datetime.fromisoformat(first["due"]) == datetime(2026, 11, 20, 2, tzinfo=UTC)


def test_tasks_pass_offset_and_limit(client, operaton, realm):
    reply = client.get("/tasks?offset=100&limit=200", headers=bearer(realm))

    assert reply.status_code == 200
    assert operaton.queries[0][1:] == (100, 200)


@pytest.mark.parametrize("query", ["offset=-1", "limit=0", "limit=201", "limit=x"])
def test_paging_outside_limits_is_refused(client, operaton, realm, query):
    reply = client.get(f"/tasks?{query}", headers=bearer(realm))

    assert reply.status_code == 422
    assert operaton.queries == []


def test_tasks_need_access_token(client, operaton):
    reply = client.get("/tasks")

    assert reply.status_code == 401
    assert operaton.queries == []


def test_unavailable_operaton_gives_503(client, operaton, realm, caplog):
    operaton.failure = OperatonUnavailableError("Service core đang tạm ngừng gọi Operaton")

    reply = client.get("/tasks", headers=bearer(realm))

    assert (reply.status_code, reply.json()) == (
        503,
        {"detail": "Chưa lấy được danh sách việc vì Operaton chưa sẵn sàng"},
    )
    assert caplog.records[-1].levelno == logging.WARNING


def test_error_of_operaton_gives_502(client, operaton, realm, caplog):
    operaton.failure = OperatonError(400, "Candidate group list is empty")

    reply = client.get("/tasks", headers=bearer(realm))

    assert (reply.status_code, reply.json()) == (
        502,
        {"detail": "Operaton báo lỗi khi lấy danh sách việc"},
    )
    assert "Candidate group list is empty" in caplog.records[-1].getMessage()


def test_worker_claims_unassigned_task_of_own_group(client, operaton, realm):
    operaton.add_task(groups=("quan-ly", WORKER))

    reply = claim(client, bearer(realm, WORKER))

    assert (reply.status_code, reply.content) == (204, b"")
    assert operaton.claims == [("viec-1", realm.subject)]
    assert operaton.queries == [
        (
            {
                "taskId": "viec-1",
                "candidateGroups": ["authenticated", WORKER],
                "includeAssignedTasks": True,
            },
            0,
            1,
        )
    ]


def test_caller_outside_candidate_groups_cannot_claim(client, operaton, realm):
    operaton.add_task(groups=(WORKER,))

    reply = claim(client, bearer(realm, "nguoi-gui", "admin"))

    assert (reply.status_code, reply.json()) == (403, NOT_CANDIDATE)
    assert operaton.claims == []
    assert operaton.items["viec-1"]["assignee"] is None


def test_claim_of_unknown_task_is_not_found(client, operaton, realm):
    reply = claim(client, bearer(realm, WORKER))

    assert (reply.status_code, reply.json()) == (404, NOT_FOUND)
    assert operaton.claims == []


def test_task_taken_by_another_cannot_be_claimed(client, operaton, realm):
    operaton.add_task(assignee="nguoi-khac")

    reply = claim(client, bearer(realm, WORKER))

    assert (reply.status_code, reply.json()) == (409, TAKEN)
    assert operaton.claims == []
    assert operaton.items["viec-1"]["assignee"] == "nguoi-khac"


def test_claim_of_own_task_changes_nothing(client, operaton, realm):
    operaton.add_task(assignee=realm.subject)

    reply = claim(client, bearer(realm, WORKER))

    assert reply.status_code == 204
    assert operaton.claims == []


def test_suspended_task_cannot_be_claimed(client, operaton, realm):
    operaton.add_task(suspended=True)

    reply = claim(client, bearer(realm, WORKER))

    assert (reply.status_code, reply.json()) == (409, SUSPENDED)
    assert operaton.claims == []


@pytest.mark.parametrize(
    ("change", "status", "detail"),
    [
        (lambda realm: {"assignee": "nguoi-khac"}, 409, TAKEN),
        (lambda realm: {"assignee": realm.subject}, 204, None),
        (lambda realm: {"suspended": True}, 409, SUSPENDED),
        (None, 404, NOT_FOUND),
    ],
    ids=[
        "người khác nhận trước",
        "người gọi nhận trước",
        "việc vừa tạm ngưng",
        "việc vừa kết thúc",
    ],
)
def test_claim_refused_by_operaton_follows_new_state_of_task(
    client, operaton, realm, change, status, detail
):
    operaton.add_task()

    def race(task_id):
        if change is None:
            del operaton.items[task_id]
        else:
            operaton.items[task_id] |= change(realm)
        raise OperatonError(500, LOCKED)

    operaton.race = race

    reply = claim(client, bearer(realm, WORKER))

    assert reply.status_code == status
    assert detail is None or reply.json() == detail


def test_other_error_of_claim_gives_502(client, operaton, realm, caplog):
    operaton.add_task()

    def race(task_id):
        raise OperatonError(500, "Lỗi khác của Operaton")

    operaton.race = race

    reply = claim(client, bearer(realm, WORKER))

    assert (reply.status_code, reply.json()) == (502, {"detail": "Operaton báo lỗi khi nhận việc"})
    assert caplog.records[-1].levelno == logging.ERROR
    assert "Lỗi khác của Operaton" in caplog.records[-1].getMessage()


@pytest.mark.parametrize("task_id", ["viec_1", "viec.1", "viec%3A1", "%2E%2E", "a" * 65])
def test_task_id_outside_pattern_is_refused(client, operaton, realm, task_id):
    operaton.add_task(task_id)

    reply = claim(client, bearer(realm, WORKER), task_id)

    assert reply.status_code in (404, 422)
    assert operaton.queries == []


def test_claim_needs_access_token(client, operaton):
    operaton.add_task()

    assert client.post("/tasks/viec-1/claim").status_code == 401
    assert operaton.queries == []


def test_unavailable_operaton_gives_503_for_claim(client, operaton, realm):
    operaton.failure = OperatonUnavailableError("Không kết nối được Operaton: refused")

    reply = claim(client, bearer(realm, WORKER))

    assert (reply.status_code, reply.json()) == (
        503,
        {"detail": "Chưa nhận được việc vì Operaton chưa sẵn sàng"},
    )


def test_openapi_document_describes_claim(client):
    document = client.get("/openapi.json").json()
    operation = document["paths"]["/tasks/{task_id}/claim"]["post"]

    assert operation["security"] == [{"HTTPBearer": []}]
    assert {"204", "401", "403", "404", "409", "422", "502", "503"} <= operation["responses"].keys()
    assert "content" not in operation["responses"]["204"]


def test_assignee_completes_task_through_form_with_variables(client, operaton, realm, assigned):
    variables = {"ket_qua": "Đã thay cáp", "so_gio": 2, "ty_le": 0.5, "xong": True, "ghi_chu": None}

    reply = complete(client, bearer(realm, WORKER), variables=variables)

    assert (reply.status_code, reply.content) == (204, b"")
    assert operaton.submitted == [
        (
            "viec-1",
            {
                "ket_qua": {"value": "Đã thay cáp", "type": "String"},
                "so_gio": {"value": 2, "type": "Long"},
                "ty_le": {"value": 0.5, "type": "Double"},
                "xong": {"value": True, "type": "Boolean"},
                "ghi_chu": {"value": None, "type": "Null"},
            },
        )
    ]
    assert "viec-1" not in operaton.items


def test_complete_without_body_submits_empty_form(client, operaton, realm, assigned):
    reply = client.post("/tasks/viec-1/complete", headers=bearer(realm, WORKER))

    assert reply.status_code == 204
    assert operaton.submitted == [("viec-1", {})]


@pytest.mark.parametrize("assignee", [None, "nguoi-khac"], ids=["chưa ai nhận", "người khác nhận"])
def test_only_assignee_can_complete_task(client, operaton, realm, assignee):
    operaton.deploy("yeu_cau", PROCESS)
    operaton.add_task(assignee=assignee)

    reply = complete(client, bearer(realm, WORKER, "admin"))

    assert (reply.status_code, reply.json()) == (403, NOT_ASSIGNEE)
    assert operaton.submitted == []
    assert operaton.items["viec-1"]["assignee"] == assignee


def test_complete_of_unknown_task_is_not_found(client, operaton, realm):
    reply = complete(client, bearer(realm, WORKER))

    assert (reply.status_code, reply.json()) == (404, NOT_FOUND)
    assert operaton.submitted == []


def test_suspended_task_cannot_be_completed(client, operaton, realm):
    operaton.deploy("yeu_cau", PROCESS)
    operaton.add_task(assignee=realm.subject, suspended=True)

    reply = complete(client, bearer(realm, WORKER))

    assert (reply.status_code, reply.json()) == (409, SUSPENDED)
    assert operaton.submitted == []


@pytest.mark.parametrize("name", ["initiator", "nguoi_tao"])
def test_assignee_cannot_send_variable_of_initiator(client, operaton, realm, assigned, name):
    reply = complete(client, bearer(realm, WORKER), variables={name: "nguoi-khac", "ket_qua": "x"})

    assert reply.status_code == 422
    assert reply.json()["detail"] == (
        f"Biến {name} do service core ghi bằng mã người gọi. Người gọi không gửi được biến này"
    )
    assert operaton.submitted == []


def test_bpmn_of_task_is_read_once_per_version(client, operaton, realm, assigned):
    operaton.add_task("viec-2", assignee=realm.subject)

    for task_id in ("viec-1", "viec-2"):
        assert complete(client, bearer(realm, WORKER), task_id).status_code == 204

    assert operaton.looked_up == ["yeu_cau:1:0001"]
    assert operaton.read == ["yeu_cau:1:0001"]


@pytest.mark.parametrize(
    ("change", "status", "detail"),
    [
        (None, 404, NOT_FOUND),
        (lambda realm: {"assignee": "nguoi-khac"}, 403, NOT_ASSIGNEE),
        (lambda realm: {"suspended": True}, 409, SUSPENDED),
        (lambda realm: {}, 502, {"detail": "Operaton báo lỗi khi hoàn thành việc"}),
    ],
    ids=["việc vừa kết thúc", "việc vừa chuyển cho người khác", "việc vừa tạm ngưng", "lỗi khác"],
)
def test_complete_refused_by_operaton_follows_new_state_of_task(
    client, operaton, realm, assigned, change, status, detail
):
    def race(task_id):
        if change is None:
            del operaton.items[task_id]
        else:
            operaton.items[task_id] |= change(realm)
        raise OperatonError(500, LOCKED)

    operaton.race = race

    reply = complete(client, bearer(realm, WORKER))

    assert (reply.status_code, reply.json()) == (status, detail)


@pytest.mark.parametrize(
    "content",
    [
        '{"variables": {"ket_qua": NaN}}',
        '{"variables": {"1ket_qua": "x"}}',
        '{"variables": {"ket_qua": ["x"]}}',
        '{"variables": {}, "ghi_chu": "x"}',
    ],
)
def test_body_outside_schema_is_refused_for_complete(client, operaton, realm, assigned, content):
    headers = bearer(realm, WORKER) | {"Content-Type": "application/json"}

    reply = client.post("/tasks/viec-1/complete", headers=headers, content=content)

    assert reply.status_code == 422
    assert operaton.submitted == []


def test_complete_needs_access_token(client, operaton, assigned):
    assert client.post("/tasks/viec-1/complete").status_code == 401
    assert operaton.submitted == []


def test_unavailable_operaton_gives_503_for_complete(client, operaton, realm):
    operaton.failure = OperatonUnavailableError("Không kết nối được Operaton: refused")

    reply = complete(client, bearer(realm, WORKER))

    assert (reply.status_code, reply.json()) == (
        503,
        {"detail": "Chưa hoàn thành được việc vì Operaton chưa sẵn sàng"},
    )


def test_openapi_document_describes_complete(client):
    document = client.get("/openapi.json").json()
    operation = document["paths"]["/tasks/{task_id}/complete"]["post"]
    body = operation["requestBody"]["content"]["application/json"]["schema"]

    assert operation["security"] == [{"HTTPBearer": []}]
    assert {"204", "401", "403", "404", "409", "422", "502", "503"} <= operation["responses"].keys()
    assert "CompleteRequest" in json.dumps(body)
