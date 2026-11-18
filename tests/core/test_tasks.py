# SPDX-License-Identifier: Apache-2.0
import logging
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from saigonos_core.callers import caller_of
from saigonos_core.main import create_app
from saigonos_core.operaton import OperatonError, OperatonUnavailableError
from saigonos_core.tasks import SORTING, query_of

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
