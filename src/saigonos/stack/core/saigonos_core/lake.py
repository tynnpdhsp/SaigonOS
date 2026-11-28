# SPDX-License-Identifier: Apache-2.0
import argparse
import asyncio
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

import asyncpg
import duckdb
from pydantic import ValidationError

from saigonos_core.manifest import ArchiveTable, Manifest, QualityRule, Snapshot
from saigonos_core.storage import Storage, StorageError

BUCKET = "lake"
TIMEZONE = "Asia/Ho_Chi_Minh"
TIMEZONE_PATTERN = re.compile(r"[A-Za-z0-9_+\-/]{1,64}")
NAME_PATTERN = re.compile(r"[a-z_][a-z0-9_]*")
NUMERIC_PATTERN = re.compile(r"numeric\((\d+),(\d+)\)")
CONTENT_TYPE = "application/vnd.apache.parquet"
CHUNK_SIZE = 1024 * 1024
CONNECT_TIMEOUT = 10
EXAMPLES = 3
MONTHS_PER_RUN = 24
DECIMAL_DIGITS = 38
TITLE = "Dữ liệu của ứng dụng {app} không đạt luật chất lượng"
BODY_LENGTH = 2000
SAY_NOTHING = "Không có tháng nào cần chốt số liệu và không có dòng nào cần chuyển xuống hồ."
TRY_LOCK = "SELECT pg_try_advisory_lock('core.lineage'::regclass::oid::bigint)"
LOCK = "SELECT pg_advisory_lock('core.lineage'::regclass::oid::bigint)"
APPS = (
    "SELECT name, schema_name, manifest FROM core.apps WHERE applied_at IS NOT NULL ORDER BY name"
)
PREPARE = """
SELECT set_config('TimeZone', $1, true), set_config('DateStyle', 'ISO, YMD', true),
    set_config('IntervalStyle', 'postgres', true), set_config('extra_float_digits', '1', true),
    set_config('bytea_output', 'hex', true)
"""
BECOME_LAKE = "SET LOCAL ROLE lake"
ZONE = "SELECT set_config('TimeZone', $1, false)"
COLUMNS = """
SELECT a.attname AS name, t.typname AS type, t.typcategory AS category,
    pg_catalog.format_type(a.atttypid, a.atttypmod) AS declared
FROM pg_catalog.pg_attribute AS a
JOIN pg_catalog.pg_type AS t ON t.oid = core.base_type(a.atttypid)
WHERE a.attrelid = $1::text::regclass AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY a.attnum
"""
KEYS = """
SELECT a.attname
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_attribute AS a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
WHERE i.indrelid = $1::text::regclass AND i.indisprimary
ORDER BY pg_catalog.array_position(i.indkey::int2[], a.attnum)
"""
CUTOFF = """
SELECT LEAST(localtimestamp - pg_catalog.make_interval(days => $1), $2::text::timestamp)::text
"""
PENDING = """
SELECT pg_catalog.to_char(month, 'YYYY-MM') AS period
FROM pg_catalog.generate_series(
    (SELECT pg_catalog.date_trunc('month', pg_catalog.min({column})::timestamp) FROM {relation}),
    pg_catalog.date_trunc('month', localtimestamp) - interval '1 month',
    interval '1 month'
) AS month
WHERE pg_catalog.to_char(month, 'YYYY-MM') NOT IN (
    SELECT lineage.period FROM core.lineage
    WHERE lineage.kind = 'file' AND lineage.job = 'snapshot'
        AND lineage.app = $1 AND lineage.source = $2
)
ORDER BY month
LIMIT {limit}
"""
CURRENT_MONTH = "SELECT pg_catalog.to_char(localtimestamp, 'YYYY-MM')"
CHECKED = """
INSERT INTO core.lineage (kind, job, started_by, app, source, period, time_from, time_to, rows,
    passed, results)
VALUES ('check', $1, $2, $3, $4, $5, $6::text::timestamp, $7::text::timestamp, $8, $9, $10::jsonb)
RETURNING id
"""
WRITTEN = """
INSERT INTO core.lineage (kind, job, started_by, app, source, period, time_from, time_to, rows,
    check_id, file, size, sha256)
VALUES ('file', $1, $2, $3, $4, $5, $6::text::timestamp, $7::text::timestamp, $8, $9, $10, $11,
    $12)
"""
ALERT = "SELECT core.alert_admins($1, $2, $3)"
FILES = """
SELECT id, app, job, source, file, sha256 FROM core.lineage WHERE kind = 'file' ORDER BY id
"""
LINEAGE = """
SELECT id, created_at, kind, job, started_by, app, source, period, time_from, time_to, rows,
    passed, results::text, check_id, file, size, sha256
FROM core.lineage ORDER BY id
"""
LINEAGE_TABLE = """
CREATE TABLE lineage (
    id BIGINT, created_at TIMESTAMPTZ, kind VARCHAR, job VARCHAR, started_by VARCHAR,
    app VARCHAR, source VARCHAR, period VARCHAR, time_from TIMESTAMPTZ, time_to TIMESTAMPTZ,
    rows BIGINT, passed BOOLEAN, results JSON, check_id BIGINT, file VARCHAR, size BIGINT,
    sha256 VARCHAR
)
"""
DIRECT_TYPES = {
    "int2": "SMALLINT",
    "int4": "INTEGER",
    "int8": "BIGINT",
    "float4": "FLOAT",
    "float8": "DOUBLE",
    "bool": "BOOLEAN",
    "date": "DATE",
    "timestamp": "TIMESTAMP",
    "timestamptz": "TIMESTAMPTZ",
    "time": "TIME",
    "uuid": "UUID",
    "json": "JSON",
    "jsonb": "JSON",
}
TIME_TYPES = {"timestamptz", "timestamp", "date"}
DATABASE_ERRORS = (OSError, asyncpg.PostgresError, asyncpg.InterfaceError)

Say = Callable[[str], None]


class LakeError(Exception):
    pass


class Settings(NamedTuple):
    storage_url: str
    access_key: str
    secret_key: str
    timezone: str

    @classmethod
    def from_environment(cls) -> "Settings":
        timezone = os.environ.get("LAKE_TIMEZONE", "").strip() or TIMEZONE
        if not TIMEZONE_PATTERN.fullmatch(timezone):
            raise LakeError(f"Múi giờ {timezone} của hồ dữ liệu không hợp lệ")
        return cls(
            os.environ["S3_URL"], os.environ["S3_ACCESS_KEY"], os.environ["S3_SECRET_KEY"], timezone
        )


class Column(NamedTuple):
    name: str
    type: str
    category: str
    declared: str


class Plan(NamedTuple):
    name: str
    select: str
    read: str
    convert: str


class Discard:
    def write(self, data: bytes) -> int:
        return len(data)


def ident(name: str) -> str:
    if not NAME_PATTERN.fullmatch(name):
        raise LakeError(f"Tên {name} không hợp lệ")
    return f'"{name}"'


def literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def month_bounds(period: str) -> tuple[str, str]:
    year, month = (int(part) for part in period.split("-"))
    after_year, after_month = (year + 1, 1) if month == 12 else (year, month + 1)
    return f"{year:04d}-{month:02d}-01 00:00:00", f"{after_year:04d}-{after_month:02d}-01 00:00:00"


def shown_month(period: str) -> str:
    year, month = period.split("-")
    return f"{month}/{year}"


def decimal_type(declared: str, size: tuple[int, int] | None) -> str:
    match = NUMERIC_PATTERN.fullmatch(declared)
    if match:
        precision, scale = int(match[1]), int(match[2])
        fits = precision <= DECIMAL_DIGITS and scale <= precision
        return f"DECIMAL({precision},{scale})" if fits else "VARCHAR"
    if size is None:
        return "VARCHAR"
    digits, scale = size
    width = digits + scale
    return f"DECIMAL({width},{scale})" if width <= DECIMAL_DIGITS else "VARCHAR"


def plan_of(column: Column, size: tuple[int, int] | None = None) -> Plan:
    quoted = ident(column.name)
    if column.type in DIRECT_TYPES:
        return Plan(column.name, quoted, DIRECT_TYPES[column.type], quoted)
    if column.type == "bytea":
        return Plan(column.name, quoted, "VARCHAR", f"unhex(substr({quoted}, 3)) AS {quoted}")
    if column.type == "numeric":
        return Plan(column.name, quoted, decimal_type(column.declared, size), quoted)
    if column.category in {"A", "C"}:
        return Plan(column.name, f"pg_catalog.to_jsonb({quoted})", "JSON", quoted)
    return Plan(column.name, f"{quoted}::text", "VARCHAR", quoted)


def free_numerics(columns: list[Column]) -> list[Column]:
    return [
        column
        for column in columns
        if column.type == "numeric" and not NUMERIC_PATTERN.fullmatch(column.declared)
    ]


@dataclass(frozen=True)
class Window:
    column: Column
    upper: str
    lower: str | None = None

    def where(self) -> tuple[str, list[str]]:
        quoted, cast = ident(self.column.name), self.column.type
        upper = f"{quoted} < $1::text::timestamp::{cast}"
        if self.lower is None:
            return upper, [self.upper]
        return f"{quoted} >= $2::text::timestamp::{cast} AND {upper}", [self.upper, self.lower]


def rule_checks(
    rule: QualityRule, where: str, args: list[str]
) -> list[tuple[dict[str, Any], str, list[str]]]:
    if rule.rule == "not_null":
        return [
            ({"rule": "not_null", "column": column}, f"{where} AND {ident(column)} IS NULL", args)
            for column in rule.columns
        ]
    if rule.rule == "range":
        tests, extra = [], []
        for operator, bound in (("<", rule.min), (">", rule.max)):
            if bound is not None:
                extra.append(repr(bound))
                tests.append(
                    f"{ident(rule.column)} {operator} ${len(args) + len(extra)}::text::numeric"
                )
        described = {"rule": "range", "column": rule.column, "min": rule.min, "max": rule.max}
        return [(described, f"{where} AND ({' OR '.join(tests)})", args + extra)]
    present = " AND ".join(f"{ident(column)} IS NOT NULL" for column in rule.columns)
    return [({"rule": "unique", "columns": list(rule.columns)}, f"{where} AND {present}", args)]


def number(value: float) -> str:
    return f"{value:g}"


def bounds_text(result: dict[str, Any]) -> str:
    low, high = result.get("min"), result.get("max")
    if low is not None and high is not None:
        return f"từ {number(low)} đến {number(high)}"
    if low is not None:
        return f"từ {number(low)} trở lên"
    return f"tối đa {number(high)}"


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))


def describe(results: list[dict[str, Any]]) -> str:
    sentences = []
    for result in results:
        if not result["rows"]:
            continue
        if result["rule"] == "unique":
            target = "cột " + ", ".join(result["columns"])
            examples = ", ".join(
                f"{compact(example['values'])} có {example['rows']} dòng"
                for example in result["examples"]
            )
        else:
            target = f"cột {result['column']}"
            if result["rule"] == "range":
                target += f" ({bounds_text(result)})"
            examples = ", ".join(compact(example) for example in result["examples"])
        sentences.append(
            f"Luật {result['rule']} của {target} không đạt ở {result['rows']} dòng, "
            f"ví dụ {examples}."
        )
    return " ".join(sentences)


def alert_key(app: str, job: str, source: str, period: str | None, failed: list[Any]) -> str:
    digest = hashlib.sha256(json.dumps(failed, sort_keys=True).encode()).hexdigest()
    return f"lake:{app}:{job}:{source}:{period or ''}:{digest[:16]}"


def shorten(text: str, limit: int = BODY_LENGTH) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as content:
        while chunk := content.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def duck(timezone: str, work: Path) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(
        config={
            "autoinstall_known_extensions": False,
            "autoload_known_extensions": False,
            "threads": 2,
            "memory_limit": "512MB",
            "temp_directory": str(work / "duckdb"),
            "home_directory": str(work),
            "extension_directory": f"{work}-extensions",
        }
    )
    connection.execute(f"SET TimeZone = {literal(timezone)}")
    return connection


def to_parquet(source: Path, target: Path, plans: list[Plan], timezone: str, work: Path) -> int:
    columns = ", ".join(f"{literal(plan.name)}: {literal(plan.read)}" for plan in plans)
    selected = ", ".join(plan.convert for plan in plans)
    reader = (
        f"read_csv({literal(str(source))}, header = false, columns = {{{columns}}}, "
        "nullstr = '', allow_quoted_nulls = false, auto_detect = false, delim = ',', "
        "quote = '\"', escape = '\"', max_line_size = 1073741824)"
    )
    connection = duck(timezone, work)
    try:
        connection.execute(
            f"COPY (SELECT {selected} FROM {reader}) TO {literal(str(target))} "
            "(FORMAT parquet, COMPRESSION zstd)"
        )
        found = connection.execute("SELECT count(*) FROM read_parquet(?)", [str(target)]).fetchone()
    finally:
        connection.close()
    return int(found[0]) if found else 0


@dataclass
class Job:
    connection: asyncpg.Connection
    storage: Storage
    timezone: str
    started_by: str
    say: Say
    work: Path
    ok: bool = True
    done: list[str] = field(default_factory=list)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        async with self.connection.transaction(isolation="repeatable_read"):
            await self.connection.execute(PREPARE, self.timezone)
            await self.connection.execute(BECOME_LAKE)
            yield self.connection

    def report(self, text: str) -> None:
        self.done.append(text)
        self.say(text)

    def fail(self, text: str) -> None:
        self.ok = False
        self.say(text)

    async def columns(self, relation: str) -> list[Column]:
        return [Column(*row) for row in await self.connection.fetch(COLUMNS, relation)]

    async def keys(self, relation: str, time_column: str) -> list[str]:
        found = [row[0] for row in await self.connection.fetch(KEYS, relation)]
        return found or [time_column]

    async def check(
        self, relation: str, window: Window, rules: list[QualityRule], keys: list[str]
    ) -> list[dict[str, Any]]:
        where, args = window.where()
        results = []
        for rule in rules:
            for described, condition, values in rule_checks(rule, where, args):
                results.append(await self.violations(relation, described, condition, values, keys))
        return results

    async def violations(
        self,
        relation: str,
        described: dict[str, Any],
        condition: str,
        values: list[str],
        keys: list[str],
    ) -> dict[str, Any]:
        if described["rule"] == "unique":
            columns = ", ".join(ident(name) for name in described["columns"])
            pairs = ", ".join(f"{literal(name)}, {ident(name)}" for name in described["columns"])
            groups = (
                f"SELECT {columns}, count(*) AS saigonos_rows FROM {relation} WHERE {condition} "
                f"GROUP BY {columns} HAVING count(*) > 1"
            )
            rows = await self.connection.fetchval(
                f"SELECT coalesce(sum(saigonos_rows), 0) FROM ({groups}) AS duplicates", *values
            )
            found = await self.connection.fetch(
                f"SELECT pg_catalog.jsonb_build_object({pairs})::text, saigonos_rows "
                f"FROM ({groups}) AS duplicates ORDER BY saigonos_rows DESC, {columns} "
                f"LIMIT {EXAMPLES}",
                *values,
            )
            examples = [{"values": json.loads(row[0]), "rows": row[1]} for row in found]
            return described | {"rows": int(rows), "examples": examples}
        shown = list(dict.fromkeys([*keys, described["column"]]))
        pairs = ", ".join(f"{literal(name)}, {ident(name)}" for name in shown)
        order = ", ".join(ident(name) for name in keys)
        rows = await self.connection.fetchval(
            f"SELECT count(*) FROM {relation} WHERE {condition}", *values
        )
        found = await self.connection.fetch(
            f"SELECT pg_catalog.jsonb_build_object({pairs})::text FROM {relation} "
            f"WHERE {condition} ORDER BY {order} LIMIT {EXAMPLES}",
            *values,
        )
        return described | {"rows": rows, "examples": [json.loads(row[0]) for row in found]}

    async def recorded_check(
        self,
        job: str,
        app: str,
        source: str,
        period: str | None,
        window: Window,
        rows: int,
        results: list[dict[str, Any]],
    ) -> tuple[int, bool]:
        passed = all(not result["rows"] for result in results)
        check_id = await self.connection.fetchval(
            CHECKED,
            job,
            self.started_by,
            app,
            source,
            period,
            window.lower,
            window.upper,
            rows,
            passed,
            json.dumps(results, ensure_ascii=False),
        )
        return check_id, passed

    async def alert(
        self, app: str, job: str, source: str, period: str | None, text: str, results: list[Any]
    ) -> None:
        failed = [result for result in results if result["rows"]]
        key = alert_key(app, job, source, period, failed)
        await self.connection.fetchval(ALERT, key, TITLE.format(app=app), shorten(text))

    async def export(
        self, relation: str, columns: list[Column], window: Window, keys: list[str], name: str
    ) -> tuple[Path, int]:
        where, args = window.where()
        sizes: dict[str, tuple[int, int] | None] = {}
        free = free_numerics(columns)
        if free:
            parts = []
            for column in free:
                quoted = ident(column.name)
                parts += [
                    f"coalesce(max(length(trunc(abs({quoted}))::text)), 1)",
                    f"coalesce(max(scale({quoted})), 0)",
                    f"coalesce(bool_or({quoted} IN ('NaN', 'Infinity', '-Infinity')), false)",
                ]
            found = tuple(
                await self.connection.fetchrow(
                    f"SELECT {', '.join(parts)} FROM {relation} WHERE {where}", *args
                )
            )
            for index, column in enumerate(free):
                digits, scale, special = found[index * 3 : index * 3 + 3]
                sizes[column.name] = None if special else (digits, scale)
        plans = [plan_of(column, sizes.get(column.name)) for column in columns]
        order = ", ".join(ident(key) for key in dict.fromkeys([window.column.name, *keys]))
        query = (
            f"SELECT {', '.join(plan.select for plan in plans)} FROM {relation} "
            f"WHERE {where} ORDER BY {order}"
        )
        source = self.work / f"{name}.csv"
        target = self.work / f"{name}.parquet"
        await self.connection.copy_from_query(query, *args, output=str(source), format="csv")
        count = await asyncio.to_thread(to_parquet, source, target, plans, self.timezone, self.work)
        source.unlink()
        return target, count

    def publish(self, key: str, path: Path) -> tuple[int, str]:
        size = path.stat().st_size
        digest = sha256_of(path)
        with path.open("rb") as body:
            self.storage.put(BUCKET, key, body, size, digest, CONTENT_TYPE)
        if self.storage.get(BUCKET, key, Discard()) != digest:
            raise LakeError(f"Nội dung đọc lại của file {key} không khớp mã băm vừa ghi")
        return size, digest

    def forget(self, keys: list[str]) -> None:
        for key in keys:
            try:
                self.storage.delete(BUCKET, key)
            except StorageError as error:
                self.say(f"Không xóa được file {key} vừa ghi: {error}.")


def time_column(columns: list[Column], name: str) -> Column:
    for column in columns:
        if column.name == name and column.type in TIME_TYPES:
            return column
    raise LakeError(f"Không có cột thời gian {name} kiểu timestamptz, timestamp hoặc date")


async def pending_months(job: Job, app: str, schema: str, entry: Snapshot) -> list[str]:
    relation = f"{ident(schema)}.{ident(entry.view)}"
    query = PENDING.format(column=ident(entry.column), relation=relation, limit=MONTHS_PER_RUN)
    async with job.transaction() as connection:
        rows = await connection.fetch(query, app, f"{schema}.{entry.view}")
    return [row[0] for row in rows]


async def snapshot_month(job: Job, app: str, schema: str, entry: Snapshot, period: str) -> bool:
    relation = f"{ident(schema)}.{ident(entry.view)}"
    source = f"{schema}.{entry.view}"
    where = f"{entry.view} tháng {shown_month(period)} trong ứng dụng {app}"
    key = f"snapshots/{app}/{entry.view}/{period}.parquet"
    written = []
    try:
        async with job.transaction() as connection:
            columns = await job.columns(relation)
            lower, upper = month_bounds(period)
            window = Window(time_column(columns, entry.column), upper, lower)
            keys = await job.keys(relation, entry.column)
            condition, args = window.where()
            rows = await connection.fetchval(
                f"SELECT count(*) FROM {relation} WHERE {condition}", *args
            )
            results = await job.check(relation, window, entry.rules, keys)
            check_id, passed = await job.recorded_check(
                "snapshot", app, source, period, window, rows, results
            )
            if not passed:
                text = (
                    f"Chưa chốt số liệu của {where} vì dữ liệu không đạt luật chất lượng. "
                    f"{describe(results)}"
                )
                await job.alert(app, "snapshot", source, period, text, results)
                job.fail(text)
                return False
            path, count = await job.export(relation, columns, window, keys, f"chot-{check_id}")
            if count != rows:
                raise LakeError(f"File có {count} dòng, khác {rows} dòng của tháng")
            written.append(key)
            size, digest = await asyncio.to_thread(job.publish, key, path)
            await connection.execute(
                WRITTEN,
                "snapshot",
                job.started_by,
                app,
                source,
                period,
                lower,
                upper,
                count,
                check_id,
                key,
                size,
                digest,
            )
    except (*DATABASE_ERRORS, StorageError, duckdb.Error, LakeError) as error:
        await asyncio.to_thread(job.forget, written)
        job.fail(f"Không chốt được số liệu của {where}: {error}.")
        return False
    job.report(f"Đã chốt số liệu của {where}: {count} dòng.")
    return True


async def archive_table(
    job: Job, app: str, schema: str, entry: ArchiveTable, hold: str | None
) -> None:
    relation = f"{ident(schema)}.{ident(entry.table)}"
    source = f"{schema}.{entry.table}"
    where = f"bảng {entry.table} trong ứng dụng {app}"
    written = []
    try:
        async with job.transaction() as connection:
            columns = await job.columns(relation)
            cutoff = await connection.fetchval(CUTOFF, entry.keep_days, hold)
            window = Window(time_column(columns, entry.column), cutoff)
            condition, args = window.where()
            rows = await connection.fetchval(
                f"SELECT count(*) FROM {relation} WHERE {condition}", *args
            )
            if not rows:
                return
            keys = await job.keys(relation, entry.column)
            results = await job.check(relation, window, entry.rules, keys)
            check_id, passed = await job.recorded_check(
                "archive", app, source, None, window, rows, results
            )
            if not passed:
                text = (
                    f"Chưa chuyển dòng cũ của {where} xuống hồ dữ liệu vì dữ liệu không đạt "
                    f"luật chất lượng. {describe(results)}"
                )
                await job.alert(app, "archive", source, None, text, results)
                job.fail(text)
                return
            months = [
                row[0]
                for row in await connection.fetch(
                    f"SELECT DISTINCT pg_catalog.to_char({ident(entry.column)}::timestamp, "
                    f"'YYYY-MM') FROM {relation} WHERE {condition} ORDER BY 1",
                    *args,
                )
            ]
            files = []
            for period in months:
                lower, upper = month_bounds(period)
                part = Window(window.column, min(upper, cutoff), lower)
                condition_of_part, args_of_part = part.where()
                expected = await connection.fetchval(
                    f"SELECT count(*) FROM {relation} WHERE {condition_of_part}", *args_of_part
                )
                path, count = await job.export(
                    relation, columns, part, keys, f"luu-{check_id}-{period}"
                )
                if count != expected:
                    raise LakeError(
                        f"File của tháng {period} có {count} dòng, khác {expected} dòng"
                    )
                year, month = period.split("-")
                key = f"archive/{app}/{entry.table}/{year}/{month}/{check_id}.parquet"
                written.append(key)
                size, digest = await asyncio.to_thread(job.publish, key, path)
                files.append((period, part, count, key, size, digest))
            status = await connection.execute(f"DELETE FROM {relation} WHERE {condition}", *args)
            deleted = int(status.split()[-1])
            total = sum(file[2] for file in files)
            if deleted != rows or total != rows:
                raise LakeError(
                    f"Đã ghi {total} dòng vào hồ nhưng xóa {deleted} trong {rows} dòng của bảng"
                )
            for period, part, count, key, size, digest in files:
                await connection.execute(
                    WRITTEN,
                    "archive",
                    job.started_by,
                    app,
                    source,
                    period,
                    part.lower,
                    part.upper,
                    count,
                    check_id,
                    key,
                    size,
                    digest,
                )
    except (*DATABASE_ERRORS, StorageError, duckdb.Error, LakeError) as error:
        await asyncio.to_thread(job.forget, written)
        job.fail(f"Không chuyển được dòng cũ của {where} xuống hồ dữ liệu: {error}.")
        return
    job.report(f"Đã chuyển {rows} dòng cũ của {where} xuống hồ dữ liệu, gồm {len(files)} file.")


async def run_app(job: Job, app: str, schema: str, manifest: Manifest) -> None:
    hold = None
    if manifest.snapshots:
        for entry in manifest.snapshots:
            try:
                months = await pending_months(job, app, schema, entry)
            except (*DATABASE_ERRORS, LakeError) as error:
                where = f"{entry.view} trong ứng dụng {app}"
                job.fail(f"Không đọc được các tháng cần chốt của {where}: {error}.")
                months = []
            for period in months:
                await snapshot_month(job, app, schema, entry, period)
        waiting = []
        for entry in manifest.snapshots:
            try:
                waiting += await pending_months(job, app, schema, entry)
            except (*DATABASE_ERRORS, LakeError):
                waiting.append("0001-01")
        async with job.transaction() as connection:
            current = await connection.fetchval(CURRENT_MONTH)
        hold = month_bounds(min([*waiting, current]))[0]
    for entry in manifest.archive:
        await archive_table(job, app, schema, entry, hold)


async def run(job: Job) -> bool:
    if not await job.connection.fetchval(TRY_LOCK):
        job.say("Đang chờ một lượt khác của hồ dữ liệu chạy xong.")
        await job.connection.execute(LOCK)
    for row in await job.connection.fetch(APPS):
        try:
            manifest = Manifest.model_validate(json.loads(row["manifest"] or "{}"))
        except (ValueError, ValidationError):
            job.fail(
                f"Bản khai báo đã lưu của ứng dụng {row['name']} không hợp lệ nên được bỏ qua."
            )
            continue
        await run_app(job, row["name"], row["schema_name"], manifest)
    if job.ok and not job.done:
        job.say(SAY_NOTHING)
    return job.ok


async def lake_files(connection: asyncpg.Connection, timezone: str) -> list[asyncpg.Record]:
    async with connection.transaction(isolation="repeatable_read"):
        await connection.execute(PREPARE, timezone)
        await connection.execute(BECOME_LAKE)
        return await connection.fetch(FILES)


async def verify(connection: asyncpg.Connection, settings: Settings, say: Say) -> bool:
    storage = Storage(settings.storage_url, settings.access_key, settings.secret_key)
    files = await lake_files(connection, settings.timezone)
    if not files:
        say("Hồ dữ liệu chưa có file nào.")
        return True
    broken = 0
    for row in files:
        try:
            digest = await asyncio.to_thread(storage.get, BUCKET, row["file"], Discard())
        except StorageError as error:
            say(f"Không đọc được file {row['file']}: {error}.")
            broken += 1
            continue
        if digest != row["sha256"]:
            say(f"File {row['file']} không khớp mã băm trong phả hệ. Nội dung file đã bị sửa.")
            broken += 1
    if broken:
        say(f"Có {broken} trong {len(files)} file của hồ dữ liệu bị lỗi.")
        return False
    say(f"Hồ dữ liệu có {len(files)} file. Mã băm của mọi file khớp với phả hệ.")
    return True


def views_of(files: list[tuple[str, str, str, Path]]) -> dict[tuple[str, str], list[Path]]:
    views: dict[tuple[str, str], list[Path]] = {}
    for job, _app, source, path in files:
        views.setdefault((job, source), []).append(path)
    return views


def open_lake(
    files: list[tuple[str, str, str, Path]],
    lineage: list[tuple[Any, ...]],
    timezone: str,
    work: Path,
) -> duckdb.DuckDBPyConnection:
    connection = duck(timezone, work)
    connection.execute("ATTACH ':memory:' AS snapshots")
    for (job, source), paths in sorted(views_of(files).items()):
        schema, name = source.split(".")
        catalog = "snapshots." if job == "snapshot" else ""
        listed = ", ".join(literal(str(path)) for path in paths)
        connection.execute(f"CREATE SCHEMA IF NOT EXISTS {catalog}{ident(schema)}")
        connection.execute(
            f"CREATE VIEW {catalog}{ident(schema)}.{ident(name)} AS "
            f"SELECT * FROM read_parquet([{listed}], union_by_name = true)"
        )
    connection.execute(LINEAGE_TABLE)
    if lineage:
        connection.executemany(
            "INSERT INTO lineage VALUES (" + ", ".join("?" * len(lineage[0])) + ")", lineage
        )
    connection.execute(f"SET allowed_directories = [{literal(str(work) + '/')}]")
    connection.execute("SET enable_external_access = false")
    connection.execute("SET lock_configuration = true")
    return connection


def print_table(relation: duckdb.DuckDBPyRelation, as_csv: bool) -> None:
    if as_csv:
        writer = csv.writer(sys.stdout, lineterminator="\n")
        writer.writerow(relation.columns)
        writer.writerows(relation.fetchall())
        return
    relation.show(max_width=10_000, max_rows=10_000, max_col_width=10_000)


async def query(
    connection: asyncpg.Connection, settings: Settings, text: str, as_csv: bool, say: Say
) -> bool:
    storage = Storage(settings.storage_url, settings.access_key, settings.secret_key)
    async with connection.transaction(isolation="repeatable_read"):
        await connection.execute(PREPARE, settings.timezone)
        await connection.execute(BECOME_LAKE)
        files = await connection.fetch(FILES)
        lineage = [tuple(row) for row in await connection.fetch(LINEAGE)]
    work = Path(tempfile.mkdtemp(prefix="saigonos-lake-"))
    try:
        local = []
        for row in files:
            path = work / f"{row['id']}.parquet"
            with path.open("wb") as sink:
                digest = await asyncio.to_thread(storage.get, BUCKET, row["file"], sink)
            if digest != row["sha256"]:
                say(
                    f"File {row['file']} không khớp mã băm trong phả hệ nên không được đọc. "
                    "Hãy chạy saigonos lake verify để kiểm tra hồ dữ liệu."
                )
                return False
            local.append((row["job"], row["app"], row["source"], path))
        lake = open_lake(local, lineage, settings.timezone, work)
        try:
            relation = lake.sql(text)
            if relation is None:
                say("Câu lệnh đã chạy xong.")
            else:
                print_table(relation, as_csv)
        except duckdb.Error as error:
            say(f"Câu truy vấn bị lỗi: {error}")
            return False
        finally:
            lake.close()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return True


def parser() -> argparse.ArgumentParser:
    commands = argparse.ArgumentParser(
        prog="docker compose exec core python -m saigonos_core.lake",
        description="Làm việc với hồ dữ liệu của SaigonOS.",
    )
    actions = commands.add_subparsers(dest="command", required=True, metavar="LỆNH")
    run_command = actions.add_parser(
        "run",
        help="Chốt số liệu các tháng đã hết rồi chuyển dòng cũ xuống hồ.",
        description=(
            "Chạy ngay việc của hẹn giờ: chốt số liệu các tháng đã hết của các mục snapshots, "
            "rồi chuyển dòng cũ hơn hạn của các bảng trong mục archive xuống hồ dữ liệu."
        ),
    )
    run_command.add_argument("--timer", action="store_true", help=argparse.SUPPRESS)
    query_command = actions.add_parser(
        "query",
        help="Chạy câu truy vấn SQL của DuckDB trên hồ dữ liệu.",
        description="Chạy câu truy vấn SQL của DuckDB trên các file Parquet của hồ dữ liệu.",
    )
    query_command.add_argument("--csv", action="store_true", help="In kết quả dạng CSV.")
    query_command.add_argument("sql", metavar="SQL", help="Câu truy vấn SQL.")
    actions.add_parser(
        "verify",
        help="Tính lại mã băm của mọi file trong hồ và so với phả hệ.",
        description="Tính lại mã băm của mọi file trong hồ dữ liệu và so với bảng core.lineage.",
    )
    return commands


def echo(text: str) -> None:
    print(text, flush=True)


async def main_async(arguments: argparse.Namespace, settings: Settings) -> bool:
    try:
        connection = await asyncpg.connect(
            timeout=CONNECT_TIMEOUT,
            statement_cache_size=0,
            server_settings={"application_name": "saigonos-lake"},
        )
    except DATABASE_ERRORS as error:
        echo(f"Không kết nối được PostgreSQL: {error}.")
        return False
    try:
        try:
            await connection.execute(ZONE, settings.timezone)
        except asyncpg.PostgresError:
            echo(f"Múi giờ {settings.timezone} của hồ dữ liệu không hợp lệ.")
            return False
        return await command_of(arguments, connection, settings)
    except DATABASE_ERRORS as error:
        echo(f"Mất kết nối PostgreSQL: {error}.")
        return False
    finally:
        await connection.close()


async def command_of(
    arguments: argparse.Namespace, connection: asyncpg.Connection, settings: Settings
) -> bool:
    if arguments.command == "verify":
        return await verify(connection, settings, echo)
    if arguments.command == "query":
        return await query(connection, settings, arguments.sql, arguments.csv, echo)
    work = Path(tempfile.mkdtemp(prefix="saigonos-lake-"))
    try:
        storage = Storage(settings.storage_url, settings.access_key, settings.secret_key)
        started_by = "timer" if arguments.timer else "command"
        return await run(Job(connection, storage, settings.timezone, started_by, echo, work))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        settings = Settings.from_environment()
    except (KeyError, LakeError) as error:
        echo(f"Service core thiếu cấu hình của hồ dữ liệu: {error}.")
        return 2
    return 0 if asyncio.run(main_async(arguments, settings)) else 1


if __name__ == "__main__":
    sys.exit(main())
