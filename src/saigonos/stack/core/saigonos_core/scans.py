# SPDX-License-Identifier: Apache-2.0
import asyncio
import logging
from contextlib import suppress
from tempfile import SpooledTemporaryFile
from time import monotonic
from uuid import UUID

from asyncpg import Record
from starlette.concurrency import run_in_threadpool

from saigonos_core.clamav import ClamAV, ClamAVUnavailableError, ScanError
from saigonos_core.database import Database
from saigonos_core.storage import CLEAN, QUARANTINE, Storage, StorageError

SPOOL_SIZE = 1024 * 1024
RETRY = 10
MAX_DELAY = 3600
NEXT = """
SELECT id, type, size, sha256 FROM core.files
WHERE status = 'pending_scan' AND id <> ALL($1::uuid[])
ORDER BY uploaded_at, id
LIMIT 1
FOR UPDATE SKIP LOCKED
"""
MARK_CLEAN = "UPDATE core.files SET status = 'clean', scanned_at = now() WHERE id = $1"
MARK_INFECTED = """
UPDATE core.files SET status = 'infected', malware = $2, scanned_at = now() WHERE id = $1
"""

logger = logging.getLogger(__name__)


class Scans:
    def __init__(
        self, database: Database, storage: Storage, clamav: ClamAV, retry: float = RETRY
    ) -> None:
        self.database = database
        self.storage = storage
        self.clamav = clamav
        self.retry = retry
        self.wake = asyncio.Event()
        self.failures: dict[UUID, tuple[int, float]] = {}

    def notify(self) -> None:
        self.wake.set()

    async def run(self) -> None:
        while True:
            self.wake.clear()
            try:
                await self.scan_pending()
            except Exception:
                logger.exception("Quét file bị lỗi. Service sẽ thử lại sau %s giây", self.retry)
            with suppress(TimeoutError):
                await asyncio.wait_for(self.wake.wait(), self.retry)

    async def scan_pending(self) -> None:
        ready = False
        while True:
            async with self.database.transaction() as connection:
                file = await connection.fetchrow(NEXT, self.postponed())
                if file is None:
                    return
                try:
                    if not ready:
                        await run_in_threadpool(self.clamav.ping)
                        ready = True
                    malware = await run_in_threadpool(self.check, file)
                except ClamAVUnavailableError as error:
                    if ready:
                        self.postpone(file["id"], error)
                    else:
                        logger.warning("Chưa quét được file vì chưa kết nối được ClamAV: %s", error)
                    return
                except (ScanError, StorageError) as error:
                    self.postpone(file["id"], error)
                    continue
                if malware is None:
                    await connection.execute(MARK_CLEAN, file["id"])
                else:
                    await connection.execute(MARK_INFECTED, file["id"], malware)
            self.failures.pop(file["id"], None)
            if malware is None:
                await self.release(file["id"])
            else:
                logger.warning("Phát hiện mã độc %s trong file %s", malware, file["id"])

    def check(self, file: Record) -> str | None:
        key = str(file["id"])
        with SpooledTemporaryFile(SPOOL_SIZE) as spool:
            if self.storage.get(QUARANTINE, key, spool) != file["sha256"]:
                raise StorageError("Nội dung trong bucket quarantine không khớp mã băm đã ghi")
            spool.seek(0)
            malware = self.clamav.scan(spool)
            if malware is None:
                spool.seek(0)
                self.storage.put(CLEAN, key, spool, file["size"], file["sha256"], file["type"])
        return malware

    async def release(self, file_id: UUID) -> None:
        try:
            await run_in_threadpool(self.storage.delete, QUARANTINE, str(file_id))
        except StorageError as error:
            logger.warning("Không xóa được file %s khỏi bucket quarantine: %s", file_id, error)

    def postpone(self, file_id: UUID, error: Exception) -> None:
        count = self.failures.get(file_id, (0, 0.0))[0] + 1
        delay = min(self.retry * 2**count, MAX_DELAY)
        self.failures[file_id] = (count, monotonic() + delay)
        logger.warning(
            "Chưa quét được file %s: %s. Service sẽ quét lại sau %s giây", file_id, error, delay
        )

    def postponed(self) -> list[UUID]:
        now = monotonic()
        return [file_id for file_id, (_, until) in self.failures.items() if until > now]
