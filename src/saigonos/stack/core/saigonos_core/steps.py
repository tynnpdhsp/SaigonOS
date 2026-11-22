# SPDX-License-Identifier: Apache-2.0
import asyncio
import json
import logging
import re
import socket
from typing import Any

import asyncpg
from pydantic import TypeAdapter, ValidationError
from starlette.concurrency import run_in_threadpool

from saigonos_core.database import SEAL_CLAIMS, SET_CALLER, Database
from saigonos_core.operaton import Operaton, OperatonError, OperatonUnavailableError
from saigonos_core.processes import Name, Processes, Rules, Value, typed

TOPIC = "saigonos-function"
PROPERTY = "function"
ROLE = "workflow"
FUNCTION = re.compile(r"([a-z_][a-z0-9_]{0,62})\.([a-z_][a-z0-9_]{0,62})")
LOCK = 60
POLL = 5
WAIT = 10
RETRY_DELAYS = (5, 30, 120)
PLAIN = frozenset({"String", "Long", "Integer", "Short", "Double", "Boolean", "Null", "Date"})
RESULT = TypeAdapter(dict[Name, Value])
CLAIMS = json.dumps({"role": ROLE})
LIMIT = "SELECT set_config('statement_timeout', '20s', true)"
CLAIM = """
INSERT INTO core.step_runs (external_task_id, process_instance_id, activity_id, function)
VALUES ($1, $2, $3, $4)
ON CONFLICT (external_task_id) DO NOTHING
RETURNING true
"""
STORED = "SELECT result FROM core.step_runs WHERE external_task_id = $1"
FIND = """
SELECT p.oid,
       p.pronargs = 1 AND p.proargtypes[0] = 'jsonb'::regtype AS takes_jsonb,
       p.prokind = 'f' AND NOT p.proretset AND p.prorettype = 'jsonb'::regtype AS gives_jsonb,
       EXISTS (
           SELECT FROM pg_catalog.aclexplode(p.proacl) AS acl
           WHERE acl.grantee = 'workflow'::regrole AND acl.privilege_type = 'EXECUTE'
       ) AS declared
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
WHERE n.nspname = $1 AND p.proname = $2
"""
CALL = "SELECT core.run_step($1::oid::regprocedure, $2::jsonb)"
AS_SERVICE = "SELECT set_config('role', 'none', true)"
SAVE = "UPDATE core.step_runs SET result = $2::jsonb WHERE external_task_id = $1"

logger = logging.getLogger(__name__)


class InvalidStepError(Exception):
    pass


class FunctionFailedError(Exception):
    def __init__(self, message: str, details: str) -> None:
        super().__init__(message)
        self.details = details


def function_of(task: dict[str, Any]) -> tuple[str, str]:
    value = (task.get("extensionProperties") or {}).get(PROPERTY)
    if value is None:
        raise InvalidStepError("Bước máy thiếu thuộc tính function nêu tên hàm dạng schema.ten_ham")
    match = FUNCTION.fullmatch(value)
    if match is None:
        raise InvalidStepError(
            f"Tên hàm {value} không hợp lệ. Tên hàm có dạng schema.ten_ham, "
            "chỉ gồm chữ thường không dấu, chữ số và dấu gạch dưới"
        )
    return match[1], match[2]


def plain(variables: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for name, item in variables.items():
        if item["type"] not in PLAIN:
            raise InvalidStepError(
                f"Biến {name} có kiểu {item['type']}. Hàm chỉ nhận được biến kiểu chuỗi, số, "
                "ngày giờ, true, false và null"
            )
    return {name: item["value"] for name, item in variables.items()}


def procedure_of(rows: list[asyncpg.Record], label: str) -> int:
    if not rows:
        raise InvalidStepError(f"Không có hàm {label}")
    matching = [row for row in rows if row["takes_jsonb"]]
    if not matching:
        raise InvalidStepError(f"Hàm {label} phải nhận đúng một tham số kiểu jsonb")
    [row] = matching
    if not row["gives_jsonb"]:
        raise InvalidStepError(f"Hàm {label}(jsonb) phải trả về một giá trị kiểu jsonb")
    if not row["declared"]:
        raise InvalidStepError(
            f"Hàm {label}(jsonb) chưa được khai báo cho quy trình. Hãy cấp quyền bằng lệnh "
            f"GRANT EXECUTE ON FUNCTION {label}(jsonb) TO {ROLE}"
        )
    return row["oid"]


def result_of(returned: str | None, rules: Rules, label: str) -> dict[str, dict[str, Any]]:
    value = None if returned is None else json.loads(returned)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InvalidStepError(f"Hàm {label} phải trả về một object jsonb hoặc null")
    try:
        found = RESULT.validate_python(value)
    except ValidationError as error:
        key = error.errors()[0]["loc"][0]
        raise InvalidStepError(
            f"Khóa {key} trong kết quả của hàm {label} không ghi được thành biến. Tên biến gồm "
            "chữ cái không dấu, chữ số và dấu gạch dưới. Giá trị là chuỗi tối đa 4.000 ký tự, "
            "số nguyên, số thực, true, false hoặc null"
        ) from None
    reserved = sorted(rules.initiators & found.keys())
    if reserved:
        raise InvalidStepError(
            f"Hàm {label} không được ghi biến {', '.join(reserved)}. Biến này do service core ghi"
        )
    return {name: typed(item) for name, item in found.items()}


def details_of(error: asyncpg.PostgresError) -> str:
    lines = [f"SQLSTATE {error.sqlstate}: {error.args[0]}"]
    lines += [text for text in (error.detail, error.hint, error.context) if text]
    return "\n".join(lines)


def retry_after(task: dict[str, Any]) -> tuple[int, int]:
    remaining = len(RETRY_DELAYS) if task["retries"] is None else max(task["retries"] - 1, 0)
    if not remaining:
        return 0, 0
    return remaining, RETRY_DELAYS[max(len(RETRY_DELAYS) - remaining, 0)]


class Steps:
    def __init__(
        self,
        database: Database,
        operaton: Operaton,
        processes: Processes,
        worker: str | None = None,
        poll: float = POLL,
        wait: float = WAIT,
    ) -> None:
        self.database = database
        self.operaton = operaton
        self.processes = processes
        self.worker = worker or f"saigonos-core-{socket.gethostname()}"
        self.poll = poll
        self.wait = wait
        self.trouble: str | None = None

    async def run(self) -> None:
        while True:
            try:
                await self.next_steps()
            except OperatonUnavailableError as error:
                if str(error) != self.trouble:
                    logger.warning("Chưa chạy được bước máy vì Operaton chưa sẵn sàng: %s", error)
                self.trouble = str(error)
                await asyncio.sleep(self.wait)
            except Exception:
                logger.exception("Chạy bước máy bị lỗi. Service sẽ thử lại sau %s giây", self.wait)
                await asyncio.sleep(self.wait)

    async def next_steps(self) -> None:
        tasks = await run_in_threadpool(
            self.operaton.lock_external_tasks, self.worker, TOPIC, LOCK, self.poll
        )
        self.trouble = None
        for task in tasks:
            await self.handle(task)

    async def handle(self, task: dict[str, Any]) -> None:
        try:
            result = await self.perform(task)
        except InvalidStepError as error:
            logger.error(
                "Bước máy %s của quy trình %s không chạy được và trở thành incident: %s",
                task["activityId"],
                task["processInstanceId"],
                error,
            )
            await self.fail(task, str(error), str(error), 0, 0)
        except FunctionFailedError as error:
            retries, delay = retry_after(task)
            logger.warning(
                "Bước máy %s của quy trình %s bị lỗi: %s. Còn %s lần thử lại",
                task["activityId"],
                task["processInstanceId"],
                error,
                retries,
            )
            await self.fail(task, str(error), error.details, retries, delay)
        else:
            await self.complete(task, result)

    async def perform(self, task: dict[str, Any]) -> dict[str, dict[str, Any]]:
        schema, name = function_of(task)
        label = f"{schema}.{name}"
        rules = await run_in_threadpool(
            self.processes.rules, task["processDefinitionId"], task["processDefinitionKey"]
        )
        async with self.database.transaction() as connection:
            await connection.execute(LIMIT)
            run = (task["id"], task["processInstanceId"], task["activityId"], label)
            if not await connection.fetchval(CLAIM, *run):
                return result_of(await connection.fetchval(STORED, task["id"]), rules, label)
            variables = plain(task["variables"])
            procedure = procedure_of(await connection.fetch(FIND, schema, name), label)
            await connection.execute(SET_CALLER, ROLE, CLAIMS)
            await connection.execute(SEAL_CLAIMS)
            try:
                returned = await connection.fetchval(CALL, procedure, json.dumps(variables))
            except asyncpg.PostgresError as error:
                message = f"Hàm {label} báo lỗi: {error.args[0]}"
                raise FunctionFailedError(message, details_of(error)) from None
            await connection.execute(AS_SERVICE)
            result = result_of(returned, rules, label)
            await connection.execute(SAVE, task["id"], returned)
        return result

    async def complete(self, task: dict[str, Any], variables: dict[str, dict[str, Any]]) -> None:
        try:
            await run_in_threadpool(
                self.operaton.complete_external_task, task["id"], self.worker, variables
            )
        except (OperatonError, OperatonUnavailableError) as error:
            logger.warning("Chưa báo được Operaton là bước máy %s đã xong: %s", task["id"], error)

    async def fail(
        self, task: dict[str, Any], message: str, details: str, retries: int, delay: int
    ) -> None:
        try:
            await run_in_threadpool(
                self.operaton.fail_external_task,
                task["id"],
                self.worker,
                message,
                details,
                retries,
                delay,
            )
        except (OperatonError, OperatonUnavailableError) as error:
            logger.warning("Chưa báo được Operaton là bước máy %s bị lỗi: %s", task["id"], error)
