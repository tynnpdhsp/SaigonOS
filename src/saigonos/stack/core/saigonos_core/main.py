# SPDX-License-Identifier: Apache-2.0
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel

from saigonos_core import __version__
from saigonos_core.api import UNAUTHORIZED, UNAVAILABLE, User
from saigonos_core.database import Database
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

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(os.environ["JWT_ISSUER"], os.environ["JWKS_URL"], os.environ["PUBLIC_URL"])


class Health(BaseModel):
    status: str


class Me(BaseModel):
    uid: str
    unit: str | None
    role: str


router = APIRouter()


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


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    settings = settings or Settings.from_environment()
    database = database or Database()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await database.open()
        yield
        await database.close()

    app = FastAPI(
        title="SaigonOS Core API",
        description=DESCRIPTION,
        version=__version__,
        servers=[{"url": settings.public_url}],
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.tokens = TokenVerifier(settings.issuer, settings.jwks_url)
    app.state.database = database
    app.include_router(router)
    return app
