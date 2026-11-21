# SPDX-License-Identifier: Apache-2.0
import asyncio
import json

import asyncpg
import pytest

from saigonos_core.callers import caller_of
from saigonos_core.database import SET_CALLER, SET_CLAIMS, Database


class FakeTransaction:
    def __init__(self, events):
        self.events = events

    async def __aenter__(self):
        self.events.append("begin")

    async def __aexit__(self, error, *details):
        self.events.append("rollback" if error else "commit")


class FakeConnection:
    def __init__(self, events):
        self.events = events

    async def execute(self, query, *arguments):
        self.events.append((query, *arguments))

    def transaction(self):
        return FakeTransaction(self.events)


class FakePool:
    def __init__(self, options):
        self.options = options
        self.events = []
        self.failure = None

    def acquire(self):
        return self

    async def __aenter__(self):
        if self.failure:
            raise self.failure
        self.events.append("acquire")
        return FakeConnection(self.events)

    async def __aexit__(self, *details):
        self.events.append("release")

    async def close(self):
        self.events.append("close")


@pytest.fixture
def pool(monkeypatch):
    created = []

    async def create_pool(**options):
        created.append(FakePool(options))
        return created[-1]

    monkeypatch.setattr(asyncpg, "create_pool", create_pool)
    return created


def opened(pool, **options):
    database = Database(**options)
    asyncio.run(database.open())
    return database, pool[-1]


def test_pool_keeps_no_prepared_statement(pool):
    _, created = opened(pool, max_size=3)

    assert created.options["statement_cache_size"] == 0
    assert (created.options["min_size"], created.options["max_size"]) == (1, 3)
    assert created.options["server_settings"] == {"application_name": "saigonos-core"}


def test_session_discards_plans_then_sets_role_and_claims_inside_transaction(pool, realm):
    database, created = opened(pool)
    caller = caller_of(realm.claims())

    async def query():
        async with database.session(caller) as connection:
            await connection.execute("SELECT core.uid()")

    asyncio.run(query())

    assert created.events == [
        "acquire",
        "begin",
        ("DISCARD PLANS",),
        (SET_CALLER, "authenticated", json.dumps(caller.claims)),
        ("SELECT core.uid()",),
        "commit",
        "release",
    ]


def test_service_session_keeps_role_of_service_and_sets_claims_of_caller(pool, realm):
    database, created = opened(pool)
    caller = caller_of(realm.claims())

    async def query():
        async with database.service_session(caller) as connection:
            await connection.execute("UPDATE core.files SET status = 'pending_scan'")

    asyncio.run(query())

    assert created.events == [
        "acquire",
        "begin",
        ("DISCARD PLANS",),
        (SET_CLAIMS, json.dumps(caller.claims)),
        ("UPDATE core.files SET status = 'pending_scan'",),
        "commit",
        "release",
    ]


def test_set_claims_statement_is_local_to_transaction():
    assert SET_CLAIMS == "SELECT set_config('request.jwt.claims', $1, true)"


def test_session_of_anonymous_caller_uses_role_anon(pool):
    database, created = opened(pool)

    async def query():
        async with database.session(caller_of(None)):
            pass

    asyncio.run(query())

    assert created.events[3] == (SET_CALLER, "anon", '{"role": "anon"}')


def test_session_rolls_back_when_query_fails(pool):
    database, created = opened(pool)

    async def query():
        async with database.session(caller_of(None)):
            raise ValueError("truy vấn lỗi")

    with pytest.raises(ValueError, match="truy vấn lỗi"):
        asyncio.run(query())

    assert created.events[-2:] == ["rollback", "release"]


def test_set_caller_statement_is_local_to_transaction():
    assert SET_CALLER.count(", true)") == 2
    assert "set_config('role', $1, true)" in SET_CALLER
    assert "set_config('request.jwt.claims', $2, true)" in SET_CALLER


def test_database_is_available_when_query_runs(pool):
    database, created = opened(pool)

    assert asyncio.run(database.available()) is True
    assert created.events == ["acquire", ("SELECT 1",), "release"]


@pytest.mark.parametrize(
    "failure",
    [
        ConnectionRefusedError(),
        TimeoutError(),
        asyncpg.CannotConnectNowError("the database system is starting up"),
        asyncpg.InterfaceError("pool is closed"),
    ],
)
def test_database_is_unavailable_when_connection_fails(pool, failure):
    database, created = opened(pool)
    created.failure = failure

    assert asyncio.run(database.available()) is False


def test_close_closes_pool(pool):
    database, created = opened(pool)

    asyncio.run(database.close())

    assert created.events == ["close"]


class FakeListening:
    def __init__(self, options, failure):
        self.options = options
        self.failure = failure
        self.listeners = []
        self.terminated = False

    async def add_listener(self, channel, callback):
        if self.failure:
            raise self.failure
        self.listeners.append((channel, callback))

    def terminate(self):
        self.terminated = True


@pytest.fixture
def connections(monkeypatch):
    created = []
    failure = []

    async def connect(**options):
        created.append(FakeListening(options, failure[0] if failure else None))
        return created[-1]

    monkeypatch.setattr(asyncpg, "connect", connect)
    return created, failure


def test_listener_has_own_connection_and_calls_back_on_each_notification(connections):
    created, _ = connections
    calls = []

    listener = asyncio.run(Database().listen("core_deliveries", lambda: calls.append("tỉnh")))
    [(channel, callback)] = listener.listeners
    callback(listener, 4321, "core_deliveries", "")
    callback(listener, 4321, "core_deliveries", "")

    assert created == [listener]
    assert listener.options == {
        "timeout": 10,
        "server_settings": {"application_name": "saigonos-core"},
    }
    assert (channel, calls, listener.terminated) == ("core_deliveries", ["tỉnh", "tỉnh"], False)


def test_listener_connection_is_closed_when_listen_fails(connections):
    created, failure = connections
    failure.append(asyncpg.InterfaceError("kết nối đã đóng"))

    with pytest.raises(asyncpg.InterfaceError):
        asyncio.run(Database().listen("core_deliveries", lambda: None))

    assert created[0].terminated
