# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
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
CREATE TRIGGER audit AFTER INSERT OR UPDATE OR DELETE ON api.{table}
    FOR EACH ROW EXECUTE FUNCTION core.audit();
CREATE FUNCTION api.{table}_undone() RETURNS void
LANGUAGE plpgsql
AS $$ BEGIN
    INSERT INTO api.{table} (body) VALUES ('bị hủy');
    RAISE EXCEPTION 'hủy thay đổi';
END $$;
GRANT EXECUTE ON FUNCTION api.{table}_undone TO authenticated;
"""
GRANTED = """
SELECT '/' || relname FROM pg_class
WHERE relnamespace = 'api'::regnamespace AND relkind IN ('r', 'p', 'v', 'm', 'f')
AND (
    has_table_privilege('{role}', oid, 'SELECT, INSERT, UPDATE, DELETE')
    OR has_any_column_privilege('{role}', oid, 'SELECT, INSERT, UPDATE')
)
UNION
SELECT '/rpc/' || proname FROM pg_proc
WHERE pronamespace = 'api'::regnamespace AND has_function_privilege('{role}', oid, 'EXECUTE')
"""
AUDIT_CHAIN = """
SELECT json_build_object(
    'id', id,
    'occurred_at', to_char(occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'actor', actor,
    'db_role', db_role,
    'table_schema', table_schema,
    'table_name', table_name,
    'operation', operation,
    'old_row', old_row::text,
    'new_row', new_row::text,
    'hash', hash
)
FROM core.audit_log ORDER BY id
"""
HASHED = [
    "id",
    "occurred_at",
    "actor",
    "db_role",
    "table_schema",
    "table_name",
    "operation",
    "old_row",
    "new_row",
]
VERBATIM = {"id", "old_row", "new_row"}
WRONG_TRIGGER = """
CREATE TEMP TABLE {table} (id int);
CREATE TRIGGER audit {kind} EXECUTE FUNCTION core.audit();
CREATE FUNCTION pg_temp.attempt() RETURNS text
LANGUAGE plpgsql
AS $$ BEGIN
    INSERT INTO {table} VALUES (1);
    RETURN 'đã thêm';
EXCEPTION WHEN raise_exception THEN
    RETURN SQLERRM;
END $$;
SELECT pg_temp.attempt(), count(*) FROM {table};
"""
REFUSED_CHANGES = """
CREATE FUNCTION pg_temp.attempt(statement text) RETURNS text
LANGUAGE plpgsql
AS $$ BEGIN
    EXECUTE statement;
    RETURN 'đã chạy';
EXCEPTION WHEN raise_exception THEN
    RETURN SQLERRM;
END $$;
SET session_replication_role = {role};
SELECT pg_temp.attempt(statement)
FROM unnest(ARRAY[
    $$UPDATE {table} SET {change}$$,
    'DELETE FROM {table}',
    'TRUNCATE {table}'
]) WITH ORDINALITY AS attempts (statement, position)
ORDER BY position;
"""
OWNED = "SELECT relowner = current_user::regrole FROM pg_class WHERE oid = '{table}'::regclass"
AUDIT_SIZE = """
SELECT count(*), (SELECT hash FROM core.audit_log ORDER BY id DESC LIMIT 1) FROM core.audit_log
"""
AUDIT_SCANS = """
SELECT seq_scan FROM pg_stat_user_tables WHERE schemaname = 'core' AND relname = 'audit_log'
"""
COSTLY_INDEX = "SET random_page_cost = 1000000; SET cpu_index_tuple_cost = 1000000"
UNLOCK = "ALTER TABLE core.audit_log DISABLE TRIGGER append_only"
LOCK = "ALTER TABLE core.audit_log ENABLE ALWAYS TRIGGER append_only"
CHANGED = (
    "Dòng {row} của audit log không khớp mã băm. Nội dung hoặc mã băm của dòng này đã bị sửa.\n"
)
MISSING = "Audit log thiếu dòng {row}. Dòng này đã bị xóa hoặc bị đổi số thứ tự.\n"
EDITS = {
    "new_row": """new_row = new_row || '{"body": "đã bị sửa tay"}'""",
    "actor": "actor = 'nguoi-khac'",
    "occurred_at": "occurred_at = occurred_at - interval '1 day'",
    "hash": "hash = repeat('0', 64)",
}
PHONES = {
    "0912345678": "091****678",
    "+84912345678": "+84****678",
    "091 234 5678": "091****678",
    "091234567": "*********",
    "": "",
}
EMAILS = {
    "nguyenvana@gmail.com": "ngu*******@gmail.com",
    "nguyễnvăna@hcmue.edu.vn": "ngu*******@hcmue.edu.vn",
    "abcdef@example.com": "abc***@example.com",
    "abcde@example.com": "*****@example.com",
    "a@b@example.com": "***@example.com",
    "khongcoacong": "kho*********",
    "": "",
}
CONTACTS = """\
CREATE SCHEMA {schema};
CREATE TABLE {schema}.contacts (owner text NOT NULL, phone text NOT NULL, email text NOT NULL);
ALTER TABLE {schema}.contacts ENABLE ROW LEVEL SECURITY;
CREATE POLICY own_rows ON {schema}.contacts FOR SELECT TO authenticated
    USING (owner = core.uid() OR core.has_role('{lead}'));
GRANT USAGE ON SCHEMA {schema} TO authenticated;
GRANT SELECT ON {schema}.contacts TO authenticated;
CREATE VIEW api.{schema} WITH (security_invoker = true) AS
SELECT owner,
    CASE WHEN core.has_role('{lead}') THEN phone ELSE core.mask_phone(phone) END AS phone,
    CASE WHEN core.has_role('{lead}') THEN email ELSE core.mask_email(email) END AS email
FROM {schema}.contacts;
GRANT SELECT ON api.{schema} TO authenticated;
"""
POLICY = "du-lieu-ca-nhan"
AGREE = """\
CREATE FUNCTION api.{name}(version text) RETURNS core.consents
LANGUAGE sql SECURITY DEFINER SET search_path = ''
BEGIN ATOMIC
    INSERT INTO core.consents (policy, policy_version) VALUES ('{policy}', version) RETURNING *;
END;
GRANT EXECUTE ON FUNCTION api.{name} TO authenticated;
"""
INCOMPLETE_CONSENTS = """
CREATE FUNCTION pg_temp.attempt(statement text) RETURNS text
LANGUAGE plpgsql
AS $$ BEGIN
    EXECUTE statement;
    RETURN 'đã thêm';
EXCEPTION WHEN not_null_violation OR check_violation THEN
    RETURN SQLSTATE;
END $$;
SELECT pg_temp.attempt('INSERT INTO core.consents ' || consent)
FROM unnest(ARRAY[
    $$(policy, policy_version) VALUES ('p', '1')$$,
    $$(subject, policy, policy_version) VALUES ('', 'p', '1')$$,
    $$(subject, policy_version) VALUES ('s', '1')$$,
    $$(subject, policy, policy_version) VALUES ('s', '', '1')$$,
    $$(subject, policy) VALUES ('s', 'p')$$,
    $$(subject, policy, policy_version) VALUES ('s', 'p', '')$$
]) WITH ORDINALITY AS attempts (consent, position)
ORDER BY position;
"""
CONSENTS_SIZE = "SELECT count(*) FROM core.consents"


def unique(prefix):
    return f"{prefix}_{secrets.token_hex(4)}"


def served(stack, path):
    token = stack.token(stack.new_user())
    deadline = time.monotonic() + 10
    while path not in documented(stack, token)[0]:
        assert time.monotonic() < deadline, f"PostgREST chưa phục vụ {path}"
        time.sleep(0.5)


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

    def rpc(self, name, user=None, method="GET"):
        url = f"{self.stack.url}/api/rpc/{self.table}_{name}"
        reply = self.stack.call(method, url, token=self.stack.token(user) if user else None)
        return reply.status, json.loads(reply.body)

    def add(self, user):
        status, rows = self.call(user, "POST", body={"body": "ghi chú"})
        assert status == 201, rows
        return rows[0]

    def stored(self, user):
        query = f"SELECT id, body FROM api.{self.table} WHERE owner = '{user.id}'"
        return [[int(row), body] for row, body in self.stack.sql(query)]


def documented(stack, token=None):
    reply = stack.call("GET", f"{stack.url}/api/", token=token)
    assert reply.status == 200, reply.body
    document = json.loads(reply.body)
    return set(document["paths"]) - {"/"}, set(document.get("definitions", {}))


def granted(stack, role):
    return {path for [path] in stack.sql(GRANTED.format(role=role))}


def audit_entries(stack, condition):
    query = f"SELECT row_to_json(log) FROM core.audit_log AS log WHERE {condition} ORDER BY id"
    return [json.loads("|".join(row)) for row in stack.sql(query)]


def expected_hash(previous, entry):
    def as_json(name):
        if entry[name] is None:
            return "null"
        if name in VERBATIM:
            return str(entry[name])
        return json.dumps(entry[name], ensure_ascii=False)

    names = sorted(HASHED, key=lambda name: (len(name), name))
    row = "{" + ", ".join(f'"{name}": {as_json(name)}' for name in names) + "}"
    return hashlib.sha256((previous + row).encode()).hexdigest()


def broken_links(stack):
    previous = {"id": 0, "hash": "0" * 64}
    broken = []
    for line in stack.sql(AUDIT_CHAIN):
        entry = json.loads("|".join(line))
        linked = entry["id"] == previous["id"] + 1
        if not linked or entry["hash"] != expected_hash(previous["hash"], entry):
            broken.append(entry["id"])
        previous = entry
    return broken


def written_entries(stack, notes, count=3):
    body = unique("ngoai_api")
    rows = ", ".join([f"('quan-tri', '{body}')"] * count)
    stack.sql(f"INSERT INTO api.{notes.table} (owner, body) VALUES {rows}")
    return [entry["id"] for entry in audit_entries(stack, f"new_row ->> 'body' = '{body}'")]


def verify(stack):
    result = stack.saigonos("audit", "verify")
    return result.returncode, result.stdout


@contextmanager
def tampered(stack, statement):
    copy = unique("core.audit_copy")
    stack.sql(f"CREATE TABLE {copy} AS TABLE core.audit_log")
    try:
        stack.sql(f"{UNLOCK}; {statement}; {LOCK}")
        yield
    finally:
        restore = f"DELETE FROM core.audit_log; INSERT INTO core.audit_log SELECT * FROM {copy}"
        stack.sql(f"{UNLOCK}; {restore}; {LOCK}; DROP TABLE {copy}")


@pytest.fixture(scope="module")
def notes(stack):
    notes = Notes(stack, unique("row_security"))
    text = NOTES.format(table=notes.table, lead=LEAD)
    stack.add_migration(f"9005_{notes.table}.sql", text)
    started = stack.up()
    assert started.returncode == 0, started.stderr
    served(stack, f"/{notes.table}")
    return notes


@pytest.fixture(scope="module")
def contacts(stack):
    schema = unique("contacts")
    stack.add_migration(f"9006_{schema}.sql", CONTACTS.format(schema=schema, lead=LEAD))
    started = stack.up()
    assert started.returncode == 0, started.stderr
    served(stack, f"/{schema}")
    return schema


@pytest.fixture(scope="module")
def agree(stack):
    name = unique("agree")
    stack.add_migration(f"9007_{name}.sql", AGREE.format(name=name, policy=POLICY))
    started = stack.up()
    assert started.returncode == 0, started.stderr
    served(stack, f"/rpc/{name}")

    def call(user, version="2026-11"):
        url = f"{stack.url}/api/rpc/{name}"
        reply = stack.call("POST", url, token=stack.token(user), body={"version": version})
        return reply.status, json.loads(reply.body)

    return call


def test_migrate_records_each_shipped_file(stack):
    shipped = {
        entry.name: hashlib.sha256(entry.read_bytes()).hexdigest() for entry in MIGRATIONS.iterdir()
    }

    recorded = dict(stack.sql("SELECT name, checksum FROM core.migrations WHERE scope = 'core'"))

    assert shipped
    assert shipped.items() <= recorded.items()


@pytest.mark.parametrize("role", ["anon", "authenticated", "core_service"])
def test_vietnamese_search_ignores_marks_and_case_for_every_role(stack, role):
    query = (
        f"SET ROLE {role}; SELECT core.search_vector('Nguyễn Văn ĐỨC', 'Ổn định'), "
        "core.search_vector('nguyen van duc') @@ core.search_query('Nguyễn Văn'), "
        "core.search_vector('Nguyễn Văn Đức') @@ core.search_query('\"nguyen van\" -an')"
    )

    result = stack.sql(query)[-1]

    assert result == ["'dinh':5 'duc':3 'nguyen':1 'on':4 'van':2", "t", "t"]


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

    first = stack.up()
    second = stack.up()

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert stack.sql(f"SELECT step FROM {table}") == [["b"]]
    assert stack.logs("migrate").splitlines()[-1] == "Không có file SQL mới"


def test_changed_file_stops_migrate(stack):
    path = stack.add_migration(f"9002_{unique('migrate_changed')}.sql", "SELECT 1;")
    assert stack.up().returncode == 0

    path.write_text("SELECT 2;", encoding="utf-8")
    try:
        changed = stack.up()
        logs = stack.logs("migrate")
    finally:
        path.write_text("SELECT 1;", encoding="utf-8")

    assert changed.returncode != 0
    assert f"File {path.name} đã được chạy trước đó nhưng nội dung đã thay đổi." in logs
    assert stack.up().returncode == 0


def test_failed_file_changes_nothing_and_stops_later_files(stack):
    table = unique("migrate_failed")
    failing = stack.add_migration(
        f"9003_{table}_a.sql", f"CREATE TABLE {table} (id int);\nSELECT 1 / 0;"
    )
    later = stack.add_migration(f"9003_{table}_b.sql", f"CREATE TABLE {table}_later (id int);")
    try:
        failed = stack.up()
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
    assert stack.up().returncode == 0


def test_postgrest_serves_view_from_new_file_without_restart(stack):
    view = unique("migrate_view")
    postgrest = stack.container("postgrest")
    started = stack.inspect(postgrest, "{{.State.StartedAt}}")
    stack.add_migration(
        f"9004_{view}.sql",
        f"CREATE VIEW api.{view} AS SELECT 1 AS one;\nGRANT SELECT ON api.{view} TO authenticated;",
    )

    assert stack.up().returncode == 0

    token = stack.token(stack.new_user())
    deadline = time.monotonic() + 10
    while (reply := stack.call("GET", f"{stack.url}/api/{view}", token=token)).status != 200:
        assert time.monotonic() < deadline, reply.body
        time.sleep(0.5)
    assert json.loads(reply.body) == [{"one": 1}]
    assert stack.container("postgrest") == postgrest
    assert stack.inspect(postgrest, "{{.State.StartedAt}}") == started


def test_claim_functions_trust_only_sealed_claims(stack):
    query = "SELECT core.uid() IS NULL, core.unit() IS NULL, core.has_role('authenticated')"

    unset = stack.sql(query)
    empty = stack.sql(f"SET request.jwt.claims = ''; {query}")
    claims = '{"sub": "ai-do", "unit": "khoa-a", "realm_access": {"roles": ["authenticated"]}}'
    unsealed = stack.sql(f"SET ROLE authenticated; SET request.jwt.claims = '{claims}'; {query}")
    sealed = stack.sql(
        f"SET ROLE authenticated; SET request.jwt.claims = '{claims}'; "
        f"SELECT core.seal_claims(); SELECT core.uid(), core.unit(), core.has_role('authenticated')"
    )

    assert unset == [["t", "t", "f"]]
    assert empty[-1] == ["t", "t", "f"]
    assert unsealed[-1] == ["t", "t", "f"]
    assert sealed[-1] == ["ai-do", "khoa-a", "t"]


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


def test_api_accepts_access_token_only(stack, notes):
    user = stack.new_user()
    tokens = json.loads(stack.login(user, scope="openid").body)
    path = f"/rpc/{notes.table}_open"

    def through_gateway(token=None):
        reply = stack.call("GET", f"{stack.url}/api{path}", token=token)
        return reply.status, json.loads(reply.body), reply.headers.get("WWW-Authenticate")

    rejected = through_gateway(tokens["id_token"])
    document = stack.call("GET", f"{stack.url}/api/", token=tokens["id_token"]).status

    assert through_gateway(tokens["access_token"])[:2] == (
        200,
        {"role": "authenticated", "uid": user.id},
    )
    assert through_gateway()[:2] == (200, {"role": "anon", "uid": None})
    assert rejected[0] == 401
    assert (rejected[1]["code"], rejected[1]["message"]) == ("SGN01", "Access token không hợp lệ")
    assert rejected[2] == 'Bearer error="invalid_token"'
    assert stack.postgrest_status(path, tokens["id_token"]) == 401
    assert document == 401


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


def test_api_document_lists_only_tables_and_functions_granted_to_caller(stack, notes):
    table = notes.table
    token = stack.token(stack.new_user())

    user_paths, user_tables = documented(stack, token)
    anon_paths, anon_tables = documented(stack)

    own = {f"/rpc/{table}_{name}" for name in ("caller", "nested", "open", "undone")}
    assert user_paths == granted(stack, "authenticated")
    assert anon_paths == granted(stack, "anon")
    assert {path for path in user_paths if table in path} == {f"/{table}", *own}
    assert {path for path in anon_paths if table in path} == {
        f"/rpc/{table}_nested",
        f"/rpc/{table}_open",
    }
    assert table in user_tables
    assert anon_tables == set()


def test_api_document_follows_grant_and_revoke_at_once(stack, notes):
    function = f"api.{notes.table}_closed"
    path = f"/rpc/{notes.table}_closed"

    stack.sql(f"GRANT EXECUTE ON FUNCTION {function} TO anon")
    try:
        after_grant = documented(stack)[0]
    finally:
        stack.sql(f"REVOKE EXECUTE ON FUNCTION {function} FROM anon")
    after_revoke = documented(stack)[0]

    assert path in after_grant
    assert path not in after_revoke


def test_audit_log_records_who_changed_which_values(stack, notes):
    user = stack.new_user(unit="khoa-a")
    started = stack.sql("SELECT clock_timestamp()")[0][0]
    row = notes.add(user)
    changed = row | {"body": "đã sửa"}
    only_row = f"?id=eq.{row['id']}"

    notes.call(user, "PATCH", only_row, {"body": "đã sửa"})
    notes.call(user, "DELETE", only_row)

    recent = f"occurred_at BETWEEN '{started}' AND clock_timestamp()"
    entries = audit_entries(stack, f"actor = '{user.id}' AND {recent}")
    changes = [(entry["operation"], entry["old_row"], entry["new_row"]) for entry in entries]
    sources = {(entry["db_role"], entry["table_schema"], entry["table_name"]) for entry in entries}
    assert changes == [("INSERT", None, row), ("UPDATE", row, changed), ("DELETE", changed, None)]
    assert sources == {("authenticated", "api", notes.table)}


def test_audit_log_records_database_role_of_change_made_outside_api(stack, notes):
    body = unique("ngoai_api")

    stack.sql(f"INSERT INTO api.{notes.table} (owner, body) VALUES ('quan-tri', '{body}')")

    entries = audit_entries(stack, f"new_row ->> 'body' = '{body}'")
    assert [(entry["actor"], entry["db_role"]) for entry in entries] == [(None, "postgres")]


def test_rejected_or_undone_change_leaves_no_audit_entry(stack, notes):
    owner, other = stack.new_user(), stack.new_user()
    row = notes.add(owner)
    only_row = f"?id=eq.{row['id']}"

    notes.call(other, "PATCH", only_row, {"body": "đã bị sửa"})
    notes.call(other, "DELETE", only_row)
    notes.call(other, "POST", body={"owner": owner.id, "body": "mạo danh"})
    status, error = notes.rpc("undone", other, method="POST")

    assert (status, error["message"]) == (400, "hủy thay đổi")
    assert audit_entries(stack, f"actor = '{other.id}'") == []
    assert [entry["operation"] for entry in audit_entries(stack, f"actor = '{owner.id}'")] == [
        "INSERT"
    ]


def test_audit_chain_stays_unbroken_when_many_connections_write_at_once(stack, notes):
    user = stack.new_user()
    token = stack.token(user)
    headers = {"Prefer": "return=minimal"}

    def write(number):
        if number % 4 == 0:
            url = f"{stack.url}/api/rpc/{notes.table}_undone"
            return stack.call("POST", url, token=token).status
        body = {"body": f"ghi chú {number}"}
        return stack.call("POST", notes.url, token=token, body=body, headers=headers).status

    with ThreadPoolExecutor(8) as pool:
        statuses = list(pool.map(write, range(120)))

    entries = audit_entries(stack, f"actor = '{user.id}'")
    assert statuses == [400 if number % 4 == 0 else 201 for number in range(120)]
    assert sorted(entry["new_row"]["body"] for entry in entries) == sorted(
        f"ghi chú {number}" for number in range(120) if number % 4
    )
    assert broken_links(stack) == []


def test_audit_hash_covers_every_column_of_audit_log(stack):
    query = """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'core' AND table_name = 'audit_log' ORDER BY ordinal_position
    """

    assert [column for [column] in stack.sql(query)] == [*HASHED, "hash"]


@pytest.mark.parametrize(
    "kind", ["BEFORE INSERT ON {table} FOR EACH ROW", "AFTER INSERT ON {table} FOR EACH STATEMENT"]
)
def test_audit_function_refuses_trigger_that_does_not_run_after_each_row(stack, kind):
    table = unique("audit_trigger")

    attempt = stack.sql(WRONG_TRIGGER.format(table=table, kind=kind.format(table=table)))

    refused = "Hàm core.audit() chỉ dùng cho trigger AFTER INSERT OR UPDATE OR DELETE"
    assert attempt[-1] == [f"{refused} ... FOR EACH ROW", "0"]


def test_api_roles_cannot_use_audit_log_directly(stack):
    query = """
        SELECT role,
            has_table_privilege(role, 'core.audit_log', 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE'),
            has_function_privilege(role, 'core.audit_hash(text, core.audit_log)', 'EXECUTE'),
            has_function_privilege(role, 'core.audit()', 'EXECUTE'),
            has_function_privilege(role, 'core.append_only()', 'EXECUTE')
        FROM unnest(ARRAY['anon', 'authenticated']) AS role
    """

    assert stack.sql(query) == [["anon", *"ffff"], ["authenticated", *"ffff"]]


def test_audit_trigger_never_scans_whole_audit_log(stack, notes):
    rows = "SELECT 'quan-tri', 'nhiều dòng' FROM generate_series(1, 50)"
    before = stack.sql(AUDIT_SCANS)

    stack.sql(f"{COSTLY_INDEX}; INSERT INTO api.{notes.table} (owner, body) {rows}")

    assert stack.sql(AUDIT_SCANS) == before


@pytest.mark.parametrize("role", ["origin", "replica"])
def test_audit_log_refuses_update_delete_and_truncate_even_from_owner(stack, notes, role):
    written_entries(stack, notes)
    before = stack.sql(AUDIT_SIZE)
    changes = REFUSED_CHANGES.format(role=role, table="core.audit_log", change="actor = 'khac'")

    refused = stack.sql(changes)[-3:]

    assert stack.sql(OWNED.format(table="core.audit_log")) == [["t"]]
    assert refused == [
        [f"Bảng core.audit_log chỉ cho phép thêm dòng, không cho phép {operation}"]
        for operation in ("UPDATE", "DELETE", "TRUNCATE")
    ]
    assert stack.sql(AUDIT_SIZE) == before


def test_audit_verify_accepts_chain_written_by_trigger(stack, notes):
    written_entries(stack, notes)
    [[rows, last_hash]] = stack.sql(AUDIT_SIZE)

    assert verify(stack) == (
        0,
        f"Audit log có {rows} dòng. Chuỗi mã băm khớp.\nMã băm của dòng cuối: {last_hash}\n",
    )
    assert broken_links(stack) == []


@pytest.mark.parametrize("edit", EDITS.values(), ids=EDITS.keys())
def test_audit_verify_points_at_row_edited_by_superuser(stack, notes, edit):
    _, edited, _ = written_entries(stack, notes)

    with tampered(stack, f"UPDATE core.audit_log SET {edit} WHERE id = {edited}"):
        broken = verify(stack)

    assert broken == (1, CHANGED.format(row=edited))
    assert verify(stack)[0] == 0


def test_audit_verify_points_at_row_deleted_by_superuser(stack, notes):
    _, deleted, _ = written_entries(stack, notes)

    with tampered(stack, f"DELETE FROM core.audit_log WHERE id = {deleted}"):
        broken = verify(stack)

    assert broken == (1, MISSING.format(row=deleted))
    assert verify(stack)[0] == 0


def test_audit_verify_points_at_first_of_several_broken_rows(stack, notes):
    first, _, later, _ = written_entries(stack, notes, 4)
    edit = "UPDATE core.audit_log SET actor = 'nguoi-khac' WHERE id = {row}"
    delete = "DELETE FROM core.audit_log WHERE id = {row}"

    with tampered(stack, f"{edit.format(row=first)}; {delete.format(row=later)}"):
        edited_first = verify(stack)
    with tampered(stack, f"{delete.format(row=first)}; {edit.format(row=later)}"):
        deleted_first = verify(stack)

    assert edited_first == (1, CHANGED.format(row=first))
    assert deleted_first == (1, MISSING.format(row=first))
    assert verify(stack)[0] == 0


@pytest.mark.parametrize(
    ("function", "examples"),
    [("mask_phone", PHONES), ("mask_email", EMAILS)],
    ids=["phone", "email"],
)
def test_mask_function_hides_part_of_value(stack, function, examples):
    values = ", ".join(f"'{value}'" for value in examples)
    query = f"SELECT value, core.{function}(value) FROM unnest(ARRAY[{values}]) AS value"

    assert dict(stack.sql(query)) == examples
    assert stack.sql(f"SELECT core.{function}(NULL) IS NULL") == [["t"]]


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_api_roles_can_call_mask_functions(stack, role):
    query = "SELECT core.mask_phone('0912345678'), core.mask_email('nguyenvana@gmail.com')"

    assert stack.sql(f"SET ROLE {role}; {query}")[-1] == ["091****678", "ngu*******@gmail.com"]


def test_view_with_security_invoker_masks_contacts_and_keeps_row_security(stack, contacts):
    owner, other = stack.new_user(), stack.new_user()
    rows = {owner.id: ["0912345678", "nguyenvana@gmail.com"], other.id: ["0987654321", "b@b.vn"]}
    values = ", ".join(f"('{user}', '{phone}', '{email}')" for user, [phone, email] in rows.items())
    stack.sql(f"INSERT INTO {contacts}.contacts VALUES {values}")

    def read(user, path=contacts, headers=None):
        url = f"{stack.url}/api/{path}?order=phone"
        reply = stack.call("GET", url, token=stack.token(user), headers=headers)
        return reply.status, json.loads(reply.body)

    lead = stack.new_user(role=LEAD)
    assert read(owner) == (
        200,
        [{"owner": owner.id, "phone": "091****678", "email": "ngu*******@gmail.com"}],
    )
    assert read(lead) == (
        200,
        [{"owner": user, "phone": phone, "email": email} for user, [phone, email] in rows.items()],
    )
    assert read(lead, "contacts", {"Accept-Profile": contacts})[0] == 404


def test_consent_records_caller_policy_version_and_server_time(stack, agree):
    user = stack.new_user()
    started = stack.sql("SELECT clock_timestamp()")[0][0]

    status, consent = agree(user)

    finished = stack.sql("SELECT clock_timestamp()")[0][0]
    in_time = f"given_at BETWEEN '{started}' AND '{finished}'"
    assert status == 200, consent
    assert (consent["subject"], consent["policy"], consent["policy_version"]) == (
        user.id,
        POLICY,
        "2026-11",
    )
    assert stack.sql(f"SELECT {in_time} FROM core.consents WHERE id = {consent['id']}") == [["t"]]


def test_consent_is_written_to_audit_log(stack, agree):
    user = stack.new_user()

    _, consent = agree(user)

    written = f"table_name = 'consents' AND new_row ->> 'id' = '{consent['id']}'"
    entries = audit_entries(stack, written)
    sources = [(entry["actor"], entry["db_role"], entry["operation"]) for entry in entries]
    assert sources == [(user.id, "authenticated", "INSERT")]
    assert entries[0]["new_row"] == consent


def test_consent_needs_subject_policy_and_version(stack):
    before = stack.sql(CONSENTS_SIZE)

    attempts = stack.sql(INCOMPLETE_CONSENTS)[-6:]

    assert attempts == [[code] for code in ("23502", "23514") * 3]
    assert stack.sql(CONSENTS_SIZE) == before


@pytest.mark.parametrize("role", ["origin", "replica"])
def test_consents_refuse_update_delete_and_truncate_even_from_owner(stack, role):
    consent = f"('khach-1', '{POLICY}', '2026-11')"
    stack.sql(f"INSERT INTO core.consents (subject, policy, policy_version) VALUES {consent}")
    before = stack.sql(CONSENTS_SIZE)
    changes = REFUSED_CHANGES.format(role=role, table="core.consents", change="policy = 'khac'")

    refused = stack.sql(changes)[-3:]

    assert stack.sql(OWNED.format(table="core.consents")) == [["t"]]
    assert refused == [
        [f"Bảng core.consents chỉ cho phép thêm dòng, không cho phép {operation}"]
        for operation in ("UPDATE", "DELETE", "TRUNCATE")
    ]
    assert stack.sql(CONSENTS_SIZE) == before


def test_api_roles_cannot_use_consents_directly(stack):
    query = """
        SELECT role,
            has_table_privilege(role, 'core.consents', 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE')
        FROM unnest(ARRAY['anon', 'authenticated']) AS role
    """

    assert stack.sql(query) == [["anon", "f"], ["authenticated", "f"]]
