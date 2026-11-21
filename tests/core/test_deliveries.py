# SPDX-License-Identifier: Apache-2.0
import asyncio
import logging
import threading
from contextlib import asynccontextmanager, suppress

import pytest

from saigonos_core.deliveries import (
    DUE,
    EMAIL,
    MAX_ATTEMPTS,
    NEXT,
    NOTIFY_CHANNEL,
    POLL,
    RECORD,
    RECOVER,
    RETRY_DELAYS,
    SENDING,
    SHORTEST_WAIT,
    SKIP,
    TELEGRAM,
    Deliveries,
    Step,
    next_step,
)
from saigonos_core.outcome import FAILED, RETRY, SENT, UNKNOWN, WAIT, Outcome
from saigonos_core.telegram import message_of

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

    def rows_of(self, channel, status):
        rows = self.database.rows.values()
        return [row for row in rows if row["channel"] == channel and row["status"] == status]

    async def fetch(self, query, channel, reason):
        self.run(query)
        status = {RECOVER: ("sending", "unknown"), SKIP: ("pending", "skipped")}
        before, after = status[query]
        changed = self.rows_of(channel, before)
        for row in changed:
            row |= {"status": after, "finished": True, "error": reason}
        return [{"id": row["id"]} for row in changed]

    async def fetchrow(self, query, channel):
        self.run(query)
        assert query == NEXT
        now = self.database.clock()
        due = [row for row in self.rows_of(channel, "pending") if row["next_attempt_at"] <= now]
        if not due:
            return None
        row = min(due, key=lambda row: row["id"])
        fields = ("id", "address", "title", "body", "link", "failures")
        return {name: row[name] for name in fields}

    async def fetchval(self, query, channel):
        self.run(query)
        assert query == DUE
        times = [row["next_attempt_at"] for row in self.rows_of(channel, "pending")]
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
            "channel": TELEGRAM.name,
            "address": None,
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


class FakeSender:
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
    return FakeSender()


@pytest.fixture
def worker(database, telegram, clock):
    return Deliveries(database, SITE, TELEGRAM, telegram, clock=clock)


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


def test_worker_sends_recovers_and_skips_only_deliveries_of_its_channel(database, telegram, clock):
    others = [database.add(channel="email"), database.add(channel="email", status="sending")]
    mine = database.add()

    work(Deliveries(database, SITE, TELEGRAM, telegram, clock=clock))
    later = database.add()
    work(Deliveries(database, SITE, TELEGRAM, clock=clock))

    assert [row["status"] for row in others] == ["pending", "sending"]
    assert (mine["status"], later["status"]) == ("sent", "skipped")
    assert [message["text"] for message in telegram.messages] == ["Tin 3"]


def test_delivery_of_other_channel_does_not_shorten_wait(worker, database, clock):
    database.add(channel="email", next_attempt_at=clock.now + 1)

    assert asyncio.run(worker.due()) == POLL


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
    worker = Deliveries(database, SITE, TELEGRAM, clock=clock)
    rows = [database.add(), database.add()]

    wait = work(worker)

    assert wait == POLL
    assert [(row["status"], row["error"]) for row in rows] == [
        ("skipped", TELEGRAM.not_configured)
    ] * 2
    assert messages_of(caplog) == ["Chưa cấu hình Telegram nên tin Telegram 1, 2 không được gửi"]


def test_invalid_settings_are_logged_at_start_and_kept_with_skipped_deliveries(
    database, clock, caplog
):
    worker = Deliveries(
        database, SITE, TELEGRAM, problem="thiếu TELEGRAM_CHAT_ID", clock=clock, poll=0.01
    )
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

    assert [(row["status"], row["error"]) for row in rows] == [("unknown", TELEGRAM.stopped)] * 2
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

    assert [listener.channel for listener in database.listeners] == [NOTIFY_CHANNEL, NOTIFY_CHANNEL]
    database.listeners[-1].callback()
    assert worker.wake.is_set()


def test_notification_wakes_worker_before_poll(database, telegram, clock):
    worker = Deliveries(database, SITE, TELEGRAM, telegram, clock=clock, poll=60)

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
    worker = Deliveries(database, SITE, TELEGRAM, telegram, clock=clock)
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
    worker = Deliveries(database, SITE, TELEGRAM, telegram, clock=clock, poll=0.01)
    database.failures[RECOVER] = ConnectionRefusedError("Không kết nối được PostgreSQL")
    row = database.add()

    async def main():
        async with running(worker):
            await wait_for(lambda: row["status"] == "sent")

    asyncio.run(main())

    assert messages_of(caplog, logging.ERROR) == [
        "Gửi tin Telegram bị lỗi. Service sẽ thử lại sau 0.01 giây"
    ]


def email_row(database, **fields):
    values = {"channel": EMAIL.name, "address": "nguyen.van.a@example.com"}
    return database.add(**(values | fields))


def test_email_goes_to_address_of_delivery_with_full_link(database, clock):
    mailer = FakeSender()
    row = email_row(database, title="Đã nhận yêu cầu YC-001", body="Cảm ơn", link="/tra-cuu/YC-001")

    work(Deliveries(database, SITE, EMAIL, mailer, clock=clock))

    [sent] = mailer.messages
    assert (str(sent["To"]), str(sent["Subject"])) == (row["address"], "Đã nhận yêu cầu YC-001")
    assert sent.get_content().splitlines() == ["Cảm ơn", "", f"{SITE}/tra-cuu/YC-001"]
    assert (row["status"], row["sent_id"]) == ("sent", "1")


def test_rate_limit_of_telegram_does_not_pause_email(database, telegram, clock):
    mailer = FakeSender()
    message, letter = database.add(), email_row(database)
    telegram.outcomes = [Outcome(WAIT, "Telegram trả về mã 429: Too Many Requests", 30)]

    paused = work(Deliveries(database, SITE, TELEGRAM, telegram, clock=clock))
    work(Deliveries(database, SITE, EMAIL, mailer, clock=clock))

    assert paused == 30
    assert (message["status"], letter["status"]) == ("pending", "sent")
    assert len(mailer.messages) == 1


EMAIL_REPORTS = {
    "gui-lai": (
        Outcome(RETRY, "Máy chủ SMTP trả về mã 451"),
        logging.WARNING,
        "Chưa gửi được email 1: Máy chủ SMTP trả về mã 451. Email sẽ được gửi lại sau 5 giây",
    ),
    "khong-biet": (
        Outcome(UNKNOWN, "Mất kết nối khi chờ máy chủ SMTP trả lời"),
        logging.WARNING,
        "Không biết email 1 đã tới máy chủ SMTP hay chưa: Mất kết nối khi chờ máy chủ SMTP trả "
        "lời. Email không được gửi lại để tránh gửi trùng",
    ),
    "that-bai": (
        Outcome(FAILED, "Máy chủ SMTP trả về mã 550"),
        logging.ERROR,
        "Không gửi được email 1 sau 1 lần thử: Máy chủ SMTP trả về mã 550",
    ),
}


@pytest.mark.parametrize(
    ("outcome", "level", "logged"), EMAIL_REPORTS.values(), ids=EMAIL_REPORTS.keys()
)
def test_email_outcomes_are_logged_as_email(database, clock, caplog, outcome, level, logged):
    mailer = FakeSender()
    mailer.outcomes = [outcome]
    email_row(database)

    work(Deliveries(database, SITE, EMAIL, mailer, clock=clock))

    assert messages_of(caplog, level) == [logged]


def test_without_smtp_pending_emails_are_skipped(database, clock, caplog):
    rows = [email_row(database), email_row(database)]

    work(Deliveries(database, SITE, EMAIL, clock=clock))

    assert [(row["status"], row["error"]) for row in rows] == [
        ("skipped", "Chưa cấu hình SMTP")
    ] * 2
    assert messages_of(caplog) == ["Chưa cấu hình SMTP nên email 1, 2 không được gửi"]


def test_invalid_smtp_settings_are_logged_and_kept_with_skipped_emails(database, clock, caplog):
    worker = Deliveries(database, SITE, EMAIL, problem="thiếu SMTP_FROM", clock=clock, poll=0.01)
    row = email_row(database)

    async def main():
        async with running(worker):
            await wait_for(lambda: row["status"] == "skipped")
            await asyncio.sleep(0.05)

    asyncio.run(main())

    reason = "Cấu hình SMTP chưa đúng: thiếu SMTP_FROM"
    assert row["error"] == reason
    assert messages_of(caplog, logging.ERROR) == [f"{reason}. Email sẽ không được gửi"]


def test_emails_left_sending_become_unknown_at_start(database, clock, caplog):
    rows = [email_row(database, status="sending"), database.add(status="sending")]

    work(Deliveries(database, SITE, EMAIL, FakeSender(), clock=clock))

    assert [(row["status"], row["error"]) for row in rows] == [
        ("unknown", EMAIL.stopped),
        ("sending", None),
    ]
    assert EMAIL.stopped == (
        "Service core dừng khi đang gửi email nên không biết email đã tới máy chủ SMTP hay chưa"
    )
    assert messages_of(caplog) == [
        "Email 1 đang được gửi khi service core dừng. Không biết các email này đã tới máy chủ "
        "SMTP hay chưa nên chúng không được gửi lại"
    ]
