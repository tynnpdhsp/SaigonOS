# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from typing import Any

ANON = "anon"
AUTHENTICATED = "authenticated"


@dataclass(frozen=True)
class Caller:
    role: str
    claims: dict[str, Any]

    @property
    def authenticated(self) -> bool:
        return self.role == AUTHENTICATED


def caller_of(claims: dict[str, Any] | None) -> Caller:
    if claims is None:
        return Caller(ANON, {"role": ANON})
    access = claims.get("realm_access")
    roles = access.get("roles") if isinstance(access, dict) else None
    role = AUTHENTICATED if isinstance(roles, list) and AUTHENTICATED in roles else ANON
    return Caller(role, {**claims, "role": role})
