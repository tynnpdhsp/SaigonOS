# SPDX-License-Identifier: Apache-2.0
import asyncio
import logging
import time
from collections.abc import Callable
from contextlib import suppress
from typing import Any, NamedTuple

import asyncpg
from starlette.concurrency import run_in_threadpool

from saigonos_core.database import Database
from saigonos_core.telegram import RETRY, SENT, UNKNOWN, WAIT, Outcome, Telegram, message_of

CHANNEL = "core_deliveries"
RETRY_DELAYS = (5, 30, 120, 600)
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1
POLL = 10
SHORTEST_WAIT = 0.1
NOT_CONFIGURED = "Chưa cấu hình Telegram"
STOPPED = "Service core dừng khi đang gửi tin nên không biết tin đã tới Telegram hay chưa"
RECOVER = """
UPDATE core.deliveries SET status = 'unknown', finished_at = now(), error = $1
WHERE status = 'sending'
RETURNING id
"""
SKIP = """
UPDATE core.deliveries SET status = 'skipped', finished_at = now(), error = $1
WHERE status = 'pending'
RETURNING id
"""
NEXT = """
SELECT id, title, body, link, failures FROM core.deliveries
WHERE status = 'pending' AND next_attempt_at <= now()
ORDER BY id
LIMIT 1
FOR UPDATE SKIP LOCKED
"""
SENDING = "UPDATE core.deliveries SET status = 'sending' WHERE id = $1"
RECORD = """
UPDATE core.deliveries SET
    status = $2,
    failures = $3,
    next_attempt_at = CASE WHEN $4::float8 IS NULL THEN next_attempt_at
        ELSE now() + make_interval(secs => $4::float8) END,
    finished_at = CASE WHEN $2 = 'pending' THEN NULL ELSE now() END,
    sent_id = $5,
    error = $6
WHERE id = $1
"""
DUE = """
SELECT extract(epoch FROM min(next_attempt_at) - now())::float8 FROM core.deliveries
WHERE status = 'pending'
"""

logger = logging.getLogger(__name__)


class Step(NamedTuple):
    status: str
    failures: int
    delay: float | None


def next_step(outcome: Outcome, failures: int) -> Step:
    if outcome.result == SENT:
        return Step("sent", failures, None)
    if outcome.result == WAIT:
        return Step("pending", failures, outcome.wait)
    if outcome.result == UNKNOWN:
        return Step("unknown", failures, None)
    failures += 1
    if outcome.result == RETRY and failures < MAX_ATTEMPTS:
        return Step("pending", failures, RETRY_DELAYS[failures - 1])
    return Step("failed", failures, None)


def listed(rows: list[Any]) -> str:
    return ", ".join(str(row["id"]) for row in rows)


class Deliveries:
    def __init__(
        self,
        database: Database,
        site_url: str,
        telegram: Telegram | None = None,
        problem: str | None = None,
        poll: float = POLL,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.database = database
        self.site_url = site_url
        self.telegram = telegram
        self.problem = problem
        self.poll = poll
        self.clock = clock
        self.wake = asyncio.Event()
        self.listener: asyncpg.Connection | None = None
        self.recovered = False
        self.resume_at = 0.0
        self.unrecorded: tuple[int, Outcome, Step] | None = None

    def notify(self) -> None:
        self.wake.set()

    async def run(self) -> None:
        if self.problem:
            logger.error(
                "Cấu hình Telegram chưa đúng: %s. Tin Telegram sẽ không được gửi", self.problem
            )
        try:
            while True:
                self.wake.clear()
                try:
                    wait = await self.work()
                except Exception:
                    logger.exception(
                        "Gửi tin Telegram bị lỗi. Service sẽ thử lại sau %s giây", self.poll
                    )
                    wait = self.poll
                with suppress(TimeoutError):
                    await asyncio.wait_for(self.wake.wait(), wait)
        finally:
            if self.listener is not None:
                self.listener.terminate()

    async def work(self) -> float:
        if not self.recovered:
            await self.recover()
        if self.listener is None or self.listener.is_closed():
            self.listener = await self.database.listen(CHANNEL, self.notify)
        if self.unrecorded is not None:
            await self.record(*self.unrecorded)
        while True:
            pause = self.resume_at - self.clock()
            if pause > 0:
                return pause
            if self.telegram is None:
                await self.skip()
                return self.poll
            if not await self.send_next(self.telegram):
                return await self.due()

    async def recover(self) -> None:
        async with self.database.transaction() as connection:
            rows = await connection.fetch(RECOVER, STOPPED)
        self.recovered = True
        if rows:
            logger.warning(
                "Tin Telegram %s đang được gửi khi service core dừng. Không biết các tin này đã "
                "tới nhóm hay chưa nên chúng không được gửi lại",
                listed(rows),
            )

    async def skip(self) -> None:
        reason = f"Cấu hình Telegram chưa đúng: {self.problem}" if self.problem else NOT_CONFIGURED
        async with self.database.transaction() as connection:
            rows = await connection.fetch(SKIP, reason)
        if rows:
            logger.warning("%s nên tin Telegram %s không được gửi", reason, listed(rows))

    async def send_next(self, telegram: Telegram) -> bool:
        async with self.database.transaction() as connection:
            row = await connection.fetchrow(NEXT)
            if row is None:
                return False
            await connection.execute(SENDING, row["id"])
        sending = asyncio.ensure_future(self.send(telegram, row))
        try:
            await asyncio.shield(sending)
        except asyncio.CancelledError:
            with suppress(Exception):
                await sending
            raise
        return True

    async def send(self, telegram: Telegram, row: Any) -> None:
        message = message_of(row["title"], row["body"], row["link"], self.site_url)
        outcome = await run_in_threadpool(telegram.send, message)
        step = next_step(outcome, row["failures"])
        if outcome.result == WAIT:
            self.resume_at = self.clock() + outcome.wait
        report(row["id"], outcome, step)
        self.unrecorded = (row["id"], outcome, step)
        await self.record(row["id"], outcome, step)

    async def record(self, delivery_id: int, outcome: Outcome, step: Step) -> None:
        sent_id, error = (
            (outcome.detail, None) if outcome.result == SENT else (None, outcome.detail)
        )
        async with self.database.transaction() as connection:
            await connection.execute(
                RECORD, delivery_id, step.status, step.failures, step.delay, sent_id, error
            )
        self.unrecorded = None

    async def due(self) -> float:
        async with self.database.transaction() as connection:
            wait = await connection.fetchval(DUE)
        if wait is None:
            return self.poll
        return min(max(wait, SHORTEST_WAIT), self.poll)


def report(delivery_id: int, outcome: Outcome, step: Step) -> None:
    if outcome.result == SENT:
        return
    if outcome.result == WAIT:
        logger.warning(
            "Telegram yêu cầu chờ %s giây trước khi gửi tiếp. Tin Telegram %s sẽ được gửi lại "
            "sau đó: %s",
            outcome.wait,
            delivery_id,
            outcome.detail,
        )
    elif step.status == "pending":
        logger.warning(
            "Chưa gửi được tin Telegram %s: %s. Tin sẽ được gửi lại sau %s giây",
            delivery_id,
            outcome.detail,
            step.delay,
        )
    elif step.status == "unknown":
        logger.warning(
            "Không biết tin Telegram %s đã tới nhóm hay chưa: %s. Tin không được gửi lại để "
            "tránh gửi trùng",
            delivery_id,
            outcome.detail,
        )
    else:
        logger.error(
            "Không gửi được tin Telegram %s sau %s lần thử: %s",
            delivery_id,
            step.failures,
            outcome.detail,
        )
