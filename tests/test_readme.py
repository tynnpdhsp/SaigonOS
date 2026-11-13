# SPDX-License-Identifier: Apache-2.0
import re
import shlex
from pathlib import Path

import pytest

from saigonos.cli import main
from saigonos.home import DEFAULT_ADMIN_PORT, DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT

README = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
BLOCK_LINES = [
    line.strip()
    for block in re.findall(r"```bash\n(.*?)```", README, re.DOTALL)
    for line in block.splitlines()
]
INLINE = re.findall(r"`([^`\n]+)`", README)
COMMANDS = sorted({text for text in [*BLOCK_LINES, *INLINE] if text.startswith("saigonos ")})


def test_readme_shows_the_whole_install_path():
    assert {"pip install .", "saigonos init", "docker compose up -d --wait"} <= set(BLOCK_LINES)
    assert "saigonos doctor" in BLOCK_LINES


@pytest.mark.parametrize("line", COMMANDS)
def test_readme_command_is_accepted_by_cli(line):
    name, *arguments = shlex.split(line)[1:]

    assert name in main.commands
    with main.commands[name].make_context(name, arguments) as context:
        assert context.command.name == name


def test_readme_options_exist_in_cli():
    documented = {text for text in INLINE if text.startswith("--")}
    known = {
        option
        for command in main.commands.values()
        for parameter in command.params
        for option in parameter.opts
    }

    assert documented
    assert documented <= known


def test_readme_states_the_default_values():
    assert f"| `--http-host` | `{DEFAULT_HTTP_HOST}` |" in README
    assert f"| `--http-port` | `{DEFAULT_HTTP_PORT}` |" in README
    assert f"| `--admin-port` | `{DEFAULT_ADMIN_PORT}` |" in README
    assert f"| `--url` | `http://localhost:{DEFAULT_HTTP_PORT}` |" in README
    assert "| `--home` | `~/saigonos` |" in README
