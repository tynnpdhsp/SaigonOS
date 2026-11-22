# SPDX-License-Identifier: Apache-2.0
import os
import re
import stat
from email.utils import formatdate
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from saigonos_core.database import UNAVAILABLE
from saigonos_core.manifest import NAME_PATTERN

APPS = Path("/apps")
FIND = "SELECT manifest ->> 'ui' FROM core.apps WHERE name = $1 AND applied_at IS NOT NULL"
INDEX = "index.html"
API = "api"
SEGMENT = re.compile(r"[^/\\\x00-\x1f\x7f.][^/\\\x00-\x1f\x7f]*")
POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
    "frame-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'; "
    "object-src 'none'"
)
SECURITY = {
    "Content-Security-Policy": POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
}
TEXT = "; charset=utf-8"
TYPES = {
    ".html": "text/html" + TEXT,
    ".js": "text/javascript" + TEXT,
    ".mjs": "text/javascript" + TEXT,
    ".css": "text/css" + TEXT,
    ".txt": "text/plain" + TEXT,
    ".json": "application/json",
    ".map": "application/json",
    ".webmanifest": "application/manifest+json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".wasm": "application/wasm",
    ".pdf": "application/pdf",
}
BINARY = "application/octet-stream"
FOLDER_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK

router = APIRouter(include_in_schema=False)


def parts_of(path: str) -> list[str] | None:
    parts = path.split("/")
    if parts[-1] == "":
        parts.pop()
    if not all(SEGMENT.fullmatch(part) for part in parts):
        return None
    return parts


def type_of(name: str) -> str:
    return TYPES.get(PurePosixPath(name).suffix.lower(), BINARY)


def open_file(base: Path, parts: list[str]) -> tuple[int, os.stat_result] | None:
    try:
        folder = os.open(base, FOLDER_FLAGS)
    except OSError:
        return None
    try:
        for part in parts[:-1]:
            inner = os.open(part, FOLDER_FLAGS, dir_fd=folder)
            os.close(folder)
            folder = inner
        found = os.open(parts[-1], FILE_FLAGS, dir_fd=folder)
    except OSError:
        return None
    finally:
        os.close(folder)
    info = os.fstat(found)
    if not stat.S_ISREG(info.st_mode):
        os.close(found)
        return None
    return found, info


def matches(tag: str, header: str) -> bool:
    wanted = (item.strip().removeprefix("W/") for item in header.split(","))
    return any(item in (tag, "*") for item in wanted)


def file_response(request: Request, opened: tuple[int, os.stat_result], name: str) -> Response:
    found, info = opened
    index = name == INDEX
    tag = f'"{info.st_mtime_ns:x}-{info.st_size:x}"'
    headers = SECURITY | {
        "Cache-Control": "no-store" if index else "no-cache",
        "ETag": tag,
        "Last-Modified": formatdate(info.st_mtime, usegmt=True),
    }
    with os.fdopen(found, "rb") as file:
        if not index and matches(tag, request.headers.get("if-none-match", "")):
            return Response(status_code=304, headers=headers)
        content = file.read()
    return Response(content, media_type=type_of(name), headers=headers)


def not_found(detail: str) -> HTTPException:
    return HTTPException(404, detail, SECURITY)


async def folder_of(request: Request, name: str) -> list[str]:
    if not re.fullmatch(NAME_PATTERN, name):
        raise not_found("Không tìm thấy ứng dụng")
    try:
        async with request.app.state.database.transaction() as connection:
            folder = await connection.fetchval(FIND, name)
    except UNAVAILABLE:
        raise HTTPException(503, "Không kết nối được cơ sở dữ liệu") from None
    parts = parts_of(folder) if folder else None
    if not parts:
        raise not_found("Không tìm thấy giao diện của ứng dụng")
    return [name, *parts]


@router.api_route("/apps/{name}", methods=["GET", "HEAD"])
async def app_root(request: Request, name: str) -> Response:
    await folder_of(request, name)
    return RedirectResponse(f"/apps/{name}/", 308, SECURITY)


@router.api_route("/apps/{name}/{path:path}", methods=["GET", "HEAD"])
async def app_file(request: Request, name: str, path: str) -> Response:
    folder = await folder_of(request, name)
    parts = parts_of(path)
    if parts is None or parts[:1] == [API]:
        raise not_found("Không tìm thấy file")
    base = request.app.state.apps_folder
    opened = open_file(base, [*folder, *parts]) if parts else None
    if opened is not None:
        return file_response(request, opened, parts[-1])
    if parts and PurePosixPath(parts[-1]).suffix:
        raise not_found("Không tìm thấy file")
    index = open_file(base, [*folder, INDEX])
    if index is None:
        raise not_found("Không tìm thấy file index.html của ứng dụng")
    return file_response(request, index, INDEX)
