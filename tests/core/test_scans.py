# SPDX-License-Identifier: Apache-2.0
import asyncio
import hashlib
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from saigonos_core import scans as scans_module
from saigonos_core.clamav import ClamAVUnavailableError, ScanError
from saigonos_core.scans import MARK_CLEAN, MARK_INFECTED, MAX_DELAY, NEXT, Scans
from saigonos_core.storage import CLEAN, QUARANTINE, StorageError

PNG = b"\x89PNG\r\n\x1a\n" + b"\x01" * 50
INFECTED = b"noi dung co ma doc"
RETRY = 10


def sha256(content):
    return hashlib.sha256(content).hexdigest()


class FakeConnection:
    def __init__(self, database):
        self.database = database

    async def fetchrow(self, query, postponed):
        assert query == NEXT
        pending = [
            row
            for row in self.database.rows
            if row["status"] == "pending_scan" and row["id"] not in postponed
        ]
        if not pending:
            return None
        row = min(pending, key=lambda row: row["uploaded_at"])
        return {name: row[name] for name in ("id", "type", "size", "sha256")}

    async def execute(self, query, file_id, *arguments):
        row = next(row for row in self.database.rows if row["id"] == file_id)
        row["scanned_at"] = datetime.now(UTC)
        if query == MARK_CLEAN:
            row["status"] = "clean"
        else:
            assert query == MARK_INFECTED
            row |= {"status": "infected", "malware": arguments[0]}


class FakeDatabase:
    def __init__(self):
        self.rows = []
        self.failure = None

    @asynccontextmanager
    async def transaction(self):
        if self.failure:
            raise self.failure
        yield FakeConnection(self)

    def add(self, content, type="image/png", age=0):
        row = {"id": uuid4(), "type": type, "size": len(content), "sha256": sha256(content)}
        row |= {"status": "pending_scan", "malware": None, "scanned_at": None}
        row["uploaded_at"] = datetime.now(UTC) - timedelta(seconds=age)
        self.rows.append(row)
        return row


class FakeStorage:
    def __init__(self):
        self.objects = {}
        self.metadata = {}
        self.calls = []
        self.failures = {}

    def get(self, bucket, key, sink):
        self.called("get", bucket, key)
        if (bucket, key) not in self.objects:
            raise StorageError("Kho file trả về mã 404")
        sink.write(self.objects[bucket, key])
        return sha256(self.objects[bucket, key])

    def put(self, bucket, key, body, size, digest, content_type):
        self.called("put", bucket, key)
        self.objects[bucket, key] = body.read()
        self.metadata[bucket, key] = (size, digest, content_type)

    def delete(self, bucket, key):
        self.called("delete", bucket, key)
        self.objects.pop((bucket, key), None)

    def called(self, method, bucket, key):
        self.calls.append((method, bucket, key))
        if method in self.failures:
            raise self.failures[method]


class FakeClamAV:
    def __init__(self):
        self.down = False
        self.results = {INFECTED: "Eicar-Test-Signature"}
        self.scanned = []
        self.pings = 0

    def ping(self):
        self.pings += 1
        if self.down:
            raise ClamAVUnavailableError("Không kết nối được ClamAV: Connection refused")

    def scan(self, content):
        self.scanned.append(content.read())
        result = self.results.get(self.scanned[-1])
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def database():
    return FakeDatabase()


@pytest.fixture
def storage():
    return FakeStorage()


@pytest.fixture
def clamav():
    return FakeClamAV()


@pytest.fixture
def worker(database, storage, clamav):
    return Scans(database, storage, clamav, RETRY)


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(scans_module, "monotonic", lambda: now[0])
    return now


def uploaded(database, storage, content, **fields):
    row = database.add(content, **fields)
    storage.objects[QUARANTINE, str(row["id"])] = content
    return row


def scan(worker):
    asyncio.run(worker.scan_pending())


async def wait_for(condition, timeout=5):
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.01)


@asynccontextmanager
async def running(worker):
    task = asyncio.create_task(worker.run())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def test_clean_file_moves_from_quarantine_to_clean(worker, database, storage):
    row = uploaded(database, storage, PNG)

    scan(worker)

    key = str(row["id"])
    assert (row["status"], row["malware"]) == ("clean", None)
    assert row["scanned_at"] is not None
    assert storage.objects == {(CLEAN, key): PNG}
    assert storage.metadata[CLEAN, key] == (len(PNG), row["sha256"], "image/png")


def test_infected_file_stays_in_quarantine_with_malware_name(worker, database, storage, caplog):
    row = uploaded(database, storage, INFECTED, type="text/plain")

    scan(worker)

    assert (row["status"], row["malware"]) == ("infected", "Eicar-Test-Signature")
    assert row["scanned_at"] is not None
    assert storage.objects == {(QUARANTINE, str(row["id"])): INFECTED}
    assert f"Phát hiện mã độc Eicar-Test-Signature trong file {row['id']}" in caplog.text


def test_files_are_scanned_oldest_first(worker, database, storage, clamav):
    uploaded(database, storage, b"moi hon")
    uploaded(database, storage, b"cu hon", age=60)

    scan(worker)

    assert clamav.scanned == [b"cu hon", b"moi hon"]


def test_clamav_is_pinged_once_per_round(worker, database, storage, clamav):
    for content in [b"mot", b"hai", b"ba"]:
        uploaded(database, storage, content)

    scan(worker)

    assert clamav.pings == 1
    assert len(clamav.scanned) == 3


def test_file_waits_without_reading_storage_while_clamav_is_down(
    worker, database, storage, clamav, caplog
):
    row = uploaded(database, storage, PNG)
    clamav.down = True

    scan(worker)
    waiting = (row["status"], list(storage.calls))
    clamav.down = False
    scan(worker)

    assert waiting == ("pending_scan", [])
    assert "Chưa quét được file vì chưa kết nối được ClamAV" in caplog.text
    assert row["status"] == "clean"
    assert worker.failures == {}


def test_file_that_breaks_clamav_is_postponed_while_others_are_scanned(
    worker, database, storage, clamav
):
    poison = uploaded(database, storage, b"lam clamav dung", age=60)
    other = uploaded(database, storage, PNG)
    clamav.results[b"lam clamav dung"] = ClamAVUnavailableError("ClamAV đóng kết nối")

    scan(worker)
    first = (poison["status"], other["status"])
    scan(worker)

    assert first == ("pending_scan", "pending_scan")
    assert (poison["status"], other["status"]) == ("pending_scan", "clean")
    assert list(worker.failures) == [poison["id"]]


def test_scan_error_postpones_only_that_file(worker, database, storage, clamav, caplog):
    broken = uploaded(database, storage, b"khong quet duoc", age=60)
    other = uploaded(database, storage, PNG)
    error = ScanError("ClamAV không quét được nội dung: INSTREAM size limit exceeded. ERROR")
    clamav.results[b"khong quet duoc"] = error

    scan(worker)

    assert (broken["status"], other["status"]) == ("pending_scan", "clean")
    assert f"Chưa quét được file {broken['id']}: {error}" in caplog.text
    assert "Service sẽ quét lại sau 20 giây" in caplog.text


def test_postponed_file_is_scanned_again_after_its_delay(worker, database, storage, clamav, clock):
    row = uploaded(database, storage, b"loi tam thoi")
    clamav.results[b"loi tam thoi"] = ScanError("ClamAV không quét được nội dung: ERROR")

    scan(worker)
    del clamav.results[b"loi tam thoi"]
    clock[0] += RETRY * 2 - 0.1
    scan(worker)
    early = row["status"]
    clock[0] += 0.2
    scan(worker)

    assert early == "pending_scan"
    assert row["status"] == "clean"
    assert worker.failures == {}


def test_delay_doubles_after_each_failure_up_to_one_hour(worker, clock):
    file_id = uuid4()
    delays = []

    for _ in range(12):
        worker.postpone(file_id, ScanError("ClamAV không quét được nội dung: ERROR"))
        delays.append(worker.failures[file_id][1] - clock[0])

    assert delays[:3] == [RETRY * 2, RETRY * 4, RETRY * 8]
    assert delays[-1] == MAX_DELAY


def test_content_that_differs_from_recorded_hash_is_not_scanned(worker, database, storage, clamav):
    row = uploaded(database, storage, PNG)
    storage.objects[QUARANTINE, str(row["id"])] = PNG + b"\x00"

    scan(worker)

    assert row["status"] == "pending_scan"
    assert clamav.scanned == []
    assert (CLEAN, str(row["id"])) not in storage.objects
    assert row["id"] in worker.failures


def test_missing_content_postpones_file(worker, database, storage):
    row = database.add(PNG)

    scan(worker)

    assert row["status"] == "pending_scan"
    assert row["id"] in worker.failures


def test_file_stays_pending_when_clean_bucket_refuses_content(worker, database, storage):
    row = uploaded(database, storage, PNG)
    storage.failures["put"] = StorageError("Kho file trả về mã 503")

    scan(worker)

    assert row["status"] == "pending_scan"
    assert storage.objects == {(QUARANTINE, str(row["id"])): PNG}


def test_clean_file_stays_clean_when_quarantine_copy_cannot_be_deleted(
    worker, database, storage, caplog
):
    row = uploaded(database, storage, PNG)
    storage.failures["delete"] = StorageError("Kho file trả về mã 503")

    scan(worker)

    assert row["status"] == "clean"
    assert storage.objects[CLEAN, str(row["id"])] == PNG
    assert f"Không xóa được file {row['id']} khỏi bucket quarantine" in caplog.text


def test_run_scans_pending_files_at_start(database, storage, clamav):
    worker = Scans(database, storage, clamav, retry=60)
    row = uploaded(database, storage, PNG)

    async def main():
        async with running(worker):
            await wait_for(lambda: row["status"] == "clean")

    asyncio.run(main())


def test_run_scans_new_upload_as_soon_as_notified(database, storage, clamav):
    worker = Scans(database, storage, clamav, retry=60)

    async def main():
        async with running(worker):
            await asyncio.sleep(0.05)
            row = uploaded(database, storage, PNG)
            worker.notify()
            await wait_for(lambda: row["status"] == "clean")

    asyncio.run(main())


def test_run_tries_again_after_retry_without_notification(database, storage, clamav):
    worker = Scans(database, storage, clamav, retry=0.05)
    clamav.down = True
    row = uploaded(database, storage, PNG)

    async def main():
        async with running(worker):
            await wait_for(lambda: clamav.pings >= 2)
            clamav.down = False
            await wait_for(lambda: row["status"] == "clean")

    asyncio.run(main())


def test_run_keeps_going_after_database_error(database, storage, clamav, caplog):
    worker = Scans(database, storage, clamav, retry=0.05)
    database.failure = ConnectionRefusedError("Không kết nối được PostgreSQL")
    row = uploaded(database, storage, PNG)

    async def main():
        async with running(worker):
            await wait_for(lambda: "Quét file bị lỗi" in caplog.text)
            database.failure = None
            await wait_for(lambda: row["status"] == "clean")

    asyncio.run(main())

    assert "Service sẽ thử lại sau 0.05 giây" in caplog.text
