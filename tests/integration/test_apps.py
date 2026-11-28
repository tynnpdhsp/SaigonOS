# SPDX-License-Identifier: Apache-2.0
import base64
import copy
import json
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
MANIFEST = {
    "name": "nghi-phep",
    "title": "Nghỉ phép",
    "version": "0.1.0",
    "roles": [{"name": "nghi-phep.quan-ly", "description": "Duyệt đơn"}],
    "database": "database",
    "processes": "processes",
    "ui": "ui",
}
PROCESS = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                  xmlns:operaton="http://operaton.org/schema/1.0/bpmn"
                  id="duyet_dinh_nghia" targetNamespace="https://dx.example.com/bpmn">
  <bpmn:process id="nghi_phep.duyet" isExecutable="true" operaton:historyTimeToLive="P30D">
    <bpmn:startEvent id="bat_dau" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="hinh">
    <bpmndi:BPMNPlane id="mat_phang" bpmnElement="nghi_phep.duyet">
      <bpmndi:BPMNShape id="bat_dau_hinh" bpmnElement="bat_dau">
        <dc:Bounds x="100" y="80" width="36" height="36" />
      </bpmndi:BPMNShape>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>
"""
FILES = {
    "database/0001_don.sql": "CREATE TABLE nghi_phep.don (id bigint);\n",
    "processes/duyet.bpmn": PROCESS,
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


def notes_app(
    folder,
    name,
    version="0.1.0",
    files=None,
    roles=("nguoi-dung",),
    ui=None,
    access=None,
    search=None,
    archive=None,
    snapshots=None,
):
    manifest = {
        "name": name,
        "title": "Ghi chú thử",
        "version": version,
        "roles": [{"name": f"{name}.{role}", "description": f"Vai trò {role}"} for role in roles],
        "database": "database",
    }
    if access is not None:
        manifest["access"] = access
    if search is not None:
        manifest["search"] = search
    if archive is not None:
        manifest["archive"] = archive
    if snapshots is not None:
        manifest["snapshots"] = snapshots
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


def table_call(stack, method, name, token, body=None, table="notes"):
    return stack.call(method, f"{stack.url}/apps/{name}/api/{table}", token=token, body=body)


def wait_until_served(stack, name, token, table="notes"):
    deadline = time.monotonic() + 15
    while table_call(stack, "GET", name, token, table=table).status != 200:
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
    created = table_call(stack, "POST", name, token, {"body": "Xin chào"})
    assert created.status == 201, created.body
    mine = json.loads(table_call(stack, "GET", name, token).body)
    theirs = json.loads(table_call(stack, "GET", name, stack.app_token(other, name)).body)
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
        "Không có gì thay đổi.\n",
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
        (source, method): table_call(
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
    assert table_call(stack, "GET", plugged.name, own).status == 200
    assert stack.api(tokens["ung-dung-khac"]).status == 200
    written = f"SELECT count(*) FROM {schema_of(plugged.name)}.notes WHERE body = 'Ghi lén'"
    assert stack.sql(written) == [["0"]]


def test_call_without_token_into_schema_of_app_still_runs_as_anon(stack, tmp_path):
    name = new_name()
    files = {"0002_board.sql": BOARD_SQL.format(schema=schema_of(name))}
    assert plug(stack, notes_app(tmp_path / name, name, files=files)).returncode == 0
    wait_until_served(stack, name, None, table="board")

    anonymous = table_call(stack, "GET", name, None, table="board")
    foreign = table_call(stack, "GET", name, stack.token(stack.new_user()), table="board")

    assert (anonymous.status, json.loads(anonymous.body)) == (200, [])
    assert foreign.status == 403


SEARCHED = [{"table": "notes", "columns": ["body"]}]
NOTES_OF_ROWS = """
SET session_replication_role = replica;
INSERT INTO {schema}.notes (body, owner)
SELECT (ARRAY['Máy tính không lên màn hình', 'Bàn phím hỏng phím Enter', 'Chuột không nhận',
    'Mạng chập chờn ở phòng I.201', 'Nguyễn Văn An báo máy chạy chậm'])[1 + n % 5] || ' số ' || n,
    CASE WHEN n % 2 = 0 THEN '{owner}' ELSE 'nguoi-khac' END
FROM generate_series(1, 10000) AS n;
ANALYZE {schema}.notes
"""


def search_call(stack, name, token, text):
    path = f"/apps/{name}/api/rpc/search_notes?{urlencode({'q': text})}"
    return stack.call("GET", f"{stack.url}{path}", token=token)


def bodies(reply):
    assert reply.status == 200, reply.body
    return [note["body"] for note in json.loads(reply.body)]


def test_search_of_app_ignores_marks_ranks_rows_and_keeps_row_security(stack, tmp_path):
    name = new_name()
    result = plug(stack, notes_app(tmp_path / name, name, search=SEARCHED))
    token = stack.app_token(stack.new_user(), name)
    other = stack.app_token(stack.new_user(), name)
    wait_until_served(stack, name, token)
    for body in ("Nguyễn Văn An báo máy hỏng", "Máy hỏng, máy hỏng nặng", "Máy in kẹt giấy"):
        assert table_call(stack, "POST", name, token, {"body": body}).status == 201
    assert (
        table_call(stack, "POST", name, other, {"body": "Nguyễn Văn Bình hỏng máy"}).status == 201
    )

    plain = search_call(stack, name, token, "nguyen van")
    marked = search_call(stack, name, other, "NGUYỄN VĂN")
    ranked = search_call(stack, name, token, "hong")
    phrase = search_call(stack, name, token, '"may hong" -nguyen')

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Đã tạo tìm kiếm cho bảng notes.\n" in result.stdout
    assert bodies(plain) == ["Nguyễn Văn An báo máy hỏng"]
    assert bodies(marked) == ["Nguyễn Văn Bình hỏng máy"]
    assert bodies(ranked) == ["Máy hỏng, máy hỏng nặng", "Nguyễn Văn An báo máy hỏng"]
    assert bodies(phrase) == ["Máy hỏng, máy hỏng nặng"]


def test_search_of_app_stays_on_apply_again_and_goes_when_left_out(stack, tmp_path):
    name = new_name()
    folder = notes_app(tmp_path / name, name, search=SEARCHED)
    assert plug(stack, folder).returncode == 0
    token = stack.app_token(stack.new_user(), name)
    wait_until_served(stack, name, token)

    again = plug(stack, folder)
    without = plug(stack, notes_app(tmp_path / "ban-sau" / name, name, version="0.2.0"))

    assert printed_last(again.stdout, "Không có gì thay đổi.\n")
    assert "Đã gỡ tìm kiếm của bảng notes.\n" in without.stdout
    deadline = time.monotonic() + 15
    while search_call(stack, name, token, "may").status != 404:
        assert time.monotonic() < deadline, "PostgREST vẫn phục vụ hàm tìm kiếm đã gỡ"
        time.sleep(0.2)
    index = f"{schema_of(name)}.saigonos_search_notes"
    assert stack.sql(f"SELECT to_regclass('{index}') IS NULL") == [["t"]]


@pytest.mark.parametrize(
    ("search", "expected"),
    [
        (
            [{"table": "khong_co", "columns": ["body"]}],
            "Mục search khai bảng khong_co, nhưng schema {schema} không có bảng này.",
        ),
        (
            [{"table": "notes", "columns": ["tieu_de"]}],
            "Mục search khai cột tieu_de của bảng notes, nhưng bảng không có cột này.",
        ),
        (
            [{"table": "notes", "columns": ["id"]}],
            "Cột id của bảng notes có kiểu bigint. "
            "Mục search chỉ nhận cột kiểu text, varchar hoặc char.",
        ),
    ],
    ids=["thieu-bang", "thieu-cot", "cot-khong-phai-chu"],
)
def test_search_of_missing_table_or_column_stops_apply(stack, tmp_path, search, expected):
    name = new_name()

    result = plug(stack, notes_app(tmp_path / name, name, search=search))

    assert result.returncode == 1, result.stdout
    assert printed_last(result.stdout, expected.format(schema=schema_of(name)) + "\n")


def test_search_does_not_take_over_function_made_by_app(stack, tmp_path):
    name = new_name()
    own = {"0002_own.sql": "CREATE FUNCTION search_notes(q text) RETURNS bigint RETURN 1;\n"}

    result = plug(stack, notes_app(tmp_path / name, name, files=own, search=SEARCHED))

    assert result.returncode == 1, result.stdout
    assert printed_last(
        result.stdout,
        f"Schema {schema_of(name)} đã có hàm search_notes nhưng không do SaigonOS tạo. "
        "Hãy đổi tên hàm này hoặc bỏ bảng notes khỏi mục search.\n",
    )


def test_search_of_app_answers_within_a_second_on_ten_thousand_rows(stack, tmp_path):
    name = new_name()
    assert plug(stack, notes_app(tmp_path / name, name, search=SEARCHED)).returncode == 0
    user = stack.new_user()
    token = stack.app_token(user, name)
    wait_until_served(stack, name, token)
    stack.sql(NOTES_OF_ROWS.format(schema=schema_of(name), owner=user.id))

    started = time.monotonic()
    reply = search_call(stack, name, token, "man hinh")
    elapsed = time.monotonic() - started

    assert len(bodies(reply)) == 1000
    assert elapsed < 1


LAKE_SQL = """\
CREATE TABLE yeu_cau (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma text,
    diem numeric,
    tao_luc timestamptz NOT NULL
);
ALTER TABLE yeu_cau ENABLE ROW LEVEL SECURITY;
CREATE POLICY khong_ai_doc ON yeu_cau USING (false);
CREATE TRIGGER audit AFTER INSERT OR UPDATE OR DELETE ON yeu_cau
    FOR EACH ROW EXECUTE FUNCTION core.audit();
CREATE VIEW chot_yeu_cau AS SELECT ma, diem, tao_luc FROM yeu_cau;
"""
QUALITY = [
    {"rule": "not_null", "columns": ["ma"]},
    {"rule": "unique", "columns": ["ma"]},
    {"rule": "range", "column": "diem", "min": 1, "max": 5},
]
ARCHIVED = [{"table": "yeu_cau", "column": "tao_luc", "keep_days": 30, "rules": QUALITY}]
FROZEN = [{"view": "chot_yeu_cau", "column": "tao_luc", "rules": QUALITY}]
LOCAL = "'Asia/Ho_Chi_Minh'"
CASCADE_SQL = "CREATE TABLE y_kien (yeu_cau_id bigint REFERENCES yeu_cau ON DELETE CASCADE);\n"
FLIP = """\
import hashlib, io, os, sys
from saigonos_core.storage import Storage
storage = Storage(os.environ["S3_URL"], os.environ["S3_ACCESS_KEY"], os.environ["S3_SECRET_KEY"])
content = io.BytesIO()
storage.get("lake", sys.argv[1], content)
data = bytearray(content.getvalue())
data[len(data) // 2] ^= 1
digest = hashlib.sha256(data).hexdigest()
storage.put("lake", sys.argv[1], io.BytesIO(data), len(data), digest, "application/octet-stream")
"""


def lake_app(stack, tmp_path, archive=None, snapshots=None):
    name = new_name()
    files = {"0002_yeu_cau.sql": LAKE_SQL}
    folder = notes_app(tmp_path / name, name, files=files, archive=archive, snapshots=snapshots)
    result = plug(stack, folder)
    assert result.returncode == 0, result.stdout + result.stderr
    return name


def add_rows(stack, name, rows):
    values = ", ".join(f"({ma}, {diem}, {moment})" for ma, diem, moment in rows)
    stack.sql(f"INSERT INTO {schema_of(name)}.yeu_cau (ma, diem, tao_luc) VALUES {values}")


def month_start(months_ago):
    month = f"date_trunc('month', now() AT TIME ZONE {LOCAL}) - interval '{months_ago} months'"
    return f"(({month}) AT TIME ZONE {LOCAL})"


def period_of(stack, months_ago):
    [[period]] = stack.sql(
        f"SELECT to_char({month_start(months_ago)} AT TIME ZONE {LOCAL}, 'YYYY-MM')"
    )
    return period


def shown(period):
    return f"{period[5:]}/{period[:4]}"


def lineage_of(stack, name, kind):
    columns = "period, rows, file" if kind == "file" else "passed, rows"
    return stack.sql(
        f"SELECT {columns} FROM core.lineage WHERE app = '{name}' AND kind = '{kind}' ORDER BY id"
    )


def lake(stack, *args):
    return stack.saigonos("lake", *args)


def test_old_rows_move_to_lake_by_local_month_and_new_rows_stay(stack, tmp_path):
    name = lake_app(stack, tmp_path, archive=ARCHIVED)
    schema = schema_of(name)
    add_rows(
        stack,
        name,
        [
            ("'YC-1'", "3.5", "'2025-03-10 09:00+07'"),
            ("'YC-2'", "4", "'2025-03-31 23:30+07'"),
            ("'YC-3'", "2.25", "'2025-04-01 00:15+07'"),
            ("'YC-4'", "5", "now()"),
            ("'YC-5'", "1", "now() - interval '1 day'"),
        ],
    )
    old = f"SELECT count(*), sum(diem) FROM {schema}.yeu_cau WHERE tao_luc < '2026-01-01'"
    before = stack.sql(old)

    moved = lake(stack, "run")
    again = lake(stack, "run")
    summed = lake(stack, "query", "--csv", f"SELECT count(*), sum(diem) FROM {schema}.yeu_cau")

    assert moved.returncode == 0, moved.stdout + moved.stderr
    assert (
        f"Đã chuyển 3 dòng cũ của bảng yeu_cau trong ứng dụng {name} xuống hồ dữ liệu, "
        "gồm 2 file.\n"
    ) in moved.stdout
    assert f"ứng dụng {name}" not in again.stdout
    assert stack.sql(f"SELECT ma FROM {schema}.yeu_cau ORDER BY ma") == [["YC-4"], ["YC-5"]]
    assert before == [["3", "9.75"]]
    assert summed.returncode == 0, summed.stdout + summed.stderr
    assert summed.stdout.splitlines()[1:] == ["3,9.75"]
    [[check]] = stack.sql(f"SELECT id FROM core.lineage WHERE app = '{name}' AND kind = 'check'")
    folder = f"archive/{name}/yeu_cau"
    assert lineage_of(stack, name, "file") == [
        ["2025-03", "2", f"{folder}/2025/03/{check}.parquet"],
        ["2025-04", "1", f"{folder}/2025/04/{check}.parquet"],
    ]
    assert stack.sql(
        f"SELECT time_from, time_to FROM core.lineage WHERE app = '{name}' AND period = '2025-04'"
    ) == [["2025-04-01 00:00:00+07", "2025-05-01 00:00:00+07"]]
    assert stack.sql(
        "SELECT count(*) FROM core.audit_log WHERE db_role = 'lake' AND operation = 'DELETE' "
        f"AND table_schema = '{schema}'"
    ) == [["3"]]


def test_old_rows_breaking_quality_rules_stay_until_fixed_and_admin_is_told(stack, tmp_path):
    name = lake_app(stack, tmp_path, archive=ARCHIVED)
    schema = schema_of(name)
    add_rows(
        stack,
        name,
        [
            ("NULL", "3", "'2025-05-02 08:00+07'"),
            ("'YC-9'", "9", "'2025-05-03 08:00+07'"),
            ("'YC-9'", "2", "'2025-05-04 08:00+07'"),
        ],
    )
    [[first, second]] = stack.sql(f"SELECT min(id), min(id) + 1 FROM {schema}.yeu_cau")

    refused = lake(stack, "run")
    rows = stack.sql(f"SELECT count(*) FROM {schema}.yeu_cau")
    stack.sql(f"UPDATE {schema}.yeu_cau SET ma = 'YC-' || id, diem = 3")
    fixed = lake(stack, "run")

    text = (
        f"Chưa chuyển dòng cũ của bảng yeu_cau trong ứng dụng {name} xuống hồ dữ liệu vì dữ liệu "
        "không đạt luật chất lượng. "
        f'Luật not_null của cột ma không đạt ở 1 dòng, ví dụ {{"id": {first}, "ma": null}}. '
        'Luật unique của cột ma không đạt ở 2 dòng, ví dụ {"ma": "YC-9"} có 2 dòng. '
        f"Luật range của cột diem (từ 1 đến 5) không đạt ở 1 dòng, "
        f'ví dụ {{"id": {second}, "diem": 9}}.'
    )
    assert refused.returncode == 1
    assert f"{text}\n" in refused.stdout
    assert rows == [["3"]]
    assert stack.sql(
        f"SELECT channel, title, body FROM core.deliveries WHERE dedup_key LIKE 'lake:{name}:%'"
    ) == [["telegram", f"Dữ liệu của ứng dụng {name} không đạt luật chất lượng", text]]
    assert (
        f"Đã chuyển 3 dòng cũ của bảng yeu_cau trong ứng dụng {name} xuống hồ dữ liệu, "
        "gồm 1 file.\n"
    ) in fixed.stdout
    assert lineage_of(stack, name, "check") == [["f", "3"], ["t", "3"]]


def test_finished_months_are_frozen_once_and_never_overwritten(stack, tmp_path):
    name = lake_app(stack, tmp_path, snapshots=FROZEN)
    schema = schema_of(name)
    add_rows(
        stack,
        name,
        [
            ("'YC-1'", "3", f"{month_start(2)} + interval '3 days'"),
            ("'YC-2'", "4", f"{month_start(2)} + interval '10 days'"),
            ("'YC-3'", "5", month_start(1)),
            ("'YC-4'", "2", "now()"),
        ],
    )
    older, last = period_of(stack, 2), period_of(stack, 1)

    first = lake(stack, "run")
    files = lineage_of(stack, name, "file")
    add_rows(stack, name, [("'YC-5'", "1", f"{month_start(1)} + interval '1 day'")])
    second = lake(stack, "run")
    frozen = lake(
        stack, "query", "--csv", f"SELECT ma FROM snapshots.{schema}.chot_yeu_cau ORDER BY ma"
    )

    where = f"trong ứng dụng {name}"
    assert first.returncode == 0, first.stdout + first.stderr
    assert f"Đã chốt số liệu của chot_yeu_cau tháng {shown(older)} {where}: 2 dòng.\n" in (
        first.stdout
    )
    assert f"Đã chốt số liệu của chot_yeu_cau tháng {shown(last)} {where}: 1 dòng.\n" in (
        first.stdout
    )
    assert f"ứng dụng {name}" not in second.stdout
    folder = f"snapshots/{name}/chot_yeu_cau"
    assert files == [
        [older, "2", f"{folder}/{older}.parquet"],
        [last, "1", f"{folder}/{last}.parquet"],
    ]
    assert lineage_of(stack, name, "file") == files
    assert frozen.stdout.splitlines() == ["ma", "YC-1", "YC-2", "YC-3"]


def test_month_with_row_breaking_rule_is_frozen_only_after_fix_and_admin_is_told(stack, tmp_path):
    name = lake_app(stack, tmp_path, snapshots=FROZEN)
    schema = schema_of(name)
    add_rows(
        stack,
        name,
        [
            ("'YC-1'", "9", f"{month_start(1)} + interval '2 days'"),
            ("'YC-2'", "3", f"{month_start(1)} + interval '3 days'"),
        ],
    )
    period = period_of(stack, 1)
    [[moment]] = stack.sql(
        f"SELECT to_char(({month_start(1)} + interval '2 days') AT TIME ZONE {LOCAL}, "
        "'YYYY-MM-DD\"T\"HH24:MI:SS') || '+07:00'"
    )

    refused = lake(stack, "run")
    files = lineage_of(stack, name, "file")
    stack.sql(f"UPDATE {schema}.yeu_cau SET diem = 4 WHERE ma = 'YC-1'")
    fixed = lake(stack, "run")

    text = (
        f"Chưa chốt số liệu của chot_yeu_cau tháng {shown(period)} trong ứng dụng {name} vì dữ "
        "liệu không đạt luật chất lượng. Luật range của cột diem (từ 1 đến 5) không đạt ở 1 "
        f'dòng, ví dụ {{"diem": 9, "tao_luc": "{moment}"}}.'
    )
    assert refused.returncode == 1
    assert f"{text}\n" in refused.stdout
    assert files == []
    assert stack.sql(
        f"SELECT body FROM core.deliveries WHERE dedup_key LIKE 'lake:{name}:snapshot:%'"
    ) == [[text]]
    assert (
        f"Đã chốt số liệu của chot_yeu_cau tháng {shown(period)} trong ứng dụng {name}: 2 dòng.\n"
    ) in fixed.stdout
    assert lineage_of(stack, name, "check") == [["f", "2"], ["t", "2"]]


@pytest.mark.parametrize(
    ("archive", "snapshots", "files", "expected"),
    [
        (
            [{"table": "khong_co", "column": "tao_luc", "keep_days": 1}],
            None,
            {},
            "Mục archive khai bảng khong_co, nhưng schema {schema} không có bảng này.",
        ),
        (
            [{"table": "yeu_cau", "column": "ma", "keep_days": 1}],
            None,
            {},
            "Cột ma của bảng yeu_cau có kiểu text. "
            "Cột thời gian phải có kiểu timestamptz, timestamp hoặc date.",
        ),
        (
            None,
            [
                {
                    "view": "chot_yeu_cau",
                    "column": "tao_luc",
                    "rules": [QUALITY[0] | {"columns": ["so"]}],
                }
            ],
            {},
            "Mục snapshots khai cột so của chot_yeu_cau, nhưng chot_yeu_cau không có cột này.",
        ),
        (
            ARCHIVED,
            None,
            {"0003_y_kien.sql": CASCADE_SQL},
            "Bảng yeu_cau được bảng {schema}.y_kien tham chiếu với ON DELETE CASCADE. Khi dòng cũ "
            "được chuyển xuống hồ, dòng của bảng {schema}.y_kien bị đổi theo mà không được lưu vào "
            "hồ. Hãy đổi khóa ngoại sang ON DELETE RESTRICT hoặc bỏ bảng yeu_cau khỏi mục archive.",
        ),
    ],
    ids=["thieu-bang", "cot-thoi-gian-la-chu", "thieu-cot-cua-luat", "khoa-ngoai-cascade"],
)
def test_lake_entries_not_matching_database_stop_apply(
    stack, tmp_path, archive, snapshots, files, expected
):
    name = new_name()
    sql = {"0002_yeu_cau.sql": LAKE_SQL} | files
    folder = notes_app(tmp_path / name, name, files=sql, archive=archive, snapshots=snapshots)

    result = plug(stack, folder)

    assert result.returncode == 1, result.stdout
    assert printed_last(result.stdout, expected.format(schema=schema_of(name)) + "\n")


def test_lake_role_gets_only_declared_rights_and_loses_them_when_left_out(stack, tmp_path):
    name = new_name()
    schema = schema_of(name)
    files = {"0002_yeu_cau.sql": LAKE_SQL}
    rights = (
        f"SELECT has_table_privilege('lake', '{schema}.yeu_cau', 'SELECT'), "
        f"has_table_privilege('lake', '{schema}.yeu_cau', 'DELETE'), "
        f"has_table_privilege('lake', '{schema}.chot_yeu_cau', 'SELECT'), "
        f"has_table_privilege('lake', '{schema}.notes', 'SELECT'), "
        f"has_schema_privilege('lake', '{schema}', 'USAGE')"
    )

    first = plug(
        stack, notes_app(tmp_path / name, name, files=files, archive=ARCHIVED, snapshots=FROZEN)
    )
    granted = stack.sql(rights)
    later = plug(stack, notes_app(tmp_path / "sau" / name, name, version="0.2.0", files=files))

    assert first.returncode == 0, first.stdout + first.stderr
    assert "Đã bật lưu trữ cho bảng yeu_cau.\nĐã bật chốt số liệu cho chot_yeu_cau.\n" in (
        first.stdout
    )
    assert granted == [["t", "t", "t", "f", "t"]]
    assert later.returncode == 0, later.stdout + later.stderr
    assert "Đã tắt lưu trữ của bảng yeu_cau.\nĐã tắt chốt số liệu của chot_yeu_cau.\n" in (
        later.stdout
    )
    assert stack.sql(rights) == [["f", "f", "f", "f", "f"]]


@pytest.mark.parametrize(
    "text",
    ["SELECT * FROM read_csv('/etc/passwd')", "INSTALL httpfs"],
    ids=["doc-file", "cai-extension"],
)
def test_lake_query_cannot_reach_files_or_network_of_server(stack, text):
    result = lake(stack, "query", text)

    assert result.returncode == 1
    assert result.stdout.startswith("Câu truy vấn bị lỗi: Permission Error: ")


def flip_byte(stack, key):
    result = stack.exec("core", "python", "-c", FLIP, key)
    assert result.returncode == 0, result.stdout + result.stderr


def test_changing_one_byte_of_a_lake_file_is_found_by_verify_and_blocks_query(stack, tmp_path):
    name = lake_app(stack, tmp_path, snapshots=FROZEN)
    add_rows(stack, name, [("'YC-1'", "3", f"{month_start(1)} + interval '1 day'")])
    frozen = lake(stack, "run")
    [[_, _, key]] = lineage_of(stack, name, "file")
    clean = lake(stack, "verify")

    flip_byte(stack, key)
    try:
        changed = lake(stack, "verify")
        refused = lake(stack, "query", "SELECT 1")
    finally:
        flip_byte(stack, key)
    restored = lake(stack, "verify")

    assert f"trong ứng dụng {name}: 1 dòng.\n" in frozen.stdout
    assert clean.returncode == 0, clean.stdout
    assert clean.stdout.endswith("Mã băm của mọi file khớp với phả hệ.\n")
    assert changed.returncode == 1
    assert f"File {key} không khớp mã băm trong phả hệ. Nội dung file đã bị sửa.\n" in (
        changed.stdout
    )
    assert refused.returncode == 1
    assert f"File {key} không khớp mã băm trong phả hệ nên không được đọc." in refused.stdout
    assert restored.returncode == 0, restored.stdout


def rpc(stack, name, token, function, body):
    return table_call(stack, "POST", name, token, body, table=f"rpc/{function}")


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
    assert table_call(stack, "POST", name, victim_token, {"body": "Bí mật"}).status == 201
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
    own = json.loads(table_call(stack, "GET", name, victim_token).body)
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
    assert table_call(stack, "POST", plugged.other, theirs, {"body": "Của B"}).status == 201
    assert table_call(stack, "POST", name, own, {"body": "Của A"}).status == 201

    calls = [
        ("read_other", lambda: rpc(stack, name, own, "read_other", {})),
        ("switch_role", lambda: rpc(stack, name, own, "switch_role", {})),
        ("switch_by_clause", lambda: rpc(stack, name, own, "switch_by_clause", {})),
        ("switched", lambda: table_call(stack, "GET", name, own, table="switched")),
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
    mine = json.loads(table_call(stack, "GET", plugged.other, theirs).body)
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
        f"Đã cập nhật realm role {name}.nguoi-dung.\n"
        f"Đã cập nhật client {name}.\n"
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
        f"Đã cập nhật client {name}.\nĐã cài đặt ứng dụng {name} 0.2.0.\n",
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
    folder = notes_app(stack.home / "apps" / "sai-ten", name)

    result = run_apps(stack, "apply", "sai-ten")

    shutil.rmtree(folder)
    assert result.returncode == 1, result.stdout + result.stderr
    assert printed_last(
        result.stdout,
        f"Thư mục sai-ten chứa bản khai báo của ứng dụng {name}. "
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
        "core.apply_search(text, jsonb)",
        "core.apply_lake(text, jsonb, jsonb)",
        "core.check_lake_entry(text, oid, text, jsonb, text)",
        "core.pre_config()",
    ]
    roles = [
        "anon",
        "authenticated",
        "authenticator",
        "core_service",
        "workflow",
        "centrifugo",
        "lake",
    ]

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
        f"Đã cập nhật route app-{name}.\nĐã cài đặt ứng dụng {name} 0.1.0.\n",
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
def test_path_with_dot_dot_is_blocked_at_gateway(stack, with_ui, path):
    reply = app_call(stack, "GET", with_ui.name, path)

    assert reply.status == 403, reply.body
    assert json.loads(reply.body)["code"] == "SGN04"
    assert with_ui.name.encode() not in reply.body


def test_ui_of_app_not_installed_is_not_found(stack):
    name = new_name()
    folder = notes_app(stack.home / "apps" / name, name, ui=UI)

    copied = app_call(stack, "GET", name, "")
    unknown = app_call(stack, "GET", new_name(), "index.html")

    shutil.rmtree(folder)
    assert (copied.status, unknown.status) == (404, 404)


ENGINE = "http://127.0.0.1:8080/operaton/engine-rest"
RESULT_SQL = """\
CREATE TABLE ket_qua (
    noi_dung text NOT NULL,
    ket_qua text NOT NULL,
    nguoi_gui text NOT NULL,
    nguoi_chay text NOT NULL
);
GRANT INSERT ON ket_qua TO {schema}_user;
CREATE FUNCTION ghi_ket_qua(bien jsonb) RETURNS jsonb LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO {schema}.ket_qua
    VALUES (bien ->> 'noi_dung', bien ->> 'ket_qua', bien ->> 'initiator', current_user);
    PERFORM core.send_email(
        'nguoi-gui@example.com', '{schema}-' || (bien ->> 'noi_dung'), 'Yêu cầu đã được xử lý'
    );
    PERFORM core.notify(bien ->> 'initiator', 'xong-' || (bien ->> 'noi_dung'), 'Đã xử lý xong');
    PERFORM core.publish('role:{app}.xu-ly', jsonb_build_object('xong', bien ->> 'noi_dung'));
    RETURN jsonb_build_object('da_ghi', true);
END $$;
GRANT EXECUTE ON FUNCTION ghi_ket_qua(jsonb) TO workflow;
"""
REQUIRED_FIELD = """\
      <bpmn:extensionElements>
        <operaton:formData>
          <operaton:formField id="{field}" label="{label}" type="string">
            <operaton:validation>
              <operaton:constraint name="required" />
            </operaton:validation>
          </operaton:formField>
        </operaton:formData>
      </bpmn:extensionElements>
"""
STEP_TASK = """\
    <bpmn:serviceTask id="ghi" name="Ghi kết quả" operaton:type="external"
                      operaton:topic="saigonos-function">
      <bpmn:extensionElements>
        <operaton:properties>
          <operaton:property name="function" value="{function}" />
        </operaton:properties>
      </bpmn:extensionElements>
    </bpmn:serviceTask>
"""


def picture(key, nodes):
    shapes, edges = [], []
    for index, node in enumerate(nodes):
        shapes.append(
            f'      <bpmndi:BPMNShape id="{node}_hinh" bpmnElement="{node}">\n'
            f'        <dc:Bounds x="{100 + 160 * index}" y="80" width="100" height="80" />\n'
            "      </bpmndi:BPMNShape>\n"
        )
    for index in range(1, len(nodes)):
        start = 200 + 160 * (index - 1)
        edges.append(
            f'      <bpmndi:BPMNEdge id="luong_{index}_hinh" bpmnElement="luong_{index}">\n'
            f'        <di:waypoint x="{start}" y="120" />\n'
            f'        <di:waypoint x="{start + 60}" y="120" />\n'
            "      </bpmndi:BPMNEdge>\n"
        )
    return (
        '  <bpmndi:BPMNDiagram id="hinh">\n'
        f'    <bpmndi:BPMNPlane id="mat_phang" bpmnElement="{key}">\n'
        f"{''.join(shapes)}{''.join(edges)}"
        "    </bpmndi:BPMNPlane>\n"
        "  </bpmndi:BPMNDiagram>\n"
    )


def process_bpmn(key, starters, function, worker=None, task="Xử lý yêu cầu", extra=""):
    nodes = ["bat_dau", "xu_ly", "ghi", "ket_thuc"] if worker else ["bat_dau", "ghi", "ket_thuc"]
    body = '    <bpmn:startEvent id="bat_dau">\n'
    body += REQUIRED_FIELD.format(field="noi_dung", label="Nội dung") + "    </bpmn:startEvent>\n"
    if worker:
        body += (
            f'    <bpmn:userTask id="xu_ly" name="{task}" operaton:candidateGroups="{worker}">\n'
        )
        body += REQUIRED_FIELD.format(field="ket_qua", label="Kết quả") + "    </bpmn:userTask>\n"
    body += STEP_TASK.format(function=function) + '    <bpmn:endEvent id="ket_thuc" />\n'
    for index in range(1, len(nodes)):
        body += (
            f'    <bpmn:sequenceFlow id="luong_{index}" sourceRef="{nodes[index - 1]}" '
            f'targetRef="{nodes[index]}" />\n'
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                  xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
                  xmlns:operaton="http://operaton.org/schema/1.0/bpmn"
                  id="dinh_nghia" targetNamespace="https://saigonos.example/bpmn">
  <bpmn:process id="{key}" name="Yêu cầu thử" isExecutable="true"
                operaton:historyTimeToLive="P30D" operaton:candidateStarterGroups="{starters}">
{body}{extra}  </bpmn:process>
{picture(key, nodes)}</bpmn:definitions>
"""


def process_app(folder, name, task="Xử lý yêu cầu", extra=""):
    schema = schema_of(name)
    manifest = {
        "name": name,
        "title": "Yêu cầu thử",
        "version": "0.1.0",
        "roles": [
            {"name": f"{name}.nguoi-gui", "description": "Gửi yêu cầu"},
            {"name": f"{name}.xu-ly", "description": "Xử lý yêu cầu"},
        ],
        "database": "database",
        "processes": "processes",
    }
    for part in ("database", "processes"):
        (folder / part).mkdir(parents=True, exist_ok=True)
    sql = RESULT_SQL.replace("{schema}", schema).replace("{app}", name)
    (folder / "database" / "0001_ket_qua.sql").write_text(sql, encoding="utf-8")
    bpmn = process_bpmn(
        f"{schema}.yeu_cau",
        f"{name}.nguoi-gui",
        f"{schema}.ghi_ket_qua",
        worker=f"{name}.xu-ly",
        task=task,
        extra=extra,
    )
    (folder / "processes" / "yeu-cau.bpmn").write_text(bpmn, encoding="utf-8")
    content = json.dumps(manifest, ensure_ascii=False, indent=2)
    (folder / "saigonos-app.json").write_text(content, encoding="utf-8")
    return folder


def operaton_rest(stack, *options, input=None):
    account = f"core:{stack.env['CORE_OPERATON_PASSWORD']}"
    command = ["exec", "-T", "operaton", "curl", "--silent", "--fail", "--user", account]
    result = stack.compose_result(*command, *options, input=input)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def operaton_get(stack, path):
    return operaton_rest(stack, f"{ENGINE}{path}")


def deploy_directly(stack, file, text, tenant=None):
    fields = ["--form-string", f"deployment-name={file}"]
    fields += ["--form-string", "deployment-source=kiem-thu", "--form", f"data=@-;filename={file}"]
    if tenant is not None:
        fields += ["--form-string", f"tenant-id={tenant}"]
    return operaton_rest(stack, *fields, f"{ENGINE}/deployment/create", input=text)


def wait_for(found, message, timeout=30):
    deadline = time.monotonic() + timeout
    while not (value := found()):
        assert time.monotonic() < deadline, message
        time.sleep(0.5)
    return value


def core_call(stack, method, path, token, body=None):
    reply = stack.call(method, f"{stack.url}/core/{path}", token=token, body=body)
    return reply.status, json.loads(reply.body) if reply.body else None


def start_process(stack, key, token, text="Máy 12 không lên màn hình"):
    return core_call(
        stack, "POST", f"processes/{key}/start", token, {"variables": {"noi_dung": text}}
    )


def finished(stack, instance):
    def state():
        found = operaton_get(stack, f"/history/process-instance/{instance}")["state"]
        return None if found == "ACTIVE" else found

    return wait_for(state, f"Quy trình {instance} chưa kết thúc")


def incident_message(stack, instance):
    path = f"/incident?processInstanceId={instance}"
    [incident] = wait_for(
        lambda: operaton_get(stack, path), f"Quy trình {instance} chưa có incident"
    )
    return incident["incidentMessage"]


def task_of_instance(stack, token, instance):
    status, tasks = core_call(stack, "GET", "tasks", token)
    assert status == 200, tasks
    return next((task for task in tasks if task["process_instance_id"] == instance), None)


def test_process_of_app_runs_to_the_end_with_tokens_of_app(stack, tmp_path):
    name = new_name()
    schema = schema_of(name)
    key = f"{schema}.yeu_cau"

    result = plug(stack, process_app(tmp_path / name, name))

    assert result.returncode == 0, result.stdout + result.stderr
    assert printed_last(
        result.stdout,
        f"Đã tạo route app-{name}.\n"
        f"Đã triển khai file yeu-cau.bpmn: quy trình {key}, phiên bản 1.\n"
        f"Đã cài đặt ứng dụng {name} 0.1.0.\n",
    )
    [definition] = operaton_get(stack, f"/process-definition?key={key}")
    [deployment] = operaton_get(stack, f"/deployment?id={definition['deploymentId']}")
    assert (definition["tenantId"], deployment["source"]) == (name, f"app:{name}")
    sender = user_with_roles(stack, f"{name}.nguoi-gui")
    worker = user_with_roles(stack, f"{name}.xu-ly")
    token = stack.app_token(worker, name)
    status, started = start_process(stack, key, stack.app_token(sender, name), "May 12")
    assert (status, started["version"]) == (201, 1), started
    task = wait_for(lambda: task_of_instance(stack, token, started["id"]), "Chưa có việc")
    assert core_call(stack, "POST", f"tasks/{task['id']}/claim", token) == (204, None)
    done = {"variables": {"ket_qua": "Đã thay cáp"}}
    assert core_call(stack, "POST", f"tasks/{task['id']}/complete", token, done) == (204, None)
    assert finished(stack, started["id"]) == "COMPLETED"
    assert stack.sql(f"SELECT * FROM {schema}.ket_qua") == [
        ["May 12", "Đã thay cáp", sender.id, f"{schema}_user"]
    ]
    assert stack.sql(
        f"SELECT count(*) FROM core.deliveries WHERE dedup_key = '{schema}-May 12'"
    ) == [["1"]]
    status, mine = core_call(stack, "GET", "notifications", stack.app_token(sender, name))
    assert (status, [item["title"] for item in mine]) == (200, ["Đã xử lý xong"])
    assert core_call(stack, "GET", "notifications", stack.token(sender)) == (200, [])


def test_changed_bpmn_file_makes_new_version_and_running_process_keeps_old(stack, tmp_path):
    name = new_name()
    key = f"{schema_of(name)}.yeu_cau"
    app = process_app(tmp_path / name, name)
    assert plug(stack, app).returncode == 0
    sender = user_with_roles(stack, f"{name}.nguoi-gui", f"{name}.xu-ly")
    token = stack.app_token(sender, name)
    _, first = start_process(stack, key, token)

    again = plug(stack, app)
    process_app(app, name, task="Kiểm tra yêu cầu")
    changed = plug(stack, app)

    assert again.returncode == 0, again.stdout + again.stderr
    assert printed_last(
        again.stdout,
        "Không có gì thay đổi.\n",
    )
    assert changed.returncode == 0, changed.stdout + changed.stderr
    assert f"Đã triển khai file yeu-cau.bpmn: quy trình {key}, phiên bản 2.\n" in changed.stdout
    _, second = start_process(stack, key, token)
    assert (first["version"], second["version"]) == (1, 2)
    old = wait_for(lambda: task_of_instance(stack, token, first["id"]), "Chưa có việc cũ")
    new = wait_for(lambda: task_of_instance(stack, token, second["id"]), "Chưa có việc mới")
    assert (old["name"], new["name"]) == ("Xử lý yêu cầu", "Kiểm tra yêu cầu")
    assert old["process_definition_id"] != new["process_definition_id"]
    done = {"variables": {"ket_qua": "Xong"}}
    assert core_call(stack, "POST", f"tasks/{old['id']}/claim", token) == (204, None)
    assert core_call(stack, "POST", f"tasks/{old['id']}/complete", token, done) == (204, None)
    assert finished(stack, first["id"]) == "COMPLETED"


def test_tokens_of_other_clients_do_not_reach_processes_of_app(stack, tmp_path):
    name, other = new_name(), new_name()
    key = f"{schema_of(name)}.yeu_cau"
    for app in (name, other):
        assert plug(stack, process_app(tmp_path / app, app)).returncode == 0
    roles = [f"{app}.{role}" for app in (name, other) for role in ("nguoi-gui", "xu-ly")]
    user = user_with_roles(stack, *roles)
    own, foreign, plain = (
        stack.app_token(user, name),
        stack.app_token(user, other),
        stack.token(user),
    )
    system = f"chung_{secrets.token_hex(3)}"
    simple = process_bpmn(system, f"{name}.nguoi-gui", "thu_nghiem.khong_co")
    deploy_directly(stack, f"{system}.bpmn", simple)
    _, started = start_process(stack, key, own)
    task = wait_for(lambda: task_of_instance(stack, own, started["id"]), "Chưa có việc")

    for token in (foreign, plain):
        assert task_of_instance(stack, token, started["id"]) is None
        assert start_process(stack, key, token)[0] == 404
        assert core_call(stack, "POST", f"tasks/{task['id']}/claim", token)[0] == 404
        assert core_call(stack, "POST", f"tasks/{task['id']}/complete", token)[0] == 404
    assert start_process(stack, system, own)[0] == 404
    assert start_process(stack, system, plain)[0] == 201
    assert core_call(stack, "POST", f"tasks/{task['id']}/claim", own) == (204, None)


def test_step_calling_function_of_another_app_becomes_incident(stack, tmp_path):
    name, other = new_name(), new_name()
    schema = schema_of(name)
    for app in (name, other):
        assert plug(stack, process_app(tmp_path / app, app)).returncode == 0
    user = user_with_roles(stack, f"{name}.nguoi-gui")
    crossing = process_bpmn(
        f"{schema}.goi_khac", f"{name}.nguoi-gui", f"{schema_of(other)}.ghi_ket_qua"
    )
    deploy_directly(stack, "goi-khac.bpmn", crossing, tenant=name)
    system = f"chung_{secrets.token_hex(3)}"
    deploy_directly(
        stack, f"{system}.bpmn", process_bpmn(system, f"{name}.nguoi-gui", f"{schema}.ghi_ket_qua")
    )

    _, inside = start_process(stack, f"{schema}.goi_khac", stack.app_token(user, name))
    _, outside = start_process(stack, system, stack.token(user))

    assert incident_message(stack, inside["id"]) == (
        f"Quy trình của ứng dụng {name} chỉ gọi được hàm trong schema {schema}. "
        f"Hàm {schema_of(other)}.ghi_ket_qua nằm ngoài schema này"
    )
    assert incident_message(stack, outside["id"]) == (
        f"Quy trình không thuộc ứng dụng nào nên không gọi được hàm {schema}.ghi_ket_qua "
        f"của ứng dụng {name}"
    )
    for app in (name, other):
        assert stack.sql(f"SELECT count(*) FROM {schema_of(app)}.ket_qua") == [["0"]]


def test_apply_refuses_bpmn_running_code_before_changing_anything(stack, tmp_path):
    name = new_name()
    script = '    <bpmn:scriptTask id="chay" scriptFormat="groovy" />\n'
    app = process_app(tmp_path / name, name, extra=script)
    line = (app / "processes" / "yeu-cau.bpmn").read_text(encoding="utf-8").splitlines()
    number = next(index for index, text in enumerate(line, 1) if "scriptTask" in text)

    result = plug(stack, app)

    assert result.returncode == 1, result.stdout + result.stderr
    assert (
        f'- processes: "processes/yeu-cau.bpmn", dòng {number}: '
        "Thẻ scriptTask chạy script trong Operaton nên không được dùng.\n"
    ) in result.stdout
    assert stack.sql(f"SELECT count(*) FROM core.apps WHERE name = '{name}'") == [["0"]]
    assert keycloak_client(stack, name) == []


NOTICE_SQL = """\
CREATE FUNCTION bao(tieu_de text) RETURNS uuid LANGUAGE sql
RETURN core.notify(core.uid(), 'khoa-chung', tieu_de);
CREATE FUNCTION so_thong_bao() RETURNS bigint LANGUAGE sql
RETURN (SELECT count(*) FROM core.notifications);
CREATE FUNCTION gui(kenh text) RETURNS uuid LANGUAGE sql RETURN core.publish(kenh, '{}');
GRANT EXECUTE ON FUNCTION bao(text), so_thong_bao(), gui(text) TO {schema}_user;
"""


@pytest.fixture(scope="module")
def noticing(stack, tmp_path_factory):
    names = new_name(), new_name()
    for name in names:
        folder = tmp_path_factory.mktemp("thong-bao") / name
        files = {"0002_thong_bao.sql": NOTICE_SQL.replace("{schema}", schema_of(name))}
        result = plug(stack, notes_app(folder, name, files=files))
        assert result.returncode == 0, result.stdout + result.stderr
    return names


def titles(stack, token):
    status, found = core_call(stack, "GET", "notifications", token)
    assert status == 200, found
    return [item["title"] for item in found]


def test_notifications_of_app_are_seen_only_with_token_of_that_app(stack, noticing):
    name, other = noticing
    user = stack.new_user()
    own, foreign = stack.app_token(user, name), stack.app_token(user, other)
    wait_until_served(stack, name, own)
    wait_until_served(stack, other, foreign)

    sent = [
        outcome(rpc(stack, app, token, "bao", {"tieu_de": f"Của {app}"}))
        for app, token in ((name, own), (other, foreign))
    ]
    stack.sql(f"SET ROLE workflow; SELECT core.notify('{user.id}', 'khoa-chung', 'Của hệ thống')")

    assert [status for status, _ in sent] == [200, 200]
    assert titles(stack, own) == [f"Của {name}"]
    assert titles(stack, foreign) == [f"Của {other}"]
    assert titles(stack, stack.token(user)) == ["Của hệ thống"]
    assert outcome(rpc(stack, other, foreign, "so_thong_bao", {})) == (200, 1)
    marked = stack.call("POST", f"{stack.url}/core/notifications/{sent[0][1]}/read", token=foreign)
    assert marked.status == 404


@pytest.mark.parametrize("target", ["role:{app}.quan-ly", "public:{app}.bang-tin", "user:{app}.x"])
def test_code_of_app_cannot_publish_into_channels_of_another_app(stack, noticing, target):
    name, other = noticing
    token = stack.app_token(stack.new_user(), other)
    wait_until_served(stack, other, token)
    channel = target.format(app=name)

    refused = outcome(rpc(stack, other, token, "gui", {"kenh": channel}))
    own = outcome(rpc(stack, other, token, "gui", {"kenh": target.format(app=other)}))

    assert refused == (403, f"Ứng dụng {other} không gửi được tin vào kênh '{channel}'")
    assert own[0] == 200


def test_code_of_app_cannot_publish_into_channels_of_system(stack, noticing):
    _, other = noticing
    user = stack.new_user()
    token = stack.app_token(user, other)
    wait_until_served(stack, other, token)

    replies = [
        outcome(rpc(stack, other, token, "gui", {"kenh": channel}))[0]
        for channel in (f"user:#{user.id}", "role:admin", "public:bang-tin")
    ]

    assert replies == [403, 403, 403]


def test_personal_channel_of_app_needs_channel_token_given_to_that_app(stack, noticing):
    name, other = noticing
    user = stack.new_user()
    own, foreign = stack.app_token(user, name), stack.app_token(user, other)
    channel = f"user:{name}.{user.id}"
    wait_until_served(stack, name, own)

    asked = {
        label: stack.call(
            "POST", f"{stack.url}/core/realtime/token", token=token, body={"channel": channel}
        )
        for label, token in (("own", own), ("foreign", foreign), ("plain", stack.token(user)))
    }
    with stack.realtime() as client:
        assert "connect" in client.connect(own)
        bare = client.command("subscribe", {"channel": channel})
        granted = json.loads(asked["own"].body)["token"]
        joined = client.command("subscribe", {"channel": channel, "token": granted})
        assert rpc(stack, name, own, "bao", {"tieu_de": "Có đơn mới"}).status == 200
        pushed = client.receive()

    assert {label: reply.status for label, reply in asked.items()} == {
        "own": 200,
        "foreign": 403,
        "plain": 403,
    }
    assert bare["error"] == {"code": 103, "message": "permission denied"}
    assert "subscribe" in joined
    assert pushed["push"]["channel"] == channel
    assert pushed["push"]["pub"]["data"]["notification"]["title"] == "Có đơn mới"


KEPT = "Schema, dữ liệu, role và việc gán role vẫn được giữ lại."


def realm_roles_of(stack, user):
    return {role["name"] for role in admin_json(stack, f"/users/{user.id}/role-mappings/realm")}


def test_saigonos_up_puts_back_parts_of_apps_edited_by_hand(stack, tmp_path):
    name = new_name()
    assert plug(stack, notes_app(tmp_path / name, name)).returncode == 0
    route = route_state(stack, name)
    edited = copy.deepcopy(route)
    edited["uris"].append("/khac/*")
    assert stack.gateway_admin("PUT", f"/routes/app-{name}", edited).status == 200
    [client] = keycloak_client(stack, name)
    assert (
        stack.admin("PUT", f"/clients/{client['id']}", client | {"redirectUris": ["*"]}).status
        == 204
    )

    result = stack.up()

    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        f"{name}: Đã cập nhật client {name}.\n"
        f"{name}: Đã cập nhật route app-{name}.\n"
        f"{name}: Đã cài đặt ứng dụng {name} 0.1.0.\n"
    ) in result.stdout
    assert route_state(stack, name) == route
    assert keycloak_client(stack, name)[0]["redirectUris"] == [f"{stack.url}/apps/{name}/*"]


def test_removed_app_keeps_its_data_and_other_apps_keep_running(stack, tmp_path):
    name, other = new_name(), new_name()
    schema = schema_of(name)
    app = notes_app(tmp_path / name, name, ui=UI)
    for folder in (app, notes_app(tmp_path / other, other)):
        assert plug(stack, folder).returncode == 0
    user = stack.new_user()
    stack.grant_role(user, f"{name}.nguoi-dung")
    token = stack.app_token(user, name)
    wait_until_served(stack, name, token)
    assert table_call(stack, "POST", name, token, {"body": "Giữ lại"}).status == 201

    result = stack.saigonos("remove", name)

    assert result.returncode == 0, result.stdout + result.stderr
    assert printed_last(
        result.stdout,
        f"Đã gỡ route app-{name}.\n"
        f"Đã gỡ client {name}.\n"
        f"Đã bỏ schema {schema} khỏi API.\n"
        f"Đã gỡ ứng dụng {name}. {KEPT}\n",
    )
    assert not (stack.home / "apps" / name).exists()
    assert keycloak_client(stack, name) == []
    assert f"{name}.nguoi-dung" in realm_roles_of(stack, user)
    assert app_call(stack, "GET", name, "api/notes").status == 404
    assert app_call(stack, "GET", name, "").status == 404
    assert stack.sql(f"SELECT body FROM {schema}.notes") == [["Giữ lại"]]
    doctor = stack.saigonos("doctor")
    assert doctor.returncode == 0, doctor.stdout
    assert f"Ứng dụng {name} " not in doctor.stdout
    assert f"Ứng dụng {other} " in doctor.stdout
    wait_until_served(stack, other, stack.app_token(stack.new_user(), other))

    again = plug(stack, app)

    assert again.returncode == 0, again.stdout + again.stderr
    assert printed_last(
        again.stdout,
        f"Đã tạo client {name}.\nĐã tạo route app-{name}.\nĐã cài đặt ứng dụng {name} 0.1.0.\n",
    )
    token = stack.app_token(user, name)
    wait_until_served(stack, name, token)
    notes = json.loads(table_call(stack, "GET", name, token).body)
    assert [note["body"] for note in notes] == ["Giữ lại"]
    assert app_call(stack, "GET", name, "").status == 200


def test_removed_app_pauses_its_processes_until_it_is_installed_again(stack, tmp_path):
    name = new_name()
    key = f"{schema_of(name)}.yeu_cau"
    app = process_app(tmp_path / name, name)
    assert plug(stack, app).returncode == 0
    user = user_with_roles(stack, f"{name}.nguoi-gui", f"{name}.xu-ly")
    _, started = start_process(stack, key, stack.app_token(user, name))

    removed = stack.saigonos("remove", name)
    paused = operaton_get(stack, f"/process-instance/{started['id']}")["suspended"]
    again = plug(stack, app)

    assert removed.returncode == 0, removed.stdout + removed.stderr
    assert f"Đã tạm dừng quy trình {key} trên Operaton.\n" in removed.stdout
    assert paused is True
    assert again.returncode == 0, again.stdout + again.stderr
    assert f"Đã chạy lại quy trình {key} trên Operaton.\n" in again.stdout
    token = stack.app_token(user, name)
    task = wait_for(lambda: task_of_instance(stack, token, started["id"]), "Chưa có việc")
    assert task["suspended"] is False
    done = {"variables": {"ket_qua": "Xong sau khi cài đặt lại"}}
    assert core_call(stack, "POST", f"tasks/{task['id']}/claim", token) == (204, None)
    assert core_call(stack, "POST", f"tasks/{task['id']}/complete", token, done) == (204, None)
    assert finished(stack, started["id"]) == "COMPLETED"


def test_purge_leaves_nothing_of_app(stack, tmp_path):
    name = new_name()
    schema, key = schema_of(name), f"{schema_of(name)}.yeu_cau"
    app = process_app(tmp_path / name, name)
    assert plug(stack, app).returncode == 0
    user = user_with_roles(stack, f"{name}.nguoi-gui", f"{name}.xu-ly")
    token = stack.app_token(user, name)
    _, started = start_process(stack, key, token)
    task = wait_for(lambda: task_of_instance(stack, token, started["id"]), "Chưa có việc")
    core_call(stack, "POST", f"tasks/{task['id']}/claim", token)
    core_call(stack, "POST", f"tasks/{task['id']}/complete", token, {"variables": {"ket_qua": "x"}})
    assert finished(stack, started["id"]) == "COMPLETED"

    refused = stack.saigonos("remove", name, "--purge")
    result = stack.saigonos("remove", name, "--purge", "--yes")

    assert refused.returncode == 1
    assert "Hãy chạy lại trong terminal hoặc thêm tùy chọn --yes." in refused.stdout
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"Đã xóa realm role {name}.nguoi-gui.\n" in result.stdout
    assert printed_last(result.stdout, f"Đã xóa hẳn ứng dụng {name}.\n")
    assert stack.sql(
        f"SELECT (SELECT count(*) FROM pg_namespace WHERE nspname = '{schema}'), "
        f"(SELECT count(*) FROM pg_roles WHERE rolname IN ('{schema}', '{schema}_user')), "
        f"(SELECT count(*) FROM core.apps WHERE name = '{name}'), "
        f"(SELECT count(*) FROM core.migrations WHERE scope = '{name}'), "
        f"(SELECT count(*) FROM core.notifications WHERE app = '{name}'), "
        f"(SELECT count(*) FROM core.deliveries WHERE app = '{name}'), "
        f"(SELECT count(*) FROM core.step_runs WHERE function LIKE '{schema}.%')"
    ) == [["0"] * 7]
    assert keycloak_client(stack, name) == []
    for role in ("nguoi-gui", "xu-ly"):
        assert stack.admin("GET", f"/roles/{name}.{role}").status == 404
    assert stack.gateway_admin("GET", f"/routes/app-{name}").status == 404
    assert operaton_get(stack, f"/deployment?tenantIdIn={name}") == []
    assert operaton_get(stack, f"/history/process-instance?processInstanceId={started['id']}") == []
    assert not (stack.home / "apps" / name).exists()
    fresh = plug(stack, app)
    assert fresh.returncode == 0, fresh.stdout + fresh.stderr
    assert f"Đã tạo schema {schema}, role {schema} và role {schema}_user của ứng dụng.\n" in (
        fresh.stdout
    )


def test_remove_of_app_never_installed_fails(stack):
    result = stack.saigonos("remove", new_name())

    assert result.returncode == 1
    assert "chưa được cài đặt." in result.stdout


def guarded_app(stack, tmp_path, name, access):
    folder = notes_app(tmp_path / name, name, roles=("nguoi-dung", "quan-ly"), access=access)
    result = plug(stack, folder)
    assert result.returncode == 0, result.stdout + result.stderr
    return folder


def refusal(reply):
    error = json.loads(reply.body)
    return reply.status, error["code"], error["message"]


def app_login_with_otp(stack, user, name):
    actions = {"requiredActions": ["CONFIGURE_TOTP"]}
    assert stack.admin("PUT", f"/users/{user.id}", actions).status == 204
    redirect = f"{stack.url}/apps/{name}/"
    first, otp = stack.browser_login(name, redirect, user)
    second, _ = stack.browser_login(name, redirect, user, otp)
    assert first.status == 200, first.body
    assert second.status == 200, second.body
    return json.loads(first.body)["access_token"], json.loads(second.body)["access_token"]


def test_general_api_address_does_not_reach_schema_of_app(stack, plugged):
    token = stack.app_token(stack.new_user(), plugged.name)
    wait_until_served(stack, plugged.name, token)
    headers = {
        "Accept-Profile": schema_of(plugged.name),
        "Content-Profile": schema_of(plugged.name),
    }

    read = stack.call("GET", f"{stack.url}/api/notes", token=token, headers=headers)
    write = stack.call("POST", f"{stack.url}/api/notes", token=token, headers=headers, body={})

    assert (read.status, write.status) == (404, 404)


def test_access_rules_of_app_are_checked_at_gateway_and_follow_apply(stack, tmp_path):
    name = new_name()
    rule = {"methods": ["POST"], "paths": ["/notes"], "roles": [f"{name}.quan-ly"]}
    folder = guarded_app(stack, tmp_path, name, [rule])
    staff = stack.app_token(user_with_roles(stack, f"{name}.nguoi-dung"), name)
    manager = stack.app_token(user_with_roles(stack, f"{name}.quan-ly"), name)
    wait_until_served(stack, name, manager)

    refused = table_call(stack, "POST", name, staff, {"body": "Nhân viên"})
    allowed = table_call(stack, "POST", name, manager, {"body": "Quản lý"})
    read = table_call(stack, "GET", name, staff)
    anonymous = table_call(stack, "POST", name, None, {"body": "Ẩn danh"})
    route = route_state(stack, name)
    notes_app(folder, name, roles=("nguoi-dung", "quan-ly"))
    replugged = plug(stack, folder)
    opened = table_call(stack, "POST", name, staff, {"body": "Sau khi bỏ luật"})

    message = f"Lời gọi này cần một trong các role: {name}.quan-ly."
    assert refusal(refused) == (403, "SGN03", message)
    assert refused.headers["Content-Type"] == "application/json; charset=utf-8"
    assert allowed.status == 201, allowed.body
    assert read.status == 200
    assert refusal(anonymous) == (401, "SGN03", "Lời gọi này cần access token.")
    assert anonymous.headers["WWW-Authenticate"] == "Bearer"
    assert route["labels"]["saigonos.access.1"] == json.dumps(rule, separators=(",", ":"))
    assert route["plugins"]["opa"]["policy"] == "saigonos/apps/decision"
    assert replugged.returncode == 0, replugged.stdout + replugged.stderr
    assert f"Đã cập nhật route app-{name}." in replugged.stdout.splitlines()
    assert "opa" not in route_state(stack, name)["plugins"]
    assert opened.status == 201, opened.body


def test_access_rule_with_otp_needs_login_with_otp(stack, tmp_path):
    name = new_name()
    guarded_app(stack, tmp_path, name, [{"methods": ["POST"], "otp": True}])
    user = user_with_roles(stack, f"{name}.nguoi-dung")
    without, with_otp = app_login_with_otp(stack, user, name)
    wait_until_served(stack, name, with_otp)

    refused = table_call(stack, "POST", name, without, {"body": "Chưa nhập OTP"})
    allowed = table_call(stack, "POST", name, with_otp, {"body": "Đã nhập OTP"})

    assert claims_of(without)["amr"] == ["pwd"]
    assert claims_of(with_otp)["amr"] == ["pwd", "otp"]
    message = "Lời gọi này cần đăng nhập bằng mật khẩu và mã OTP."
    assert refusal(refused) == (403, "SGN03", message)
    assert allowed.status == 201, allowed.body


def test_access_rule_with_networks_refuses_other_addresses(stack, tmp_path):
    name = new_name()
    guarded_app(stack, tmp_path, name, [{"networks": ["192.0.2.0/24"]}])
    token = stack.app_token(user_with_roles(stack, f"{name}.nguoi-dung"), name)

    reply = table_call(stack, "GET", name, token)

    message = "Địa chỉ IP này không được gọi đường dẫn này của ứng dụng."
    assert refusal(reply) == (403, "SGN03", message)


def test_app_with_rules_is_refused_while_opa_is_stopped(stack, plugged, tmp_path):
    name = new_name()
    guarded_app(stack, tmp_path, name, [{"otp": True}])
    open_token = stack.app_token(stack.new_user(), plugged.name)
    wait_until_served(stack, plugged.name, open_token)
    assert stack.compose_result("stop", "opa").returncode == 0
    try:
        guarded = table_call(stack, "GET", name, None).status
        unguarded = table_call(stack, "GET", plugged.name, open_token).status
    finally:
        started = stack.compose_result("up", "-d", "--wait", "opa", timeout=180)

    assert (guarded, unguarded) == (403, 200)
    assert started.returncode == 0, started.stderr
