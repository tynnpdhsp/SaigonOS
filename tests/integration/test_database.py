# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
import secrets
import time
from importlib.resources import files

import pytest

pytestmark = pytest.mark.integration

MIGRATIONS = files("saigonos") / "stack" / "config" / "postgres" / "migrations"
LEAD = "truong-don-vi"
NOTES = """\
CREATE TABLE api.{table} (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner text NOT NULL DEFAULT core.uid(),
    unit text DEFAULT core.unit(),
    body text NOT NULL
);
ALTER TABLE api.{table} ENABLE ROW LEVEL SECURITY;
CREATE POLICY own_rows ON api.{table} TO authenticated
    USING (owner = core.uid())
    WITH CHECK (owner = core.uid() AND unit IS NOT DISTINCT FROM core.unit());
CREATE POLICY unit_rows ON api.{table} FOR SELECT TO authenticated
    USING (core.has_role('{lead}') AND unit = core.unit());
GRANT SELECT, INSERT, UPDATE, DELETE ON api.{table} TO authenticated;
CREATE FUNCTION api.{table}_caller() RETURNS json
LANGUAGE sql STABLE
RETURN json_build_object('uid', core.uid(), 'unit', core.unit(), 'lead', core.has_role('{lead}'));
GRANT EXECUTE ON FUNCTION api.{table}_caller TO authenticated;
CREATE FUNCTION api.{table}_open() RETURNS json
LANGUAGE sql STABLE
RETURN json_build_object('role', current_role, 'uid', core.uid());
GRANT EXECUTE ON FUNCTION api.{table}_open TO anon, authenticated;
CREATE FUNCTION api.{table}_closed() RETURNS text
LANGUAGE sql STABLE
RETURN 'chưa cấp cho ai';
CREATE FUNCTION api.{table}_nested() RETURNS json
LANGUAGE plpgsql STABLE
AS $$ BEGIN RETURN api.{table}_caller(); END $$;
GRANT EXECUTE ON FUNCTION api.{table}_nested TO anon, authenticated;
"""


def unique(prefix):
    return f"{prefix}_{secrets.token_hex(4)}"


class Notes:
    def __init__(self, stack, table):
        self.stack = stack
        self.table = table
        self.url = f"{stack.url}/api/{table}"

    def call(self, user, method, query="", body=None):
        reply = self.stack.call(
            method,
            f"{self.url}{query}",
            token=self.stack.token(user) if user else None,
            body=body,
            headers={"Prefer": "return=representation"},
        )
        return reply.status, json.loads(reply.body)

    def rpc(self, name, user=None):
        url = f"{self.stack.url}/api/rpc/{self.table}_{name}"
        reply = self.stack.call("GET", url, token=self.stack.token(user) if user else None)
        return reply.status, json.loads(reply.body)

    def add(self, user):
        status, rows = self.call(user, "POST", body={"body": "ghi chú"})
        assert status == 201, rows
        return rows[0]

    def stored(self, user):
        query = f"SELECT id, body FROM api.{self.table} WHERE owner = '{user.id}'"
        return [[int(row), body] for row, body in self.stack.sql(query)]


@pytest.fixture(scope="module")
def notes(stack):
    notes = Notes(stack, unique("row_security"))
    text = NOTES.format(table=notes.table, lead=LEAD)
    stack.add_migration(f"9005_{notes.table}.sql", text)
    started = stack.saigonos("up")
    assert started.returncode == 0, started.stderr
    token = stack.token(stack.new_user())
    deadline = time.monotonic() + 10
    while (reply := stack.call("GET", notes.url, token=token)).status != 200:
        assert time.monotonic() < deadline, reply.body
        time.sleep(0.5)
    return notes


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


def test_claim_functions_return_nothing_outside_api(stack):
    query = "SELECT core.uid() IS NULL, core.unit() IS NULL, core.has_role('authenticated')"

    unset = stack.sql(query)
    empty = stack.sql(f"SET request.jwt.claims = ''; {query}")

    assert unset == [["t", "t", "f"]]
    assert empty[-1] == ["t", "t", "f"]


def test_claim_functions_return_claims_of_caller(stack, notes):
    lead = stack.new_user(unit="khoa-a", role=LEAD)
    newcomer = stack.new_user()

    assert notes.rpc("caller", lead) == (200, {"uid": lead.id, "unit": "khoa-a", "lead": True})
    assert notes.rpc("caller", newcomer) == (
        200,
        {"uid": newcomer.id, "unit": None, "lead": False},
    )


def test_user_cannot_read_change_or_delete_row_of_another_user(stack, notes):
    owner, other = stack.new_user(unit="khoa-a"), stack.new_user(unit="khoa-a")
    row = notes.add(owner)
    only_row = f"?id=eq.{row['id']}"

    read = notes.call(other, "GET", only_row)
    changed = notes.call(other, "PATCH", only_row, {"body": "đã bị sửa"})
    deleted = notes.call(other, "DELETE", only_row)

    assert (row["owner"], row["unit"]) == (owner.id, "khoa-a")
    assert (read, changed, deleted) == ((200, []), (200, []), (200, []))
    assert notes.call(owner, "GET") == (200, [row])
    assert notes.stored(owner) == [[row["id"], "ghi chú"]]


def test_user_cannot_add_row_in_name_of_another_user(stack, notes):
    owner, other = stack.new_user(), stack.new_user()

    status, error = notes.call(other, "POST", body={"owner": owner.id, "body": "mạo danh"})

    assert (status, error["code"]) == (403, "42501")
    assert notes.stored(owner) == []


def test_user_cannot_hand_own_row_to_another_user(stack, notes):
    owner, other = stack.new_user(), stack.new_user()
    row = notes.add(other)

    status, error = notes.call(other, "PATCH", f"?id=eq.{row['id']}", {"owner": owner.id})

    assert (status, error["code"]) == (403, "42501")
    assert notes.stored(owner) == []
    assert notes.stored(other) == [[row["id"], "ghi chú"]]


def test_user_cannot_add_row_to_another_unit(stack, notes):
    user = stack.new_user(unit="khoa-a")

    status, error = notes.call(user, "POST", body={"unit": "khoa-b", "body": "sai đơn vị"})

    assert (status, error["code"]) == (403, "42501")
    assert notes.stored(user) == []


def test_unit_lead_reads_rows_of_own_unit_only(stack, notes):
    unit, other_unit = unique("khoa"), unique("khoa")
    member = stack.new_user(unit=unit)
    row = notes.add(member)
    notes.add(stack.new_user())
    only_row = f"?id=eq.{row['id']}"
    lead = stack.new_user(unit=unit, role=LEAD)

    seen = {
        "trưởng đơn vị": notes.call(lead, "GET"),
        "trưởng đơn vị khác": notes.call(stack.new_user(unit=other_unit, role=LEAD), "GET"),
        "trưởng chưa có đơn vị": notes.call(stack.new_user(role=LEAD), "GET"),
        "người cùng đơn vị": notes.call(stack.new_user(unit=unit), "GET"),
    }
    changed = notes.call(lead, "PATCH", only_row, {"body": "đã bị sửa"})
    deleted = notes.call(lead, "DELETE", only_row)

    assert seen == {
        "trưởng đơn vị": (200, [row]),
        "trưởng đơn vị khác": (200, []),
        "trưởng chưa có đơn vị": (200, []),
        "người cùng đơn vị": (200, []),
    }
    assert (changed, deleted) == ((200, []), (200, []))
    assert notes.stored(member) == [[row["id"], "ghi chú"]]


def test_call_without_token_runs_as_anon(stack, notes):
    user = stack.new_user()

    assert notes.rpc("open") == (200, {"role": "anon", "uid": None})
    assert notes.rpc("open", user) == (200, {"role": "authenticated", "uid": user.id})


def test_anon_cannot_use_table_or_function_not_granted_to_it(stack, notes):
    owner = stack.new_user()
    row = notes.add(owner)
    only_row = f"?id=eq.{row['id']}"

    denied = {
        "đọc bảng": notes.call(None, "GET"),
        "thêm dòng": notes.call(None, "POST", body={"body": "không có token"}),
        "sửa dòng": notes.call(None, "PATCH", only_row, {"body": "đã bị sửa"}),
        "xóa dòng": notes.call(None, "DELETE", only_row),
        "hàm của người đã đăng nhập": notes.rpc("caller"),
        "hàm chưa cấp cho ai": notes.rpc("closed"),
    }

    codes = {name: (status, error["code"]) for name, (status, error) in denied.items()}
    assert codes == dict.fromkeys(denied, (401, "42501"))
    added = f"SELECT count(*) FROM api.{notes.table} WHERE body = 'không có token'"
    assert notes.stored(owner) == [[row["id"], "ghi chú"]]
    assert stack.sql(added) == [["0"]]


def test_anon_holds_no_privilege_until_granted(stack, notes):
    functions = """
        SELECT proname FROM pg_proc
        WHERE pronamespace = 'api'::regnamespace AND has_function_privilege('anon', oid, 'EXECUTE')
        ORDER BY proname
    """
    relations = """
        SELECT relname FROM pg_class
        WHERE relnamespace IN ('api'::regnamespace, 'core'::regnamespace)
        AND relkind IN ('r', 'p', 'v', 'm', 'f')
        AND has_table_privilege('anon', oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE')
    """

    assert stack.sql(functions) == [[f"{notes.table}_nested"], [f"{notes.table}_open"]]
    assert stack.sql(relations) == []


def test_anon_cannot_reuse_query_plan_made_for_user(stack, notes):
    user = stack.new_user()
    warmed = [notes.rpc(name, user)[0] for name in ("caller", "nested") for _ in range(3)]

    denied = {"gọi thẳng": notes.rpc("caller"), "gọi qua hàm khác": notes.rpc("nested")}

    codes = {name: (status, error["code"]) for name, (status, error) in denied.items()}
    assert warmed == [200] * 6
    assert codes == dict.fromkeys(denied, (401, "42501"))


def test_new_function_is_closed_to_users_until_granted(stack, notes):
    status, error = notes.rpc("closed", stack.new_user())

    assert (status, error["code"]) == (403, "42501")


def test_token_without_role_authenticated_runs_as_anon(stack, notes):
    user = stack.new_user()
    stack.revoke_roles(user)

    status, error = notes.rpc("caller", user)

    assert notes.rpc("open", user) == (200, {"role": "anon", "uid": user.id})
    assert (status, error["code"]) == (401, "42501")
    assert notes.call(user, "GET")[0] == 401


def test_forged_token_is_rejected_where_anon_is_allowed(stack, notes):
    forged = stack.forged_tokens(stack.new_user())
    path = f"/rpc/{notes.table}_open"

    gateway = {
        name: stack.call("GET", f"{stack.url}/api{path}", token=token).status
        for name, token in forged.items()
    }
    postgrest = {name: stack.postgrest_status(path, token) for name, token in forged.items()}

    assert stack.postgrest_status(path) == 200
    assert gateway == dict.fromkeys(forged, 401)
    assert postgrest == dict.fromkeys(forged, 401)
