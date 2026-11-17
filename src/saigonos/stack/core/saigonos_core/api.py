# SPDX-License-Identifier: Apache-2.0
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from saigonos_core.callers import Caller, caller_of
from saigonos_core.tokens import InvalidTokenError, KeysUnavailableError


class Message(BaseModel):
    detail: str


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
