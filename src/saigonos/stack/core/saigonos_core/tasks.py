# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from saigonos_core.api import (
    BAD_GATEWAY,
    UNAUTHORIZED,
    UNAVAILABLE,
    Message,
    User,
    operaton_errors,
)
from saigonos_core.callers import Caller
from saigonos_core.operaton import Operaton, OperatonError
from saigonos_core.processes import Name, Processes, Value, check_variables, typed

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
TASK_ID = r"^[A-Za-z0-9-]+$"
MAX_ID = 64
TIME = "%Y-%m-%dT%H:%M:%S.%f%z"
SORTING = [{"sortBy": "created", "sortOrder": "asc"}, {"sortBy": "id", "sortOrder": "asc"}]
NOT_FOUND = "Không tìm thấy việc"
NOT_CANDIDATE = "Người gọi không có realm role nằm trong nhóm ứng viên của việc này"
TAKEN = "Việc đã có người khác nhận"
NOT_ASSIGNEE = "Chỉ người nhận việc mới hoàn thành được việc này"
SUSPENDED = "Việc đang tạm ngưng"

TaskId = Annotated[str, Path(pattern=TASK_ID, max_length=MAX_ID, description="Mã của việc")]


class CompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variables: dict[Name, Value] = Field(
        default_factory=dict,
        description=(
            "Biến ghi vào quy trình khi hoàn thành việc. Giá trị là chuỗi tối đa 4.000 ký tự, "
            "số nguyên, số thực, true, false hoặc null"
        ),
        examples=[{"ket_qua": "Đã thay cáp màn hình"}],
    )


class Task(BaseModel):
    id: str
    name: str | None
    description: str | None
    assignee: str | None = Field(
        description="Mã (sub) của người nhận việc. Giá trị null nghĩa là việc đang chờ nhận"
    )
    created: datetime
    due: datetime | None = Field(description="Hạn xử lý")
    priority: int
    task_key: str = Field(description="Mã của việc trong file BPMN")
    process_instance_id: str
    process_definition_id: str
    suspended: bool


def instant(value: str | None) -> datetime | None:
    return None if value is None else datetime.strptime(value, TIME)


def task_of(data: dict[str, Any]) -> Task:
    return Task(
        id=data["id"],
        name=data["name"],
        description=data["description"],
        assignee=data["assignee"],
        created=instant(data["created"]),
        due=instant(data["due"]),
        priority=data["priority"],
        task_key=data["taskDefinitionKey"],
        process_instance_id=data["processInstanceId"],
        process_definition_id=data["processDefinitionId"],
        suspended=data["suspended"],
    )


def query_of(caller: Caller) -> dict[str, Any]:
    mine = {"assignee": caller.claims["sub"]}
    groups = sorted(caller.realm_roles)
    if not groups:
        return mine | {"sorting": SORTING}
    return {"orQueries": [mine | {"candidateGroups": groups}], "sorting": SORTING}


def candidate_query(task_id: str, caller: Caller) -> dict[str, Any]:
    groups = sorted(caller.realm_roles)
    return {"taskId": task_id, "candidateGroups": groups, "includeAssignedTasks": True}


def claimed_by(task: dict[str, Any], user: str) -> bool:
    if task["assignee"] == user:
        return True
    if task["assignee"] is not None:
        raise HTTPException(409, TAKEN)
    if task["suspended"]:
        raise HTTPException(409, SUSPENDED)
    return False


def claim_task(operaton: Operaton, task_id: str, caller: Caller) -> None:
    user = caller.claims["sub"]
    found = operaton.tasks(candidate_query(task_id, caller), 0, 1)
    if not found:
        if operaton.task(task_id) is None:
            raise HTTPException(404, NOT_FOUND)
        raise HTTPException(403, NOT_CANDIDATE)
    if claimed_by(found[0], user):
        return
    try:
        operaton.claim(task_id, user)
    except OperatonError:
        task = operaton.task(task_id)
        if task is None:
            raise HTTPException(404, NOT_FOUND) from None
        if not claimed_by(task, user):
            raise


def check_assignee(task: dict[str, Any], user: str) -> None:
    if task["assignee"] != user:
        raise HTTPException(403, NOT_ASSIGNEE)
    if task["suspended"]:
        raise HTTPException(409, SUSPENDED)


def complete_task(
    processes: Processes, task_id: str, caller: Caller, variables: dict[str, Any]
) -> None:
    operaton = processes.operaton
    user = caller.claims["sub"]
    task = operaton.task(task_id)
    if task is None:
        raise HTTPException(404, NOT_FOUND)
    check_assignee(task, user)
    check_variables(processes.rules(task["processDefinitionId"]), variables)
    try:
        operaton.submit_task_form(
            task_id, {name: typed(value) for name, value in variables.items()}
        )
    except OperatonError:
        task = operaton.task(task_id)
        if task is None:
            raise HTTPException(404, NOT_FOUND) from None
        check_assignee(task, user)
        raise


router = APIRouter(prefix="/tasks")


@router.get(
    "",
    summary="Việc của người gọi và việc chờ nhận",
    description=(
        "Trả về các việc mà người gọi đã nhận và các việc chưa ai nhận có nhóm ứng viên "
        "là một realm role của người gọi. Các việc được xếp theo thời điểm tạo"
    ),
    responses=UNAUTHORIZED | BAD_GATEWAY | UNAVAILABLE,
)
async def list_tasks(
    request: Request,
    user: User,
    offset: Annotated[int, Query(ge=0, description="Số việc bỏ qua ở đầu danh sách")] = 0,
    limit: Annotated[
        int, Query(ge=1, le=MAX_LIMIT, description="Số việc tối đa được trả về")
    ] = DEFAULT_LIMIT,
) -> list[Task]:
    with operaton_errors("Chưa lấy được danh sách việc", "lấy danh sách việc"):
        found = await run_in_threadpool(
            request.app.state.operaton.tasks, query_of(user), offset, limit
        )
    return [task_of(data) for data in found]


@router.post(
    "/{task_id}/claim",
    status_code=204,
    summary="Nhận việc",
    description=(
        "Nhận một việc chưa có người nhận. Người gọi cần một realm role nằm trong nhóm ứng viên "
        "của việc. Khi nhiều người cùng nhận một việc, chỉ một người nhận được. Gọi lại với "
        "việc mà người gọi đã nhận thì không có gì thay đổi"
    ),
    responses=UNAUTHORIZED
    | {
        403: {"model": Message, "description": NOT_CANDIDATE},
        404: {"model": Message, "description": NOT_FOUND},
        409: {"model": Message, "description": f"{TAKEN}, hoặc việc đang tạm ngưng"},
    }
    | BAD_GATEWAY
    | UNAVAILABLE,
)
async def claim(task_id: TaskId, request: Request, user: User) -> None:
    with operaton_errors("Chưa nhận được việc", "nhận việc"):
        await run_in_threadpool(claim_task, request.app.state.operaton, task_id, user)


@router.post(
    "/{task_id}/complete",
    status_code=204,
    summary="Hoàn thành việc",
    description=(
        "Hoàn thành một việc mà người gọi đã nhận. Các biến trong nội dung được gửi qua form "
        "của việc trong Operaton rồi ghi vào quy trình. Sau đó, quy trình đi tiếp"
    ),
    responses=UNAUTHORIZED
    | {
        403: {"model": Message, "description": NOT_ASSIGNEE},
        404: {"model": Message, "description": NOT_FOUND},
        409: {"model": Message, "description": SUSPENDED},
    }
    | BAD_GATEWAY
    | UNAVAILABLE,
)
async def complete(
    task_id: TaskId,
    request: Request,
    user: User,
    completion: Annotated[CompleteRequest | None, Body()] = None,
) -> None:
    variables = completion.variables if completion else {}
    with operaton_errors("Chưa hoàn thành được việc", "hoàn thành việc"):
        await run_in_threadpool(
            complete_task, request.app.state.processes, task_id, user, variables
        )
