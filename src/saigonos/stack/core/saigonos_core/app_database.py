# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
import secrets
import string
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from fnmatch import fnmatchcase
from pathlib import Path
from typing import NamedTuple

import asyncpg

from saigonos_core.manifest import Manifest

LOCK = "SELECT pg_advisory_lock('core.apps'::regclass::oid::bigint)"
PREPARE = "SELECT core.prepare_app($1)"
APPLIED = "SELECT name, checksum FROM core.migrations WHERE scope = $1"
OPEN_LOGIN = "SELECT core.open_app_login($1, $2)"
CLOSE_LOGIN = "SELECT core.close_app_login($1)"
RUN = "SELECT core.run_app_sql($1)"
SECURE = "SELECT core.secure_app()"
RECORD = "SELECT core.record_migration($1, $2)"
FINISH = "SELECT core.finish_app($1, $2, $3, $4::jsonb, $5)"
SEARCH = "SELECT core.apply_search($1, $2::jsonb)"
WAS_REMOVED = "SELECT removed_at IS NOT NULL FROM core.apps WHERE name = $1"
INSTALLED = "SELECT name FROM core.apps WHERE applied_at IS NOT NULL ORDER BY name"
KNOWN = "SELECT EXISTS (SELECT FROM core.apps WHERE name = $1)"
REMOVE = "SELECT core.remove_app($1)"
PURGE = "SELECT core.purge_app($1)"
CONNECT_TIMEOUT = 10
PASSWORD_ALPHABET = string.ascii_letters + string.digits
PASSWORD_LENGTH = 32
APPLICATION = "saigonos-apps"
UNREACHABLE = (OSError, TimeoutError, asyncpg.CannotConnectNowError)
TRANSACTION_COMMANDS = "transaction commands"
CREATED = "Đã tạo schema {schema}, role {schema} và role {schema}_user của ứng dụng."
RAN = "Đã chạy file {name}."
LEFT_API = "Đã bỏ schema {schema} khỏi API."
DROPPED = "Đã xóa schema {schema}, role {schema} và role {schema}_user của ứng dụng."
NOT_READY = (
    "Cơ sở dữ liệu chưa có các hàm để cài đặt ứng dụng. "
    "Hãy chạy lệnh saigonos up để cập nhật cơ sở dữ liệu rồi chạy lại."
)


class ApplyError(Exception):
    pass


class SqlFile(NamedTuple):
    name: str
    checksum: str
    text: str


def schema_of(app: str) -> str:
    return app.replace("-", "_")


def sql_files(folder: Path, manifest: Manifest) -> list[SqlFile]:
    if manifest.database is None:
        return []
    files = []
    for entry in sorted((folder / manifest.database).iterdir()):
        if not entry.is_file() or not fnmatchcase(entry.name, "*.sql"):
            continue
        content = entry.read_bytes()
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ApplyError(f"File {entry.name} phải được lưu bằng bảng mã UTF-8.") from None
        files.append(SqlFile(entry.name, hashlib.sha256(content).hexdigest(), text))
    return files


def new_password() -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH))


def explained(error: asyncpg.PostgresError) -> str:
    text = error.message.rstrip(".")
    if error.hint:
        text += f". {error.hint.rstrip('.')}"
    return f"{text}."


def line_of(file: SqlFile, error: asyncpg.PostgresError) -> int | None:
    position = getattr(error, "internal_position", None)
    if not position or getattr(error, "internal_query", None) != file.text:
        return None
    return file.text.count("\n", 0, int(position) - 1) + 1


def file_failure(file: SqlFile, error: asyncpg.PostgresError) -> str:
    line = line_of(file, error)
    where = f" ở dòng {line}" if line else ""
    if isinstance(error, asyncpg.FeatureNotSupportedError) and (
        TRANSACTION_COMMANDS in error.message
    ):
        reason = "file SQL của ứng dụng không được dùng BEGIN, COMMIT, ROLLBACK hay SAVEPOINT."
    else:
        reason = explained(error)
    return (
        f"Không chạy được file {file.name}{where}: {reason} Mọi thay đổi của file này đã được hủy."
    )


async def connect(
    user: str | None = None, password: str | None = None, search_path: str | None = None
) -> asyncpg.Connection:
    settings = {"application_name": APPLICATION}
    if search_path is not None:
        settings["search_path"] = search_path
    try:
        return await asyncpg.connect(
            user=user,
            password=password,
            timeout=CONNECT_TIMEOUT,
            statement_cache_size=0,
            server_settings=settings,
        )
    except UNREACHABLE as error:
        raise ApplyError(
            f"Không kết nối được PostgreSQL: {error}. "
            "Hãy khởi động hệ thống bằng lệnh saigonos up rồi chạy lại."
        ) from error
    except asyncpg.PostgresError as error:
        raise ApplyError(f"PostgreSQL từ chối kết nối: {explained(error)}") from error


async def run_file(connection: asyncpg.Connection, file: SqlFile) -> None:
    try:
        async with connection.transaction():
            await connection.execute(RUN, file.text)
            await connection.execute(SECURE)
            await connection.execute(RECORD, file.name, file.checksum)
    except asyncpg.PostgresError as error:
        raise ApplyError(file_failure(file, error)) from error


async def run_files(
    admin: asyncpg.Connection, app: str, files: list[SqlFile], say: Callable[[str], None]
) -> None:
    password = new_password()
    await admin.execute(OPEN_LOGIN, app, password)
    try:
        connection = await connect(schema_of(app), password, schema_of(app))
        try:
            for file in files:
                await run_file(connection, file)
                say(RAN.format(name=file.name))
        finally:
            await connection.close()
    finally:
        await admin.execute(CLOSE_LOGIN, app)


@asynccontextmanager
async def admin_connection() -> AsyncIterator[asyncpg.Connection]:
    admin = await connect()
    try:
        yield admin
    except asyncpg.UndefinedFunctionError as error:
        raise ApplyError(NOT_READY) from error
    except asyncpg.UndefinedColumnError as error:
        raise ApplyError(NOT_READY) from error
    except asyncpg.PostgresError as error:
        raise ApplyError(explained(error)) from error
    finally:
        await admin.close()


async def apply_database(
    manifest: Manifest,
    folder: Path,
    say: Callable[[str], None],
    before_finish: Callable[[bool], object] | None = None,
) -> bool:
    app = manifest.name
    files = sql_files(folder, manifest)
    async with admin_connection() as admin:
        await admin.execute(LOCK)
        removed = bool(await admin.fetchval(WAS_REMOVED, app))
        if await admin.fetchval(PREPARE, app):
            say(CREATED.format(schema=schema_of(app)))
        applied = dict(await admin.fetch(APPLIED, app))
        for file in files:
            if applied.get(file.name, file.checksum) != file.checksum:
                raise ApplyError(
                    f"File {file.name} đã được chạy trước đó nhưng nội dung đã thay đổi. "
                    "Mỗi thay đổi của cơ sở dữ liệu cần được viết thành một file SQL mới."
                )
        pending = [file for file in files if file.name not in applied]
        if pending:
            await run_files(admin, app, pending, say)
        wanted = json.dumps([table.model_dump() for table in manifest.search])
        searched = await admin.fetchval(SEARCH, app, wanted) or []
        for line in searched:
            say(line)
        if before_finish is not None:
            before_finish(removed)
        content = json.dumps(manifest.model_dump(mode="json", by_alias=True, exclude_defaults=True))
        return await admin.fetchval(
            FINISH, app, manifest.title, manifest.version, content, bool(pending or searched)
        )


async def installed_apps() -> list[str]:
    async with admin_connection() as admin:
        return [row["name"] for row in await admin.fetch(INSTALLED)]


async def known_app(app: str) -> bool:
    async with admin_connection() as admin:
        return await admin.fetchval(KNOWN, app)


async def remove_database(app: str, purge: bool, say: Callable[[str], None]) -> bool:
    async with admin_connection() as admin:
        await admin.execute(LOCK)
        changed = await admin.fetchval(PURGE if purge else REMOVE, app)
    if changed:
        say((DROPPED if purge else LEFT_API).format(schema=schema_of(app)))
    return changed
