# SPDX-License-Identifier: Apache-2.0
import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from saigonos_core import __version__, files, processes
from saigonos_core.api import UNAUTHORIZED, UNAVAILABLE, User
from saigonos_core.clamav import ClamAV
from saigonos_core.database import Database
from saigonos_core.downloads import DownloadLinks
from saigonos_core.operaton import Operaton
from saigonos_core.processes import Processes
from saigonos_core.scans import Scans
from saigonos_core.storage import Storage
from saigonos_core.tokens import TokenVerifier

DESCRIPTION = (
    "API của service core trong lõi SaigonOS. Lời gọi dành cho người dùng đã đăng nhập "
    "cần access token do Keycloak cấp trong header Authorization."
)
ME = "SELECT core.uid() AS uid, core.unit() AS unit, current_role AS role"


@dataclass(frozen=True)
class Settings:
    issuer: str
    jwks_url: str
    public_url: str
    storage_url: str
    storage_access_key: str
    storage_secret_key: str
    max_file_size: int
    clamav_host: str
    clamav_port: int
    download_key: str
    operaton_url: str
    operaton_password: str

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            os.environ["JWT_ISSUER"],
            os.environ["JWKS_URL"],
            os.environ["PUBLIC_URL"],
            os.environ["S3_URL"],
            os.environ["S3_ACCESS_KEY"],
            os.environ["S3_SECRET_KEY"],
            int(os.environ["MAX_FILE_SIZE"]),
            os.environ["CLAMAV_HOST"],
            int(os.environ["CLAMAV_PORT"]),
            os.environ["DOWNLOAD_KEY"],
            os.environ["OPERATON_URL"],
            os.environ["OPERATON_PASSWORD"],
        )


class Health(BaseModel):
    status: str


class Me(BaseModel):
    uid: str
    unit: str | None
    role: str


router = APIRouter()


async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
    errors = [
        {name: value for name, value in item.items() if name != "input"} for item in error.errors()
    ]
    return JSONResponse({"detail": jsonable_encoder(errors)}, status_code=422)


@router.get("/health", summary="Trạng thái của service", responses=UNAVAILABLE)
async def health(request: Request) -> Health:
    if not await request.app.state.database.available():
        raise HTTPException(503, "Không kết nối được cơ sở dữ liệu")
    return Health(status="ok")


@router.get("/me", summary="Thông tin của người gọi", responses=UNAUTHORIZED | UNAVAILABLE)
async def me(request: Request, user: User) -> Me:
    async with request.app.state.database.session(user) as connection:
        row = await connection.fetchrow(ME)
    return Me(**row)


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
    storage: Storage | None = None,
    scans: Scans | None = None,
    operaton: Operaton | None = None,
) -> FastAPI:
    settings = settings or Settings.from_environment()
    database = database or Database()
    storage = storage or Storage(
        settings.storage_url, settings.storage_access_key, settings.storage_secret_key
    )
    scans = scans or Scans(database, storage, ClamAV(settings.clamav_host, settings.clamav_port))
    operaton = operaton or Operaton(settings.operaton_url, settings.operaton_password)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await database.open()
        worker = asyncio.create_task(scans.run())
        yield
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker
        await database.close()

    app = FastAPI(
        title="SaigonOS Core API",
        description=DESCRIPTION,
        version=__version__,
        servers=[{"url": settings.public_url}],
        docs_url=None,
        redoc_url=None,
        redirect_slashes=False,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.tokens = TokenVerifier(settings.issuer, settings.jwks_url)
    app.state.database = database
    app.state.storage = storage
    app.state.scans = scans
    app.state.downloads = DownloadLinks(settings.download_key)
    app.state.operaton = operaton
    app.state.processes = Processes(operaton)
    app.add_exception_handler(RequestValidationError, invalid_request)
    app.include_router(router)
    app.include_router(files.router)
    app.include_router(processes.router)
    return app
