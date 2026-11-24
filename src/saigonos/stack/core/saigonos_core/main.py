# SPDX-License-Identifier: Apache-2.0
import asyncio
import os
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from saigonos_core import __version__, files, notifications, processes, realtime, tasks, ui
from saigonos_core.api import UNAUTHORIZED, UNAVAILABLE, User
from saigonos_core.clamav import ClamAV
from saigonos_core.database import Database
from saigonos_core.deliveries import EMAIL, TELEGRAM, Channel, Deliveries
from saigonos_core.downloads import DownloadLinks
from saigonos_core.lake_timer import INTERVAL, LakeTimer
from saigonos_core.metrics import PORT, Metrics
from saigonos_core.operaton import Operaton
from saigonos_core.processes import Processes
from saigonos_core.realtime import SubscriptionTokens
from saigonos_core.scans import Scans
from saigonos_core.scopes import Scopes
from saigonos_core.smtp import SmtpSettingsError
from saigonos_core.smtp import configured as smtp_configured
from saigonos_core.steps import Steps
from saigonos_core.storage import Storage
from saigonos_core.telegram import DEFAULT_API_URL, TelegramSettingsError
from saigonos_core.telegram import configured as telegram_configured
from saigonos_core.tokens import TokenVerifier

DESCRIPTION = (
    "API của service core trong lõi SaigonOS. Lời gọi dành cho người dùng đã đăng nhập "
    "cần access token do Keycloak cấp trong header Authorization."
)
ME = "SELECT core.uid() AS uid, core.unit() AS unit, current_role AS role"
SMTP_VARIABLES = (
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_SECURITY",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "SMTP_FROM_NAME",
)


def optional(name: str) -> str:
    return os.environ.get(name, "").strip()


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
    subscription_key: str
    site_url: str
    telegram_api_url: str = DEFAULT_API_URL
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_topic_id: str = ""
    smtp_host: str = ""
    smtp_port: str = ""
    smtp_security: str = ""
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_from_name: str = ""
    lake_interval: float = 0
    metrics_port: int = 0

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
            os.environ["SUBSCRIPTION_KEY"],
            os.environ["SAIGONOS_URL"],
            optional("TELEGRAM_API_URL") or DEFAULT_API_URL,
            *map(optional, ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_TOPIC_ID")),
            *map(optional, SMTP_VARIABLES),
            lake_interval=INTERVAL,
            metrics_port=PORT,
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


def worker_of(
    settings: Settings,
    database: Database,
    channel: Channel,
    configured: Callable[..., Any],
    values: tuple[str, ...],
) -> Deliveries:
    try:
        sender = configured(*values)
    except (TelegramSettingsError, SmtpSettingsError) as error:
        return Deliveries(database, settings.site_url, channel, problem=str(error))
    return Deliveries(database, settings.site_url, channel, sender)


def deliveries_of(settings: Settings, database: Database) -> tuple[Deliveries, ...]:
    telegram = (
        settings.telegram_api_url,
        settings.telegram_bot_token,
        settings.telegram_chat_id,
        settings.telegram_topic_id,
    )
    email = (
        settings.smtp_host,
        settings.smtp_port,
        settings.smtp_security,
        settings.smtp_username,
        settings.smtp_password,
        settings.smtp_from,
        settings.smtp_from_name,
    )
    return (
        worker_of(settings, database, TELEGRAM, telegram_configured, telegram),
        worker_of(settings, database, EMAIL, smtp_configured, email),
    )


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
    storage: Storage | None = None,
    scans: Scans | None = None,
    operaton: Operaton | None = None,
    steps: Steps | None = None,
    deliveries: Sequence[Deliveries] | None = None,
    scopes: Scopes | None = None,
) -> FastAPI:
    settings = settings or Settings.from_environment()
    database = database or Database()
    storage = storage or Storage(
        settings.storage_url, settings.storage_access_key, settings.storage_secret_key
    )
    scans = scans or Scans(database, storage, ClamAV(settings.clamav_host, settings.clamav_port))
    operaton = operaton or Operaton(settings.operaton_url, settings.operaton_password)
    definitions = Processes(operaton)
    steps = steps or Steps(database, operaton, definitions)
    deliveries = tuple(deliveries or deliveries_of(settings, database))

    timers = [LakeTimer(settings.lake_interval)] if settings.lake_interval else []
    metrics = Metrics(database, settings.metrics_port) if settings.metrics_port else None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await database.open()
        if metrics is not None:
            await metrics.start()
        running = (scans, steps, *deliveries, *timers)
        workers = [asyncio.create_task(worker.run()) for worker in running]
        yield
        for worker in workers:
            worker.cancel()
        for worker in workers:
            with suppress(asyncio.CancelledError):
                await worker
        if metrics is not None:
            await metrics.close()
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
    app.state.processes = definitions
    app.state.scopes = scopes or Scopes(database)
    app.state.steps = steps
    app.state.deliveries = deliveries
    app.state.subscription_tokens = SubscriptionTokens(settings.subscription_key)
    app.state.timers = timers
    app.state.metrics = metrics
    app.state.apps_folder = ui.APPS
    app.add_exception_handler(RequestValidationError, invalid_request)
    app.include_router(router)
    app.include_router(files.router)
    app.include_router(processes.router)
    app.include_router(tasks.router)
    app.include_router(realtime.router)
    app.include_router(notifications.router)
    app.include_router(ui.router)
    return app
