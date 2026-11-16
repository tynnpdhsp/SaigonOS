# SPDX-License-Identifier: Apache-2.0
import json
import re
import shlex
from pathlib import Path

import click
import pytest

from saigonos.cli import main
from saigonos.home import (
    APISIX_INTERNAL_PORTS,
    DEFAULT_ADMIN_PORT,
    DEFAULT_HTTP_HOST,
    DEFAULT_HTTP_PORT,
    DEFAULT_KEYCLOAK_PORT,
    DEFAULT_SEAWEEDFS_PORT,
)

README = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
BLOCK_LINES = [
    line.strip()
    for block in re.findall(r"```bash\n(.*?)```", README, re.DOTALL)
    for line in block.splitlines()
]
INLINE = re.findall(r"`([^`\n]+)`", README)
COMMANDS = sorted({text for text in [*BLOCK_LINES, *INLINE] if text.startswith("saigonos ")})
SAMPLES = re.findall(r"```text\n(.*?)```", README, re.DOTALL)
DOCTOR_SAMPLE = SAMPLES[0]
VERIFY_SAMPLES = [sample for sample in SAMPLES if "audit log" in sample.lower()]
PROSE = re.sub(r"```.*?```", "", README, flags=re.DOTALL)
HEADINGS = re.findall(r"^#{1,6} (.+)$", PROSE, re.MULTILINE)


def anchor(heading):
    return re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")


def leaf_commands(group):
    for command in group.commands.values():
        if isinstance(command, click.Group):
            yield from leaf_commands(command)
        else:
            yield command


def test_readme_shows_the_whole_install_path():
    assert {"pip install .", "saigonos init", "docker compose up -d --wait"} <= set(BLOCK_LINES)
    assert "saigonos doctor" in BLOCK_LINES


@pytest.mark.parametrize("line", COMMANDS)
def test_readme_command_is_accepted_by_cli(line):
    command, arguments = main, shlex.split(line)[1:]
    while isinstance(command, click.Group):
        name, *arguments = arguments
        assert name in command.commands
        command = command.commands[name]

    with command.make_context(command.name, arguments) as context:
        assert context.command is command


def test_readme_options_exist_in_cli():
    documented = {text for text in INLINE if text.startswith("--")}
    known = {
        option
        for command in leaf_commands(main)
        for parameter in command.params
        for option in [*parameter.opts, *parameter.secondary_opts]
    }

    assert documented
    assert documented <= known


def test_readme_shows_real_output_of_doctor(tmp_path, cli, docker, gateway):
    rows = [re.split(r" {2,}", row, maxsplit=2) for row in DOCTOR_SAMPLE.splitlines()]
    finished = {name: detail == "đã chạy xong" for _, name, detail in rows[:-3]}
    docker.services(
        {name: {"restart": "no" if done else "unless-stopped"} for name, done in finished.items()},
        [
            {"Service": name, "State": "exited" if done else "running", "ExitCode": 0}
            for name, done in finished.items()
        ],
    )
    cli("init", "--home", tmp_path / "home", "--url", gateway.url)

    result = cli("doctor", "--home", tmp_path / "home")

    assert finished
    assert result.output == DOCTOR_SAMPLE.replace("http://localhost:9080", gateway.url)


def test_readme_shows_real_output_of_audit_verify(tmp_path, cli, docker):
    unbroken, changed = VERIFY_SAMPLES
    states = [
        {"rows": int(re.search(r"\d+", unbroken)[0]), "last_hash": unbroken.split()[-1]},
        {"rows": 1250, "last_hash": "", "changed": int(re.search(r"\d+", changed)[0])},
    ]
    cli("init", "--home", tmp_path / "home")
    outputs = []

    for state in states:
        docker.reply("exec", json.dumps({"missing": None, "changed": None} | state))
        outputs.append(cli("audit", "verify", "--home", tmp_path / "home").output)

    assert outputs == VERIFY_SAMPLES


def test_readme_lists_ports_that_http_port_cannot_use():
    *first, last = APISIX_INTERNAL_PORTS

    assert f"Cổng HTTP không được trùng các cổng {', '.join(first)} và {last}." in README


def test_readme_lists_ports_used_by_default():
    ports = [DEFAULT_HTTP_PORT, DEFAULT_ADMIN_PORT, DEFAULT_KEYCLOAK_PORT, DEFAULT_SEAWEEDFS_PORT]
    *first, last = map(str, ports)

    assert f"Hệ thống dùng các cổng {', '.join(first)} và {last}." in README


def test_readme_links_point_to_existing_sections():
    links = re.findall(r"\]\(#([^)]+)\)", PROSE)

    assert links
    assert set(links) <= {anchor(heading) for heading in HEADINGS}


def test_readme_states_the_default_values():
    assert f"| `--http-host` | `{DEFAULT_HTTP_HOST}` |" in README
    assert f"| `--http-port` | `{DEFAULT_HTTP_PORT}` |" in README
    assert f"| `--admin-port` | `{DEFAULT_ADMIN_PORT}` |" in README
    assert f"| `--keycloak-port` | `{DEFAULT_KEYCLOAK_PORT}` |" in README
    assert f"| `--seaweedfs-port` | `{DEFAULT_SEAWEEDFS_PORT}` |" in README
    assert f"| `--url` | `http://localhost:{DEFAULT_HTTP_PORT}` |" in README
    assert "| `--home` | `~/saigonos` |" in README
    assert "| `--caddy`, `--no-caddy` | Tắt |" in README
