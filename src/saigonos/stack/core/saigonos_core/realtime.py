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
ROLE_CHANNEL = r"^role:[A-Za-z0-9_.-]+$"
MAX_CHANNEL = 255
FORBIDDEN = "Người gọi không có realm role của kênh này"

router = APIRouter(prefix="/realtime")


class TokenRequest(BaseModel):
    channel: str = Field(
        pattern=ROLE_CHANNEL,
        max_length=MAX_CHANNEL,
        description="Kênh cần nghe, có dạng role:<realm role>",
        examples=["role:quan-ly"],
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
    summary="Cấp token kênh để nghe kênh role:<realm role>",
    description=(
        "Người gọi cần có realm role ghi sau role: trong tên kênh. Token kênh có hiệu lực "
        "60 giây và hết hạn không muộn hơn access token của lời gọi"
    ),
    responses=UNAUTHORIZED | {403: {"model": Message, "description": FORBIDDEN}},
)
async def subscription_token(
    request: Request, user: User, wanted: TokenRequest
) -> SubscriptionToken:
    if wanted.channel.removeprefix(ROLE_PREFIX) not in user.realm_roles:
        raise HTTPException(403, FORBIDDEN)
    tokens = request.app.state.subscription_tokens
    token = tokens.issue(user.claims["sub"], wanted.channel, int(user.claims["exp"]))
    return SubscriptionToken(token=token)
