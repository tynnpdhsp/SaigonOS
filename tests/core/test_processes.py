# SPDX-License-Identifier: Apache-2.0
import logging

import pytest
from fastapi.testclient import TestClient

from saigonos_core.main import create_app
from saigonos_core.operaton import OperatonError, OperatonUnavailableError
from saigonos_core.processes import rules_of

OPERATON = "http://operaton.org/schema/1.0/bpmn"
CAMUNDA = "http://camunda.org/schema/1.0/bpmn"
STARTER = "nguoi-gui"
FORBIDDEN = {"detail": "Người gọi không có realm role được bắt đầu quy trình này"}
REQUIRED = '<operaton:constraint name="required" />'


def form_field(name, kind="string", *constraints):
    validation = f"<operaton:validation>{''.join(constraints)}</operaton:validation>"
    return f'<operaton:formField id="{name}" type="{kind}">{validation}</operaton:formField>'


FIELDS = (
    form_field("noi_dung"),
    form_field("so_luong", "long"),
    form_field("khan", "boolean"),
    form_field("han", "date"),
    form_field("ghi"),
)


def bpmn(key, starters=None, initiator=None, prefix="operaton", extra="", fields=FIELDS):
    starter = f' {prefix}:candidateStarterGroups="{starters}"' if starters is not None else ""
    event = f' {prefix}:initiator="{initiator}"' if initiator else ""
    data = ""
    if fields is not None:
        data = f"<operaton:formData>{''.join(fields)}</operaton:formData>"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:operaton="{OPERATON}" xmlns:camunda="{CAMUNDA}"
                  id="dinh_nghia" targetNamespace="https://dx.example.com/bpmn">
  <bpmn:process id="khac" isExecutable="true" operaton:candidateStarterGroups="{STARTER}">
    <bpmn:startEvent id="bat_dau_khac" operaton:initiator="nguoi_khac" />
  </bpmn:process>
  <bpmn:process id="{key}" isExecutable="true"{starter}{extra}>
    <bpmn:startEvent id="bat_dau"{event}>
      <bpmn:extensionElements>{data}</bpmn:extensionElements>
    </bpmn:startEvent>
  </bpmn:process>
</bpmn:definitions>
"""


class IdleDatabase:
    async def open(self):
        pass

    async def close(self):
        pass


@pytest.fixture
def client(settings, scans, operaton, steps):
    app = create_app(settings, IdleDatabase(), scans=scans, operaton=operaton, steps=steps)
    with TestClient(app) as client:
        yield client


def bearer(realm, *roles, **changes):
    token = realm.token(realm_access={"roles": ["authenticated", *roles]}, **changes)
    return {"Authorization": f"Bearer {token}"}


def start(client, headers, key="yeu_cau", variables=None):
    body = None if variables is None else {"variables": variables}
    return client.post(f"/processes/{key}/start", headers=headers, json=body)


def initiator(realm):
    return {"value": realm.subject, "type": "String"}


def test_caller_with_starter_role_starts_latest_version(client, operaton, realm):
    operaton.deploy("yeu_cau", bpmn("yeu_cau", f"quan-ly,{STARTER}"), version=1)
    latest = operaton.deploy("yeu_cau", bpmn("yeu_cau", f"quan-ly,{STARTER}"), version=3)
    variables = {"noi_dung": "Máy 12 hỏng", "so_luong": 2, "khan": True, "ghi": None}

    reply = start(client, bearer(realm, STARTER), variables=variables)

    assert reply.status_code == 201
    assert reply.json() == {"id": "quy-trinh-1", "process_key": "yeu_cau", "version": 3}
    assert operaton.started == [
        (
            latest["id"],
            {
                "noi_dung": {"value": "Máy 12 hỏng", "type": "String"},
                "so_luong": {"value": 2, "type": "Long"},
                "khan": {"value": True, "type": "Boolean"},
                "ghi": {"value": None, "type": "Null"},
                "initiator": initiator(realm),
            },
        )
    ]


def test_start_without_body_sends_only_initiator(client, operaton, realm):
    operaton.deploy("yeu_cau", bpmn("yeu_cau", STARTER))

    reply = client.post("/processes/yeu_cau/start", headers=bearer(realm, STARTER))

    assert reply.status_code == 201
    assert operaton.started == [("yeu_cau:1:0001", {"initiator": initiator(realm)})]


def test_variable_named_by_initiator_of_start_event_gets_caller(client, operaton, realm):
    operaton.deploy("yeu_cau", bpmn("yeu_cau", STARTER, initiator="nguoi_tao"))

    reply = start(client, bearer(realm, STARTER), variables={"noi_dung": "Máy 12 hỏng"})

    assert reply.status_code == 201
    assert operaton.started[0][1] == {
        "noi_dung": {"value": "Máy 12 hỏng", "type": "String"},
        "initiator": initiator(realm),
        "nguoi_tao": initiator(realm),
    }


def test_caller_without_starter_role_cannot_start(client, operaton, realm):
    operaton.deploy("yeu_cau", bpmn("yeu_cau", STARTER))

    reply = start(client, bearer(realm, "nguoi", "nguoi-gui-khac", "admin"))

    assert (reply.status_code, reply.json()) == (403, FORBIDDEN)
    assert operaton.started == []


@pytest.mark.parametrize("starters", [None, "", " , ", "${'nguoi-gui'}"])
def test_process_without_starter_groups_cannot_be_started_by_anyone(
    client, operaton, realm, starters
):
    operaton.deploy("yeu_cau", bpmn("yeu_cau", starters))

    reply = start(client, bearer(realm, STARTER, "admin"))

    assert (reply.status_code, reply.json()) == (403, FORBIDDEN)
    assert operaton.started == []


@pytest.mark.parametrize(
    ("xml", "starters"),
    [
        (bpmn("yeu_cau", " nguoi-gui , ,quan-ly "), {"nguoi-gui", "quan-ly"}),
        (bpmn("yeu_cau", "nguoi-gui", prefix="camunda"), {"nguoi-gui"}),
        (
            bpmn("yeu_cau", "quan-ly", extra=' camunda:candidateStarterGroups="nguoi-gui"'),
            {"quan-ly"},
        ),
        (bpmn("yeu_cau", extra=' activiti:candidateStarterGroups="nguoi-gui"'), set()),
        (bpmn("khong_co_trong_file", "nguoi-gui"), set()),
    ],
)
def test_starter_groups_are_read_as_operaton_reads_them(xml, starters):
    xml = xml.replace(
        'xmlns:camunda="', 'xmlns:activiti="http://activiti.org/bpmn" xmlns:camunda="'
    )

    assert rules_of(xml, "yeu_cau").starters == starters


@pytest.mark.parametrize(
    ("xml", "initiators"),
    [
        (bpmn("yeu_cau", STARTER), {"initiator"}),
        (bpmn("yeu_cau", STARTER, initiator="nguoi_tao"), {"initiator", "nguoi_tao"}),
        (
            bpmn("yeu_cau", STARTER, initiator="nguoi_tao", prefix="camunda"),
            {"initiator", "nguoi_tao"},
        ),
    ],
)
def test_initiators_are_read_from_start_events_of_process(xml, initiators):
    rules = rules_of(xml, "yeu_cau")

    assert (rules.starters, rules.initiators) == (frozenset({STARTER}), frozenset(initiators))


@pytest.mark.parametrize("name", ["initiator", "nguoi_tao"])
def test_caller_cannot_send_variable_of_initiator(client, operaton, realm, name):
    operaton.deploy("yeu_cau", bpmn("yeu_cau", STARTER, initiator="nguoi_tao"))

    reply = start(client, bearer(realm, STARTER), variables={name: "nguoi-khac", "noi_dung": "x"})

    assert reply.status_code == 422
    assert reply.json()["detail"] == (
        f"Biến {name} do service core ghi bằng mã người gọi. Người gọi không gửi được biến này"
    )
    assert operaton.started == []


def test_values_are_sent_with_types_of_start_form(client, operaton, realm):
    operaton.deploy("yeu_cau", bpmn("yeu_cau", STARTER))

    reply = start(client, bearer(realm, STARTER), variables={"han": "2026-11-20T09:00:00+07:00"})

    assert reply.status_code == 201
    assert operaton.started[0][1] == {
        "han": {"value": "2026-11-20T02:00:00.000+0000", "type": "Date"},
        "initiator": initiator(realm),
    }


def test_variable_outside_start_form_is_refused(client, operaton, realm):
    operaton.deploy("yeu_cau", bpmn("yeu_cau", STARTER))

    reply = start(client, bearer(realm, STARTER), variables={"noi_dung": "x", "ty_le": 0.5})

    assert (reply.status_code, reply.json()) == (
        422,
        {"detail": "Form bắt đầu của quy trình không nhận biến ty_le"},
    )
    assert operaton.started == []


@pytest.mark.parametrize("fields", [None, ()], ids=["không có form", "form không có trường"])
def test_process_without_start_form_is_started_without_variables(client, operaton, realm, fields):
    operaton.deploy("yeu_cau", bpmn("yeu_cau", STARTER, fields=fields))

    started = start(client, bearer(realm, STARTER))
    refused = start(client, bearer(realm, STARTER), variables={"noi_dung": "x"})

    assert started.status_code == 201
    assert (refused.status_code, refused.json()) == (
        422,
        {"detail": "Form bắt đầu của quy trình không nhận biến noi_dung"},
    )
    assert operaton.started == [("yeu_cau:1:0001", {"initiator": initiator(realm)})]


@pytest.mark.parametrize(
    "variables",
    [{"ghi": "x"}, {"noi_dung": None}, {"noi_dung": ""}, {"noi_dung": " \t\n "}],
    ids=["thiếu", "null", "rỗng", "khoảng trắng"],
)
def test_required_field_of_start_form_needs_value(client, operaton, realm, variables):
    fields = (form_field("noi_dung", "string", REQUIRED), form_field("ghi"))
    operaton.deploy("yeu_cau", bpmn("yeu_cau", STARTER, fields=fields))

    reply = start(client, bearer(realm, STARTER), variables=variables)

    assert (reply.status_code, reply.json()) == (
        422,
        {"detail": "LỖI TUÂN THỦ: Phải nhập noi_dung"},
    )
    assert operaton.started == []


def test_unknown_process_is_not_found(client, operaton, realm):
    reply = start(client, bearer(realm, STARTER), key="khong_co")

    assert (reply.status_code, reply.json()) == (
        404,
        {"detail": "Không tìm thấy quy trình khong_co"},
    )


@pytest.mark.parametrize("key", ["1yeu_cau", "-yeu_cau", "yeu cau", "yeu%2Fcau", "y" * 256])
def test_key_outside_pattern_is_refused(client, operaton, realm, key):
    operaton.deploy(key, bpmn(key, STARTER))

    reply = start(client, bearer(realm, STARTER), key=key)

    assert reply.status_code in (404, 422)
    assert operaton.started == []


def test_suspended_process_cannot_be_started(client, operaton, realm):
    operaton.deploy("yeu_cau", bpmn("yeu_cau", STARTER), suspended=True)

    reply = start(client, bearer(realm, STARTER))

    assert (reply.status_code, reply.json()) == (409, {"detail": "Quy trình đang tạm ngưng"})
    assert operaton.started == []


@pytest.mark.parametrize(
    "variables",
    [
        {"1noi_dung": "x"},
        {"noi-dung": "x"},
        {"n" * 65: "x"},
        {"so_luong": 2**63},
        {"so_luong": -(2**63) - 1},
        {"noi_dung": "x" * 4001},
        {"noi_dung": {"tieu_de": "x"}},
        {"noi_dung": ["x"]},
    ],
)
def test_variable_outside_supported_values_is_refused(client, operaton, realm, variables):
    operaton.deploy("yeu_cau", bpmn("yeu_cau", STARTER))

    reply = start(client, bearer(realm, STARTER), variables=variables)

    assert reply.status_code == 422
    assert operaton.started == []


def test_largest_supported_values_are_accepted(client, operaton, realm):
    fields = (form_field("n" * 64), form_field("lon", "long"), form_field("nho", "long"))
    operaton.deploy("yeu_cau", bpmn("yeu_cau", STARTER, fields=fields))
    variables = {"n" * 64: "x" * 4000, "lon": 2**63 - 1, "nho": -(2**63)}

    reply = start(client, bearer(realm, STARTER), variables=variables)

    assert reply.status_code == 201
    assert operaton.started[0][1]["lon"] == {"value": 2**63 - 1, "type": "Long"}


@pytest.mark.parametrize(
    "content",
    [
        '{"variables": {"ty_le": NaN}}',
        '{"variables": {"ty_le": Infinity}}',
        '{"variables": {}, "businessKey": "x"}',
        '{"variables": "x"}',
    ],
)
def test_body_outside_schema_is_refused(client, operaton, realm, content):
    operaton.deploy("yeu_cau", bpmn("yeu_cau", STARTER))
    headers = bearer(realm, STARTER) | {"Content-Type": "application/json"}

    reply = client.post("/processes/yeu_cau/start", headers=headers, content=content)

    assert reply.status_code == 422
    assert operaton.started == []


def test_bpmn_is_read_once_per_version(client, operaton, realm):
    first = operaton.deploy("yeu_cau", bpmn("yeu_cau", STARTER))
    for _ in range(2):
        start(client, bearer(realm, STARTER))
    second = operaton.deploy("yeu_cau", bpmn("yeu_cau", "quan-ly"), version=2)

    refused = start(client, bearer(realm, STARTER))

    assert refused.status_code == 403
    assert operaton.read == [first["id"], second["id"]]


def test_unavailable_operaton_gives_503(client, operaton, realm, caplog):
    operaton.failure = OperatonUnavailableError("Không kết nối được Operaton: refused")

    reply = start(client, bearer(realm, STARTER))

    assert (reply.status_code, reply.json()) == (
        503,
        {"detail": "Chưa bắt đầu được quy trình vì Operaton chưa sẵn sàng"},
    )
    assert caplog.records[-1].levelno == logging.WARNING
    assert "Không kết nối được Operaton: refused" in caplog.records[-1].getMessage()


def test_error_of_operaton_gives_502_and_is_logged(client, operaton, realm, caplog):
    operaton.failure = OperatonError(500, "ENGINE-03043 Process Definition is suspended")

    reply = start(client, bearer(realm, STARTER))

    assert (reply.status_code, reply.json()) == (
        502,
        {"detail": "Operaton báo lỗi khi bắt đầu quy trình"},
    )
    assert caplog.records[-1].levelno == logging.ERROR
    assert "ENGINE-03043" in caplog.records[-1].getMessage()


def test_start_needs_access_token(client, operaton, realm):
    operaton.deploy("yeu_cau", bpmn("yeu_cau", STARTER))

    reply = start(client, {})

    assert reply.status_code == 401
    assert operaton.started == []


def test_openapi_document_describes_start(client):
    document = client.get("/openapi.json").json()
    operation = document["paths"]["/processes/{key}/start"]["post"]

    assert operation["security"] == [{"HTTPBearer": []}]
    assert {"201", "401", "403", "404", "409", "422", "502", "503"} <= operation["responses"].keys()
