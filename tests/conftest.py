# SPDX-License-Identifier: Apache-2.0
import os

import pytest
from click.testing import CliRunner

from saigonos.cli import main

FAKE_DOCKER = """\
#!/bin/sh
dir="${0%/*}"
printf '%s\\n' "$(pwd -P): $*" >> "$dir/calls"
[ -f "$dir/$2.out" ] && cat "$dir/$2.out"
[ -f "$dir/$2.err" ] && cat "$dir/$2.err" >&2
[ -f "$dir/$2.code" ] && exit "$(cat "$dir/$2.code")"
exit 0
"""


class FakeDocker:
    def __init__(self, directory):
        self.directory = directory

    def reply(self, subcommand, output="", error="", code=0):
        (self.directory / f"{subcommand}.out").write_text(output, encoding="utf-8")
        (self.directory / f"{subcommand}.err").write_text(error, encoding="utf-8")
        (self.directory / f"{subcommand}.code").write_text(str(code), encoding="utf-8")

    @property
    def calls(self):
        log = self.directory / "calls"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


@pytest.fixture(autouse=True)
def no_home_variable(monkeypatch):
    monkeypatch.delenv("SAIGONOS_HOME", raising=False)


@pytest.fixture
def cli():
    def invoke(*args):
        return CliRunner().invoke(main, [str(arg) for arg in args])

    return invoke


@pytest.fixture
def docker(tmp_path, monkeypatch):
    directory = tmp_path / "bin"
    directory.mkdir()
    script = directory / "docker"
    script.write_text(FAKE_DOCKER, encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ['PATH']}")
    return FakeDocker(directory)
