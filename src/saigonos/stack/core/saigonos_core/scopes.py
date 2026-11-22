# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from typing import Any

from saigonos_core.callers import Caller
from saigonos_core.database import Database

FIND = "SELECT EXISTS (SELECT FROM core.apps WHERE name = $1)"


@dataclass(frozen=True)
class Scope:
    app: str | None = None

    @property
    def query(self) -> dict[str, Any]:
        return {"tenantIdIn": [self.app]} if self.app else {"withoutTenantId": True}

    def holds(self, item: dict[str, Any]) -> bool:
        return item.get("tenantId") == self.app


class Scopes:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def of(self, caller: Caller) -> Scope:
        client = caller.claims.get("azp")
        if not isinstance(client, str) or not client:
            return Scope()
        async with self.database.transaction() as connection:
            known = await connection.fetchval(FIND, client)
        return Scope(client if known else None)
