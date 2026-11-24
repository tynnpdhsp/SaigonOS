# SPDX-License-Identifier: Apache-2.0
import asyncio
from contextlib import asynccontextmanager

import asyncpg

from saigonos_core.metrics import COUNTS, Metrics, render

ROWS = [
    {
        "app": "nghi-phep",
        "job": "archive",
        "failed_checks": 1,
        "files": 3,
        "rows": 120,
        "bytes": 4096,
    },
    {
        "app": "nghi-phep",
        "job": "snapshot",
        "failed_checks": 0,
        "files": 2,
        "rows": 40,
        "bytes": 900,
    },
]
EXPECTED = """\
# HELP saigonos_lake_failed_checks_total Số lần kiểm luật chất lượng không đạt
# TYPE saigonos_lake_failed_checks_total counter
saigonos_lake_failed_checks_total{app="nghi-phep",type="archive"} 1
saigonos_lake_failed_checks_total{app="nghi-phep",type="snapshot"} 0
# HELP saigonos_lake_files Số file trong hồ dữ liệu
# TYPE saigonos_lake_files gauge
saigonos_lake_files{app="nghi-phep",type="archive"} 3
saigonos_lake_files{app="nghi-phep",type="snapshot"} 2
# HELP saigonos_lake_rows Số dòng trong các file của hồ dữ liệu
# TYPE saigonos_lake_rows gauge
saigonos_lake_rows{app="nghi-phep",type="archive"} 120
saigonos_lake_rows{app="nghi-phep",type="snapshot"} 40
# HELP saigonos_lake_bytes Dung lượng các file của hồ dữ liệu, tính bằng byte
# TYPE saigonos_lake_bytes gauge
saigonos_lake_bytes{app="nghi-phep",type="archive"} 4096
saigonos_lake_bytes{app="nghi-phep",type="snapshot"} 900
"""


class FakeConnection:
    def __init__(self, pool):
        self.pool = pool

    async def fetch(self, query):
        self.pool.queries.append(query)
        if self.pool.down:
            raise asyncpg.CannotConnectNowError("đang khởi động")
        return ROWS


class FakePool:
    def __init__(self):
        self.queries = []
        self.down = False

    @asynccontextmanager
    async def acquire(self):
        yield FakeConnection(self)


class FakeDatabase:
    def __init__(self):
        self.pool = FakePool()


def test_counts_of_lake_are_rendered_for_prometheus():
    assert render(ROWS) == EXPECTED
    assert render([]).count("\n") == 8


async def ask(metrics, request):
    port = metrics.server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(request)
    await writer.drain()
    reply = await reader.read()
    writer.close()
    await writer.wait_closed()
    return reply.decode()


def served(requests, down=False):
    database = FakeDatabase()
    database.pool.down = down

    async def scenario():
        metrics = Metrics(database, port=0, host="127.0.0.1")
        await metrics.start()
        try:
            return [await ask(metrics, request) for request in requests]
        finally:
            await metrics.close()

    return asyncio.run(scenario()), database.pool.queries


def test_metrics_are_read_from_database_on_each_request():
    [reply], queries = served([b"GET /metrics HTTP/1.1\r\nHost: core\r\n\r\n"])

    head, body = reply.split("\r\n\r\n", 1)
    assert head.splitlines()[0] == "HTTP/1.1 200 OK"
    assert "Content-Type: text/plain; version=0.0.4; charset=utf-8" in head
    assert body == EXPECTED
    assert queries == [COUNTS]


def test_other_paths_are_not_found():
    [reply], queries = served([b"GET /health HTTP/1.1\r\n\r\n"])

    assert reply.startswith("HTTP/1.1 404 Not Found\r\n")
    assert queries == []


def test_unreachable_database_answers_503():
    [reply], _ = served([b"GET /metrics HTTP/1.1\r\n\r\n"], down=True)

    assert reply.startswith("HTTP/1.1 503 Service Unavailable\r\n")
    assert reply.endswith("Không đọc được số liệu của hồ dữ liệu.\n")


def test_unfinished_request_gets_no_answer():
    [reply], queries = served([b"GET /metrics"])

    assert reply == ""
    assert queries == []
