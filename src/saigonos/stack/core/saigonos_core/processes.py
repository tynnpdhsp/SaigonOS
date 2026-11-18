# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from typing import Annotated, Any
from xml.etree import ElementTree

from fastapi import APIRouter, Body, HTTPException, Path, Request
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    StringConstraints,
)
from starlette.concurrency import run_in_threadpool

from saigonos_core.api import BAD_GATEWAY, UNAUTHORIZED, UNAVAILABLE, Message, User, operaton_errors
from saigonos_core.operaton import Operaton

BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
EXTENSIONS = ("http://operaton.org/schema/1.0/bpmn", "http://camunda.org/schema/1.0/bpmn")
INITIATOR = "initiator"
KEY = r"^[A-Za-z_][A-Za-z0-9_.-]*$"
NAME = r"^[A-Za-z_][A-Za-z0-9_]*$"
MAX_KEY = 255
MAX_NAME = 64
MAX_TEXT = 4000
MAX_LONG = 2**63 - 1
NOT_FOUND = "Không tìm thấy quy trình"
FORBIDDEN = "Người gọi không có realm role được bắt đầu quy trình này"
SUSPENDED = "Quy trình đang tạm ngưng"


def floating(value: Any) -> Any:
    if not isinstance(value, float):
        raise ValueError("Giá trị phải là số thực")
    return value


Text = Annotated[StrictStr, Field(max_length=MAX_TEXT)]
Whole = Annotated[StrictInt, Field(ge=-MAX_LONG - 1, le=MAX_LONG)]
Number = Annotated[StrictFloat, Field(allow_inf_nan=False), BeforeValidator(floating)]
Value = StrictBool | Whole | Number | Text | None
Name = Annotated[str, StringConstraints(pattern=NAME, max_length=MAX_NAME)]
Key = Annotated[
    str, Path(pattern=KEY, max_length=MAX_KEY, description="Mã quy trình trong file BPMN")
]


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variables: dict[Name, Value] = Field(
        default_factory=dict,
        description=(
            "Biến của quy trình. Giá trị là chuỗi tối đa 4.000 ký tự, số nguyên, số thực, "
            "true, false hoặc null"
        ),
        examples=[{"noi_dung": "Máy 12 không lên màn hình", "so_luong": 1}],
    )


class StartedProcess(BaseModel):
    id: str = Field(description="Mã của quy trình vừa bắt đầu (process instance)")
    process_key: str = Field(description="Mã quy trình trong file BPMN")
    version: int = Field(description="Phiên bản của quy trình")


@dataclass(frozen=True)
class Rules:
    starters: frozenset[str]
    initiators: frozenset[str]


def extension(element: ElementTree.Element, name: str) -> str | None:
    for namespace in EXTENSIONS:
        value = element.get(f"{{{namespace}}}{name}")
        if value is not None:
            return value
    return None


def listed(value: str | None) -> frozenset[str]:
    return frozenset(part.strip() for part in (value or "").split(",") if part.strip())


def rules_of(xml: str, key: str) -> Rules:
    for process in ElementTree.fromstring(xml).iter(f"{{{BPMN}}}process"):
        if process.get("id") == key:
            events = process.findall(f"{{{BPMN}}}startEvent")
            initiators = {extension(event, "initiator") for event in events}
            return Rules(
                listed(extension(process, "candidateStarterGroups")),
                frozenset({INITIATOR} | {name for name in initiators if name}),
            )
    return Rules(frozenset(), frozenset({INITIATOR}))


def typed(value: Any) -> dict[str, Any]:
    if value is None:
        kind = "Null"
    elif isinstance(value, bool):
        kind = "Boolean"
    elif isinstance(value, int):
        kind = "Long"
    elif isinstance(value, float):
        kind = "Double"
    else:
        kind = "String"
    return {"value": value, "type": kind}


class Processes:
    def __init__(self, operaton: Operaton) -> None:
        self.operaton = operaton
        self.known: dict[str, Rules] = {}

    def latest(self, key: str) -> tuple[dict[str, Any], Rules] | None:
        definition = self.operaton.latest_definition(key)
        if definition is None:
            return None
        rules = self.known.get(definition["id"])
        if rules is None:
            rules = rules_of(self.operaton.definition_xml(definition["id"]), key)
            self.known[definition["id"]] = rules
        return definition, rules


router = APIRouter(prefix="/processes")


@router.post(
    "/{key}/start",
    status_code=201,
    summary="Bắt đầu phiên bản mới nhất của quy trình",
    responses=UNAUTHORIZED
    | {
        403: {"model": Message, "description": FORBIDDEN},
        404: {"model": Message, "description": NOT_FOUND},
        409: {"model": Message, "description": SUSPENDED},
    }
    | BAD_GATEWAY
    | UNAVAILABLE,
)
async def start_process(
    key: Key,
    request: Request,
    user: User,
    start: Annotated[StartRequest | None, Body()] = None,
) -> StartedProcess:
    variables = start.variables if start else {}
    processes = request.app.state.processes
    with operaton_errors("Chưa bắt đầu được quy trình", "bắt đầu quy trình"):
        found = await run_in_threadpool(processes.latest, key)
        if found is None:
            raise HTTPException(404, f"{NOT_FOUND} {key}")
        definition, rules = found
        if not rules.starters & user.realm_roles:
            raise HTTPException(403, FORBIDDEN)
        if definition["suspended"]:
            raise HTTPException(409, SUSPENDED)
        reserved = sorted(rules.initiators & variables.keys())
        if reserved:
            raise HTTPException(
                422,
                f"Biến {', '.join(reserved)} do service core ghi bằng mã người gọi. "
                "Người gọi không gửi được biến này",
            )
        sent = {name: typed(value) for name, value in variables.items()}
        sent |= {name: typed(user.claims["sub"]) for name in rules.initiators}
        instance = await run_in_threadpool(
            processes.operaton.submit_start_form, definition["id"], sent
        )
    return StartedProcess(id=instance["id"], process_key=key, version=definition["version"])
