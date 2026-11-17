# SPDX-License-Identifier: Apache-2.0
import hashlib
import logging
from collections.abc import Iterator
from contextlib import ExitStack
from datetime import UTC, datetime
from tempfile import SpooledTemporaryFile
from typing import Annotated, BinaryIO, Literal, NamedTuple
from uuid import UUID

from asyncpg import Record
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from saigonos_core.api import UNAUTHORIZED, UNAVAILABLE, Message, User
from saigonos_core.downloads import ExpiredLinkError, InvalidLinkError, attachment
from saigonos_core.kinds import HEADER_SIZE, KINDS, checked_name
from saigonos_core.storage import CHUNK_SIZE, CLEAN, QUARANTINE, Storage, StorageError

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
SCANNED_CLEAN = "clean"
NOT_FOUND = "Không tìm thấy file"
UPLOADED = "File đã được tải lên"
NOT_DOWNLOADABLE = {
    "pending_upload": "File chưa có nội dung nên chưa tải về được",
    "pending_scan": "File đang chờ quét mã độc nên chưa tải về được",
    "infected": "File có mã độc nên không tải về được",
}
INVALID_LINK = "Đường dẫn tải về không hợp lệ"
EXPIRED_LINK = "Đường dẫn tải về đã hết hạn"
MISSING = {404: {"model": Message, "description": NOT_FOUND}}
NOT_CLEAN = {409: {"model": Message, "description": "File chưa được quét mã độc hoặc có mã độc"}}
BINARY = {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}
CONTENT = {
    "requestBody": {
        "required": True,
        "description": "Nội dung của file",
        "content": BINARY,
    }
}
SENT = {
    200: {"description": "Nội dung của file", "content": BINARY},
    403: {"model": Message, "description": "Đường dẫn tải về không hợp lệ hoặc đã hết hạn"},
    500: {"model": Message, "description": "Nội dung trong kho file không khớp mã băm đã ghi"},
}
SAFE_HEADERS = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}

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


class DownloadLink(BaseModel):
    download_url: str = Field(
        description="Đường dẫn tải file về bằng lệnh GET, mở được mà không cần access token"
    )
    expires_at: datetime = Field(description="Thời điểm đường dẫn hết hạn")


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


def downloadable(row: Record | None) -> Record:
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    if row["status"] != SCANNED_CLEAN:
        raise HTTPException(409, NOT_DOWNLOADABLE[row["status"]])
    return row


async def read_clean(storage: Storage, row: Record, spool: BinaryIO) -> None:
    try:
        sha256 = await run_in_threadpool(storage.get, CLEAN, str(row["id"]), spool)
    except StorageError as error:
        logger.warning("Không đọc được file %s từ kho file: %s", row["id"], error)
        raise HTTPException(503, "Chưa tải được file vì kho file chưa sẵn sàng") from None
    if sha256 != row["sha256"]:
        logger.error("Nội dung của file %s trong bucket clean không khớp mã băm đã ghi", row["id"])
        raise HTTPException(500, "Nội dung của file không khớp mã băm đã ghi")
    spool.seek(0)


def chunks(spool: BinaryIO) -> Iterator[bytes]:
    with spool:
        while chunk := spool.read(CHUNK_SIZE):
            yield chunk


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


@router.post(
    "/{file_id}/download-url",
    summary="Xin đường dẫn tải file về",
    responses=UNAUTHORIZED | MISSING | NOT_CLEAN | UNAVAILABLE,
)
async def create_download_url(file_id: UUID, request: Request, user: User) -> DownloadLink:
    async with request.app.state.database.session(user) as connection:
        downloadable(await connection.fetchrow(FIND, file_id))
    query, expires = request.app.state.downloads.query(file_id)
    return DownloadLink(
        download_url=f"{request.app.state.settings.public_url}/files/{file_id}/content?{query}",
        expires_at=datetime.fromtimestamp(expires, UTC),
    )


@router.get(
    "/{file_id}/content",
    summary="Tải file về bằng đường dẫn tải về",
    response_class=StreamingResponse,
    responses=SENT | MISSING | NOT_CLEAN | UNAVAILABLE,
)
async def download_file(
    file_id: UUID,
    request: Request,
    expires: Annotated[str, Query(description="Thời điểm hết hạn của đường dẫn")] = "",
    signature: Annotated[str, Query(description="Chữ ký của đường dẫn")] = "",
) -> StreamingResponse:
    try:
        request.app.state.downloads.check(file_id, expires, signature)
    except InvalidLinkError:
        raise HTTPException(403, INVALID_LINK) from None
    except ExpiredLinkError:
        raise HTTPException(403, EXPIRED_LINK) from None
    async with request.app.state.database.transaction() as connection:
        row = downloadable(await connection.fetchrow(FIND, file_id))
    with ExitStack() as cleanup:
        spool = cleanup.enter_context(SpooledTemporaryFile(SPOOL_SIZE))
        await read_clean(request.app.state.storage, row, spool)
        cleanup.pop_all()
    headers = {
        "Content-Type": row["type"],
        "Content-Length": str(row["size"]),
        "Content-Disposition": attachment(row["name"]),
        **SAFE_HEADERS,
    }
    return StreamingResponse(chunks(spool), headers=headers)
