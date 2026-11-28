# SPDX-License-Identifier: Apache-2.0
import fcntl
import json
import os
import stat
import threading

import pytest

from saigonos import compose
from saigonos.apps import LOCK_FILE, locked

APPS_DOCKER = """\
#!/bin/sh
dir="${0%/*}"
printf '%s\\n' "$(pwd -P): $*" >> "$dir/calls"
case "$*" in
    *" apps apply "*) step=apply; (cd apps && find . | sort) > "$dir/apps-during-apply" ;;
    *) step=check ;;
esac
[ -f "$dir/$step.code" ] && exit "$(cat "$dir/$step.code")"
exit 0
"""
MANIFEST = {
    "name": "nghi-phep",
    "title": "Nghỉ phép",
    "version": "0.2.0",
    "roles": [{"name": "nghi-phep.quan-ly", "description": "Duyệt đơn"}],
    "database": "database",
    "ui": "web/dist/",
}
SOURCE_FILES = {
    "database/0001_don.sql": "CREATE TABLE don (id bigint);\n",
    "web/dist/index.html": "<!doctype html>\n",
    "web/dist/assets/app.js": "console.log(1);\n",
    "web/src/main.js": "console.log('nguồn');\n",
    ".git/config": "[core]\n",
    "ghi-chu.txt": "không chép\n",
}
COPIED = [
    ".",
    "./database",
    "./database/0001_don.sql",
    "./saigonos-app.json",
    "./web",
    "./web/dist",
    "./web/dist/assets",
    "./web/dist/assets/app.js",
    "./web/dist/index.html",
]
as_root = pytest.mark.skipif(os.geteuid() == 0, reason="root đọc được mọi file")


@pytest.fixture
def home(tmp_path, cli):
    path = tmp_path / "home"
    cli("init", "--home", path)
    return path


@pytest.fixture
def folder(tmp_path):
    path = tmp_path / "nghi-phep"
    path.mkdir()
    return path


@pytest.fixture
def source(tmp_path):
    app = tmp_path / "nguon"
    for name, text in SOURCE_FILES.items():
        (app / name).parent.mkdir(parents=True, exist_ok=True)
        (app / name).write_text(text, encoding="utf-8")
    (app / "web" / "dist" / "assets" / "app.js").chmod(0o600)
    (app / "saigonos-app.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    return app


@pytest.fixture
def steps(docker):
    (docker.directory / "docker").write_text(APPS_DOCKER, encoding="utf-8")
    return docker


def fail(steps, step, code=1):
    (steps.directory / f"{step}.code").write_text(str(code), encoding="utf-8")


def run_call(home, folder):
    user = f"{os.getuid()}:{os.getgid()}"
    return (
        f"{home.resolve()}: compose run --rm --no-deps --user {user} "
        f"--volume {folder.resolve()}:/check:ro apps check /check"
    )


def apply_call(home, name="nghi-phep"):
    return f"{home.resolve()}: compose run --rm apps apply {name}"


def listing(folder):
    return sorted(
        "." if path == folder else f"./{path.relative_to(folder).as_posix()}"
        for path in [folder, *folder.rglob("*")]
    )


def mode(path):
    return stat.S_IMODE(path.lstat().st_mode)


def old_version(home, extra="database/0000_cu.sql"):
    app = home / "apps" / "nghi-phep"
    (app / extra).parent.mkdir(parents=True)
    (app / extra).write_text("-- bản cũ\n", encoding="utf-8")
    (app / "saigonos-app.json").write_text(
        json.dumps(MANIFEST | {"version": "0.1.0"}), encoding="utf-8"
    )
    return listing(app)


def test_check_runs_apps_service_on_folder_mounted_read_only(home, folder, cli, docker):
    result = cli("apply", "--check", folder, "--home", home)

    assert result.exit_code == 0
    assert docker.calls == [run_call(home, folder)]


def test_check_returns_exit_code_of_apps_service(home, folder, cli, docker):
    docker.reply("run", code=1)

    assert cli("apply", "--check", folder, "--home", home).exit_code == 1


def test_check_mounts_real_path_of_folder(home, folder, tmp_path, cli, docker, monkeypatch):
    (tmp_path / "lien-ket").symlink_to(folder)
    monkeypatch.chdir(tmp_path)

    result = cli("apply", "--check", "lien-ket", "--home", home)

    assert result.exit_code == 0
    assert docker.calls == [run_call(home, folder)]


def test_check_needs_existing_folder(home, tmp_path, cli, docker):
    result = cli("apply", "--check", tmp_path / "khong-co", "--home", home)

    assert result.exit_code == 1
    assert f"Không tìm thấy thư mục {tmp_path / 'khong-co'}." in result.output
    assert docker.calls == []


def test_check_needs_folder_not_file(home, tmp_path, cli, docker):
    (tmp_path / "saigonos-app.json").write_text("{}", encoding="utf-8")

    result = cli("apply", "--check", tmp_path / "saigonos-app.json", "--home", home)

    assert result.exit_code == 1
    assert f"{tmp_path / 'saigonos-app.json'} không phải thư mục." in result.output
    assert docker.calls == []


def test_folder_with_colon_cannot_be_mounted(home, tmp_path, cli, docker):
    (tmp_path / "a:b").mkdir()

    result = cli("apply", "--check", tmp_path / "a:b", "--home", home)

    assert result.exit_code == 1
    assert "có dấu hai chấm" in result.output
    assert docker.calls == []


@pytest.mark.parametrize("options", [["--check"], []], ids=["chi-soat", "cam"])
@pytest.mark.parametrize("missing", ["compose.yaml", ".env"])
def test_apply_needs_initialized_home(home, folder, cli, docker, missing, options):
    (home / missing).unlink()

    result = cli("apply", *options, folder, "--home", home)

    assert result.exit_code == 1
    assert "Hãy chạy lệnh saigonos init trước." in result.output
    assert docker.calls == []


def test_check_needs_docker(home, folder, tmp_path, cli, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))

    result = cli("apply", "--check", folder, "--home", home)

    assert result.exit_code == 1
    assert "Không tìm thấy lệnh docker." in result.output


def test_apply_checks_copies_declared_parts_and_plugs_app(home, source, cli, steps):
    result = cli("apply", source, "--home", home)

    app = home / "apps" / "nghi-phep"
    assert result.exit_code == 0, result.output
    assert steps.calls == [run_call(home, source), apply_call(home)]
    assert listing(app) == COPIED
    assert listing(home / "apps") == [
        ".",
        "./nghi-phep",
        *(f"./nghi-phep{p[1:]}" for p in COPIED[1:]),
    ]
    assert {mode(path) for path in app.rglob("*") if path.is_dir()} == {0o755}
    assert {mode(path) for path in app.rglob("*") if path.is_file()} == {0o644}
    assert mode(app) == 0o755
    assert (steps.directory / "apps-during-apply").read_text(encoding="utf-8").splitlines() == [
        ".",
        "./nghi-phep",
        *(f"./nghi-phep{p[1:]}" for p in COPIED[1:]),
    ]


def test_apply_replaces_previous_version_when_it_succeeds(home, source, cli, steps):
    old_version(home)

    result = cli("apply", source, "--home", home)

    assert result.exit_code == 0, result.output
    assert listing(home / "apps" / "nghi-phep") == COPIED
    during = (steps.directory / "apps-during-apply").read_text(encoding="utf-8").splitlines()
    assert "./.nghi-phep.old/database/0000_cu.sql" in during
    assert sorted(path.name for path in (home / "apps").iterdir()) == ["nghi-phep"]


def test_failed_apply_keeps_last_good_version(home, source, cli, steps):
    kept = old_version(home)
    fail(steps, "apply")

    result = cli("apply", source, "--home", home)

    assert result.exit_code == 1
    assert listing(home / "apps" / "nghi-phep") == kept
    assert sorted(path.name for path in (home / "apps").iterdir()) == ["nghi-phep"]


def test_failed_first_apply_leaves_no_folder(home, source, cli, steps):
    fail(steps, "apply", code=3)

    result = cli("apply", source, "--home", home)

    assert result.exit_code == 3
    assert list((home / "apps").iterdir()) == []


def test_failed_check_copies_nothing(home, source, cli, steps):
    kept = old_version(home)
    fail(steps, "check")

    result = cli("apply", source, "--home", home)

    assert result.exit_code == 1
    assert steps.calls == [run_call(home, source)]
    assert listing(home / "apps" / "nghi-phep") == kept


@pytest.mark.parametrize("broken", [True, False], ids=["con-ban-do-dang", "mat-ban-dang-dung"])
def test_last_good_version_left_by_interrupted_apply_is_restored_first(
    home, source, cli, steps, broken
):
    apps = home / "apps"
    kept = old_version(home)
    (apps / "nghi-phep").rename(apps / ".nghi-phep.old")
    if broken:
        (apps / "nghi-phep" / "database").mkdir(parents=True)
    (apps / ".nghi-phep.new").mkdir()
    fail(steps, "apply")

    result = cli("apply", source, "--home", home)

    assert result.exit_code == 1
    assert listing(apps / "nghi-phep") == kept
    assert sorted(path.name for path in apps.iterdir()) == ["nghi-phep"]


@pytest.mark.parametrize(
    "failure",
    [KeyboardInterrupt(), compose.ComposeError("Lệnh docker compose run không chạy được")],
    ids=["ngat-giua-chung", "loi-docker-compose"],
)
def test_interrupted_apply_restores_last_good_version(
    home, source, cli, steps, monkeypatch, failure
):
    kept = old_version(home)
    original = compose.run

    def run(home_folder, *args):
        if "apply" in args:
            raise failure
        return original(home_folder, *args)

    monkeypatch.setattr(compose, "run", run)

    result = cli("apply", source, "--home", home)

    assert result.exit_code == 1
    assert listing(home / "apps" / "nghi-phep") == kept
    assert sorted(path.name for path in (home / "apps").iterdir()) == ["nghi-phep"]


def test_missing_apps_folder_is_created(home, source, cli, steps):
    (home / "apps").rmdir()

    result = cli("apply", source, "--home", home)

    assert result.exit_code == 0, result.output
    assert mode(home / "apps") == 0o755


@as_root
def test_copy_failure_leaves_previous_version_untouched(home, source, cli, steps):
    kept = old_version(home)
    (source / "web" / "dist" / "assets").chmod(0)

    result = cli("apply", source, "--home", home)

    (source / "web" / "dist" / "assets").chmod(0o755)
    assert result.exit_code == 1
    assert f"Không chép được ứng dụng vào {home / 'apps'}:" in result.output
    assert steps.calls == [run_call(home, source)]
    assert listing(home / "apps" / "nghi-phep") == kept
    assert sorted(path.name for path in (home / "apps").iterdir()) == ["nghi-phep"]


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (json.dumps(MANIFEST | {"name": "../ngoai"}), "Tên ứng dụng trong file"),
        (json.dumps([MANIFEST]), "không còn là một đối tượng JSON"),
        ("{", "Expecting property name"),
    ],
    ids=["ten-ra-ngoai", "khong-phai-doi-tuong", "json-hong"],
)
def test_manifest_changed_after_check_is_refused(home, source, cli, steps, content, reason):
    (source / "saigonos-app.json").write_text(content, encoding="utf-8")

    result = cli("apply", source, "--home", home)

    assert result.exit_code == 1
    assert "Không đọc được bản khai báo của ứng dụng:" in result.output
    assert reason in result.output
    assert steps.calls == [run_call(home, source)]
    assert list((home / "apps").iterdir()) == []


def test_folder_pointing_outside_app_is_not_copied(home, source, cli, steps):
    manifest = MANIFEST | {"ui": "../ngoai", "processes": 7}
    (source / "saigonos-app.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = cli("apply", source, "--home", home)

    assert result.exit_code == 0, result.output
    assert listing(home / "apps" / "nghi-phep") == [
        ".",
        "./database",
        "./database/0001_don.sql",
        "./saigonos-app.json",
    ]


def test_symlink_is_copied_as_link_and_keeps_its_target(home, source, tmp_path, cli, steps):
    secret = tmp_path / "bi-mat.txt"
    secret.write_text("bí mật\n", encoding="utf-8")
    secret.chmod(0o600)
    (source / "web" / "dist" / "lien-ket").symlink_to(secret)

    result = cli("apply", source, "--home", home)

    copied = home / "apps" / "nghi-phep" / "web" / "dist" / "lien-ket"
    assert result.exit_code == 0, result.output
    assert copied.is_symlink()
    assert mode(secret) == 0o600


def test_second_apply_waits_for_first(home):
    waited = threading.Event()
    entered = threading.Event()

    def second():
        with locked(home, waited.set):
            entered.set()

    with (home / LOCK_FILE).open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        worker = threading.Thread(target=second)
        worker.start()
        assert waited.wait(5)
        assert not entered.is_set()
    worker.join(5)

    assert entered.is_set()
