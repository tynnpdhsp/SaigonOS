# SPDX-License-Identifier: Apache-2.0
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from saigonos_core import __version__
from saigonos_core.callers import Caller, caller_of
from saigonos_core.database import Database
from saigonos_core.tokens import InvalidTokenError, KeysUnavailableError, TokenVerifier

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


class Message(BaseModel):
    detail: str


class Health(BaseModel):
    status: str


class Me(BaseModel):
    uid: str
    unit: str | None
    role: str


bearer = HTTPBearer(auto_error=False, description="Access token do Keycloak cấp")
UNAUTHORIZED = {
    401: {"model": Message, "description": "Thiếu access token hoặc access token không hợp lệ"}
}
UNAVAILABLE = {503: {"model": Message, "description": "Service chưa sẵn sàng"}}


def get_caller(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Caller:
    if credentials is None:
        return caller_of(None)
    try:
        return caller_of(request.app.state.tokens.verify(credentials.credentials))
    except InvalidTokenError:
        raise HTTPException(
            401, "Access token không hợp lệ", {"WWW-Authenticate": 'Bearer error="invalid_token"'}
        ) from None
    except KeysUnavailableError:
        raise HTTPException(
            503, "Chưa kiểm tra được access token vì không lấy được khóa ký của Keycloak"
        ) from None


def get_user(caller: Annotated[Caller, Depends(get_caller)]) -> Caller:
    if not caller.authenticated:
        raise HTTPException(
            401,
            "Lời gọi này cần access token của người dùng đã đăng nhập",
            {"WWW-Authenticate": "Bearer"},
        )
    return caller


User = Annotated[Caller, Depends(get_user)]
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
