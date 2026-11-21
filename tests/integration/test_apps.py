# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

SCHEMA_FILE = Path(__file__).resolve().parents[2] / "schemas" / "saigonos-app.schema.json"
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
