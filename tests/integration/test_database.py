# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
import secrets
import time
from importlib.resources import files

import pytest

pytestmark = pytest.mark.integration

MIGRATIONS = files("saigonos") / "stack" / "config" / "postgres" / "migrations"


def unique(prefix):
    return f"{prefix}_{secrets.token_hex(4)}"


def test_migrate_records_each_shipped_file(stack):
    shipped = {
        entry.name: hashlib.sha256(entry.read_bytes()).hexdigest() for entry in MIGRATIONS.iterdir()
    }

    recorded = dict(stack.sql("SELECT name, checksum FROM core.migrations WHERE scope = 'core'"))

    assert shipped
    assert shipped.items() <= recorded.items()


def test_api_role_cannot_read_records_of_migrate(stack):
    query = "SELECT has_table_privilege('authenticated', 'core.migrations', 'SELECT')"

    assert stack.sql(query) == [["f"]]


def test_postgrest_starts_after_migrate_has_finished(stack):
    services = json.loads(stack.compose("config", "--format", "json"))["services"]

    condition = services["postgrest"]["depends_on"]["migrate"]["condition"]

    assert services["migrate"]["restart"] == "no"
    assert condition == "service_completed_successfully"


def test_new_files_run_once_in_name_order(stack):
    table = unique("migrate_order")
    stack.add_migration(f"9001_{table}_b.sql", f"INSERT INTO {table} VALUES ('b');")
    stack.add_migration(f"9001_{table}_a.sql", f"CREATE TABLE {table} (step text);")

    first = stack.saigonos("up")
    second = stack.saigonos("up")

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert stack.sql(f"SELECT step FROM {table}") == [["b"]]
    assert stack.logs("migrate").splitlines()[-1] == "Không có file SQL mới"


def test_changed_file_stops_migrate(stack):
    path = stack.add_migration(f"9002_{unique('migrate_changed')}.sql", "SELECT 1;")
    assert stack.saigonos("up").returncode == 0

    path.write_text("SELECT 2;", encoding="utf-8")
    try:
        changed = stack.saigonos("up")
        logs = stack.logs("migrate")
    finally:
        path.write_text("SELECT 1;", encoding="utf-8")

    assert changed.returncode != 0
    assert f"File {path.name} đã được chạy trước đó nhưng nội dung đã thay đổi." in logs
    assert stack.saigonos("up").returncode == 0


def test_failed_file_changes_nothing_and_stops_later_files(stack):
    table = unique("migrate_failed")
    failing = stack.add_migration(
        f"9003_{table}_a.sql", f"CREATE TABLE {table} (id int);\nSELECT 1 / 0;"
    )
    later = stack.add_migration(f"9003_{table}_b.sql", f"CREATE TABLE {table}_later (id int);")
    try:
        failed = stack.saigonos("up")
        logs = stack.logs("migrate")
    finally:
        failing.unlink()
        later.unlink()

    assert failed.returncode != 0
    assert "division by zero" in logs
    assert f"Không chạy được file {failing.name}. Mọi thay đổi của file này đã được hủy." in logs
    assert stack.sql(f"SELECT to_regclass('{table}'), to_regclass('{table}_later')") == [["", ""]]
    records = f"SELECT count(*) FROM core.migrations WHERE starts_with(name, '9003_{table}')"
    assert stack.sql(records) == [["0"]]
    assert stack.saigonos("up").returncode == 0


def test_postgrest_serves_view_from_new_file_without_restart(stack):
    view = unique("migrate_view")
    postgrest = stack.container("postgrest")
    started = stack.inspect(postgrest, "{{.State.StartedAt}}")
    stack.add_migration(
        f"9004_{view}.sql",
        f"CREATE VIEW api.{view} AS SELECT 1 AS one;\nGRANT SELECT ON api.{view} TO authenticated;",
    )

    assert stack.saigonos("up").returncode == 0

    token = stack.token(stack.new_user())
    deadline = time.monotonic() + 10
    while (reply := stack.call("GET", f"{stack.url}/api/{view}", token=token)).status != 200:
        assert time.monotonic() < deadline, reply.body
        time.sleep(0.5)
    assert json.loads(reply.body) == [{"one": 1}]
    assert stack.container("postgrest") == postgrest
    assert stack.inspect(postgrest, "{{.State.StartedAt}}") == started
