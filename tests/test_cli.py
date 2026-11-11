# SPDX-License-Identifier: Apache-2.0
import runpy
import sys
from importlib.metadata import entry_points, version

import pytest
from click.testing import CliRunner

from saigonos import __version__
from saigonos.cli import main


def test_version_comes_from_package_metadata():
    assert __version__ == version("saigonos")


def test_version_option_prints_name_and_version():
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert result.output == f"saigonos {__version__}\n"


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_option_shows_usage(flag):
    result = CliRunner().invoke(main, [flag], prog_name="saigonos")

    assert result.exit_code == 0
    assert result.output.startswith("Usage: saigonos ")


def test_console_script_points_to_cli():
    (script,) = entry_points(group="console_scripts", name="saigonos")

    assert script.value == "saigonos.cli:main"


def test_module_can_run_with_python_m(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["saigonos", "--version"])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("saigonos", run_name="__main__")

    assert exit_info.value.code == 0
    assert capsys.readouterr().out == f"saigonos {__version__}\n"
