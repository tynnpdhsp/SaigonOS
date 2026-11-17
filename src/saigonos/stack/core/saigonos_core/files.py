# SPDX-License-Identifier: Apache-2.0
import hashlib
import logging
from datetime import datetime
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, Literal, NamedTuple
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from saigonos_core.api import UNAUTHORIZED, UNAVAILABLE, Message, User
from saigonos_core.kinds import HEADER_SIZE, KINDS, checked_name
from saigonos_core.storage import QUARANTINE, StorageError

MB = 1024 * 1024
SPOOL_SIZE = MB
CREATE = """
INSERT INTO core.files (name, type, size) VALUES ($1, $2, $3)
RETURNING id, name, type, size, sha256, status, malware, created_at, uploaded_at, scanned_at
"""
FIND = """
SELECT id, name, type, size, sha256, status, malware, created_at, uploaded_at, scanned_at
FROM core.files WHERE id = $1
"""
FIND_OWN = """
SELECT id, name, type, size, sha256, status, malware, created_at, uploaded_at, scanned_at
FROM core.files WHERE id = $1 AND owner = core.uid()
"""
LOCK_PENDING = """
SELECT id FROM core.files
WHERE id = $1 AND owner = core.uid() AND status = 'pending_upload'
FOR UPDATE
"""
FINISH_UPLOAD = """
UPDATE core.files SET status = 'pending_scan', sha256 = $2, uploaded_at = now()
WHERE id = $1
RETURNING id, name, type, size, sha256, status, malware, created_at, uploaded_at, scanned_at
"""
PENDING_UPLOAD = "pending_upload"
NOT_FOUND = "Không tìm thấy file"
UPLOADED = "File đã được tải lên"
MISSING = {404: {"model": Message, "description": NOT_FOUND}}
CONTENT = {
    "requestBody": {
        "required": True,
        "description": "Nội dung của file",
        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
    }
}

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/files")


class NewFile(BaseModel):
    name: str = Field(description="Tên file, gồm cả phần mở rộng", examples=["anh-may-hong.png"])
    type: str = Field(description="Loại file (MIME type)", examples=["image/png"])
    size: int = Field(gt=0, description="Dung lượng của file, tính bằng byte", examples=[183520])


class FileInfo(BaseModel):
    id: UUID
    name: str
    type: str
    size: int = Field(description="Dung lượng của file, tính bằng byte")
    sha256: str | None = Field(description="Mã băm SHA-256 của nội dung, có sau khi tải lên")
    status: Literal["pending_upload", "pending_scan", "clean", "infected"] = Field(
        description=(
            "pending_upload: chờ tải lên. pending_scan: chờ quét mã độc. "
            "clean: không phát hiện mã độc. infected: phát hiện mã độc"
        )
    )
    malware: str | None = Field(description="Tên mã độc mà ClamAV phát hiện")
    created_at: datetime
    uploaded_at: datetime | None
    scanned_at: datetime | None = Field(description="Thời điểm quét mã độc xong")


class CreatedFile(FileInfo):
    upload_url: str = Field(description="Đường dẫn để gửi nội dung của file bằng lệnh PUT")


class Received(NamedTuple):
    size: int
    header: bytes
    sha256: str


async def receive(request: Request, spool: BinaryIO, limit: int) -> Received:
    digest = hashlib.sha256()
    header = bytearray()
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            break
        if len(header) < HEADER_SIZE:
            header += chunk[: HEADER_SIZE - len(header)]
        digest.update(chunk)
        spool.write(chunk)
    return Received(size, bytes(header), digest.hexdigest())


@router.post(
    "",
    status_code=201,
    summary="Khai báo file mới và nhận đường dẫn tải lên",
    responses=UNAUTHORIZED
    | {
        413: {"model": Message, "description": "Dung lượng vượt giới hạn"},
        415: {"model": Message, "description": "Loại file không được phép"},
    }
    | UNAVAILABLE,
)
async def create_file(request: Request, user: User, declared: NewFile) -> CreatedFile:
    settings = request.app.state.settings
    type = declared.type.lower()
    if type not in KINDS:
        raise HTTPException(
            415,
            f"Loại file {declared.type} không được phép. "
            f"Các loại file được phép gồm {', '.join(KINDS)}",
        )
    if declared.size > settings.max_file_size * MB:
        raise HTTPException(413, f"File vượt quá dung lượng tối đa {settings.max_file_size} MB")
    try:
        name = checked_name(declared.name, type)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    async with request.app.state.database.service_session(user) as connection:
        row = await connection.fetchrow(CREATE, name, type, declared.size)
    return CreatedFile(**row, upload_url=f"{settings.public_url}/files/{row['id']}/content")


@router.put(
    "/{file_id}/content",
    summary="Tải nội dung của file lên",
    responses=UNAUTHORIZED
    | MISSING
    | {409: {"model": Message, "description": UPLOADED}}
    | UNAVAILABLE,
    openapi_extra=CONTENT,
)
async def upload_file(file_id: UUID, request: Request, user: User) -> FileInfo:
    database = request.app.state.database
    async with database.service_session(user) as connection:
        found = await connection.fetchrow(FIND_OWN, file_id)
    if found is None:
        raise HTTPException(404, NOT_FOUND)
    if found["status"] != PENDING_UPLOAD:
        raise HTTPException(409, UPLOADED)
    with SpooledTemporaryFile(SPOOL_SIZE) as spool:
        received = await receive(request, spool, found["size"])
        if received.size != found["size"]:
            raise HTTPException(
                422,
                f"Dung lượng của nội dung khác dung lượng đã khai báo là {found['size']} byte",
            )
        if not KINDS[found["type"]].matches(received.header):
            raise HTTPException(422, f"Phần đầu của nội dung không đúng định dạng {found['type']}")
        spool.seek(0)
        async with database.service_session(user) as connection:
            if await connection.fetchrow(LOCK_PENDING, file_id) is None:
                raise HTTPException(409, UPLOADED)
            try:
                await run_in_threadpool(
                    request.app.state.storage.put,
                    QUARANTINE,
                    str(file_id),
                    spool,
                    received.size,
                    received.sha256,
                    found["type"],
                )
            except StorageError as error:
                logger.warning("Không lưu được file %s vào kho file: %s", file_id, error)
                raise HTTPException(503, "Chưa lưu được file vì kho file chưa sẵn sàng") from None
            row = await connection.fetchrow(FINISH_UPLOAD, file_id, received.sha256)
    request.app.state.scans.notify()
    return FileInfo(**row)


@router.get(
    "/{file_id}",
    summary="Thông tin của file",
    responses=UNAUTHORIZED | MISSING | UNAVAILABLE,
)
async def get_file(file_id: UUID, request: Request, user: User) -> FileInfo:
    async with request.app.state.database.session(user) as connection:
        row = await connection.fetchrow(FIND, file_id)
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return FileInfo(**row)
