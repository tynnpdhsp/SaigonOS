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

    @property
    def realm_roles(self) -> frozenset[str]:
        return realm_roles_of(self.claims)


def realm_roles_of(claims: dict[str, Any]) -> frozenset[str]:
    access = claims.get("realm_access")
    roles = access.get("roles") if isinstance(access, dict) else None
    if not isinstance(roles, list):
        return frozenset()
    return frozenset(role for role in roles if isinstance(role, str))


def caller_of(claims: dict[str, Any] | None) -> Caller:
    if claims is None:
        return Caller(ANON, {"role": ANON})
    role = AUTHENTICATED if AUTHENTICATED in realm_roles_of(claims) else ANON
    return Caller(role, {**claims, "role": role})
