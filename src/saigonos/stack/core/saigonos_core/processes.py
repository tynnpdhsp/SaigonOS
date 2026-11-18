# SPDX-License-Identifier: Apache-2.0
import re
from collections.abc import Callable
from dataclasses import dataclass, field
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
from saigonos_core.forms import START_FORM, Form, FormField, submitted
from saigonos_core.operaton import Operaton

BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
EXTENSIONS = ("http://operaton.org/schema/1.0/bpmn", "http://camunda.org/schema/1.0/bpmn")
INITIATOR = "initiator"
NUMBER = re.compile(r"[+-]?[0-9]+")
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
            "Giá trị của các trường trong form bắt đầu của quy trình. Tên biến là thuộc tính id "
            "của trường trong file BPMN"
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
    start_form: Form = ()
    task_forms: dict[str, Form] = field(default_factory=dict)


def extension(element: ElementTree.Element, name: str) -> str | None:
    for namespace in EXTENSIONS:
        value = element.get(f"{{{namespace}}}{name}")
        if value is not None:
            return value
    return None


def children(element: ElementTree.Element | None, name: str) -> list[ElementTree.Element]:
    if element is None:
        return []
    for namespace in EXTENSIONS:
        found = element.findall(f"{{{namespace}}}{name}")
        if found:
            return found
    return []


def child(element: ElementTree.Element | None, name: str) -> ElementTree.Element | None:
    return next(iter(children(element, name)), None)


def listed(value: str | None) -> frozenset[str]:
    return frozenset(part.strip() for part in (value or "").split(",") if part.strip())


def number(config: str | None) -> int | None:
    return int(config) if config is not None and NUMBER.fullmatch(config) else None


def bound(
    configs: dict[str | None, list[int | None]], name: str, strictest: Callable[[list[int]], int]
) -> int | None:
    values = [value for value in configs.get(name, []) if value is not None]
    return strictest(values) if values else None


def field_of(element: ElementTree.Element) -> FormField:
    configs: dict[str | None, list[int | None]] = {}
    for constraint in children(child(element, "validation"), "constraint"):
        configs.setdefault(constraint.get("name"), []).append(number(constraint.get("config")))
    choices = (value.get("id") for value in children(element, "value"))
    return FormField(
        name=element.get("id", ""),
        kind=element.get("type", ""),
        label=(element.get("label") or "").strip() or None,
        required="required" in configs,
        readonly="readonly" in configs,
        min_length=bound(configs, "minlength", max),
        max_length=bound(configs, "maxlength", min),
        minimum=bound(configs, "min", max),
        maximum=bound(configs, "max", min),
        choices=tuple(choice for choice in choices if choice is not None),
    )


def form_of(element: ElementTree.Element | None) -> Form:
    if element is None:
        return ()
    data = child(element.find(f"{{{BPMN}}}extensionElements"), "formData")
    fields: dict[str, FormField] = {}
    for item in children(data, "formField"):
        found = field_of(item)
        fields.setdefault(found.name, found)
    return tuple(fields.values())


def initial_event(process: ElementTree.Element) -> ElementTree.Element | None:
    for event in process.findall(f"{{{BPMN}}}startEvent"):
        if not any(item.tag.endswith(("EventDefinition", "eventDefinitionRef")) for item in event):
            return event
    return None


def rules_of(xml: str, key: str) -> Rules:
    for process in ElementTree.fromstring(xml).iter(f"{{{BPMN}}}process"):
        if process.get("id") == key:
            events = process.findall(f"{{{BPMN}}}startEvent")
            initiators = {extension(event, "initiator") for event in events}
            tasks = process.iter(f"{{{BPMN}}}userTask")
            return Rules(
                listed(extension(process, "candidateStarterGroups")),
                frozenset({INITIATOR} | {name for name in initiators if name}),
                form_of(initial_event(process)),
                {task.get("id", ""): form_of(task) for task in tasks},
            )
    return Rules(frozenset(), frozenset({INITIATOR}))


def check_variables(rules: Rules, variables: dict[str, Any]) -> None:
    reserved = sorted(rules.initiators & variables.keys())
    if reserved:
        raise HTTPException(
            422,
            f"Biến {', '.join(reserved)} do service core ghi bằng mã người gọi. "
            "Người gọi không gửi được biến này",
        )


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

    def rules(self, definition_id: str, key: str | None = None) -> Rules:
        rules = self.known.get(definition_id)
        if rules is None:
            if key is None:
                key = self.operaton.definition(definition_id)["key"]
            rules = rules_of(self.operaton.definition_xml(definition_id), key)
            self.known[definition_id] = rules
        return rules

    def latest(self, key: str) -> tuple[dict[str, Any], Rules] | None:
        definition = self.operaton.latest_definition(key)
        if definition is None:
            return None
        return definition, self.rules(definition["id"], key)


router = APIRouter(prefix="/processes")


@router.post(
    "/{key}/start",
    status_code=201,
    summary="Bắt đầu phiên bản mới nhất của quy trình",
    description=(
        "Bắt đầu quy trình bằng form bắt đầu khai trong file BPMN. Nội dung chỉ được chứa các "
        "trường của form này. Khi một giá trị không đạt ràng buộc của trường, lời gọi nhận mã 422 "
        "với nội dung bắt đầu bằng LỖI TUÂN THỦ"
    ),
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
        check_variables(rules, variables)
        sent = submitted(rules.start_form, variables, START_FORM)
        sent |= {name: typed(user.claims["sub"]) for name in rules.initiators}
        instance = await run_in_threadpool(
            processes.operaton.submit_start_form, definition["id"], sent
        )
    return StartedProcess(id=instance["id"], process_key=key, version=definition["version"])
