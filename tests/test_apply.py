# SPDX-License-Identifier: Apache-2.0
import os

import pytest


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


def run_call(home, folder):
    user = f"{os.getuid()}:{os.getgid()}"
    return (
        f"{home.resolve()}: compose run --rm --no-deps --user {user} "
        f"--volume {folder.resolve()}:/check:ro apps check /check"
    )


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


def test_apply_needs_check_option_for_now(home, folder, cli, docker):
    result = cli("apply", folder, "--home", home)

    assert result.exit_code == 2
    assert "Lệnh apply hiện chỉ chạy với tùy chọn --check." in result.output
    assert docker.calls == []


@pytest.mark.parametrize("missing", ["compose.yaml", ".env"])
def test_check_needs_initialized_home(home, folder, cli, docker, missing):
    (home / missing).unlink()

    result = cli("apply", "--check", folder, "--home", home)

    assert result.exit_code == 1
    assert "Hãy chạy lệnh saigonos init trước." in result.output
    assert docker.calls == []


def test_check_needs_docker(home, folder, tmp_path, cli, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))

    result = cli("apply", "--check", folder, "--home", home)

    assert result.exit_code == 1
    assert "Không tìm thấy lệnh docker." in result.output
