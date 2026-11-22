# SPDX-License-Identifier: Apache-2.0
import asyncio
import json
import logging
import socket
from contextlib import asynccontextmanager, suppress

import asyncpg
import pytest

from saigonos_core.database import SEAL_CLAIMS, SET_CALLER
from saigonos_core.operaton import OperatonError, OperatonUnavailableError
from saigonos_core.processes import Processes
from saigonos_core.steps import (
    AS_SERVICE,
    CALL,
    CLAIM,
    FIND,
    LIMIT,
    LOCK,
    POLL,
    SAVE,
    STORED,
    TOPIC,
    Steps,
)

FUNCTION = "ung_dung.cap_nhat"
OID = 41000
DEFINITION = "yeu_cau:1:0001"
PROCESS = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:operaton="http://operaton.org/schema/1.0/bpmn"
                  id="dinh_nghia" targetNamespace="https://dx.example.com/bpmn">
  <bpmn:process id="yeu_cau" isExecutable="true" operaton:candidateStarterGroups="nguoi-gui">
    <bpmn:startEvent id="bat_dau" operaton:initiator="nguoi_tao" />
  </bpmn:process>
</bpmn:definitions>
"""
DECLARED = {"oid": OID, "takes_jsonb": True, "gives_jsonb": True, "declared": True}


class FakeConnection:
    def __init__(self, database):
        self.database = database
        self.role = "core_service"
        self.claimed = {}

    async def execute(self, query, *arguments):
        self.database.statements.append((query, *arguments))
        if query == SET_CALLER:
            self.role = arguments[0]
        elif query == SEAL_CLAIMS:
            assert self.role == "workflow"
        elif query == AS_SERVICE:
            self.role = "core_service"
        elif query == SAVE:
            assert self.role == "core_service"
            self.claimed[arguments[0]]["result"] = arguments[1]
        else:
            assert query == LIMIT

    async def fetchval(self, query, *arguments):
        self.database.statements.append((query, *arguments))
        if query == CLAIM:
            task_id, instance, activity, function = arguments
            if task_id in self.database.runs:
                return None
            self.claimed[task_id] = {"instance": instance, "activity": activity}
            self.claimed[task_id] |= {"function": function, "result": None}
            return True
        if query == STORED:
            return self.database.runs[arguments[0]]["result"]
        assert query == CALL
        assert self.role == "workflow"
        procedure, variables = arguments
        self.database.calls.append((procedure, json.loads(variables)))
        return self.database.function(json.loads(variables))

    async def fetch(self, query, schema, name):
        self.database.statements.append((query, schema, name))
        assert query == FIND
        return self.database.catalog.get(f"{schema}.{name}", [])


class FakeDatabase:
    def __init__(self):
        self.statements = []
        self.runs = {}
        self.calls = []
        self.catalog = {FUNCTION: [DECLARED]}
        self.function = lambda variables: json.dumps({"da_xu_ly": True})
        self.failure = None

    @asynccontextmanager
    async def transaction(self):
        if self.failure:
            error, self.failure = self.failure, None
            raise error
        connection = FakeConnection(self)
        yield connection
        self.runs |= connection.claimed


@pytest.fixture
def database():
    return FakeDatabase()


@pytest.fixture
def steps(database, operaton):
    operaton.deploy("yeu_cau", PROCESS)
    return Steps(database, operaton, Processes(operaton), worker="may-thu", poll=0.01, wait=0)


def external(function=FUNCTION, variables=None, retries=None, **changes):
    task = {
        "id": "buoc-1",
        "activityId": "cap_nhat",
        "processInstanceId": "quy-trinh-1",
        "processDefinitionId": DEFINITION,
        "processDefinitionKey": "yeu_cau",
        "retries": retries,
        "extensionProperties": {} if function is None else {"function": function},
        "variables": variables or {},
    } | changes
    return task


def handle(steps, task):
    asyncio.run(steps.handle(task))


def incident(operaton):
    [(task_id, worker, message, details, retries, delay)] = operaton.failed
    assert (task_id, worker, retries, delay) == ("buoc-1", "may-thu", 0, 0)
    assert details == message
    assert operaton.completed == []
    return message


def test_step_calls_declared_function_with_variables_as_workflow(steps, database, operaton):
    variables = {
        "noi_dung": {"type": "String", "value": "Máy 12 hỏng"},
        "so_luong": {"type": "Long", "value": 2},
        "uu_tien": {"type": "Integer", "value": 1},
        "ty_le": {"type": "Double", "value": 0.5},
        "khan": {"type": "Boolean", "value": True},
        "ghi_chu": {"type": "Null", "value": None},
        "han": {"type": "Date", "value": "2026-11-20T02:00:00.000+0000"},
    }
    result = {"da_xu_ly": True, "so_lan": 2, "ty_le": 0.25, "nhan": "Đã xử lý", "ghi_chu": None}
    database.function = lambda received: json.dumps(result)

    handle(steps, external(variables=variables))

    assert database.calls == [(OID, {name: item["value"] for name, item in variables.items()})]
    assert operaton.completed == [
        (
            "buoc-1",
            "may-thu",
            {
                "da_xu_ly": {"value": True, "type": "Boolean"},
                "so_lan": {"value": 2, "type": "Long"},
                "ty_le": {"value": 0.25, "type": "Double"},
                "nhan": {"value": "Đã xử lý", "type": "String"},
                "ghi_chu": {"value": None, "type": "Null"},
            },
        )
    ]
    assert database.runs == {
        "buoc-1": {
            "instance": "quy-trinh-1",
            "activity": "cap_nhat",
            "function": FUNCTION,
            "result": json.dumps(result),
        }
    }
    queries = [statement[0] for statement in database.statements]
    assert queries == [LIMIT, CLAIM, FIND, SET_CALLER, SEAL_CLAIMS, CALL, AS_SERVICE, SAVE]
    assert database.statements[3][1:] == ("workflow", json.dumps({"role": "workflow"}))


def test_step_that_already_ran_completes_with_stored_result(steps, database, operaton):
    database.runs["buoc-1"] = {"result": json.dumps({"da_xu_ly": True})}

    handle(steps, external())

    assert database.calls == []
    assert operaton.completed == [
        ("buoc-1", "may-thu", {"da_xu_ly": {"value": True, "type": "Boolean"}})
    ]


@pytest.mark.parametrize("returned", [None, "null"])
def test_function_returning_null_completes_without_variables(steps, database, operaton, returned):
    database.function = lambda variables: returned

    handle(steps, external())

    assert operaton.completed == [("buoc-1", "may-thu", {})]


@pytest.mark.parametrize(
    ("function", "message"),
    [
        (None, "Bước máy thiếu thuộc tính function nêu tên hàm dạng schema.ten_ham"),
        ("cap_nhat", "Tên hàm cap_nhat không hợp lệ."),
        ("Ung_Dung.Cap_Nhat", "Tên hàm Ung_Dung.Cap_Nhat không hợp lệ."),
        ("ung_dung.cap_nhat.phu", "Tên hàm ung_dung.cap_nhat.phu không hợp lệ."),
        ('ung_dung."cap nhat"', "không hợp lệ"),
        (f"ung_dung.{'a' * 64}", "không hợp lệ"),
    ],
    ids=["thieu-function", "thieu-schema", "chu-hoa", "ba-phan", "dau-ngoac-kep", "ten-qua-dai"],
)
def test_step_without_valid_function_name_becomes_incident(
    steps, database, operaton, function, message
):
    handle(steps, external(function))

    assert message in incident(operaton)
    assert database.statements == []


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([], "Không có hàm ung_dung.cap_nhat"),
        (
            [DECLARED | {"oid": 1, "takes_jsonb": False}],
            "Hàm ung_dung.cap_nhat phải nhận đúng một tham số kiểu jsonb",
        ),
        (
            [DECLARED | {"gives_jsonb": False}],
            "Hàm ung_dung.cap_nhat(jsonb) phải trả về một giá trị kiểu jsonb",
        ),
        (
            [DECLARED | {"declared": False}],
            "Hàm ung_dung.cap_nhat(jsonb) chưa được khai báo cho quy trình. Hãy cấp quyền bằng "
            "lệnh GRANT EXECUTE ON FUNCTION ung_dung.cap_nhat(jsonb) TO workflow",
        ),
    ],
    ids=["khong-co-ham", "sai-kieu-tham-so", "sai-kieu-tra-ve", "chua-khai-bao"],
)
def test_function_that_cannot_run_becomes_incident_without_call(
    steps, database, operaton, rows, message
):
    database.catalog[FUNCTION] = rows

    handle(steps, external())

    assert incident(operaton) == message
    assert database.calls == []
    assert database.runs == {}


def test_overload_with_jsonb_parameter_is_called(steps, database, operaton):
    database.catalog[FUNCTION] = [DECLARED | {"oid": 1, "takes_jsonb": False}, DECLARED]

    handle(steps, external())

    assert [procedure for procedure, _ in database.calls] == [OID]


@pytest.mark.parametrize("kind", ["Object", "Json", "Bytes", "File"])
def test_variable_of_other_type_becomes_incident(steps, database, operaton, kind):
    variables = {"tep": {"type": kind, "value": "..."}}

    handle(steps, external(variables=variables))

    assert incident(operaton).startswith(f"Biến tep có kiểu {kind}.")
    assert database.calls == []
    assert database.runs == {}


@pytest.mark.parametrize(
    ("retries", "left", "delay"),
    [(None, 3, 5), (3, 2, 30), (2, 1, 120), (1, 0, 0), (10, 9, 5)],
    ids=["lan-loi-dau", "lan-thu-hai", "lan-thu-ba", "het-luot", "quan-tri-cho-them-luot"],
)
def test_function_error_is_retried_with_growing_delay(
    steps, database, operaton, caplog, retries, left, delay
):
    def failing(variables):
        raise asyncpg.RaiseError("Không đủ dữ liệu")

    database.function = failing

    handle(steps, external(retries=retries))

    [(_, _, message, details, reported, waited)] = operaton.failed
    assert message == "Hàm ung_dung.cap_nhat báo lỗi: Không đủ dữ liệu"
    assert details == "SQLSTATE P0001: Không đủ dữ liệu"
    assert (reported, waited) == (left, delay)
    assert database.runs == {}
    assert operaton.completed == []
    assert caplog.records[-1].levelno == logging.WARNING


def test_details_of_function_error_keep_detail_hint_and_context(steps, database, operaton):
    def failing(variables):
        error = asyncpg.InsufficientPrivilegeError("permission denied for table yeu_cau")
        error.hint = "Hãy cấp quyền UPDATE cho role workflow"
        error.context = "SQL statement in function ung_dung.cap_nhat"
        raise error

    database.function = failing

    handle(steps, external())

    assert operaton.failed[0][3] == (
        "SQLSTATE 42501: permission denied for table yeu_cau\n"
        "Hãy cấp quyền UPDATE cho role workflow\n"
        "SQL statement in function ung_dung.cap_nhat"
    )


@pytest.mark.parametrize(
    ("returned", "message"),
    [
        ("[1, 2]", "Hàm ung_dung.cap_nhat phải trả về một object jsonb hoặc null"),
        ('"xong"', "Hàm ung_dung.cap_nhat phải trả về một object jsonb hoặc null"),
        ('{"so-lieu": 1}', "Khóa so-lieu trong kết quả của hàm ung_dung.cap_nhat"),
        ('{"chi_tiet": {"a": 1}}', "Khóa chi_tiet trong kết quả của hàm ung_dung.cap_nhat"),
        ('{"danh_sach": [1]}', "Khóa danh_sach trong kết quả"),
        (json.dumps({"dai": "x" * 4001}), "Khóa dai trong kết quả"),
        ('{"lon": 9223372036854775808}', "Khóa lon trong kết quả"),
        ('{"initiator": "nguoi-khac"}', "Hàm ung_dung.cap_nhat không được ghi biến initiator."),
        ('{"nguoi_tao": "nguoi-khac"}', "Hàm ung_dung.cap_nhat không được ghi biến nguoi_tao."),
    ],
    ids=[
        "mang",
        "chuoi",
        "ten-bien-sai",
        "object-long-nhau",
        "gia-tri-mang",
        "chuoi-qua-dai",
        "so-qua-lon",
        "ghi-initiator",
        "ghi-nguoi-tao",
    ],
)
def test_result_that_cannot_become_variables_becomes_incident(
    steps, database, operaton, returned, message
):
    database.function = lambda variables: returned

    handle(steps, external())

    assert message in incident(operaton)
    assert database.runs == {}


def test_largest_result_values_are_accepted(steps, database, operaton):
    result = {"n" * 64: "x" * 4000, "lon": 2**63 - 1, "nho": -(2**63)}
    database.function = lambda variables: json.dumps(result)

    handle(steps, external())

    assert operaton.completed[0][2]["lon"] == {"value": 2**63 - 1, "type": "Long"}


def test_refused_completion_is_logged_and_result_is_kept(steps, database, operaton, caplog):
    operaton.errors["complete"] = OperatonError(400, "It is locked by worker 'may-khac'.")

    handle(steps, external())

    assert "buoc-1" in database.runs
    assert caplog.records[-1].levelno == logging.WARNING
    assert "Chưa báo được Operaton là bước máy buoc-1 đã xong" in caplog.records[-1].getMessage()


def test_refused_failure_report_is_logged(steps, database, operaton, caplog):
    operaton.errors["fail"] = OperatonUnavailableError("Không kết nối được Operaton")

    handle(steps, external(function=None))

    assert caplog.records[-1].levelno == logging.WARNING
    assert "Chưa báo được Operaton là bước máy buoc-1 bị lỗi" in caplog.records[-1].getMessage()


def test_rules_of_definition_are_read_once(steps, database, operaton):
    for task_id in ("buoc-1", "buoc-2"):
        handle(steps, external(id=task_id))

    assert operaton.read == [DEFINITION]
    assert operaton.looked_up == []


async def drive(steps, done):
    worker = asyncio.create_task(steps.run())
    for _ in range(500):
        if done():
            break
        await asyncio.sleep(0.01)
    worker.cancel()
    with suppress(asyncio.CancelledError):
        await worker


def test_worker_locks_one_task_of_saigonos_topic_at_a_time(steps, database, operaton):
    operaton.external = [external(id="buoc-1"), external(id="buoc-2")]

    asyncio.run(drive(steps, lambda: len(operaton.completed) == 2))

    assert [task_id for task_id, _, _ in operaton.completed] == ["buoc-1", "buoc-2"]
    assert operaton.locks[0] == ("may-thu", TOPIC, LOCK, 0.01)
    assert (TOPIC, LOCK, POLL) == ("saigonos-function", 60, 5)


def test_worker_logs_unavailable_operaton_once_and_recovers(steps, operaton, caplog):
    operaton.errors["lock"] = OperatonUnavailableError("Không kết nối được Operaton: refused")
    operaton.external = [external()]

    def recovered():
        if len(operaton.locks) >= 5:
            operaton.errors.pop("lock", None)
        return bool(operaton.completed)

    asyncio.run(drive(steps, recovered))

    warnings = [
        record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING
    ]
    assert warnings == [
        "Chưa chạy được bước máy vì Operaton chưa sẵn sàng: Không kết nối được Operaton: refused"
    ]
    assert operaton.completed


def test_worker_keeps_running_after_unexpected_error(steps, database, operaton, caplog):
    database.failure = OSError("Không kết nối được PostgreSQL")
    operaton.external = [external(id="buoc-1"), external(id="buoc-2")]

    asyncio.run(drive(steps, lambda: bool(operaton.completed)))

    assert caplog.records[0].levelno == logging.ERROR
    assert "Chạy bước máy bị lỗi" in caplog.records[0].getMessage()
    assert [task_id for task_id, _, _ in operaton.completed] == ["buoc-2"]
    assert operaton.failed == []


def test_worker_is_named_after_container(database, operaton):
    steps = Steps(database, operaton, Processes(operaton))

    assert steps.worker == f"saigonos-core-{socket.gethostname()}"
