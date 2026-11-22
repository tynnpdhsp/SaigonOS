# SPDX-License-Identifier: Apache-2.0
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from saigonos_core.api import UNAUTHORIZED, Message, User

LIFETIME = 60
ALGORITHM = "HS256"
ROLE_PREFIX = "role:"
USER_PREFIX = "user:"
CHANNEL = r"^(?:role:[A-Za-z0-9_.-]+|user:[a-z][a-z0-9-]*\.[A-Za-z0-9_.-]+)$"
MAX_CHANNEL = 255
FORBIDDEN = "Người gọi không có realm role của kênh này"
NOT_OWN = "Kênh cá nhân này không thuộc người gọi hoặc không thuộc ứng dụng của access token"
DENIED = "Người gọi không được nghe kênh này"

router = APIRouter(prefix="/realtime")


class TokenRequest(BaseModel):
    channel: str = Field(
        pattern=CHANNEL,
        max_length=MAX_CHANNEL,
        description="Kênh cần nghe, có dạng role:<realm role> hoặc user:<tên ứng dụng>.<sub>",
        examples=["role:quan-ly", "user:nghi-phep.4f1b0c0e-nguoi-dung"],
    )


class SubscriptionToken(BaseModel):
    token: str = Field(description="Token kênh, gửi trong lệnh subscribe của Centrifugo")


@dataclass(frozen=True)
class SubscriptionTokens:
    key: str = field(repr=False)
    lifetime: int = LIFETIME
    clock: Callable[[], float] = field(default=time.time, compare=False)

    def issue(self, user: str, channel: str, deadline: int) -> str:
        expires = min(int(self.clock()) + self.lifetime, deadline)
        claims = {"sub": user, "channel": channel, "exp": expires}
        return jwt.encode(claims, self.key, algorithm=ALGORITHM)


@router.post(
    "/token",
    summary="Cấp token kênh để nghe kênh role:<realm role> hoặc kênh cá nhân của ứng dụng",
    description=(
        "Với kênh role:<realm role>, người gọi cần có realm role ghi sau role: trong tên kênh. "
        "Với kênh user:<tên ứng dụng>.<sub>, access token phải được cấp cho client của ứng dụng "
        "đó và sub phải là của người gọi. Token kênh có hiệu lực 60 giây và hết hạn không muộn "
        "hơn access token của lời gọi"
    ),
    responses=UNAUTHORIZED | {403: {"model": Message, "description": DENIED}},
)
async def subscription_token(
    request: Request, user: User, wanted: TokenRequest
) -> SubscriptionToken:
    channel = wanted.channel
    if channel.startswith(ROLE_PREFIX):
        if channel.removeprefix(ROLE_PREFIX) not in user.realm_roles:
            raise HTTPException(403, FORBIDDEN)
    else:
        app, _, subject = channel.removeprefix(USER_PREFIX).partition(".")
        scope = await request.app.state.scopes.of(user)
        if (app, subject) != (scope.app, user.claims["sub"]):
            raise HTTPException(403, NOT_OWN)
    tokens = request.app.state.subscription_tokens
    token = tokens.issue(user.claims["sub"], channel, int(user.claims["exp"]))
    return SubscriptionToken(token=token)
