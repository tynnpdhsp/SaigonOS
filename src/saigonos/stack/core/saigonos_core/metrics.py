# SPDX-License-Identifier: Apache-2.0
import asyncio
from collections.abc import Sequence
from contextlib import suppress
from typing import Any

from saigonos_core.database import UNAVAILABLE, Database

PORT = 9100
TIMEOUT = 5
CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
COUNTS = "SELECT app, job, failed_checks, files, rows, bytes FROM core.lake_counts()"
METRICS = (
    (
        "saigonos_lake_failed_checks_total",
        "counter",
        "failed_checks",
        "Số lần kiểm luật chất lượng không đạt",
    ),
    ("saigonos_lake_files", "gauge", "files", "Số file trong hồ dữ liệu"),
    ("saigonos_lake_rows", "gauge", "rows", "Số dòng trong các file của hồ dữ liệu"),
    ("saigonos_lake_bytes", "gauge", "bytes", "Dung lượng các file của hồ dữ liệu, tính bằng byte"),
)


def render(rows: Sequence[Any]) -> str:
    lines = []
    for name, kind, field, description in METRICS:
        lines += [f"# HELP {name} {description}", f"# TYPE {name} {kind}"]
        lines += [
            f'{name}{{app="{row["app"]}",type="{row["job"]}"}} {int(row[field])}' for row in rows
        ]
    return "\n".join(lines) + "\n"


def response(status: str, text: str) -> bytes:
    body = text.encode()
    head = (
        f"HTTP/1.1 {status}\r\nContent-Type: {CONTENT_TYPE}\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
    )
    return head.encode() + body


class Metrics:
    def __init__(self, database: Database, port: int = PORT, host: str = "0.0.0.0") -> None:
        self.database = database
        self.port = port
        self.host = host
        self.server: asyncio.Server | None = None

    async def start(self) -> None:
        self.server = await asyncio.start_server(self.answer, self.host, self.port)

    async def close(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()

    async def answer(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), TIMEOUT)
            if request.split(b"\r\n", 1)[0].split()[:2] == [b"GET", b"/metrics"]:
                writer.write(await self.metrics())
            else:
                writer.write(response("404 Not Found", "Không có đường dẫn này.\n"))
            await writer.drain()
        except (TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, OSError):
            pass
        finally:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()

    async def metrics(self) -> bytes:
        try:
            async with self.database.pool.acquire() as connection:
                rows = await connection.fetch(COUNTS)
        except UNAVAILABLE:
            return response("503 Service Unavailable", "Không đọc được số liệu của hồ dữ liệu.\n")
        return response("200 OK", render(rows))
