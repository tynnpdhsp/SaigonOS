# SPDX-License-Identifier: Apache-2.0
import pytest

from saigonos import compose


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


@pytest.mark.parametrize("command", ["up", "down", "doctor"])
@pytest.mark.parametrize("missing", ["compose.yaml", ".env"])
def test_commands_need_initialized_home(home, cli, docker, command, missing):
    (home / missing).unlink()

    result = cli(command, "--home", home)

    assert result.exit_code == 1
    assert "Hãy chạy lệnh saigonos init trước." in result.output
    assert docker.calls == []


@pytest.mark.parametrize("command", ["up", "down", "doctor"])
def test_commands_need_docker(home, cli, tmp_path, monkeypatch, command):
    monkeypatch.setenv("PATH", str(tmp_path))

    result = cli(command, "--home", home)

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
)
def test_capture_raises_with_reason_when_compose_fails(home, docker, error, reason):
    docker.reply("ps", error=error, code=2)

    with pytest.raises(compose.ComposeError) as raised:
        compose.capture(home, "ps")

    assert str(raised.value) == f"Lệnh docker compose ps không chạy được: {reason}"
