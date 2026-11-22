# SPDX-License-Identifier: Apache-2.0
import base64
import copy
import json
import re
import secrets
import shutil
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = ROOT / "schemas" / "saigonos-app.schema.json"
README = (ROOT / "README.md").read_text(encoding="utf-8")
MANIFEST = {
    "name": "nghi-phep",
    "title": "Nghỉ phép",
    "version": "0.1.0",
    "roles": [{"name": "nghi-phep.quan-ly", "description": "Duyệt đơn"}],
    "database": "database",
    "processes": "processes",
    "ui": "ui",
}
FILES = {
    "database/0001_don.sql": "CREATE TABLE nghi_phep.don (id bigint);\n",
    "processes/duyet.bpmn": "<definitions/>\n",
    "ui/index.html": "<!doctype html>\n",
    "ui/app.js": "console.log(1);\n",
}
SYMLINK = "là symlink. Thư mục đã khai không được chứa symlink."
NOTES_SQL = """\
CREATE TABLE notes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    body text NOT NULL,
    owner text NOT NULL DEFAULT core.uid()
);
ALTER TABLE notes ENABLE ROW LEVEL SECURITY;
CREATE POLICY own ON notes USING (owner = core.uid());
CREATE TRIGGER audit AFTER INSERT OR UPDATE OR DELETE ON notes
    FOR EACH ROW EXECUTE FUNCTION core.audit();
GRANT SELECT, INSERT ON notes TO {schema}_user;
"""
WHO_SQL = """\
CREATE TABLE who AS
SELECT current_user::text AS who_current, session_user::text AS who_session,
    (SELECT rolcanlogin FROM pg_roles WHERE rolname = current_user) AS could_log_in;
"""
BOARD_SQL = """\
CREATE TABLE board (id int);
GRANT USAGE ON SCHEMA {schema} TO anon;
GRANT SELECT ON board TO anon, {schema}_user;
"""
TOTAL_SQL = (
    "CREATE FUNCTION total() RETURNS bigint LANGUAGE sql RETURN (SELECT count(*) FROM notes);\n"
)
OWNER_TOTAL_SQL = """\
CREATE FUNCTION owner_total() RETURNS bigint LANGUAGE sql SECURITY DEFINER SET search_path = ''
RETURN (SELECT count(*) FROM {schema}.notes);
GRANT EXECUTE ON FUNCTION owner_total() TO {schema}_user;
"""
CROSS_SQL = """\
SET check_function_bodies = off;
CREATE FUNCTION read_other() RETURNS bigint LANGUAGE sql
AS $f$ SELECT count(*) FROM {other}.notes $f$;
CREATE FUNCTION switch_role() RETURNS bigint LANGUAGE plpgsql AS $f$
BEGIN
    SET LOCAL ROLE {other}_user;
    RETURN (SELECT count(*) FROM {other}.notes);
END $f$;
CREATE FUNCTION switch_by_clause() RETURNS bigint LANGUAGE sql SET role = '{other}_user'
AS $f$ SELECT count(*) FROM {other}.notes $f$;
CREATE FUNCTION make_invoker() RETURNS void LANGUAGE plpgsql AS $f$
BEGIN
    ALTER FUNCTION {schema}.switch_role() SECURITY INVOKER;
END $f$;
CREATE FUNCTION own_count() RETURNS bigint LANGUAGE sql RETURN (SELECT count(*) FROM notes);
CREATE VIEW switched AS
SELECT set_config('role', '{other}_user', true) AS role,
    query_to_xml('SELECT * FROM {other}.notes', false, false, '')::text AS notes;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA {schema} TO {schema}_user;
GRANT SELECT ON switched TO {schema}_user;
"""
FORGERY_SQL = """\
CREATE TABLE loot (claims text, seal text);
GRANT SELECT, INSERT ON loot TO {schema}_user;
CREATE FUNCTION claims_of(victim text) RETURNS text LANGUAGE sql
RETURN json_build_object(
    'sub', victim, 'role', 'authenticated', 'typ', 'Bearer', 'azp', '{app}'
)::text;
CREATE FUNCTION set_claims(claims text, seal text DEFAULT NULL) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    EXECUTE format('SET LOCAL request.jwt.claims = %L', claims);
    IF seal IS NOT NULL THEN
        EXECUTE format('SET LOCAL saigonos.claims_seal = %L', seal);
    END IF;
END $$;
CREATE FUNCTION forged_uid(victim text) RETURNS text LANGUAGE plpgsql AS $$
BEGIN
    PERFORM set_claims(claims_of(victim));
    RETURN core.uid();
END $$;
CREATE FUNCTION read_with_set_config(victim text) RETURNS bigint LANGUAGE plpgsql AS $$
BEGIN
    PERFORM set_config('request.jwt.claims', claims_of(victim), true);
    RETURN (SELECT count(*) FROM notes);
END $$;
CREATE FUNCTION read_with_set_local(victim text) RETURNS bigint LANGUAGE plpgsql AS $$
BEGIN
    PERFORM set_claims(claims_of(victim));
    RETURN (SELECT count(*) FROM notes);
END $$;
CREATE FUNCTION read_after_pre_request(victim text) RETURNS bigint LANGUAGE plpgsql AS $$
BEGIN
    PERFORM set_claims(claims_of(victim));
    PERFORM core.pre_request();
    RETURN (SELECT count(*) FROM notes);
END $$;
CREATE FUNCTION read_after_seal(victim text) RETURNS bigint LANGUAGE plpgsql AS $$
BEGIN
    PERFORM set_claims(claims_of(victim));
    PERFORM core.seal_claims();
    RETURN (SELECT count(*) FROM notes);
END $$;
CREATE FUNCTION keep_claims() RETURNS void LANGUAGE sql AS $f$
    INSERT INTO loot VALUES (
        current_setting('request.jwt.claims', true), current_setting('saigonos.claims_seal', true)
    )
$f$;
CREATE FUNCTION read_with_kept_claims() RETURNS bigint LANGUAGE plpgsql AS $$
BEGIN
    PERFORM set_claims(claims, seal) FROM loot;
    RETURN (SELECT count(*) FROM notes);
END $$;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA {schema} TO {schema}_user;
"""
PAGE = '<!doctype html><title>Ghi chú</title><script src="app.js"></script>\n'
SCRIPT = "console.log('ghi chú');\n"
UI = {"index.html": PAGE, "app.js": SCRIPT, "css/site.css": "body { margin: 0; }\n"}
UI |= {".bi-mat": "không phục vụ\n"}
REFUSED_FILES = {
    "doc-ung-dung-khac": "SELECT * FROM {other}.notes;",
    "doc-audit-log": "SELECT * FROM core.audit_log;",
    "ghi-migrations": "INSERT INTO core.migrations VALUES ('core', '9999_gia.sql', 'x');",
    "doi-sang-postgres": "SET ROLE postgres;",
    "doi-sang-authenticated": "SET ROLE authenticated;",
    "doi-sang-role-user": "SET ROLE {own}_user;",
    "cap-schema-cho-authenticated": "GRANT USAGE ON SCHEMA {own} TO authenticated;",
    "reset-role": "RESET ROLE;\nSELECT * FROM core.audit_log;",
    "commit": "COMMIT;",
}


@pytest.fixture(scope="module")
def apps_stack(idle_stack):
    created = idle_stack.saigonos("init")
    assert created.returncode == 0, created.stdout + created.stderr
    yield idle_stack
    idle_stack.compose_result("--profile", "apps", "down", "--volumes", "--rmi", "local")


def make_app(folder, **changes):
    for name, text in FILES.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")
    manifest = json.dumps(MANIFEST | changes, ensure_ascii=False, indent=2)
    (folder / "saigonos-app.json").write_text(manifest, encoding="utf-8")
    return folder


def project_containers(stack):
    label = f"label=com.docker.compose.project={stack.home.name}"
    return stack.run_docker("ps", "--all", "--quiet", "--filter", label).stdout.split()


def printed_last(output, text):
    return f"\n{output}".endswith(f"\n{text}")


def run_apps(stack, *args):
    return stack.compose_result("run", "--rm", "apps", *args, timeout=600)


def test_check_passes_without_starting_any_service(apps_stack, tmp_path):
    app = make_app(tmp_path / "ban-sao")

    result = apps_stack.saigonos("apply", "--check", str(app))

    assert result.returncode == 0, result.stdout + result.stderr
    assert printed_last(result.stdout, "Ứng dụng nghi-phep 0.1.0 không có lỗi.\n")
    assert project_containers(apps_stack) == []


def test_check_lists_every_problem_and_sees_symlinks_through_mount(apps_stack, tmp_path):
    roles = [{"name": "don-tu.quan-ly", "description": "Duyệt đơn"}]
    app = make_app(tmp_path / "nghi-phep", version="1.0", roles=roles)
    (app / "ui" / "index.html").unlink()
    (app / "ui" / "secret").symlink_to("/etc/passwd")
    (app / "ui" / "db").symlink_to("../database")

    result = apps_stack.saigonos("apply", "--check", str(app))

    assert result.returncode == 1, result.stderr
    assert printed_last(
        result.stdout,
        "Ứng dụng có 5 lỗi:\n"
        "- version: Phiên bản phải theo Semantic Versioning, ví dụ 1.0.0 hoặc 1.0.0-beta.1.\n"
        '- roles[0].name: Tên role phải bắt đầu bằng "nghi-phep.".\n'
        f'- ui: "ui/db" {SYMLINK}\n'
        f'- ui: "ui/secret" {SYMLINK}\n'
        '- ui: Thư mục "ui" không có file index.html.\n',
    )
    assert project_containers(apps_stack) == []


def test_check_runs_with_docker_compose_alone(apps_stack):
    make_app(apps_stack.home / "apps" / "nghi-phep")

    result = run_apps(apps_stack, "check", "nghi-phep")

    assert result.returncode == 0, result.stdout + result.stderr
    assert printed_last(result.stdout, "Ứng dụng nghi-phep 0.1.0 không có lỗi.\n")


def test_file_readable_only_by_owner_fails_check_inside_apps_folder(apps_stack):
    app = make_app(apps_stack.home / "apps" / "rieng-tu")
    (app / "ui" / "app.js").chmod(0o600)

    copied = run_apps(apps_stack, "check", "rieng-tu")
    own = apps_stack.saigonos("apply", "--check", str(app))

    assert copied.returncode == 1, copied.stderr
    assert printed_last(
        copied.stdout, 'Ứng dụng có 1 lỗi:\n- ui: Không đọc được file "ui/app.js".\n'
    )
    assert own.returncode == 0, own.stdout + own.stderr


def test_check_reports_missing_app_folder(apps_stack):
    result = run_apps(apps_stack, "check", "khong-co")

    assert result.returncode == 1, result.stderr
    assert printed_last(result.stdout, "Không tìm thấy thư mục khong-co.\n")


def test_apps_service_prints_schema_kept_in_repository(apps_stack):
    result = run_apps(apps_stack, "schema")

    assert result.returncode == 0, result.stderr
    assert printed_last(result.stdout, SCHEMA_FILE.read_text(encoding="utf-8"))


def test_apps_service_is_left_out_of_running_system(apps_stack):
    services = json.loads(apps_stack.compose("config", "--format", "json"))["services"]

    assert "core" in services
    assert "apps" not in services


def new_name():
    return f"thu-{secrets.token_hex(3)}"


def schema_of(name):
    return name.replace("-", "_")


def notes_app(folder, name, version="0.1.0", files=None, roles=("nguoi-dung",), ui=None):
    manifest = {
        "name": name,
        "title": "Ghi chú thử",
        "version": version,
        "roles": [{"name": f"{name}.{role}", "description": f"Vai trò {role}"} for role in roles],
        "database": "database",
    }
    if ui is not None:
        manifest["ui"] = "giao-dien"
        for file, text in ui.items():
            (folder / "giao-dien" / file).parent.mkdir(parents=True, exist_ok=True)
            (folder / "giao-dien" / file).write_text(text, encoding="utf-8")
    (folder / "database").mkdir(parents=True, exist_ok=True)
    notes = NOTES_SQL.format(schema=schema_of(name))
    (folder / "database" / "0001_notes.sql").write_text(notes, encoding="utf-8")
    for file, text in (files or {}).items():
        (folder / "database" / file).write_text(text, encoding="utf-8")
    content = json.dumps(manifest, ensure_ascii=False, indent=2)
    (folder / "saigonos-app.json").write_text(content, encoding="utf-8")
    return folder


def plug(stack, folder):
    return stack.saigonos("apply", str(folder))


def profile_call(stack, method, name, token, body=None, table="notes"):
    headers = {"Accept-Profile": schema_of(name), "Content-Profile": schema_of(name)}
    return stack.call(method, f"{stack.url}/api/{table}", token=token, body=body, headers=headers)


def wait_until_served(stack, name, token, table="notes"):
    deadline = time.monotonic() + 15
    while profile_call(stack, "GET", name, token, table=table).status != 200:
        assert time.monotonic() < deadline, "PostgREST chưa phục vụ schema của ứng dụng"
        time.sleep(0.2)


def started(stack, service):
    return stack.inspect(stack.container(service), "{{.State.StartedAt}} {{.RestartCount}}")


def claims_of(token):
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def admin_json(stack, path):
    reply = stack.admin("GET", path)
    assert reply.status == 200, reply.body
    return json.loads(reply.body)


def keycloak_client(stack, name):
    return admin_json(stack, f"/clients?{urlencode({'clientId': name})}")


def keycloak_state(stack, name):
    [client] = keycloak_client(stack, name)
    path = f"/clients/{client['id']}"
    client["attributes"].pop("client.secret.creation.time", None)
    for key in ("redirectUris", "webOrigins", "defaultClientScopes", "optionalClientScopes"):
        client[key] = sorted(client.get(key, []))
    mappings = admin_json(stack, f"{path}/scope-mappings")
    role = f"/roles/{name}.nguoi-dung"
    return {
        "client": client,
        "realm": sorted(item["name"] for item in mappings.get("realmMappings", [])),
        "clients": mappings.get("clientMappings", {}),
        "mappers": admin_json(stack, f"{path}/protocol-mappers/models"),
        "default": sorted(
            item["name"] for item in admin_json(stack, f"{path}/default-client-scopes")
        ),
        "optional": admin_json(stack, f"{path}/optional-client-scopes"),
        "role": admin_json(stack, role),
        "composites": admin_json(stack, f"{role}/composites"),
    }


def route_state(stack, name):
    reply = stack.gateway_admin("GET", f"/routes/app-{name}")
    assert reply.status == 200, reply.body
    value = json.loads(reply.body)["value"]
    return {key: item for key, item in value.items() if key not in ("create_time", "update_time")}


def user_with_roles(stack, *roles):
    user = stack.new_user()
    for role in roles:
        stack.grant_role(user, role)
    return user


def table_exists(stack, schema, table):
    return stack.sql(f"SELECT to_regclass('{schema}.{table}') IS NOT NULL") == [["t"]]


def database_state(stack, name):
    schema = schema_of(name)
    return stack.sql(
        "SELECT "
        f"(SELECT json_agg(m ORDER BY m.name) FROM core.migrations m WHERE m.scope = '{name}'), "
        f"(SELECT row_to_json(a) FROM core.apps a WHERE a.name = '{name}'), "
        "(SELECT count(*) FROM core.audit_log WHERE table_name = 'apps' "
        f"AND coalesce(new_row, old_row) ->> 'name' = '{name}'), "
        "(SELECT json_agg(c.relname || ':' || coalesce(c.relacl::text, '') ORDER BY c.relname) "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname = '{schema}'), "
        f"(SELECT row_to_json(r) FROM pg_authid r WHERE r.rolname = '{schema}')"
    )


@pytest.fixture(scope="module")
def plugged(stack, tmp_path_factory):
    name, other = new_name(), new_name()
    folder = notes_app(tmp_path_factory.mktemp("ung-dung") / name, name)
    for app in (folder, notes_app(tmp_path_factory.mktemp("ung-dung") / other, other)):
        result = plug(stack, app)
        assert result.returncode == 0, result.stdout + result.stderr
    return SimpleNamespace(name=name, folder=folder, other=other)


def test_apply_plugs_app_and_gateway_serves_its_table(stack, tmp_path):
    name = new_name()
    schema = schema_of(name)
    before = started(stack, "postgrest")
    user, other = stack.new_user(), stack.new_user()

    result = plug(stack, notes_app(tmp_path / name, name))

    assert result.returncode == 0, result.stdout + result.stderr
    token = stack.app_token(user, name)
    assert printed_last(
        result.stdout,
        f"Đã tạo schema {schema}, role {schema} và role {schema}_user của ứng dụng.\n"
        "Đã chạy file 0001_notes.sql.\n"
        f"Đã tạo realm role {name}.nguoi-dung.\n"
        f"Đã tạo client {name}.\n"
        f"Đã tạo route app-{name}.\n"
        f"Đã cài đặt ứng dụng {name} 0.1.0.\n",
    )
    wait_until_served(stack, name, token)
    created = profile_call(stack, "POST", name, token, {"body": "Xin chào"})
    assert created.status == 201, created.body
    mine = json.loads(profile_call(stack, "GET", name, token).body)
    theirs = json.loads(profile_call(stack, "GET", name, stack.app_token(other, name)).body)
    assert [(note["body"], note["owner"]) for note in mine] == [("Xin chào", user.id)]
    assert theirs == []
    assert started(stack, "postgrest") == before
    assert stack.sql(
        f"SELECT version, applied_at IS NOT NULL FROM core.apps WHERE name = '{name}'"
    ) == [["0.1.0", "t"]]
    assert stack.sql(f"SELECT name FROM core.migrations WHERE scope = '{name}'") == [
        ["0001_notes.sql"]
    ]


def test_apply_again_changes_nothing(stack, tmp_path):
    name = new_name()
    app = notes_app(tmp_path / name, name)
    assert plug(stack, app).returncode == 0
    state = database_state(stack, name), keycloak_state(stack, name), route_state(stack, name)

    result = plug(stack, app)

    assert result.returncode == 0, result.stdout + result.stderr
    assert printed_last(
        result.stdout,
        "Không có file SQL mới.\n"
        "Không có thay đổi trên Keycloak.\n"
        "Không có thay đổi trên APISIX.\n"
        f"Đã cài đặt ứng dụng {name} 0.1.0.\n",
    )
    assert (
        database_state(stack, name),
        keycloak_state(stack, name),
        route_state(stack, name),
    ) == state


def test_files_run_as_role_of_app_which_logs_in_only_during_apply(stack, tmp_path):
    name = new_name()
    schema = schema_of(name)

    result = plug(stack, notes_app(tmp_path / name, name, files={"0002_who.sql": WHO_SQL}))

    assert result.returncode == 0, result.stdout + result.stderr
    assert stack.sql(f"SELECT who_current, who_session, could_log_in FROM {schema}.who") == [
        [schema, schema, "t"]
    ]
    assert stack.sql(
        "SELECT rolcanlogin, rolpassword IS NULL, rolsuper FROM pg_authid "
        f"WHERE rolname = '{schema}'"
    ) == [["f", "t", "f"]]
    assert stack.sql(f"SELECT count(*) FROM pg_stat_activity WHERE usename = '{schema}'") == [["0"]]


def test_functions_of_app_run_as_its_user_role_and_keep_their_grants(stack, tmp_path):
    name = new_name()
    schema = schema_of(name)
    files = {"0002_total.sql": TOTAL_SQL + OWNER_TOTAL_SQL.format(schema=schema)}

    result = plug(stack, notes_app(tmp_path / name, name, files=files))

    assert result.returncode == 0, result.stdout + result.stderr
    assert stack.sql(
        "SELECT p.proname, p.prosecdef, p.proowner::regrole, "
        f"has_function_privilege('{schema}_user', p.oid, 'EXECUTE'), "
        "has_function_privilege('authenticated', p.oid, 'EXECUTE'), "
        "has_function_privilege('anon', p.oid, 'EXECUTE') "
        f"FROM pg_proc p WHERE p.pronamespace = '{schema}'::regnamespace ORDER BY p.proname"
    ) == [
        ["owner_total", "t", schema, "t", "f", "f"],
        ["total", "t", f"{schema}_user", "f", "f", "f"],
    ]


def test_changed_file_stops_apply_and_keeps_last_good_version(stack, tmp_path):
    name = new_name()
    app = notes_app(tmp_path / name, name)
    assert plug(stack, app).returncode == 0
    notes = app / "database" / "0001_notes.sql"
    notes.write_text(notes.read_text(encoding="utf-8") + "-- sửa\n", encoding="utf-8")
    (app / "database" / "0002_tags.sql").write_text("CREATE TABLE tags (id int);\n")

    result = plug(stack, app)

    copied = stack.home / "apps" / name / "database"
    assert result.returncode == 1, result.stdout + result.stderr
    assert printed_last(
        result.stdout,
        "File 0001_notes.sql đã được chạy trước đó nhưng nội dung đã thay đổi. "
        "Mỗi thay đổi của cơ sở dữ liệu cần được viết thành một file SQL mới.\n",
    )
    assert not table_exists(stack, schema_of(name), "tags")
    assert sorted(path.name for path in copied.iterdir()) == ["0001_notes.sql"]
    assert "-- sửa" not in (copied / "0001_notes.sql").read_text(encoding="utf-8")


@pytest.mark.parametrize("refused", list(REFUSED_FILES))
def test_refused_file_is_rolled_back_and_last_good_version_kept(stack, plugged, tmp_path, refused):
    app = tmp_path / plugged.name
    shutil.copytree(plugged.folder, app)
    manifest = json.loads((app / "saigonos-app.json").read_text(encoding="utf-8"))
    manifest["version"] = "0.2.0"
    (app / "saigonos-app.json").write_text(json.dumps(manifest), encoding="utf-8")
    text = REFUSED_FILES[refused].format(
        own=schema_of(plugged.name), other=schema_of(plugged.other)
    )
    (app / "database" / "0002_extra.sql").write_text(f"CREATE TABLE extra (id int);\n{text}\n")

    result = plug(stack, app)

    kept = stack.home / "apps" / plugged.name / "saigonos-app.json"
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Không chạy được file 0002_extra.sql" in result.stdout
    assert "Mọi thay đổi của file này đã được hủy." in result.stdout
    assert not table_exists(stack, schema_of(plugged.name), "extra")
    assert stack.sql(f"SELECT name FROM core.migrations WHERE scope = '{plugged.name}'") == [
        ["0001_notes.sql"]
    ]
    assert stack.sql(f"SELECT version FROM core.apps WHERE name = '{plugged.name}'") == [["0.1.0"]]
    assert json.loads(kept.read_text(encoding="utf-8"))["version"] == "0.1.0"


def test_schema_made_by_hand_is_not_taken_over(stack, tmp_path):
    name = new_name()
    schema = schema_of(name)
    stack.sql(f"CREATE SCHEMA {schema}")

    result = plug(stack, notes_app(tmp_path / name, name))

    assert result.returncode == 1, result.stdout + result.stderr
    assert printed_last(
        result.stdout,
        f"Role hoặc schema {schema} đã có trong cơ sở dữ liệu nhưng không do SaigonOS tạo "
        f"cho ứng dụng {name}. Hãy đặt tên khác cho ứng dụng.\n",
    )
    assert not (stack.home / "apps" / name).exists()
    assert stack.sql(f"SELECT count(*) FROM core.apps WHERE name = '{name}'") == [["0"]]
    assert keycloak_client(stack, name) == []


def test_app_named_after_user_role_of_another_app_is_refused(stack, plugged, tmp_path):
    name = f"{plugged.name}-user"

    result = plug(stack, notes_app(tmp_path / name, name))

    assert result.returncode == 1, result.stdout + result.stderr
    assert printed_last(
        result.stdout,
        f"Role hoặc schema {schema_of(name)} đã có trong cơ sở dữ liệu nhưng không do SaigonOS "
        f"tạo cho ứng dụng {name}. Hãy đặt tên khác cho ứng dụng.\n",
    )
    assert stack.sql(f"SELECT count(*) FROM core.apps WHERE name = '{name}'") == [["0"]]


def test_apply_creates_roles_and_public_client_with_code_flow_and_pkce_only(stack, tmp_path):
    name = new_name()
    roles = [f"{name}.nguoi-dung", f"{name}.quan-ly"]
    endpoint = f"{stack.url}/auth/realms/saigonos/protocol/openid-connect"

    result = plug(stack, notes_app(tmp_path / name, name, roles=("nguoi-dung", "quan-ly")))

    assert result.returncode == 0, result.stdout + result.stderr
    state = keycloak_state(stack, name)
    flags = ("publicClient", "standardFlowEnabled", "implicitFlowEnabled")
    flags += ("directAccessGrantsEnabled", "serviceAccountsEnabled", "fullScopeAllowed")
    assert [state["client"][flag] for flag in flags] == [True, True, False, False, False, False]
    assert state["client"]["redirectUris"] == [f"{stack.url}/apps/{name}/*"]
    assert state["client"]["attributes"]["pkce.code.challenge.method"] == "S256"
    assert state["client"]["attributes"]["saigonos.app"] == name
    assert state["realm"] == ["authenticated", *roles]
    assert (state["clients"], state["mappers"], state["optional"]) == ({}, [], [])
    assert state["default"] == ["acr", "basic", "email", "profile", "roles", "web-origins"]
    for role in roles:
        found = admin_json(stack, f"/roles/{role}")
        description = f"Vai trò {role.split('.')[1]}"
        assert (found["description"], found["attributes"]) == (
            description,
            {"saigonos.app": [name]},
        )
    user = user_with_roles(stack, *roles)
    form = {"grant_type": "password", "client_id": name}
    form |= {"username": user.name, "password": user.password}
    password = stack.call("POST", f"{endpoint}/token", form=form)
    query = {"client_id": name, "response_type": "code", "scope": "openid"}
    without_pkce = stack.call(
        "GET", f"{endpoint}/auth?{urlencode(query | {'redirect_uri': f'{stack.url}/apps/{name}/'})}"
    )
    elsewhere = stack.call(
        "GET",
        f"{endpoint}/auth?{urlencode(query | {'redirect_uri': f'{stack.url}/apps/{name}x/'})}",
    )
    assert (password.status, json.loads(password.body)["error"]) == (400, "unauthorized_client")
    assert parse_qs(urlsplit(without_pkce.headers["Location"]).query)["error"] == [
        "invalid_request"
    ]
    assert elsewhere.status == 400


def test_token_of_app_carries_only_roles_of_that_app(stack, plugged):
    user = user_with_roles(stack, f"{plugged.name}.nguoi-dung", f"{plugged.other}.nguoi-dung")

    claims = claims_of(stack.app_token(user, plugged.other))

    assert claims["azp"] == plugged.other
    roles = sorted(claims["realm_access"]["roles"])
    assert roles == ["authenticated", f"{plugged.other}.nguoi-dung"]
    assert "resource_access" not in claims


def test_schema_of_app_takes_only_access_token_of_its_client(stack, plugged):
    user = user_with_roles(stack, f"{plugged.name}.nguoi-dung", f"{plugged.other}.nguoi-dung")
    own = stack.app_token(user, plugged.name)
    tokens = {
        "ung-dung-khac": stack.app_token(user, plugged.other),
        "client-khac": stack.token(user),
    }
    wait_until_served(stack, plugged.name, own)

    replies = {
        (source, method): profile_call(
            stack, method, plugged.name, token, {"body": "Ghi lén"} if method == "POST" else None
        )
        for source, token in tokens.items()
        for method in ("GET", "POST")
    }

    details = (
        f"Schema {schema_of(plugged.name)} chỉ nhận access token được cấp cho client {plugged.name}"
    )
    refused = {
        key: (reply.status, json.loads(reply.body)["code"], json.loads(reply.body)["details"])
        for key, reply in replies.items()
    }
    assert refused == dict.fromkeys(replies, (403, "SGN02", details))
    assert profile_call(stack, "GET", plugged.name, own).status == 200
    assert stack.api(tokens["ung-dung-khac"]).status == 200
    written = f"SELECT count(*) FROM {schema_of(plugged.name)}.notes WHERE body = 'Ghi lén'"
    assert stack.sql(written) == [["0"]]


def test_call_without_token_into_schema_of_app_still_runs_as_anon(stack, tmp_path):
    name = new_name()
    files = {"0002_board.sql": BOARD_SQL.format(schema=schema_of(name))}
    assert plug(stack, notes_app(tmp_path / name, name, files=files)).returncode == 0
    wait_until_served(stack, name, None, table="board")

    anonymous = profile_call(stack, "GET", name, None, table="board")
    foreign = profile_call(stack, "GET", name, stack.token(stack.new_user()), table="board")

    assert (anonymous.status, json.loads(anonymous.body)) == (200, [])
    assert foreign.status == 403


def rpc(stack, name, token, function, body):
    return profile_call(stack, "POST", name, token, body, table=f"rpc/{function}")


def outcome(reply):
    found = json.loads(reply.body)
    return reply.status, found if reply.status == 200 else found["message"]


def test_function_of_app_cannot_pass_itself_off_as_another_user(stack, tmp_path):
    name = new_name()
    forgery = FORGERY_SQL.format(schema=schema_of(name), app=name)
    result = plug(stack, notes_app(tmp_path / name, name, files={"0002_forgery.sql": forgery}))
    assert result.returncode == 0, result.stdout + result.stderr
    victim, thief = stack.new_user(), stack.new_user()
    victim_token, thief_token = stack.app_token(victim, name), stack.app_token(thief, name)
    wait_until_served(stack, name, victim_token)
    assert profile_call(stack, "POST", name, victim_token, {"body": "Bí mật"}).status == 201
    kept = rpc(stack, name, victim_token, "keep_claims", {})
    assert kept.status in (200, 204), kept.body

    replies = {
        function: rpc(stack, name, thief_token, function, {"victim": victim.id})
        for function in (
            "forged_uid",
            "read_with_set_config",
            "read_with_set_local",
            "read_after_pre_request",
            "read_after_seal",
        )
    }
    replies["read_with_kept_claims"] = rpc(stack, name, thief_token, "read_with_kept_claims", {})

    refused = (403, "Hàm core.seal_claims() chỉ dành cho PostgREST và service core")
    assert {function: outcome(reply) for function, reply in replies.items()} == {
        "forged_uid": (200, None),
        "read_with_set_config": (403, "permission denied for function set_config"),
        "read_with_set_local": (200, 0),
        "read_after_pre_request": refused,
        "read_after_seal": refused,
        "read_with_kept_claims": (200, 0),
    }
    own = json.loads(profile_call(stack, "GET", name, victim_token).body)
    assert [(note["body"], note["owner"]) for note in own] == [("Bí mật", victim.id)]


def test_function_of_app_cannot_read_another_app_even_rows_of_caller(stack, plugged, tmp_path):
    name = new_name()
    schema, other = schema_of(name), schema_of(plugged.other)
    cross = CROSS_SQL.format(schema=schema, other=other)
    result = plug(stack, notes_app(tmp_path / name, name, files={"0002_cross.sql": cross}))
    assert result.returncode == 0, result.stdout + result.stderr
    user = stack.new_user()
    own, theirs = stack.app_token(user, name), stack.app_token(user, plugged.other)
    wait_until_served(stack, name, own)
    wait_until_served(stack, plugged.other, theirs)
    assert profile_call(stack, "POST", plugged.other, theirs, {"body": "Của B"}).status == 201
    assert profile_call(stack, "POST", name, own, {"body": "Của A"}).status == 201

    calls = [
        ("read_other", lambda: rpc(stack, name, own, "read_other", {})),
        ("switch_role", lambda: rpc(stack, name, own, "switch_role", {})),
        ("switch_by_clause", lambda: rpc(stack, name, own, "switch_by_clause", {})),
        ("switched", lambda: profile_call(stack, "GET", name, own, table="switched")),
        ("make_invoker", lambda: rpc(stack, name, own, "make_invoker", {})),
        ("switch_role_again", lambda: rpc(stack, name, own, "switch_role", {})),
        ("own_count", lambda: rpc(stack, name, own, "own_count", {})),
    ]
    replies = {label: outcome(call()) for label, call in calls}

    definer = 'cannot set parameter "role" within security-definer function'
    assert replies == {
        "read_other": (403, f"permission denied for schema {other}"),
        "switch_role": (403, definer),
        "switch_by_clause": (403, definer),
        "switched": (403, "permission denied for function set_config"),
        "make_invoker": (
            403,
            "Lệnh ALTER FUNCTION chỉ chạy được trong file SQL khi cài đặt ứng dụng",
        ),
        "switch_role_again": (403, definer),
        "own_count": (200, 1),
    }
    assert stack.sql(
        f"SELECT prosecdef, proowner::regrole FROM pg_proc WHERE oid = '{schema}.switch_role()'"
        "::regprocedure"
    ) == [["t", f"{schema}_user"]]
    mine = json.loads(profile_call(stack, "GET", plugged.other, theirs).body)
    assert [note["body"] for note in mine] == ["Của B"]


def test_client_and_role_edited_in_admin_console_are_put_back_by_apply(stack, tmp_path):
    name = new_name()
    app = notes_app(tmp_path / name, name)
    assert plug(stack, app).returncode == 0
    state = keycloak_state(stack, name)
    path = f"/clients/{state['client']['id']}"
    flows = {flow["alias"]: flow["id"] for flow in admin_json(stack, "/authentication/flows")}
    scopes = {scope["name"]: scope["id"] for scope in admin_json(stack, "/client-scopes")}
    admin = admin_json(stack, "/roles/admin")
    [management] = keycloak_client(stack, "realm-management")
    realm_admin = admin_json(stack, f"/clients/{management['id']}/roles/realm-admin")
    settings = {
        "publicClient": False,
        "directAccessGrantsEnabled": True,
        "fullScopeAllowed": True,
        "redirectUris": ["*"],
        "webOrigins": ["*"],
        "attributes": {"pkce.code.challenge.method": "plain"},
        "authenticationFlowBindingOverrides": {"browser": flows["browser"]},
    }
    mapper = {
        "name": "gia",
        "protocol": "openid-connect",
        "protocolMapper": "oidc-hardcoded-claim-mapper",
        "config": {
            "claim.name": "realm_access",
            "claim.value": '{"roles": ["admin"]}',
            "jsonType.label": "JSON",
            "access.token.claim": "true",
        },
    }
    role = f"/roles/{name}.nguoi-dung"
    edits = [
        ("PUT", path, settings),
        ("POST", f"{path}/protocol-mappers/models", mapper),
        ("POST", f"{path}/scope-mappings/realm", [admin]),
        ("POST", f"{path}/scope-mappings/clients/{management['id']}", [realm_admin]),
        ("PUT", f"{path}/optional-client-scopes/{scopes['offline_access']}", None),
        ("DELETE", f"{path}/default-client-scopes/{scopes['profile']}", None),
        ("PUT", role, {"name": f"{name}.nguoi-dung", "description": "Sửa tay"}),
        ("POST", f"{role}/composites", [admin]),
    ]
    for method, target, body in edits:
        reply = stack.admin(method, target, body)
        assert reply.status in (201, 204), (target, reply.body)
    assert keycloak_state(stack, name) != state

    result = plug(stack, app)

    assert result.returncode == 0, result.stdout + result.stderr
    assert printed_last(
        result.stdout,
        "Không có file SQL mới.\n"
        f"Đã cập nhật realm role {name}.nguoi-dung.\n"
        f"Đã cập nhật client {name}.\n"
        "Không có thay đổi trên APISIX.\n"
        f"Đã cài đặt ứng dụng {name} 0.1.0.\n",
    )
    assert keycloak_state(stack, name) == state


def test_names_made_by_hand_on_keycloak_are_not_taken_over(stack, tmp_path):
    name = new_name()
    client = {"clientId": name, "publicClient": True, "directAccessGrantsEnabled": True}
    assert stack.admin("POST", "/clients", client).status == 201
    assert stack.admin("POST", "/roles", {"name": f"{name}.nguoi-dung"}).status == 201
    before = keycloak_client(stack, name)

    result = plug(stack, notes_app(tmp_path / name, name))

    assert result.returncode == 1, result.stdout + result.stderr
    assert printed_last(
        result.stdout,
        f"Client {name} và realm role {name}.nguoi-dung đã có trong Keycloak nhưng không do "
        f"SaigonOS tạo cho ứng dụng {name}. Hãy đặt tên khác cho ứng dụng.\n",
    )
    assert keycloak_client(stack, name) == before
    assert not admin_json(stack, f"/roles/{name}.nguoi-dung").get("attributes")
    assert stack.sql(
        f"SELECT (SELECT count(*) FROM core.apps WHERE name = '{name}'), "
        f"(SELECT count(*) FROM pg_namespace WHERE nspname = '{schema_of(name)}')"
    ) == [["0", "0"]]
    assert not (stack.home / "apps" / name).exists()


def test_role_left_out_of_new_version_is_kept_but_leaves_tokens_of_app(stack, tmp_path):
    name = new_name()
    first = notes_app(tmp_path / "dau" / name, name, roles=("nguoi-dung", "quan-ly"))
    assert plug(stack, first).returncode == 0
    user = user_with_roles(stack, f"{name}.nguoi-dung", f"{name}.quan-ly")

    result = plug(stack, notes_app(tmp_path / "sau" / name, name, version="0.2.0"))

    assert result.returncode == 0, result.stdout + result.stderr
    assert printed_last(
        result.stdout,
        f"Không có file SQL mới.\nĐã cập nhật client {name}.\n"
        f"Không có thay đổi trên APISIX.\nĐã cài đặt ứng dụng {name} 0.2.0.\n",
    )
    roles = sorted(claims_of(stack.app_token(user, name))["realm_access"]["roles"])
    assert roles == ["authenticated", f"{name}.nguoi-dung"]
    kept = admin_json(stack, f"/roles/{name}.quan-ly")
    assert kept["attributes"] == {"saigonos.app": [name]}


def test_app_copied_into_apps_folder_is_plugged_with_docker_compose(stack):
    name = new_name()
    notes_app(stack.home / "apps" / name, name)

    result = run_apps(stack, "apply", name)

    assert result.returncode == 0, result.stdout + result.stderr
    assert printed_last(result.stdout, f"Đã cài đặt ứng dụng {name} 0.1.0.\n")
    assert table_exists(stack, schema_of(name), "notes")


def test_docker_compose_path_needs_folder_named_after_app(stack):
    name = new_name()
    notes_app(stack.home / "apps" / "sai-ten", name)

    result = run_apps(stack, "apply", "sai-ten")

    assert result.returncode == 1, result.stdout + result.stderr
    assert printed_last(
        result.stdout,
        f"Thư mục sai-ten chứa bản khai của ứng dụng {name}. "
        "Tên thư mục phải trùng tên ứng dụng.\n",
    )


def test_only_role_of_app_records_its_migrations(stack):
    query = "--command=SELECT core.record_migration('0001_gia.sql', 'x')"

    result = stack.exec("postgres", "psql", "--username=postgres", "--dbname=saigonos", query)

    assert result.returncode != 0
    assert "Chỉ role của ứng dụng gọi được hàm core.record_migration" in result.stderr


def test_functions_for_plugging_apps_are_closed_to_other_roles(stack):
    functions = [
        "core.prepare_app(text)",
        "core.open_app_login(text, text)",
        "core.close_app_login(text)",
        "core.finish_app(text, text, text, jsonb, boolean)",
        "core.run_app_sql(text)",
        "core.record_migration(text, text)",
        "core.secure_app()",
        "core.pre_config()",
    ]
    roles = ["anon", "authenticated", "authenticator", "core_service", "workflow", "centrifugo"]

    granted = stack.sql(
        "SELECT r, f FROM unnest(ARRAY['"
        + "', '".join(functions)
        + "']) AS f, unnest(ARRAY['"
        + "', '".join(roles)
        + "']) AS r WHERE has_function_privilege(r, f, 'EXECUTE') ORDER BY r, f"
    )

    assert granted == [["authenticator", "core.pre_config()"]]


def app_call(stack, method, name, path, token=None, body=None, headers=None):
    url = f"{stack.url}/apps/{name}/{path}"
    return stack.call(method, url, token=token, body=body, headers=headers)


@pytest.fixture(scope="module")
def with_ui(stack, tmp_path_factory):
    name = new_name()
    folder = notes_app(tmp_path_factory.mktemp("giao-dien") / name, name, ui=UI)
    result = plug(stack, folder)
    assert result.returncode == 0, result.stdout + result.stderr
    return SimpleNamespace(name=name, folder=folder)


def test_api_of_app_answers_at_its_own_address_without_profile_headers(stack, plugged):
    user = stack.new_user()
    token = stack.app_token(user, plugged.name)
    wait_until_served(stack, plugged.name, token)
    elsewhere = {"Accept-Profile": schema_of(plugged.other), "Content-Profile": "api"}

    created = app_call(stack, "POST", plugged.name, "api/notes", token, {"body": "Route riêng"})
    listed = app_call(stack, "GET", plugged.name, "api/notes", token)
    pointed = app_call(stack, "GET", plugged.name, "api/notes", token, headers=elsewhere)
    foreign = app_call(
        stack, "GET", plugged.name, "api/notes", stack.app_token(user, plugged.other)
    )
    forged = app_call(stack, "GET", plugged.name, "api/notes", "khong.phai.token")

    assert created.status == 201, created.body
    assert [note["body"] for note in json.loads(listed.body)] == ["Route riêng"]
    assert listed.headers["X-RateLimit-Limit"] == "300"
    assert json.loads(pointed.body) == json.loads(listed.body)
    assert (foreign.status, json.loads(foreign.body)["code"]) == (403, "SGN02")
    assert forged.status == 401


def test_api_document_of_app_lists_only_its_own_tables(stack, plugged):
    token = stack.app_token(stack.new_user(), plugged.name)
    wait_until_served(stack, plugged.name, token)

    reply = app_call(stack, "GET", plugged.name, "api/", token)

    document = json.loads(reply.body)
    assert reply.status == 200, reply.body
    assert set(document["paths"]) == {"/", "/notes"}
    assert set(document["definitions"]) == {"notes"}
    assert document["basePath"] == f"/apps/{plugged.name}/api"
    assert json.loads(stack.api(token).body)["basePath"] == "/api"


def test_route_edited_by_hand_is_put_back_by_apply(stack, tmp_path):
    name = new_name()
    app = notes_app(tmp_path / name, name)
    assert plug(stack, app).returncode == 0
    state = route_state(stack, name)
    edited = copy.deepcopy(state)
    del edited["plugins"]["openid-connect"]
    edited["plugins"]["limit-count"]["count"] = 100000
    edited["plugins"]["proxy-rewrite"]["headers"]["set"]["Accept-Profile"] = "api"
    edited["uris"].append("/khac/*")
    assert stack.gateway_admin("PUT", f"/routes/app-{name}", edited).status == 200
    assert route_state(stack, name) != state

    result = plug(stack, app)

    assert result.returncode == 0, result.stdout + result.stderr
    assert printed_last(
        result.stdout,
        "Không có file SQL mới.\n"
        "Không có thay đổi trên Keycloak.\n"
        f"Đã cập nhật route app-{name}.\n"
        f"Đã cài đặt ứng dụng {name} 0.1.0.\n",
    )
    assert route_state(stack, name) == state


def test_route_made_by_hand_is_not_taken_over(stack, tmp_path):
    name = new_name()
    upstream = {"type": "roundrobin", "nodes": {"core:8000": 1}}
    route = {"uris": [f"/apps/{name}/api/*"], "upstream": upstream}
    made = stack.gateway_admin("PUT", f"/routes/app-{name}", route)
    assert made.status == 201, made.body

    result = plug(stack, notes_app(tmp_path / name, name))

    stack.gateway_admin("DELETE", f"/routes/app-{name}")
    assert result.returncode == 1, result.stdout + result.stderr
    assert printed_last(
        result.stdout,
        f"Route app-{name} đã có trong APISIX nhưng không do SaigonOS tạo "
        f"cho ứng dụng {name}. Hãy đặt tên khác cho ứng dụng.\n",
    )
    assert stack.sql(f"SELECT count(*) FROM core.apps WHERE name = '{name}'") == [["0"]]
    assert keycloak_client(stack, name) == []


def test_ui_of_app_is_served_with_security_headers(stack, with_ui):
    page = app_call(stack, "GET", with_ui.name, "")
    script = app_call(stack, "GET", with_ui.name, "app.js")
    again = app_call(
        stack, "GET", with_ui.name, "app.js", headers={"If-None-Match": script.headers["ETag"]}
    )
    deep = app_call(stack, "GET", with_ui.name, "ghi-chu/12")
    missing = app_call(stack, "GET", with_ui.name, "thieu.js")
    hidden = app_call(stack, "GET", with_ui.name, ".bi-mat")
    bare = stack.call("GET", f"{stack.url}/apps/{with_ui.name}")

    assert (page.status, page.body.decode()) == (200, PAGE)
    assert page.headers["Content-Type"] == "text/html; charset=utf-8"
    assert page.headers["Cache-Control"] == "no-store"
    assert page.headers["Content-Security-Policy"].startswith("default-src 'self'; ")
    assert page.headers["X-Content-Type-Options"] == "nosniff"
    assert page.headers["Referrer-Policy"] == "same-origin"
    assert (script.status, script.body.decode()) == (200, SCRIPT)
    assert script.headers["Content-Type"] == "text/javascript; charset=utf-8"
    assert script.headers["Cache-Control"] == "no-cache"
    assert again.status == 304
    assert (deep.status, deep.body.decode()) == (200, PAGE)
    assert (missing.status, hidden.status) == (404, 404)
    assert (bare.status, bare.headers["Location"]) == (308, f"/apps/{with_ui.name}/")


@pytest.mark.parametrize(
    "path",
    [
        "..%2fsaigonos-app.json",
        "%2e%2e/saigonos-app.json",
        "%2e%2e%2fsaigonos-app.json",
        ".%2e/saigonos-app.json",
        "css/%2e%2e/%2e%2e/saigonos-app.json",
        "css/..%2f..%2fsaigonos-app.json",
    ],
)
def test_path_with_dot_dot_is_not_found(stack, with_ui, path):
    reply = app_call(stack, "GET", with_ui.name, path)

    assert reply.status == 404, reply.body
    assert with_ui.name.encode() not in reply.body


def test_ui_of_app_not_installed_is_not_found(stack):
    name = new_name()
    notes_app(stack.home / "apps" / name, name, ui=UI)

    copied = app_call(stack, "GET", name, "")
    unknown = app_call(stack, "GET", new_name(), "index.html")

    assert (copied.status, unknown.status) == (404, 404)


def readme_block(language, marker):
    blocks = re.findall(rf"```{language}\n(.*?)```", README, re.DOTALL)
    return next(block for block in blocks if marker in block)


def test_readme_example_app_is_plugged_and_serves_its_table(stack, tmp_path):
    manifest = json.loads(readme_block("json", '"roles"')) | {"processes": None, "ui": None}
    app = tmp_path / manifest["name"]
    (app / "database").mkdir(parents=True)
    sql = readme_block("sql", "CREATE TABLE don")
    (app / "database" / "0001_don.sql").write_text(sql, encoding="utf-8")
    (app / "saigonos-app.json").write_text(json.dumps(manifest), encoding="utf-8")
    user, other = stack.new_user(), stack.new_user()

    result = plug(stack, app)

    assert result.returncode == 0, result.stdout + result.stderr
    token = stack.app_token(user, "nghi-phep")
    wait_until_served(stack, "nghi-phep", token, table="don")
    body = {"ly_do": "Việc gia đình"}
    created = app_call(stack, "POST", "nghi-phep", "api/don", token, body)
    mine = json.loads(app_call(stack, "GET", "nghi-phep", "api/don", token).body)
    theirs = app_call(stack, "GET", "nghi-phep", "api/don", stack.app_token(other, "nghi-phep"))
    assert created.status == 201, created.body
    assert [(item["ly_do"], item["nguoi_gui"]) for item in mine] == [("Việc gia đình", user.id)]
    assert json.loads(theirs.body) == []
