# SPDX-License-Identifier: Apache-2.0
import asyncio
import logging
import time
from collections.abc import Callable
from contextlib import suppress
from typing import Any, NamedTuple, Protocol

import asyncpg
from starlette.concurrency import run_in_threadpool

from saigonos_core import smtp, telegram
from saigonos_core.database import Database
from saigonos_core.outcome import RETRY, SENT, UNKNOWN, WAIT, Outcome

NOTIFY_CHANNEL = "core_deliveries"
RETRY_DELAYS = (5, 30, 120, 600)
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1
POLL = 10
SHORTEST_WAIT = 0.1
RECOVER = """
UPDATE core.deliveries SET status = 'unknown', finished_at = now(), error = $2
WHERE channel = $1 AND status = 'sending'
RETURNING id
"""
SKIP = """
UPDATE core.deliveries SET status = 'skipped', finished_at = now(), error = $2
WHERE channel = $1 AND status = 'pending'
RETURNING id
"""
NEXT = """
SELECT id, address, title, body, link, failures FROM core.deliveries
WHERE channel = $1 AND status = 'pending' AND next_attempt_at <= now()
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
WHERE channel = $1 AND status = 'pending'
"""

logger = logging.getLogger(__name__)


class Sender(Protocol):
    def send(self, message: Any) -> Outcome: ...


def capitalized(text: str) -> str:
    return text[:1].upper() + text[1:]


class Channel(NamedTuple):
    name: str
    service: str
    item: str
    short: str
    receiver: str
    stopped: str
    message: Callable[[Any, str], Any]

    @property
    def not_configured(self) -> str:
        return f"Chưa cấu hình {self.service}"

    def problem(self, problem: str) -> str:
        return f"Cấu hình {self.service} chưa đúng: {problem}"


def telegram_message(row: Any, site_url: str) -> dict[str, Any]:
    return telegram.message_of(row["title"], row["body"], row["link"], site_url)


def email_message(row: Any, site_url: str) -> Any:
    return smtp.message_of(row["address"], row["title"], row["body"], row["link"], site_url)


TELEGRAM = Channel(
    "telegram",
    "Telegram",
    "tin Telegram",
    "tin",
    "nhóm",
    "Service core dừng khi đang gửi tin nên không biết tin đã tới Telegram hay chưa",
    telegram_message,
)
EMAIL = Channel(
    "email",
    "SMTP",
    "email",
    "email",
    "máy chủ SMTP",
    "Service core dừng khi đang gửi email nên không biết email đã tới máy chủ SMTP hay chưa",
    email_message,
)


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
        channel: Channel,
        sender: Sender | None = None,
        problem: str | None = None,
        poll: float = POLL,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.database = database
        self.site_url = site_url
        self.channel = channel
        self.sender = sender
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
        channel = self.channel
        if self.problem:
            logger.error(
                f"{channel.problem('%s')}. {capitalized(channel.item)} sẽ không được gửi",
                self.problem,
            )
        try:
            while True:
                self.wake.clear()
                try:
                    wait = await self.work()
                except Exception:
                    logger.exception(
                        f"Gửi {channel.item} bị lỗi. Service sẽ thử lại sau %s giây", self.poll
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
            self.listener = await self.database.listen(NOTIFY_CHANNEL, self.notify)
        if self.unrecorded is not None:
            await self.record(*self.unrecorded)
        while True:
            pause = self.resume_at - self.clock()
            if pause > 0:
                return pause
            if self.sender is None:
                await self.skip()
                return self.poll
            if not await self.send_next(self.sender):
                return await self.due()

    async def recover(self) -> None:
        channel = self.channel
        async with self.database.transaction() as connection:
            rows = await connection.fetch(RECOVER, channel.name, channel.stopped)
        self.recovered = True
        if rows:
            logger.warning(
                f"{capitalized(channel.item)} %s đang được gửi khi service core dừng. Không biết "
                f"các {channel.short} này đã tới {channel.receiver} hay chưa nên chúng không được "
                "gửi lại",
                listed(rows),
            )

    async def skip(self) -> None:
        channel = self.channel
        reason = channel.problem(self.problem) if self.problem else channel.not_configured
        async with self.database.transaction() as connection:
            rows = await connection.fetch(SKIP, channel.name, reason)
        if rows:
            logger.warning(f"%s nên {channel.item} %s không được gửi", reason, listed(rows))

    async def send_next(self, sender: Sender) -> bool:
        async with self.database.transaction() as connection:
            row = await connection.fetchrow(NEXT, self.channel.name)
            if row is None:
                return False
            await connection.execute(SENDING, row["id"])
        sending = asyncio.ensure_future(self.send(sender, row))
        try:
            await asyncio.shield(sending)
        except asyncio.CancelledError:
            with suppress(Exception):
                await sending
            raise
        return True

    async def send(self, sender: Sender, row: Any) -> None:
        message = self.channel.message(row, self.site_url)
        outcome = await run_in_threadpool(sender.send, message)
        step = next_step(outcome, row["failures"])
        if outcome.result == WAIT:
            self.resume_at = self.clock() + outcome.wait
        self.report(row["id"], outcome, step)
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
            wait = await connection.fetchval(DUE, self.channel.name)
        if wait is None:
            return self.poll
        return min(max(wait, SHORTEST_WAIT), self.poll)

    def report(self, delivery_id: int, outcome: Outcome, step: Step) -> None:
        channel = self.channel
        item, short = channel.item, capitalized(channel.short)
        if outcome.result == SENT:
            return
        if outcome.result == WAIT:
            logger.warning(
                f"{channel.service} yêu cầu chờ %s giây trước khi gửi tiếp. {capitalized(item)} "
                "%s sẽ được gửi lại sau đó: %s",
                outcome.wait,
                delivery_id,
                outcome.detail,
            )
        elif step.status == "pending":
            logger.warning(
                f"Chưa gửi được {item} %s: %s. {short} sẽ được gửi lại sau %s giây",
                delivery_id,
                outcome.detail,
                step.delay,
            )
        elif step.status == "unknown":
            logger.warning(
                f"Không biết {item} %s đã tới {channel.receiver} hay chưa: %s. {short} không "
                "được gửi lại để tránh gửi trùng",
                delivery_id,
                outcome.detail,
            )
        else:
            logger.error(
                f"Không gửi được {item} %s sau %s lần thử: %s",
                delivery_id,
                step.failures,
                outcome.detail,
            )
