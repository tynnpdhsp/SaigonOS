# SPDX-License-Identifier: Apache-2.0
import asyncio
import hashlib
import io
from datetime import UTC, datetime
from decimal import Decimal
from typing import ClassVar

import duckdb
import pytest

from saigonos_core import lake
from saigonos_core.lake import (
    FILES,
    LINEAGE,
    Column,
    LakeError,
    Plan,
    Settings,
    Window,
    alert_key,
    decimal_type,
    describe,
    ident,
    literal,
    month_bounds,
    open_lake,
    plan_of,
    rule_checks,
    shorten,
    shown_month,
    to_parquet,
)
from saigonos_core.manifest import NotNullRule, RangeRule, UniqueRule
from saigonos_core.storage import StorageError

ZONE = "Asia/Ho_Chi_Minh"
CREATED = Column("tao_luc", "timestamptz", "D", "timestamp with time zone")
PG_CSV = (
    '1,t,12.50,2026-10-05 08:00:00+07,2026-10-05,"Nguyễn ""A""\nxuống dòng","",,'
    '\\x0102ff,"{""a"": 1}",1 day 02:03:04,NaN,8b6a9d6e-1f0c-4f2e-9c49-2f8f3c0b7a11,"[1, 2]"\n'
    "2,f,-0.0001,2026-10-31 23:59:59.123456+07,2026-10-31,b,,,\\x,null,-3 mons,Infinity,,\n"
)
COLUMNS = [
    Column("id", "int8", "N", "bigint"),
    Column("ok", "bool", "B", "boolean"),
    Column("tien", "numeric", "N", "numeric(12,4)"),
    CREATED,
    Column("ngay", "date", "D", "date"),
    Column("ghi", "text", "S", "text"),
    Column("rong", "varchar", "S", "character varying(20)"),
    Column("khong_co", "text", "S", "text"),
    Column("anh", "bytea", "U", "bytea"),
    Column("du_lieu", "jsonb", "U", "jsonb"),
    Column("thoi_luong", "interval", "T", "interval"),
    Column("so_thuc", "float8", "N", "double precision"),
    Column("ma", "uuid", "U", "uuid"),
    Column("danh_sach", "_int4", "A", "integer[]"),
]


def test_names_are_quoted_and_checked():
    assert ident("yeu_cau") == '"yeu_cau"'
    assert literal("it's") == "'it''s'"
    with pytest.raises(LakeError, match="không hợp lệ"):
        ident('x"; DROP TABLE y; --')


@pytest.mark.parametrize(
    ("period", "bounds", "shown"),
    [
        ("2026-10", ("2026-10-01 00:00:00", "2026-11-01 00:00:00"), "10/2026"),
        ("2026-12", ("2026-12-01 00:00:00", "2027-01-01 00:00:00"), "12/2026"),
        ("2027-02", ("2027-02-01 00:00:00", "2027-03-01 00:00:00"), "02/2027"),
    ],
    ids=["giua-nam", "cuoi-nam", "thang-hai"],
)
def test_month_bounds_cover_whole_month(period, bounds, shown):
    assert month_bounds(period) == bounds
    assert shown_month(period) == shown


@pytest.mark.parametrize(
    ("declared", "size", "expected"),
    [
        ("numeric(12,2)", None, "DECIMAL(12,2)"),
        ("numeric(10,0)", None, "DECIMAL(10,0)"),
        ("numeric(40,2)", None, "VARCHAR"),
        ("numeric", (3, 2), "DECIMAL(5,2)"),
        ("numeric", (36, 3), "VARCHAR"),
        ("numeric", None, "VARCHAR"),
    ],
    ids=["co-khai", "so-nguyen", "qua-rong", "theo-du-lieu", "du-lieu-qua-rong", "co-nan"],
)
def test_numeric_keeps_every_digit(declared, size, expected):
    assert decimal_type(declared, size) == expected


def test_each_postgresql_type_has_a_plan():
    plans = {column.name: plan_of(column) for column in COLUMNS}

    assert plans["id"] == Plan("id", '"id"', "BIGINT", '"id"')
    assert plans["tien"].read == "DECIMAL(12,4)"
    assert plans["tao_luc"].read == "TIMESTAMPTZ"
    assert plans["anh"] == Plan("anh", '"anh"', "VARCHAR", 'unhex(substr("anh", 3)) AS "anh"')
    assert plans["du_lieu"].read == "JSON"
    assert plans["thoi_luong"] == Plan(
        "thoi_luong", '"thoi_luong"::text', "VARCHAR", '"thoi_luong"'
    )
    assert plans["danh_sach"] == Plan(
        "danh_sach", 'pg_catalog.to_jsonb("danh_sach")', "JSON", '"danh_sach"'
    )


def test_csv_of_postgresql_becomes_parquet_with_same_values(tmp_path):
    source, target = tmp_path / "vao.csv", tmp_path / "ra.parquet"
    source.write_text(PG_CSV, encoding="utf-8")
    plans = [plan_of(column) for column in COLUMNS]
    plans[11] = Plan("so_thuc", '"so_thuc"', "DOUBLE", '"so_thuc"')

    count = to_parquet(source, target, plans, ZONE, tmp_path)

    rows = duckdb.execute("SELECT * FROM read_parquet(?) ORDER BY id", [str(target)]).fetchall()
    assert count == 2
    assert rows[0][:8] == (
        1,
        True,
        Decimal("12.5000"),
        datetime(2026, 10, 5, 1, 0, tzinfo=UTC),
        datetime(2026, 10, 5).date(),
        'Nguyễn "A"\nxuống dòng',
        "",
        None,
    )
    assert rows[0][8] == b"\x01\x02\xff"
    assert rows[0][9:11] == ('{"a": 1}', "1 day 02:03:04")
    assert rows[1][2] == Decimal("-0.0001")
    assert rows[1][8:11] == (b"", "null", "-3 mons")


def test_empty_month_becomes_parquet_without_rows(tmp_path):
    source, target = tmp_path / "vao.csv", tmp_path / "ra.parquet"
    source.write_text("", encoding="utf-8")

    count = to_parquet(source, target, [plan_of(CREATED)], ZONE, tmp_path)

    assert count == 0
    described = duckdb.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(target)])
    assert described.fetchall()[0][:2] == ("tao_luc", "TIMESTAMP WITH TIME ZONE")


def test_window_casts_bounds_to_type_of_time_column():
    day = Column("ngay", "date", "D", "date")

    assert Window(day, "2026-10-25 08:00:00").where() == (
        '"ngay" < $1::text::timestamp::date',
        ["2026-10-25 08:00:00"],
    )
    assert Window(CREATED, "2026-11-01 00:00:00", "2026-10-01 00:00:00").where() == (
        '"tao_luc" >= $2::text::timestamp::timestamptz AND '
        '"tao_luc" < $1::text::timestamp::timestamptz',
        ["2026-11-01 00:00:00", "2026-10-01 00:00:00"],
    )


def test_rules_become_queries_with_bounds_as_parameters():
    where, args = "w", ["a"]

    not_null = rule_checks(NotNullRule(rule="not_null", columns=["ma", "tieu_de"]), where, args)
    unique = rule_checks(UniqueRule(rule="unique", columns=["ma", "loai"]), where, args)
    ranged = rule_checks(RangeRule(rule="range", column="diem", min=1, max=5), where, args)
    lower = rule_checks(RangeRule(rule="range", column="diem", min=0.5), where, args)

    assert not_null == [
        ({"rule": "not_null", "column": "ma"}, 'w AND "ma" IS NULL', ["a"]),
        ({"rule": "not_null", "column": "tieu_de"}, 'w AND "tieu_de" IS NULL', ["a"]),
    ]
    assert unique == [
        (
            {"rule": "unique", "columns": ["ma", "loai"]},
            'w AND "ma" IS NOT NULL AND "loai" IS NOT NULL',
            ["a"],
        )
    ]
    assert ranged == [
        (
            {"rule": "range", "column": "diem", "min": 1.0, "max": 5.0},
            'w AND ("diem" < $2::text::numeric OR "diem" > $3::text::numeric)',
            ["a", "1.0", "5.0"],
        )
    ]
    assert lower[0][1:] == ('w AND ("diem" < $2::text::numeric)', ["a", "0.5"])


RESULTS = [
    {"rule": "not_null", "column": "ma", "rows": 0, "examples": []},
    {
        "rule": "not_null",
        "column": "tieu_de",
        "rows": 2,
        "examples": [{"id": 7, "tieu_de": None}, {"id": 9, "tieu_de": None}],
    },
    {
        "rule": "unique",
        "columns": ["ma"],
        "rows": 2,
        "examples": [{"values": {"ma": "YC-1"}, "rows": 2}],
    },
    {
        "rule": "range",
        "column": "diem",
        "min": 1.0,
        "max": None,
        "rows": 1,
        "examples": [{"id": 3, "diem": 0}],
    },
]


def test_failed_rules_are_described_with_rows_and_rules():
    assert describe(RESULTS) == (
        'Luật not_null của cột tieu_de không đạt ở 2 dòng, ví dụ {"id": 7, "tieu_de": null}, '
        '{"id": 9, "tieu_de": null}. Luật unique của cột ma không đạt ở 2 dòng, ví dụ '
        '{"ma": "YC-1"} có 2 dòng. Luật range của cột diem (từ 1 trở lên) không đạt ở 1 dòng, '
        'ví dụ {"id": 3, "diem": 0}.'
    )
    assert "tối đa 5" in describe([RESULTS[3] | {"min": None, "max": 5.0}])
    assert "từ 0.5 đến 30" in describe([RESULTS[3] | {"min": 0.5, "max": 30.0}])


def test_alert_key_changes_only_with_problems():
    first = alert_key("thu", "archive", "thu.don", None, RESULTS[1:])
    again = alert_key("thu", "archive", "thu.don", None, list(RESULTS[1:]))
    other = alert_key("thu", "archive", "thu.don", None, RESULTS[2:])

    assert first == again != other
    assert first.startswith("lake:thu:archive:thu.don::")
    assert len(first) < 255


def test_long_message_is_shortened_for_alert():
    assert shorten("a" * 5) == "aaaaa"
    assert shorten("a" * 2100) == "a" * 1999 + "…"


def test_settings_come_from_environment(monkeypatch):
    monkeypatch.setenv("S3_URL", "http://seaweedfs:8333")
    monkeypatch.setenv("S3_ACCESS_KEY", "khoa")
    monkeypatch.setenv("S3_SECRET_KEY", "bi-mat")
    monkeypatch.delenv("LAKE_TIMEZONE", raising=False)

    assert Settings.from_environment() == Settings("http://seaweedfs:8333", "khoa", "bi-mat", ZONE)
    monkeypatch.setenv("LAKE_TIMEZONE", "UTC")
    assert Settings.from_environment().timezone == "UTC"
    monkeypatch.setenv("LAKE_TIMEZONE", "Asia/Ho Chi Minh'")
    with pytest.raises(LakeError, match="không hợp lệ"):
        Settings.from_environment()


def test_command_without_settings_stops_with_message(monkeypatch, capsys):
    monkeypatch.delenv("S3_URL", raising=False)

    assert lake.main(["verify"]) == 2
    assert capsys.readouterr().out == "Service core thiếu cấu hình của hồ dữ liệu: 'S3_URL'.\n"


def parquet_of(tmp_path, name, query):
    path = tmp_path / f"{name}.parquet"
    duckdb.sql(f"COPY ({query}) TO '{path}' (FORMAT parquet)")
    return path.read_bytes()


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *details):
        return False


class FakeConnection:
    def __init__(self, files, lineage=()):
        self.answers = {FILES: files, LINEAGE: list(lineage)}
        self.executed = []

    def transaction(self, isolation=None):
        self.executed.append(isolation)
        return FakeTransaction()

    async def execute(self, query, *args):
        self.executed.append(query)

    async def fetch(self, query, *args):
        return self.answers[query]


class FakeStorage:
    objects: ClassVar[dict] = {}

    def __init__(self, *settings):
        pass

    def get(self, bucket, key, sink):
        if (bucket, key) not in self.objects:
            raise StorageError("Kho file trả về mã 404")
        content = self.objects[bucket, key]
        sink.write(content)
        return hashlib.sha256(content).hexdigest()


SETTINGS = Settings("http://seaweedfs:8333", "khoa", "bi-mat", ZONE)


@pytest.fixture
def stored(tmp_path, monkeypatch):
    monkeypatch.setattr(lake, "Storage", FakeStorage)
    archived = parquet_of(
        tmp_path,
        "luu",
        "SELECT * FROM (VALUES (1, 'YC-1', 3.5), (2, 'YC-2', 4.0)) AS t(id, ma, diem)",
    )
    frozen = parquet_of(tmp_path, "chot", "SELECT 'YC-1' AS ma, DATE '2026-10-05' AS ngay")
    FakeStorage.objects = {
        ("lake", "archive/thu/don/2026/10/7.parquet"): archived,
        ("lake", "snapshots/thu/chot_don/2026-10.parquet"): frozen,
    }
    return [
        {
            "id": 8,
            "app": "thu",
            "job": "archive",
            "source": "thu.don",
            "file": "archive/thu/don/2026/10/7.parquet",
            "sha256": hashlib.sha256(archived).hexdigest(),
        },
        {
            "id": 10,
            "app": "thu",
            "job": "snapshot",
            "source": "thu.chot_don",
            "file": "snapshots/thu/chot_don/2026-10.parquet",
            "sha256": hashlib.sha256(frozen).hexdigest(),
        },
    ]


def verified(files):
    said = []
    result = asyncio.run(lake.verify(FakeConnection(files), SETTINGS, said.append))
    return result, said


def test_verify_passes_when_every_hash_matches(stored):
    assert verified(stored) == (
        True,
        ["Hồ dữ liệu có 2 file. Mã băm của mọi file khớp với phả hệ."],
    )


def test_verify_names_changed_and_missing_files(stored):
    key = stored[0]["file"]
    FakeStorage.objects["lake", key] = FakeStorage.objects["lake", key][:-1] + b"\0"
    del FakeStorage.objects["lake", stored[1]["file"]]

    assert verified(stored) == (
        False,
        [
            f"File {key} không khớp mã băm trong phả hệ. Nội dung file đã bị sửa.",
            f"Không đọc được file {stored[1]['file']}: Kho file trả về mã 404.",
            "Có 2 trong 2 file của hồ dữ liệu bị lỗi.",
        ],
    )


def test_verify_of_empty_lake_says_so():
    assert verified([]) == (True, ["Hồ dữ liệu chưa có file nào."])


LINEAGE_ROW = (
    8,
    datetime(2026, 11, 24, 1, 0, tzinfo=UTC),
    "file",
    "archive",
    "command",
    "thu",
    "thu.don",
    "2026-10",
    datetime(2026, 9, 30, 17, 0, tzinfo=UTC),
    datetime(2026, 10, 24, 17, 0, tzinfo=UTC),
    2,
    None,
    None,
    7,
    "archive/thu/don/2026/10/7.parquet",
    600,
    "a" * 64,
)


def queried(files, text, as_csv=True, lineage=(LINEAGE_ROW,)):
    said = []
    connection = FakeConnection(files, lineage)
    result = asyncio.run(lake.query(connection, SETTINGS, text, as_csv, said.append))
    return result, said


def test_query_reads_archived_tables_snapshots_and_lineage(stored, capsys):
    text = (
        "SELECT (SELECT sum(diem) FROM thu.don) AS tong, "
        "(SELECT count(*) FROM snapshots.thu.chot_don) AS chot, "
        "(SELECT source FROM lineage) AS nguon"
    )

    assert queried(stored, text) == (True, [])
    assert capsys.readouterr().out == "tong,chot,nguon\n7.5,1,thu.don\n"


def test_query_prints_table_by_default(stored, capsys):
    assert queried(stored, "SELECT ma FROM thu.don ORDER BY id", as_csv=False) == (True, [])
    output = capsys.readouterr().out
    assert "YC-1" in output and "YC-2" in output


@pytest.mark.parametrize(
    "text",
    [
        "SELECT * FROM read_csv('/etc/passwd')",
        "ATTACH '/tmp/khac.duckdb'",
        "SET enable_external_access = true",
        "INSTALL httpfs",
    ],
    ids=["doc-file", "attach", "mo-khoa", "cai-extension"],
)
def test_query_cannot_reach_files_or_network_of_server(stored, text):
    result, said = queried(stored, text)

    assert result is False
    assert said[0].startswith("Câu truy vấn bị lỗi: ")


def test_query_refuses_lake_with_changed_file(stored):
    key = stored[1]["file"]
    FakeStorage.objects["lake", key] = b"sai"

    assert queried(stored, "SELECT 1") == (
        False,
        [
            f"File {key} không khớp mã băm trong phả hệ nên không được đọc. "
            "Hãy chạy saigonos lake verify để kiểm tra hồ dữ liệu."
        ],
    )


def test_query_without_statement_is_reported(stored):
    assert queried(stored, "-- chỉ có chú thích") == (
        True,
        ["Câu lệnh đã chạy xong."],
    )


def test_lake_opens_without_files(tmp_path):
    connection = open_lake([], [], ZONE, tmp_path)
    try:
        assert connection.sql("SELECT count(*) FROM lineage").fetchall() == [(0,)]
    finally:
        connection.close()


def test_parser_hides_timer_flag():
    help_text = io.StringIO()
    lake.parser().print_help(help_text)

    assert lake.parser().parse_args(["run", "--timer"]).timer is True
    assert lake.parser().parse_args(["query", "--csv", "--", "-- ghi chú"]).sql == "-- ghi chú"
    assert "--timer" not in help_text.getvalue()
