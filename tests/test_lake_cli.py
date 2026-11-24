# SPDX-License-Identifier: Apache-2.0
import pytest

LAKE = "compose exec -T core python -m saigonos_core.lake"


@pytest.fixture
def home(tmp_path, cli):
    path = tmp_path / "home"
    cli("init", "--home", path)
    return path


@pytest.mark.parametrize(
    ("args", "call"),
    [
        (["run"], "run"),
        (
            ["query", "SELECT count(*) FROM nghi_phep.don"],
            "query -- SELECT count(*) FROM nghi_phep.don",
        ),
        (["query", "--csv", "SELECT 1"], "query --csv -- SELECT 1"),
        (["verify"], "verify"),
    ],
    ids=["run", "query", "query-csv", "verify"],
)
def test_lake_commands_run_inside_core_container(home, cli, docker, args, call):
    result = cli("lake", *args, "--home", home)

    assert result.exit_code == 0, result.output
    assert docker.calls == [f"{home.resolve()}: {LAKE} {call}"]


@pytest.mark.parametrize("command", ["run", "verify"])
def test_lake_commands_return_exit_code_of_core_container(home, cli, docker, command):
    docker.reply("exec", code=1)

    assert cli("lake", command, "--home", home).exit_code == 1


def test_lake_commands_need_initialized_home(tmp_path, cli, docker):
    result = cli("lake", "verify", "--home", tmp_path / "chua-co")

    assert result.exit_code == 1
    assert "Hãy chạy lệnh saigonos init trước." in result.output
    assert docker.calls == []
