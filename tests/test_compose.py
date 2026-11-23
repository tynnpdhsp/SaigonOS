# SPDX-License-Identifier: Apache-2.0
import json

import pytest

from saigonos import compose
from saigonos.apps import app_folders
from saigonos.cli import waiting
from saigonos.home import OPTIONAL_SERVICES

MONITORING = " ".join(OPTIONAL_SERVICES["monitoring"])


@pytest.fixture
def home(tmp_path, cli):
    path = tmp_path / "home"
    cli("init", "--home", path, "--http-port", 8000)
    return path


def test_up_runs_compose_in_home_and_prints_url(home, cli, docker):
    result = cli("up", "--home", home)

    assert result.exit_code == 0
    assert docker.calls == [f"{home.resolve()}: compose up -d --wait"]
    assert result.output == "Địa chỉ truy cập: http://localhost:8000\n"


def test_up_returns_exit_code_of_compose(home, cli, docker):
    docker.reply("up", code=3)

    result = cli("up", "--home", home)

    assert result.exit_code == 3
    assert result.output == ""


def test_down_keeps_volumes_by_default(home, cli, docker):
    result = cli("down", "--home", home)

    assert result.exit_code == 0
    assert docker.calls == [f"{home.resolve()}: compose down"]


def test_down_can_remove_volumes(home, cli, docker):
    result = cli("down", "--home", home, "--volumes")

    assert result.exit_code == 0
    assert docker.calls == [f"{home.resolve()}: compose down --volumes"]


def test_down_returns_exit_code_of_compose(home, cli, docker):
    docker.reply("down", code=1)

    assert cli("down", "--home", home).exit_code == 1


@pytest.fixture
def caddy_home(tmp_path, cli):
    path = tmp_path / "caddy"
    cli("init", "--home", path, "--url", "https://dx.example.com", "--caddy")
    return path


@pytest.mark.parametrize(("command", "compose_command"), [("up", "up -d --wait"), ("down", "down")])
def test_enabled_caddy_is_left_to_compose(caddy_home, cli, docker, command, compose_command):
    result = cli(command, "--home", caddy_home)

    assert result.exit_code == 0
    assert docker.calls == [
        f"{caddy_home.resolve()}: compose rm --stop --force {MONITORING}",
        f"{caddy_home.resolve()}: compose {compose_command}",
    ]


@pytest.mark.parametrize(("command", "compose_command"), [("up", "up -d --wait"), ("down", "down")])
def test_caddy_turned_off_is_removed_first(caddy_home, cli, docker, command, compose_command):
    cli("init", "--home", caddy_home, "--no-caddy")

    result = cli(command, "--home", caddy_home)

    assert result.exit_code == 0
    assert docker.calls == [
        f"{caddy_home.resolve()}: compose rm --stop --force caddy {MONITORING}",
        f"{caddy_home.resolve()}: compose {compose_command}",
    ]


@pytest.mark.parametrize("command", ["up", "down"])
def test_commands_stop_when_caddy_cannot_be_removed(caddy_home, cli, docker, command):
    cli("init", "--home", caddy_home, "--no-caddy")
    docker.reply("rm", error="Cannot connect to the Docker daemon\n", code=1)

    result = cli(command, "--home", caddy_home)

    assert result.exit_code == 1
    assert "Lệnh docker compose rm không chạy được: Cannot connect to the Docker daemon" in (
        result.output
    )
    assert docker.calls == [f"{caddy_home.resolve()}: compose rm --stop --force caddy {MONITORING}"]


@pytest.fixture
def monitoring_home(tmp_path, cli):
    path = tmp_path / "monitoring"
    cli("init", "--home", path, "--monitoring")
    return path


@pytest.mark.parametrize(("command", "compose_command"), [("up", "up -d --wait"), ("down", "down")])
def test_enabled_monitoring_is_left_to_compose(
    monitoring_home, cli, docker, command, compose_command
):
    result = cli(command, "--home", monitoring_home)

    assert result.exit_code == 0
    assert docker.calls == [
        f"{monitoring_home.resolve()}: compose rm --stop --force caddy",
        f"{monitoring_home.resolve()}: compose {compose_command}",
    ]


@pytest.mark.parametrize(("command", "compose_command"), [("up", "up -d --wait"), ("down", "down")])
def test_monitoring_turned_off_is_removed_first(
    monitoring_home, cli, docker, command, compose_command
):
    cli("init", "--home", monitoring_home, "--no-monitoring")

    result = cli(command, "--home", monitoring_home)

    assert result.exit_code == 0
    assert docker.calls == [
        f"{monitoring_home.resolve()}: compose rm --stop --force caddy {MONITORING}",
        f"{monitoring_home.resolve()}: compose {compose_command}",
    ]


@pytest.mark.parametrize("command", ["up", "down", "doctor", "audit verify"])
@pytest.mark.parametrize("missing", ["compose.yaml", ".env"])
def test_commands_need_initialized_home(home, cli, docker, command, missing):
    (home / missing).unlink()

    result = cli(*command.split(), "--home", home)

    assert result.exit_code == 1
    assert "Hãy chạy lệnh saigonos init trước." in result.output
    assert docker.calls == []


@pytest.mark.parametrize("command", ["up", "down", "doctor", "audit verify"])
def test_commands_need_docker(home, cli, tmp_path, monkeypatch, command):
    monkeypatch.setenv("PATH", str(tmp_path))

    result = cli(*command.split(), "--home", home)

    assert result.exit_code == 1
    assert "Không tìm thấy lệnh docker." in result.output


def test_capture_returns_output(home, docker):
    docker.reply("ps", output="kết quả\n")

    assert compose.capture(home, "ps", "--all") == "kết quả\n"
    assert docker.calls == [f"{home.resolve()}: compose ps --all"]


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        ("Cannot connect to the Docker daemon\n", "Cannot connect to the Docker daemon"),
        ("", "mã thoát 2"),
    ],
    ids=["co-stderr", "stderr-rong"],
)
def test_capture_raises_with_reason_when_compose_fails(home, docker, error, reason):
    docker.reply("ps", error=error, code=2)

    with pytest.raises(compose.ComposeError) as raised:
        compose.capture(home, "ps")

    assert str(raised.value) == f"Lệnh docker compose ps không chạy được: {reason}"


def copied(home, name="nghi-phep", manifest=None):
    folder = home / "apps" / name
    folder.mkdir(parents=True)
    content = json.dumps(manifest or {"name": name})
    (folder / "saigonos-app.json").write_text(content, encoding="utf-8")
    return folder


def test_up_reapplies_installed_apps_after_services_are_ready(home, cli, docker):
    copied(home)

    result = cli("up", "--home", home)

    assert result.exit_code == 0
    assert docker.calls == [
        f"{home.resolve()}: compose up -d --wait",
        f"{home.resolve()}: compose run --rm apps apply --all",
    ]


def test_up_skips_apps_service_without_installed_app(home, cli, docker):
    (home / "apps" / ".nghi-phep.old").mkdir()
    (home / "apps" / "khong-co-ban-khai").mkdir()

    result = cli("up", "--home", home)

    assert result.exit_code == 0
    assert docker.calls == [f"{home.resolve()}: compose up -d --wait"]


def test_up_returns_exit_code_of_reapply(home, cli, docker):
    copied(home)
    docker.reply("run", code=1)

    result = cli("up", "--home", home)

    assert result.exit_code == 1


def test_remove_runs_apps_service_then_deletes_copy(home, cli, docker):
    copied(home)
    copied(home, "khac")
    for leftover in (".nghi-phep.old", ".nghi-phep.new"):
        (home / "apps" / leftover).mkdir()

    result = cli("remove", "--home", home, "nghi-phep")

    assert result.exit_code == 0
    assert docker.calls == [f"{home.resolve()}: compose run --rm apps remove nghi-phep"]
    assert sorted(path.name for path in (home / "apps").iterdir()) == ["khac"]


def test_remove_passes_purge_and_yes(home, cli, docker):
    result = cli("remove", "--home", home, "nghi-phep", "--purge", "--yes")

    assert result.exit_code == 0
    assert docker.calls == [
        f"{home.resolve()}: compose run --rm apps remove nghi-phep --purge --yes"
    ]


def test_failed_remove_keeps_copy(home, cli, docker):
    folder = copied(home)
    docker.reply("run", code=1)

    result = cli("remove", "--home", home, "nghi-phep")

    assert result.exit_code == 1
    assert folder.is_dir()


@pytest.mark.parametrize("name", ["Nghi-Phep", "../apps", "nghi_phep"], ids=["hoa", "cha", "gach"])
def test_remove_refuses_invalid_name(home, cli, docker, name):
    result = cli("remove", "--home", home, name)

    assert result.exit_code == 1
    assert f"Tên ứng dụng {name} không hợp lệ." in result.output
    assert docker.calls == []


def test_remove_needs_working_folder(tmp_path, cli, docker):
    result = cli("remove", "--home", tmp_path / "khong-co", "nghi-phep")

    assert result.exit_code == 1
    assert "Hãy chạy lệnh saigonos init trước." in result.output
    assert not (tmp_path / "khong-co").exists()


def test_command_waiting_for_lock_says_so(capsys):
    waiting()

    assert capsys.readouterr().out == (
        "Đang chờ một lệnh saigonos khác làm việc với ứng dụng chạy xong.\n"
    )


def test_missing_apps_folder_has_no_app(tmp_path):
    assert app_folders(tmp_path / "apps") == []
