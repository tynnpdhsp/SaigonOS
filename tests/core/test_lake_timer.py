# SPDX-License-Identifier: Apache-2.0
import asyncio
import logging
import sys
import time

from saigonos_core.lake_timer import COMMAND, LakeTimer


def test_timer_runs_lake_command_of_core_with_timer_flag():
    timer = LakeTimer()

    assert timer.command == (sys.executable, "-m", "saigonos_core.lake", "run", "--timer")
    assert (timer.interval, timer.first_run) == (3600, 60)
    assert COMMAND[-2:] == ("run", "--timer")


def test_exit_code_of_failed_run_is_logged(caplog):
    timer = LakeTimer(command=(sys.executable, "-c", "raise SystemExit(3)"))

    with caplog.at_level(logging.WARNING):
        assert asyncio.run(timer.run_once()) == 3

    assert caplog.messages == ["Việc của hồ dữ liệu kết thúc với mã thoát 3"]


def test_missing_program_is_logged_and_timer_keeps_going(caplog, tmp_path):
    timer = LakeTimer(command=(str(tmp_path / "khong-co"),))

    assert asyncio.run(timer.run_once()) is None
    assert caplog.messages[0].startswith("Không chạy được việc của hồ dữ liệu: ")


def test_timer_waits_first_then_runs_every_interval(tmp_path):
    marks = tmp_path / "lan-chay"
    script = f"open({str(marks)!r}, 'a').write('x')"
    timer = LakeTimer(interval=0.2, first_run=0.1, command=(sys.executable, "-c", script))

    async def watch():
        task = asyncio.create_task(timer.run())
        await asyncio.sleep(0.05)
        started = marks.exists()
        deadline = time.monotonic() + 10
        while (marks.read_text() if marks.exists() else "") != "xx":
            assert time.monotonic() < deadline
            await asyncio.sleep(0.02)
        task.cancel()
        return started

    assert asyncio.run(watch()) is False
    assert marks.read_text() == "xx"


def test_stopping_core_stops_running_lake_command(tmp_path):
    started = tmp_path / "da-chay"
    script = f"import time; open({str(started)!r}, 'w').close(); time.sleep(60)"
    timer = LakeTimer(command=(sys.executable, "-c", script))

    async def stop():
        task = asyncio.create_task(timer.run_once())
        while not started.exists():
            await asyncio.sleep(0.02)
        begun = time.monotonic()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return time.monotonic() - begun
        return None

    elapsed = asyncio.run(stop())

    assert elapsed is not None
    assert elapsed < 5
