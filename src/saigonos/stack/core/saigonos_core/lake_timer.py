# SPDX-License-Identifier: Apache-2.0
import asyncio
import logging
import sys

INTERVAL = 3600
FIRST_RUN = 60
COMMAND = (sys.executable, "-m", "saigonos_core.lake", "run", "--timer")

logger = logging.getLogger(__name__)


class LakeTimer:
    def __init__(
        self,
        interval: float = INTERVAL,
        first_run: float = FIRST_RUN,
        command: tuple[str, ...] = COMMAND,
    ) -> None:
        self.interval = interval
        self.first_run = first_run
        self.command = command

    async def run(self) -> None:
        delay = self.first_run
        while True:
            await asyncio.sleep(delay)
            delay = self.interval
            await self.run_once()

    async def run_once(self) -> int | None:
        try:
            process = await asyncio.create_subprocess_exec(*self.command)
        except OSError as error:
            logger.error("Không chạy được việc của hồ dữ liệu: %s", error)
            return None
        try:
            code = await process.wait()
        except asyncio.CancelledError:
            process.terminate()
            await process.wait()
            raise
        if code:
            logger.warning("Việc của hồ dữ liệu kết thúc với mã thoát %s", code)
        return code
