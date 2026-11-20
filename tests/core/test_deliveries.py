# SPDX-License-Identifier: Apache-2.0
import asyncio
import logging
import threading
from contextlib import asynccontextmanager, suppress

import pytest

from saigonos_core.deliveries import (
    CHANNEL,
    DUE,
    MAX_ATTEMPTS,
    NEXT,
    NOT_CONFIGURED,
    POLL,
    RECORD,
    RECOVER,
    RETRY_DELAYS,
    SENDING,
    SHORTEST_WAIT,
    SKIP,
    STOPPED,
    Deliveries,
    Step,
    next_step,
)
from saigonos_core.telegram import FAILED, RETRY, SENT, UNKNOWN, WAIT, Outcome, message_of

SITE = "https://dx.example.com"
START = 1000.0
STEPS = {
    "da-gui": (Outcome(SENT, "42"), 0, Step("sent", 0, None)),
    "429": (Outcome(WAIT, "Too Many Requests", 3), 2, Step("pending", 2, 3)),
    "khong-biet": (Outcome(UNKNOWN, "Mất kết nối"), 1, Step("unknown", 1, None)),
    "loi-lan-1": (Outcome(RETRY, "Lỗi 500"), 0, Step("pending", 1, 5)),
    "loi-lan-2": (Outcome(RETRY, "Lỗi 500"), 1, Step("pending", 2, 30)),
    "loi-lan-3": (Outcome(RETRY, "Lỗi 500"), 2, Step("pending", 3, 120)),
    "loi-lan-4": (Outcome(RETRY, "Lỗi 500"), 3, Step("pending", 4, 600)),
    "loi-lan-5": (Outcome(RETRY, "Lỗi 500"), 4, Step("failed", 5, None)),
    "bi-tu-choi": (Outcome(FAILED, "Lỗi 400"), 0, Step("failed", 1, None)),
}


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now


class FakeListener:
    def __init__(self, channel, callback):
        self.channel = channel
        self.callback = callback
        self.closed = False
        self.terminated = False

    def is_closed(self):
        return self.closed

    def terminate(self):
        self.terminated = True


class FakeConnection:
    def __init__(self, database):
        self.database = database

    def run(self, query):
        self.database.queries.append(query)
        if query in self.database.failures:
            raise self.database.failures.pop(query)

    def pending(self):
        return [row for row in self.database.rows.values() if row["status"] == "pending"]

    async def fetch(self, query, reason):
        self.run(query)
        status = {RECOVER: ("sending", "unknown"), SKIP: ("pending", "skipped")}
        before, after = status[query]
        changed = [row for row in self.database.rows.values() if row["status"] == before]
        for row in changed:
            row |= {"status": after, "finished": True, "error": reason}
        return [{"id": row["id"]} for row in changed]

    async def fetchrow(self, query):
        self.run(query)
        assert query == NEXT
        due = [row for row in self.pending() if row["next_attempt_at"] <= self.database.clock()]
        if not due:
            return None
        row = min(due, key=lambda row: row["id"])
        return {name: row[name] for name in ("id", "title", "body", "link", "failures")}

    async def fetchval(self, query):
        self.run(query)
        assert query == DUE
        times = [row["next_attempt_at"] for row in self.pending()]
        return min(times) - self.database.clock() if times else None

    async def execute(self, query, delivery_id, *values):
        self.run(query)
        row = self.database.rows[delivery_id]
        if query == SENDING:
            row["status"] = "sending"
            return
        assert query == RECORD
        status, failures, delay, sent_id, error = values
        row |= {"status": status, "failures": failures, "sent_id": sent_id, "error": error}
        row["finished"] = status != "pending"
        if delay is not None:
            row["next_attempt_at"] = self.database.clock() + delay


class FakeDatabase:
    def __init__(self, clock):
        self.clock = clock
        self.rows = {}
        self.queries = []
        self.failures = {}
        self.listeners = []

    def add(self, status="pending", **fields):
        delivery_id = len(self.rows) + 1
        self.rows[delivery_id] = {
            "id": delivery_id,
            "title": f"Tin {delivery_id}",
            "body": None,
            "link": None,
            "status": status,
            "failures": 0,
            "next_attempt_at": self.clock(),
            "finished": False,
            "sent_id": None,
            "error": None,
        } | fields
        return self.rows[delivery_id]

    @asynccontextmanager
    async def transaction(self):
        yield FakeConnection(self)

    async def listen(self, channel, callback):
        self.listeners.append(FakeListener(channel, callback))
        return self.listeners[-1]


class FakeTelegram:
    def __init__(self):
        self.outcomes = []
        self.messages = []
        self.during = None

    def send(self, message):
        self.messages.append(message)
        if self.during:
            self.during()
        return self.outcomes.pop(0) if self.outcomes else Outcome(SENT, str(len(self.messages)))


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def database(clock):
    return FakeDatabase(clock)


@pytest.fixture
def telegram():
    return FakeTelegram()


@pytest.fixture
def worker(database, telegram, clock):
    return Deliveries(database, SITE, telegram, clock=clock)


def work(worker):
    return asyncio.run(worker.work())


async def wait_for(condition, timeout=5):
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.01)


@asynccontextmanager
async def running(worker):
    task = asyncio.create_task(worker.run())
    try:
        yield task
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def messages_of(caplog, level=logging.WARNING):
    return [record.getMessage() for record in caplog.records if record.levelno == level]


@pytest.mark.parametrize(("outcome", "failures", "step"), STEPS.values(), ids=STEPS.keys())
def test_outcome_and_failures_give_next_step(outcome, failures, step):
    assert next_step(outcome, failures) == step


def test_delay_grows_four_times_before_delivery_fails():
    assert (RETRY_DELAYS, MAX_ATTEMPTS) == ((5, 30, 120, 600), 5)


def test_delivery_is_marked_sending_before_telegram_is_called(worker, database, telegram):
    row = database.add(title="Yêu cầu YC-001", body="Máy 12 hỏng", link="/yeu-cau/YC-001")
    seen = []
    telegram.during = lambda: seen.append(row["status"])

    wait = work(worker)

    assert seen == ["sending"]
    assert telegram.messages == [
        message_of("Yêu cầu YC-001", "Máy 12 hỏng", "/yeu-cau/YC-001", SITE)
    ]
    assert (row["status"], row["sent_id"], row["error"], row["finished"]) == (
        "sent",
        "1",
        None,
        True,
    )
    assert wait == POLL
    assert database.queries == [RECOVER, NEXT, SENDING, RECORD, NEXT, DUE]


def test_deliveries_are_sent_oldest_first(worker, database, telegram):
    for _ in range(3):
        database.add()

    work(worker)

    assert [message["text"] for message in telegram.messages] == ["Tin 1", "Tin 2", "Tin 3"]
    assert {row["status"] for row in database.rows.values()} == {"sent"}


def test_failed_send_is_retried_later_and_fails_after_last_attempt(
    worker, database, telegram, clock, caplog
):
    row = database.add()
    telegram.outcomes = [Outcome(RETRY, "Telegram trả về mã 500")] * MAX_ATTEMPTS
    states = []

    for delay in (*RETRY_DELAYS, 0):
        wait = work(worker)
        states.append((row["status"], row["failures"], row["next_attempt_at"] - clock.now, wait))
        clock.now += delay

    assert states == [
        ("pending", 1, 5, 5),
        ("pending", 2, 30, 10),
        ("pending", 3, 120, 10),
        ("pending", 4, 600, 10),
        ("failed", 5, 0, 10),
    ]
    assert len(telegram.messages) == MAX_ATTEMPTS
    assert messages_of(caplog)[0] == (
        "Chưa gửi được tin Telegram 1: Telegram trả về mã 500. Tin sẽ được gửi lại sau 5 giây"
    )
    assert messages_of(caplog, logging.ERROR) == [
        "Không gửi được tin Telegram 1 sau 5 lần thử: Telegram trả về mã 500"
    ]


def test_delivery_refused_by_telegram_fails_at_once(worker, database, telegram, caplog):
    row = database.add()
    telegram.outcomes = [Outcome(FAILED, "Telegram trả về mã 400: Bad Request: chat not found")]

    work(worker)

    assert (row["status"], row["failures"], row["finished"]) == ("failed", 1, True)
    assert row["error"] == "Telegram trả về mã 400: Bad Request: chat not found"
    assert messages_of(caplog, logging.ERROR) == [
        "Không gửi được tin Telegram 1 sau 1 lần thử: "
        "Telegram trả về mã 400: Bad Request: chat not found"
    ]


def test_delivery_with_unknown_outcome_is_never_sent_again(
    worker, database, telegram, clock, caplog
):
    row = database.add()
    telegram.outcomes = [Outcome(UNKNOWN, "Mất kết nối khi chờ Telegram trả lời: timed out")]

    work(worker)
    clock.now += 3600
    work(worker)

    assert len(telegram.messages) == 1
    assert (row["status"], row["failures"], row["finished"]) == ("unknown", 0, True)
    assert messages_of(caplog) == [
        "Không biết tin Telegram 1 đã tới nhóm hay chưa: Mất kết nối khi chờ Telegram trả lời: "
        "timed out. Tin không được gửi lại để tránh gửi trùng"
    ]


def test_rate_limit_pauses_every_delivery_for_retry_after(
    worker, database, telegram, clock, caplog
):
    first, second = database.add(), database.add()
    telegram.outcomes = [Outcome(WAIT, "Telegram trả về mã 429: Too Many Requests", 3)]

    paused = work(worker)
    still_paused = work(worker)
    clock.now += 3
    work(worker)

    assert (paused, still_paused) == (3, 3)
    assert [message["text"] for message in telegram.messages] == ["Tin 1", "Tin 1", "Tin 2"]
    assert (first["status"], first["failures"]) == ("sent", 0)
    assert second["status"] == "sent"
    assert messages_of(caplog) == [
        "Telegram yêu cầu chờ 3 giây trước khi gửi tiếp. Tin Telegram 1 sẽ được gửi lại sau đó: "
        "Telegram trả về mã 429: Too Many Requests"
    ]


@pytest.mark.parametrize(
    ("due_in", "wait"),
    [(3.5, 3.5), (POLL + 50, POLL), (-2, SHORTEST_WAIT)],
    ids=["som", "con-lau", "qua-han"],
)
def test_worker_sleeps_until_next_delivery_is_due(worker, database, clock, due_in, wait):
    database.add(next_attempt_at=clock.now + due_in, status="pending")

    async def due():
        return await worker.due()

    assert asyncio.run(due()) == wait


def test_without_telegram_pending_deliveries_are_skipped(database, clock, caplog):
    worker = Deliveries(database, SITE, clock=clock)
    rows = [database.add(), database.add()]

    wait = work(worker)

    assert wait == POLL
    assert [(row["status"], row["error"]) for row in rows] == [("skipped", NOT_CONFIGURED)] * 2
    assert messages_of(caplog) == ["Chưa cấu hình Telegram nên tin Telegram 1, 2 không được gửi"]


def test_invalid_settings_are_logged_at_start_and_kept_with_skipped_deliveries(
    database, clock, caplog
):
    worker = Deliveries(database, SITE, problem="thiếu TELEGRAM_CHAT_ID", clock=clock, poll=0.01)
    row = database.add()

    async def main():
        async with running(worker):
            await wait_for(lambda: row["status"] == "skipped")
            await asyncio.sleep(0.05)

    asyncio.run(main())

    reason = "Cấu hình Telegram chưa đúng: thiếu TELEGRAM_CHAT_ID"
    assert row["error"] == reason
    assert messages_of(caplog, logging.ERROR) == [f"{reason}. Tin Telegram sẽ không được gửi"]
    assert messages_of(caplog) == [f"{reason} nên tin Telegram 1 không được gửi"]


def test_deliveries_left_sending_become_unknown_once_at_start(worker, database, telegram, caplog):
    rows = [database.add(status="sending"), database.add(status="sending")]

    work(worker)
    work(worker)

    assert [(row["status"], row["error"]) for row in rows] == [("unknown", STOPPED)] * 2
    assert database.queries.count(RECOVER) == 1
    assert telegram.messages == []
    assert messages_of(caplog) == [
        "Tin Telegram 1, 2 đang được gửi khi service core dừng. Không biết các tin này đã tới "
        "nhóm hay chưa nên chúng không được gửi lại"
    ]


def test_listener_is_opened_once_and_again_after_it_closes(worker, database):
    work(worker)
    work(worker)
    database.listeners[0].closed = True
    work(worker)

    assert [listener.channel for listener in database.listeners] == [CHANNEL, CHANNEL]
    database.listeners[-1].callback()
    assert worker.wake.is_set()


def test_notification_wakes_worker_before_poll(database, telegram, clock):
    worker = Deliveries(database, SITE, telegram, clock=clock, poll=60)

    async def main():
        async with running(worker):
            await wait_for(lambda: database.listeners)
            row = database.add()
            database.listeners[0].callback()
            await wait_for(lambda: row["status"] == "sent", timeout=2)

    asyncio.run(main())


def test_outcome_is_recorded_after_database_comes_back(worker, database, telegram):
    row = database.add()
    database.failures[RECORD] = ConnectionError("Không kết nối được PostgreSQL")

    with pytest.raises(ConnectionError):
        work(worker)
    stuck = row["status"]
    work(worker)

    assert (stuck, row["status"], row["sent_id"]) == ("sending", "sent", "1")
    assert len(telegram.messages) == 1


def test_send_in_progress_is_recorded_when_worker_stops(database, telegram, clock):
    worker = Deliveries(database, SITE, telegram, clock=clock)
    row = database.add()
    started, release = threading.Event(), threading.Event()

    def blocked():
        started.set()
        release.wait(5)

    telegram.during = blocked

    async def main():
        task = asyncio.create_task(worker.run())
        await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await asyncio.sleep(0.05)
        release.set()
        with suppress(asyncio.CancelledError):
            await task
        return task

    task = asyncio.run(main())

    assert task.cancelled()
    assert (row["status"], row["sent_id"]) == ("sent", "1")
    assert database.listeners[0].terminated


def test_worker_keeps_going_after_database_error(database, telegram, clock, caplog):
    worker = Deliveries(database, SITE, telegram, clock=clock, poll=0.01)
    database.failures[RECOVER] = ConnectionRefusedError("Không kết nối được PostgreSQL")
    row = database.add()

    async def main():
        async with running(worker):
            await wait_for(lambda: row["status"] == "sent")

    asyncio.run(main())

    assert messages_of(caplog, logging.ERROR) == [
        "Gửi tin Telegram bị lỗi. Service sẽ thử lại sau 0.01 giây"
    ]
