# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from saigonos_core.api import BAD_GATEWAY, UNAUTHORIZED, UNAVAILABLE, User, operaton_errors
from saigonos_core.callers import Caller

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
TIME = "%Y-%m-%dT%H:%M:%S.%f%z"
SORTING = [{"sortBy": "created", "sortOrder": "asc"}, {"sortBy": "id", "sortOrder": "asc"}]


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
