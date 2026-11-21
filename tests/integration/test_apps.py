# SPDX-License-Identifier: Apache-2.0
import json
import re
import secrets
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

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
GRANT USAGE ON SCHEMA {schema} TO authenticated;
GRANT SELECT, INSERT ON notes TO authenticated;
"""
WHO_SQL = """\
CREATE TABLE who AS
SELECT current_user::text AS who_current, session_user::text AS who_session,
    (SELECT rolcanlogin FROM pg_roles WHERE rolname = current_user) AS could_log_in;
"""
TOTAL_SQL = (
    "CREATE FUNCTION total() RETURNS bigint LANGUAGE sql RETURN (SELECT count(*) FROM notes);\n"
)
REFUSED_FILES = {
    "doc-ung-dung-khac": "SELECT * FROM {other}.notes;",
    "doc-audit-log": "SELECT * FROM core.audit_log;",
    "ghi-migrations": "INSERT INTO core.migrations VALUES ('core', '9999_gia.sql', 'x');",
    "doi-sang-postgres": "SET ROLE postgres;",
    "doi-sang-authenticated": "SET ROLE authenticated;",
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


def notes_app(folder, name, version="0.1.0", files=None):
    manifest = {
        "name": name,
        "title": "Ghi chú thử",
        "version": version,
        "roles": [{"name": f"{name}.nguoi-dung", "description": "Ghi chú của mình"}],
        "database": "database",
    }
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

    token = stack.token(user)
    assert result.returncode == 0, result.stdout + result.stderr
    assert printed_last(
        result.stdout,
        f"Đã tạo schema {schema} và role {schema} của ứng dụng.\n"
        "Đã chạy file 0001_notes.sql.\n"
        f"Đã cắm ứng dụng {name} 0.1.0.\n",
    )
    wait_until_served(stack, name, token)
    created = profile_call(stack, "POST", name, token, {"body": "Xin chào"})
    assert created.status == 201, created.body
    mine = json.loads(profile_call(stack, "GET", name, token).body)
    theirs = json.loads(profile_call(stack, "GET", name, stack.token(other)).body)
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
    state = database_state(stack, name)

    result = plug(stack, app)

    assert result.returncode == 0, result.stdout + result.stderr
    assert printed_last(result.stdout, f"Không có file SQL mới.\nĐã cắm ứng dụng {name} 0.1.0.\n")
    assert database_state(stack, name) == state


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


def test_function_of_app_is_not_callable_until_granted(stack, tmp_path):
    name = new_name()
    function = f"{schema_of(name)}.total()"

    result = plug(stack, notes_app(tmp_path / name, name, files={"0002_total.sql": TOTAL_SQL}))

    assert result.returncode == 0, result.stdout + result.stderr
    assert stack.sql(
        f"SELECT has_function_privilege('authenticated', '{function}', 'EXECUTE'), "
        f"has_function_privilege('anon', '{function}', 'EXECUTE')"
    ) == [["f", "f"]]


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
    text = REFUSED_FILES[refused].format(other=schema_of(plugged.other))
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


def test_app_copied_into_apps_folder_is_plugged_with_docker_compose(stack):
    name = new_name()
    notes_app(stack.home / "apps" / name, name)

    result = run_apps(stack, "apply", name)

    assert result.returncode == 0, result.stdout + result.stderr
    assert printed_last(result.stdout, f"Đã cắm ứng dụng {name} 0.1.0.\n")
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

    token = stack.token(user)
    assert result.returncode == 0, result.stdout + result.stderr
    wait_until_served(stack, "nghi-phep", token, table="don")
    body = {"ly_do": "Việc gia đình"}
    created = profile_call(stack, "POST", "nghi-phep", token, body, table="don")
    mine = json.loads(profile_call(stack, "GET", "nghi-phep", token, table="don").body)
    theirs = profile_call(stack, "GET", "nghi-phep", stack.token(other), table="don")
    assert created.status == 201, created.body
    assert [(item["ly_do"], item["nguoi_gui"]) for item in mine] == [("Việc gia đình", user.id)]
    assert json.loads(theirs.body) == []
