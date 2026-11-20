# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field

from saigonos_core.api import UNAUTHORIZED, UNAVAILABLE, Message, User

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_OFFSET = 2**63 - 1
LIST = """
SELECT id, title, body, link, created_at, read_at FROM core.notifications
WHERE recipient = core.uid()
ORDER BY created_at DESC, id DESC
OFFSET $1 LIMIT $2
"""
MARK_READ = """
UPDATE core.notifications SET read_at = now()
WHERE id = $1 AND recipient = core.uid() AND read_at IS NULL
RETURNING id, title, body, link, created_at, read_at
"""
FIND = """
SELECT id, title, body, link, created_at, read_at FROM core.notifications
WHERE id = $1 AND recipient = core.uid()
"""
NOT_FOUND = "Không tìm thấy thông báo"

router = APIRouter(prefix="/notifications")


class Notification(BaseModel):
    id: UUID
    title: str
    body: str | None
    link: str | None = Field(description="Đường dẫn tới một trang trong hệ thống, bắt đầu bằng /")
    created_at: datetime
    read_at: datetime | None = Field(
        description="Thời điểm người nhận đánh dấu đã đọc. Giá trị null nghĩa là chưa đọc"
    )


@router.get(
    "",
    summary="Thông báo của người gọi",
    description="Trả về các thông báo gửi cho người gọi. Thông báo mới nhất đứng đầu",
    responses=UNAUTHORIZED | UNAVAILABLE,
)
async def list_notifications(
    request: Request,
    user: User,
    offset: Annotated[
        int, Query(ge=0, le=MAX_OFFSET, description="Số thông báo bỏ qua ở đầu danh sách")
    ] = 0,
    limit: Annotated[
        int, Query(ge=1, le=MAX_LIMIT, description="Số thông báo tối đa được trả về")
    ] = DEFAULT_LIMIT,
) -> list[Notification]:
    async with request.app.state.database.session(user) as connection:
        rows = await connection.fetch(LIST, offset, limit)
    return [Notification(**row) for row in rows]


@router.post(
    "/{notification_id}/read",
    summary="Đánh dấu thông báo đã đọc",
    description=(
        "Ghi thời điểm đọc của một thông báo gửi cho người gọi. Gọi lại với thông báo đã đọc thì "
        "thời điểm đọc không đổi"
    ),
    responses=UNAUTHORIZED | {404: {"model": Message, "description": NOT_FOUND}} | UNAVAILABLE,
)
async def mark_read(
    notification_id: Annotated[UUID, Path(description="Mã của thông báo")],
    request: Request,
    user: User,
) -> Notification:
    async with request.app.state.database.service_session(user) as connection:
        row = await connection.fetchrow(MARK_READ, notification_id)
        if row is None:
            row = await connection.fetchrow(FIND, notification_id)
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return Notification(**row)
