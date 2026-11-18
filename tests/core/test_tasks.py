# SPDX-License-Identifier: Apache-2.0
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
SUSPENDED = {"detail": "Việc đang tạm ngưng"}
LOCKED = "ENGINE-03005 Entity was updated by another transaction concurrently."
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
