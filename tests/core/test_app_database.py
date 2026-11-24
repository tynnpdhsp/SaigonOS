# SPDX-License-Identifier: Apache-2.0
import asyncio
import hashlib
import json
import re

import asyncpg
import pytest

from saigonos_core import app_database
from saigonos_core.app_database import (
    APPLIED,
    CLOSE_LOGIN,
    FINISH,
    INSTALLED,
    KNOWN,
    LOCK,
    OPEN_LOGIN,
    PREPARE,
    PURGE,
    RECORD,
    REMOVE,
    RUN,
    SEARCH,
    SECURE,
    WAS_REMOVED,
    ApplyError,
    apply_database,
    installed_apps,
    known_app,
    remove_database,
)
from saigonos_core.manifest import MANIFEST, Manifest

FIRST = "CREATE TABLE notes (id bigint);\n"
SECOND = "CREATE TABLE tags (id bigint);\nSELEC 1;\n"
DATA = {
    "$schema": "https://example.com/saigonos-app.schema.json",
    "name": "ghi-chu",
    "title": "Ghi chú",
    "version": "0.2.0",
    "roles": [{"name": "ghi-chu.nguoi-dung", "description": "Ghi chú của mình"}],
    "database": "database/",
}


def checksum(text):
    return hashlib.sha256(text.encode()).hexdigest()


def postgres_error(code, message, **fields):
    return asyncpg.PostgresError.new({"C": code, "M": message, **fields})


class FakeTransaction:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        self.connection.log("begin")

    async def __aexit__(self, error, *details):
        self.connection.log("rollback" if error else "commit")


class FakeConnection:
    def __init__(self, server, options):
        self.server = server
        self.who = options["user"] or "postgres"
        self.options = options

    def log(self, *event):
        self.server.events.append((self.who, *event))

    async def answer(self, query, arguments):
        self.log(query, *arguments)
        failure = self.server.failures.get((query, *arguments[:1]))
        if failure:
            raise failure
        return self.server.answers.get(query)

    async def execute(self, query, *arguments):
        await self.answer(query, arguments)

    async def fetchval(self, query, *arguments):
        return await self.answer(query, arguments)

    async def fetch(self, query, *arguments):
        return await self.answer(query, arguments)

    def transaction(self):
        return FakeTransaction(self)

    async def close(self):
        self.log("close")


class FakeServer:
    def __init__(self):
        self.events = []
        self.connections = []
        self.failures = {}
        self.refusal = None
        self.answers = {PREPARE: True, APPLIED: [], FINISH: True}

    async def connect(self, **options):
        if self.refusal:
            raise self.refusal
        self.connections.append(options)
        return FakeConnection(self, options)

    def queries(self, who):
        return [event[1] for event in self.events if event[0] == who]


@pytest.fixture
def server(monkeypatch):
    fake = FakeServer()
    monkeypatch.setattr(asyncpg, "connect", fake.connect)
    return fake


@pytest.fixture
def folder(tmp_path):
    app = tmp_path / "ghi-chu"
    (app / "database" / "con").mkdir(parents=True)
    (app / "database" / "0002_tags.sql").write_text(SECOND, encoding="utf-8")
    (app / "database" / "0001_notes.sql").write_text(FIRST, encoding="utf-8")
    (app / "database" / "README.md").write_text("Không phải file SQL\n", encoding="utf-8")
    (app / "database" / "con" / "0003_bo_qua.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (app / MANIFEST).write_text(json.dumps(DATA), encoding="utf-8")
    return app


def apply(folder, data=DATA):
    said = []
    result = asyncio.run(apply_database(Manifest.model_validate(data), folder, said.append))
    return result, said


def failure_of(folder, data=DATA):
    with pytest.raises(ApplyError) as raised:
        apply(folder, data)
    return str(raised.value)


def test_new_files_run_in_name_order_with_role_of_app(server, folder):
    result, said = apply(folder)

    [admin, app] = server.connections
    password = next(event[3] for event in server.events if event[1] == OPEN_LOGIN)
    assert result is True
    assert said == [
        "Đã tạo schema ghi_chu, role ghi_chu và role ghi_chu_user của ứng dụng.",
        "Đã chạy file 0001_notes.sql.",
        "Đã chạy file 0002_tags.sql.",
    ]
    assert admin["user"] is None
    assert (app["user"], app["password"]) == ("ghi_chu", password)
    assert app["server_settings"] == {"application_name": "saigonos-apps", "search_path": "ghi_chu"}
    assert app["statement_cache_size"] == 0
    assert re.fullmatch(r"[A-Za-z0-9]{32}", password)
    assert server.events == [
        ("postgres", LOCK),
        ("postgres", WAS_REMOVED, "ghi-chu"),
        ("postgres", PREPARE, "ghi-chu"),
        ("postgres", APPLIED, "ghi-chu"),
        ("postgres", OPEN_LOGIN, "ghi-chu", password),
        ("ghi_chu", "begin"),
        ("ghi_chu", RUN, FIRST),
        ("ghi_chu", SECURE),
        ("ghi_chu", RECORD, "0001_notes.sql", checksum(FIRST)),
        ("ghi_chu", "commit"),
        ("ghi_chu", "begin"),
        ("ghi_chu", RUN, SECOND),
        ("ghi_chu", SECURE),
        ("ghi_chu", RECORD, "0002_tags.sql", checksum(SECOND)),
        ("ghi_chu", "commit"),
        ("ghi_chu", "close"),
        ("postgres", CLOSE_LOGIN, "ghi-chu"),
        ("postgres", SEARCH, "ghi-chu", "[]"),
        ("postgres", FINISH, "ghi-chu", "Ghi chú", "0.2.0", json.dumps(DATA), True),
        ("postgres", "close"),
    ]


def test_password_is_new_each_time(server, folder):
    apply(folder)
    server.answers[APPLIED] = [("0001_notes.sql", checksum(FIRST))]
    apply(folder)

    passwords = [event[3] for event in server.events if event[1] == OPEN_LOGIN]
    assert len(set(passwords)) == 2


def test_files_already_run_are_skipped(server, folder):
    server.answers[APPLIED] = [("0001_notes.sql", checksum(FIRST)), ("0000_cu.sql", "khac")]

    apply(folder)

    assert ("ghi_chu", RUN, FIRST) not in server.events
    assert ("ghi_chu", RUN, SECOND) in server.events


def test_app_without_new_file_never_opens_login(server, folder):
    server.answers[APPLIED] = [
        ("0001_notes.sql", checksum(FIRST)),
        ("0002_tags.sql", checksum(SECOND)),
    ]
    server.answers[PREPARE] = False
    server.answers[FINISH] = False

    result, said = apply(folder)

    assert result is False
    assert said == []
    assert len(server.connections) == 1
    assert server.queries("postgres") == [
        LOCK,
        WAS_REMOVED,
        PREPARE,
        APPLIED,
        SEARCH,
        FINISH,
        "close",
    ]
    assert server.events[-2][-1] is False


def test_app_without_database_folder_runs_no_file(server, folder):
    data = {key: value for key, value in DATA.items() if key != "database"}

    _, said = apply(folder, data)

    assert said == ["Đã tạo schema ghi_chu, role ghi_chu và role ghi_chu_user của ứng dụng."]
    assert server.queries("postgres") == [
        LOCK,
        WAS_REMOVED,
        PREPARE,
        APPLIED,
        SEARCH,
        FINISH,
        "close",
    ]


def test_changed_file_stops_before_any_file_runs(server, folder):
    server.answers[APPLIED] = [("0001_notes.sql", checksum("CREATE TABLE cu (id int);"))]

    message = failure_of(folder)

    assert message == (
        "File 0001_notes.sql đã được chạy trước đó nhưng nội dung đã thay đổi. "
        "Mỗi thay đổi của cơ sở dữ liệu cần được viết thành một file SQL mới."
    )
    assert server.queries("postgres") == [LOCK, WAS_REMOVED, PREPARE, APPLIED, "close"]


def test_failing_file_rolls_back_closes_login_and_shows_line(server, folder):
    position = str(SECOND.index("SELEC") + 1)
    server.failures[RUN, SECOND] = postgres_error(
        "42601", 'syntax error at or near "SELEC"', p=position, q=SECOND
    )

    message = failure_of(folder)

    assert message == (
        'Không chạy được file 0002_tags.sql ở dòng 2: syntax error at or near "SELEC". '
        "Mọi thay đổi của file này đã được hủy."
    )
    assert server.queries("ghi_chu")[-4:] == ["begin", RUN, "rollback", "close"]
    assert server.queries("postgres")[-2:] == [CLOSE_LOGIN, "close"]
    assert FINISH not in server.queries("postgres")


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (
            postgres_error("0A000", "EXECUTE of transaction commands is not implemented"),
            "file SQL của ứng dụng không được dùng BEGIN, COMMIT, ROLLBACK hay SAVEPOINT.",
        ),
        (
            postgres_error("42501", "permission denied for table audit_log"),
            "permission denied for table audit_log.",
        ),
        (
            postgres_error("42P01", 'relation "nope" does not exist', p="3", q="SELECT 1"),
            'relation "nope" does not exist.',
        ),
        (
            postgres_error("P0001", "Không đủ quyền.", H="Hãy hỏi quản trị viên."),
            "Không đủ quyền. Hãy hỏi quản trị viên.",
        ),
    ],
    ids=["lenh-transaction", "khong-co-quyen", "vi-tri-cua-cau-lenh-khac", "co-goi-y"],
)
def test_failing_file_explains_reason(server, folder, error, reason):
    server.failures[RUN, FIRST] = error

    assert failure_of(folder) == (
        f"Không chạy được file 0001_notes.sql: {reason} Mọi thay đổi của file này đã được hủy."
    )


def test_file_granting_schema_to_other_role_is_rolled_back_before_it_is_recorded(server, folder):
    server.failures[SECURE,] = postgres_error(
        "42501",
        "Schema ghi_chu chỉ được cấp quyền USAGE cho role ghi_chu_user và role anon",
        H="Hãy bỏ lệnh cấp quyền USAGE trên schema ghi_chu cho role authenticated.",
    )

    message = failure_of(folder)

    assert message == (
        "Không chạy được file 0001_notes.sql: Schema ghi_chu chỉ được cấp quyền USAGE cho role "
        "ghi_chu_user và role anon. Hãy bỏ lệnh cấp quyền USAGE trên schema ghi_chu cho role "
        "authenticated. Mọi thay đổi của file này đã được hủy."
    )
    assert server.queries("ghi_chu") == ["begin", RUN, SECURE, "rollback", "close"]
    assert FINISH not in server.queries("postgres")


def test_error_of_core_function_is_reported_with_hint(server, folder):
    server.failures[PREPARE, "ghi-chu"] = postgres_error(
        "42710",
        "Role hoặc schema ghi_chu đã có trong cơ sở dữ liệu nhưng không do SaigonOS tạo "
        "cho ứng dụng ghi-chu",
        H="Hãy đặt tên khác cho ứng dụng.",
    )

    assert failure_of(folder) == (
        "Role hoặc schema ghi_chu đã có trong cơ sở dữ liệu nhưng không do SaigonOS tạo "
        "cho ứng dụng ghi-chu. Hãy đặt tên khác cho ứng dụng."
    )
    assert server.queries("postgres") == [LOCK, WAS_REMOVED, PREPARE, "close"]


def test_step_before_finish_runs_after_files_and_its_error_stops_apply(server, folder):
    seen = []

    def before_finish(removed):
        seen.append(([event[1] for event in server.events], removed))
        raise ApplyError("Keycloak trả về mã 500 cho lời gọi POST /clients.")

    with pytest.raises(ApplyError, match="mã 500"):
        asyncio.run(apply_database(Manifest.model_validate(DATA), folder, [].append, before_finish))

    assert seen[0][0][-2:] == [CLOSE_LOGIN, SEARCH]
    assert seen[0][1] is False
    assert FINISH not in server.queries("postgres")
    assert server.events[-1] == ("postgres", "close")


SEARCHED = DATA | {
    "search": [
        {"table": "notes", "columns": ["body"]},
        {"table": "tags", "columns": ["name", "note"]},
    ]
}


def test_search_tables_are_sent_after_files_and_reported(server, folder):
    server.answers[APPLIED] = [
        ("0001_notes.sql", checksum(FIRST)),
        ("0002_tags.sql", checksum(SECOND)),
    ]
    server.answers[PREPARE] = False
    server.answers[SEARCH] = ["Đã tạo tìm kiếm cho bảng notes.", "Đã tạo tìm kiếm cho bảng tags."]

    result, said = apply(folder, SEARCHED)

    assert result is True
    assert said == ["Đã tạo tìm kiếm cho bảng notes.", "Đã tạo tìm kiếm cho bảng tags."]
    assert ("postgres", SEARCH, "ghi-chu", json.dumps(SEARCHED["search"])) in server.events
    assert server.events[-2][-1] is True


def test_error_of_search_stops_apply_before_finish(server, folder):
    failure = postgres_error(
        "22023", "Mục search khai cột body của bảng notes, nhưng bảng không có cột này"
    )
    server.failures[(SEARCH, "ghi-chu")] = failure

    message = failure_of(folder, SEARCHED)

    assert message == "Mục search khai cột body của bảng notes, nhưng bảng không có cột này."
    assert FINISH not in server.queries("postgres")


def test_database_without_functions_of_this_version_asks_to_update(server, folder):
    server.failures[PREPARE, "ghi-chu"] = postgres_error(
        "42883", "function core.prepare_app(unknown) does not exist"
    )

    assert failure_of(folder) == (
        "Cơ sở dữ liệu chưa có các hàm để cài đặt ứng dụng. "
        "Hãy chạy lệnh saigonos up để cập nhật cơ sở dữ liệu rồi chạy lại."
    )


def test_unreachable_database_asks_to_start_system(server, folder):
    server.refusal = ConnectionRefusedError("Connect call failed")

    assert failure_of(folder) == (
        "Không kết nối được PostgreSQL: Connect call failed. "
        "Hãy khởi động hệ thống bằng lệnh saigonos up rồi chạy lại."
    )


def test_refused_login_is_reported(server, folder):
    server.refusal = postgres_error("28P01", 'password authentication failed for user "postgres"')

    assert failure_of(folder) == (
        'PostgreSQL từ chối kết nối: password authentication failed for user "postgres".'
    )


def test_sql_file_must_be_utf_8_and_is_checked_before_connecting(server, folder):
    (folder / "database" / "0003_latin.sql").write_bytes("-- Chú thích\n".encode("cp1258"))

    assert failure_of(folder) == "File 0003_latin.sql phải được lưu bằng bảng mã UTF-8."
    assert server.connections == []


def test_byte_order_mark_is_dropped_but_checksum_covers_whole_file(server, folder):
    content = b"\xef\xbb\xbf" + FIRST.encode()
    (folder / "database" / "0001_notes.sql").write_bytes(content)

    apply(folder)

    assert ("ghi_chu", RUN, FIRST) in server.events
    recorded = hashlib.sha256(content).hexdigest()
    assert ("ghi_chu", RECORD, "0001_notes.sql", recorded) in server.events


def test_password_uses_letters_and_digits_only(monkeypatch):
    monkeypatch.setattr(app_database, "PASSWORD_LENGTH", 200)

    assert set(app_database.new_password()) <= set(app_database.PASSWORD_ALPHABET)


def test_removed_app_is_reported_to_step_before_finish(server, folder):
    server.answers[WAS_REMOVED] = True
    seen = []

    asyncio.run(apply_database(Manifest.model_validate(DATA), folder, [].append, seen.append))

    assert seen == [True]


def test_installed_apps_are_listed_by_name(server):
    server.answers[INSTALLED] = [{"name": "don-tu"}, {"name": "nghi-phep"}]

    assert asyncio.run(installed_apps()) == ["don-tu", "nghi-phep"]
    assert server.queries("postgres") == [INSTALLED, "close"]


def test_known_app_asks_table_of_apps(server):
    server.answers[KNOWN] = True

    assert asyncio.run(known_app("nghi-phep")) is True
    assert ("postgres", KNOWN, "nghi-phep") in server.events


@pytest.mark.parametrize(
    ("purge", "query", "message"),
    [
        (False, REMOVE, "Đã bỏ schema ghi_chu khỏi API."),
        (True, PURGE, "Đã xóa schema ghi_chu, role ghi_chu và role ghi_chu_user của ứng dụng."),
    ],
    ids=["go", "xoa-han"],
)
def test_remove_database_holds_lock_and_reports_change(server, purge, query, message):
    server.answers[query] = True
    said = []

    changed = asyncio.run(remove_database("ghi-chu", purge, said.append))

    assert (changed, said) == (True, [message])
    assert server.queries("postgres") == [LOCK, query, "close"]


def test_remove_database_without_change_says_nothing(server):
    server.answers[REMOVE] = False
    said = []

    assert asyncio.run(remove_database("ghi-chu", False, said.append)) is False
    assert said == []


@pytest.mark.parametrize(
    "error",
    [
        postgres_error("42883", "function core.remove_app(unknown) does not exist"),
        postgres_error("42703", 'column "removed_at" does not exist'),
    ],
    ids=["thieu-ham", "thieu-cot"],
)
def test_database_of_older_version_asks_to_update(server, folder, error):
    server.failures[REMOVE, "ghi-chu"] = error

    with pytest.raises(ApplyError) as raised:
        asyncio.run(remove_database("ghi-chu", False, [].append))

    assert str(raised.value).startswith("Cơ sở dữ liệu chưa có các hàm để cài đặt ứng dụng.")
