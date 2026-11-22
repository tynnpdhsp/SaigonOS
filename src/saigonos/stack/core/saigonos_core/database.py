# SPDX-License-Identifier: Apache-2.0
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import asyncpg

from saigonos_core.callers import Caller

SET_CALLER = "SELECT set_config('role', $1, true), set_config('request.jwt.claims', $2, true)"
SET_CLAIMS = "SELECT set_config('request.jwt.claims', $1, true)"
SEAL_CLAIMS = "SELECT core.seal_claims()"
UNAVAILABLE = (OSError, TimeoutError, asyncpg.PostgresError, asyncpg.InterfaceError)
CONNECT_TIMEOUT = 10
COMMAND_TIMEOUT = 30
SERVER_SETTINGS = {"application_name": "saigonos-core"}


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
            server_settings=SERVER_SETTINGS,
        )

    async def close(self) -> None:
        await self.pool.close()

    async def listen(self, channel: str, callback: Callable[[], None]) -> asyncpg.Connection:
        connection = await asyncpg.connect(timeout=CONNECT_TIMEOUT, server_settings=SERVER_SETTINGS)
        try:
            await connection.add_listener(channel, lambda *_: callback())
        except BaseException:
            connection.terminate()
            raise
        return connection

    async def available(self) -> bool:
        try:
            async with self.pool.acquire() as connection:
                await connection.execute("SELECT 1")
        except UNAVAILABLE:
            return False
        return True

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        async with self.pool.acquire() as connection, connection.transaction():
            # PostgreSQL không kiểm tra lại quyền EXECUTE khi dùng lại query plan của role khác
            await connection.execute("DISCARD PLANS")
            yield connection

    @asynccontextmanager
    async def session(self, caller: Caller) -> AsyncIterator[asyncpg.Connection]:
        async with self.transaction() as connection:
            await connection.execute(SET_CALLER, caller.role, json.dumps(caller.claims))
            await connection.execute(SEAL_CLAIMS)
            yield connection

    @asynccontextmanager
    async def service_session(self, caller: Caller) -> AsyncIterator[asyncpg.Connection]:
        async with self.transaction() as connection:
            await connection.execute(SET_CLAIMS, json.dumps(caller.claims))
            await connection.execute(SEAL_CLAIMS)
            yield connection
