# SPDX-License-Identifier: Apache-2.0
import json
import re
import shlex
from importlib.resources import files
from pathlib import Path
from typing import get_args

import click
import pytest
from fastapi import HTTPException

from saigonos.cli import main
from saigonos.doctor import PROBES
from saigonos.home import (
    APISIX_INTERNAL_PORTS,
    DEFAULT_ADMIN_PORT,
    DEFAULT_CENTRIFUGO_PORT,
    DEFAULT_HTTP_HOST,
    DEFAULT_HTTP_PORT,
    DEFAULT_KEYCLOAK_PORT,
    DEFAULT_MAX_FILE_SIZE,
    DEFAULT_SEAWEEDFS_PORT,
    LARGEST_FILE_SIZE,
)
from saigonos_core.files import FileInfo
from saigonos_core.forms import CHECKS, START_FORM, TASK_FORM, submitted
from saigonos_core.kinds import KINDS
from saigonos_core.processes import rules_of
from saigonos_core.tasks import Task

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
OPERATON = (files("saigonos") / "stack" / "config" / "operaton" / "production.yml").read_text(
    encoding="utf-8"
)


def section(title):
    return README.split(f"\n{title}\n", 1)[1].split("\n#", 1)[0]


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
    rows = [re.split(r" {2,}", row, maxsplit=2) for row in DOCTOR_SAMPLE.splitlines()[:-1]]
    probes = [name for name, _ in PROBES]
    finished = {name: detail == "đã chạy xong" for _, name, detail in rows if name not in probes}
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
    assert [name for _, name, _ in rows if name in probes] == probes
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
    ports = [
        DEFAULT_HTTP_PORT,
        DEFAULT_ADMIN_PORT,
        DEFAULT_KEYCLOAK_PORT,
        DEFAULT_SEAWEEDFS_PORT,
        DEFAULT_CENTRIFUGO_PORT,
    ]
    *first, last = map(str, ports)

    assert f"Hệ thống dùng các cổng {', '.join(first)} và {last}." in README
    assert f"Centrifugo nằm ở cổng {DEFAULT_CENTRIFUGO_PORT}," in README


def test_readme_states_file_size_limits():
    assert f"tính bằng MB, từ 1 đến {LARGEST_FILE_SIZE}." in README
    assert f"Mỗi file có dung lượng tối đa {DEFAULT_MAX_FILE_SIZE} MB" in README
    assert f"client_max_body_size {DEFAULT_MAX_FILE_SIZE}m;" in README


def test_readme_lists_every_allowed_file_type():
    rows = re.findall(r"^\| `([a-z]+/[^`]+)` \| ([^|]+) \|", README, re.MULTILINE)

    assert {kind: re.findall(r"`(\.[a-z]+)`", extensions) for kind, extensions in rows} == {
        kind: list(rule.extensions) for kind, rule in KINDS.items()
    }


def test_readme_lists_every_file_status():
    rows = re.findall(r"^\| `([a-z_]+)` \|", section("## Tải file lên"), re.MULTILINE)

    assert rows == list(get_args(FileInfo.model_fields["status"].annotation))


def test_readme_lists_every_task_field():
    rows = re.findall(r"^\| (`[^|]+) \|", section("### Danh sách việc"), re.MULTILINE)

    assert [name for row in rows for name in re.findall(r"`(\w+)`", row)] == list(Task.model_fields)


def test_readme_lists_every_form_field_type():
    kinds = section("### Form").split("| Ràng buộc |")[0]

    assert set(re.findall(r"^\| `([a-z]+)` \|", kinds, re.MULTILINE)) == set(CHECKS)


def test_readme_sample_process_accepts_values_of_examples():
    [xml] = [
        block for block in re.findall(r"```xml\n(.*?)```", README, re.DOTALL) if "yeu_cau" in block
    ]
    rules = rules_of(xml, "yeu_cau")
    started, completed = (
        dict(re.findall(r'(\w+): "([^"]*)"', values))
        for values in re.findall(r"variables: \{ ([^}]*) \}", README)
    )

    with pytest.raises(HTTPException) as refused:
        submitted(rules.task_forms["xu_ly"], {}, TASK_FORM)

    assert (
        submitted(rules.start_form, started, START_FORM)["noi_dung"]["value"] == started["noi_dung"]
    )
    assert (
        submitted(rules.task_forms["xu_ly"], completed, TASK_FORM)["ket_qua"]["value"]
        == (completed["ket_qua"])
    )
    assert [json.loads(block) for block in re.findall(r"```json\n(.*?)```", README, re.DOTALL)] == [
        {"detail": refused.value.detail}
    ]


def test_readme_links_point_to_existing_sections():
    links = re.findall(r"\]\(#([^)]+)\)", PROSE)

    assert links
    assert set(links) <= {anchor(heading) for heading in HEADINGS}


def test_readme_table_of_contents_lists_every_section():
    listed = re.findall(r"^- \[(.+)\]\(#(.+)\)$", section("## Mục lục"), re.MULTILINE)
    sections = [
        title for title in re.findall(r"^## (.+)$", PROSE, re.MULTILINE) if title != "Mục lục"
    ]

    assert listed == [(title, anchor(title)) for title in sections]


def test_readme_states_the_default_values():
    assert f"| `--http-host` | `{DEFAULT_HTTP_HOST}` |" in README
    assert f"| `--http-port` | `{DEFAULT_HTTP_PORT}` |" in README
    assert f"| `--admin-port` | `{DEFAULT_ADMIN_PORT}` |" in README
    assert f"| `--keycloak-port` | `{DEFAULT_KEYCLOAK_PORT}` |" in README
    assert f"| `--seaweedfs-port` | `{DEFAULT_SEAWEEDFS_PORT}` |" in README
    assert f"| `--centrifugo-port` | `{DEFAULT_CENTRIFUGO_PORT}` |" in README
    assert f"| `--url` | `http://localhost:{DEFAULT_HTTP_PORT}` |" in README
    assert f"| `--max-file-size` | `{DEFAULT_MAX_FILE_SIZE}` |" in README
    assert "| `--home` | `~/saigonos` |" in README
    assert "| `--caddy`, `--no-caddy` | Tắt |" in README


def test_readme_states_job_settings_of_operaton():
    wait = int(re.search(r"^ +max-wait: (\d+)$", OPERATON, re.MULTILINE)[1])
    begin, end = re.findall(r'batch-window-(?:start|end)-time: "(\d\d:\d\d)\+0700"', OPERATON)

    assert f"{wait // 1000} giây một lần" in PROSE
    assert f"từ {begin} đến {end} giờ Việt Nam" in PROSE
