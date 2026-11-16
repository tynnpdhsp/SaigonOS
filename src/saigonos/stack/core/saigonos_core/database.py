# SPDX-License-Identifier: Apache-2.0
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

from saigonos_core.callers import Caller

SET_CALLER = "SELECT set_config('role', $1, true), set_config('request.jwt.claims', $2, true)"
UNAVAILABLE = (OSError, TimeoutError, asyncpg.PostgresError, asyncpg.InterfaceError)
CONNECT_TIMEOUT = 10
COMMAND_TIMEOUT = 30


class Database:
    def __init__(self, max_size: int = 10) -> None:
        self.max_size = max_size
        self.pool: asyncpg.Pool

    async def open(self) -> None:
        self.pool = await asyncpg.create_pool(
            min_size=1,
            max_size=self.max_size,
            statement_cache_size=0,
            timeout=CONNECT_TIMEOUT,
            command_timeout=COMMAND_TIMEOUT,
            server_settings={"application_name": "saigonos-core"},
        )

    async def close(self) -> None:
        await self.pool.close()

    async def available(self) -> bool:
        try:
            async with self.pool.acquire() as connection:
                await connection.execute("SELECT 1")
        except UNAVAILABLE:
            return False
        return True

    @asynccontextmanager
    async def session(self, caller: Caller) -> AsyncIterator[asyncpg.Connection]:
        async with self.pool.acquire() as connection, connection.transaction():
            # PostgreSQL không kiểm tra lại quyền EXECUTE khi dùng lại query plan của role khác
            await connection.execute("DISCARD PLANS")
            await connection.execute(SET_CALLER, caller.role, json.dumps(caller.claims))
            yield connection
