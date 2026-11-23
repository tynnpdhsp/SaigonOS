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
from saigonos.doctor import PROBES, WAF_NAME
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
    origin_pattern,
)
from saigonos_core import apps
from saigonos_core.app_database import CREATED, RAN
from saigonos_core.app_gateway import ROUTE_CREATED, route_of
from saigonos_core.app_keycloak import CLIENT_CREATED, DEFAULT_SCOPES, OWNER, ROLE_CREATED
from saigonos_core.app_processes import DEPLOYED
from saigonos_core.deliveries import MAX_ATTEMPTS, POLL, RETRY_DELAYS
from saigonos_core.files import FileInfo
from saigonos_core.forms import CHECKS, START_FORM, TASK_FORM, submitted
from saigonos_core.kinds import KINDS
from saigonos_core.manifest import (
    DESCRIPTION_LENGTH,
    MANIFEST,
    NAME_LENGTH,
    RESERVED_NAMES,
    RESERVED_PREFIX,
    ROLE_LENGTH,
    TITLE_LENGTH,
    Manifest,
)
from saigonos_core.notifications import Notification
from saigonos_core.processes import rules_of
from saigonos_core.smtp import NONE, PORTS, STARTTLS, TLS
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
CENTRIFUGO = (files("saigonos") / "stack" / "config" / "centrifugo" / "config.yaml").read_text(
    encoding="utf-8"
)
STACK = files("saigonos") / "stack"
COMPOSE = (STACK / "compose.yaml").read_text(encoding="utf-8")
DELIVERIES = (STACK / "config" / "postgres" / "migrations" / "0016_deliveries.sql").read_text(
    encoding="utf-8"
)
JSON_BLOCKS = re.findall(r"```json\n(.*?)```", README, re.DOTALL)
MANIFEST_EXAMPLE = next(json.loads(block) for block in JSON_BLOCKS if '"roles"' in block)
CHECK_SAMPLES = [sample for sample in SAMPLES if sample.startswith("Ứng dụng")]
ROOT = Path(__file__).resolve().parent.parent
PROCESS = next(
    block
    for block in re.findall(r"```xml\n(.*?)```", README, re.DOTALL)
    if '"nghi_phep.duyet"' in block
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
    probes = [*(name for name, _ in PROBES), WAF_NAME]
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


def test_readme_lists_every_notification_field():
    rows = re.findall(r"^\| (`[^|]+) \|", section("### Đọc thông báo"), re.MULTILINE)

    assert [name for row in rows for name in re.findall(r"`(\w+)`", row)] == list(
        Notification.model_fields
    )


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
    assert [json.loads(block) for block in JSON_BLOCKS if '"detail"' in block] == [
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


def test_readme_states_history_of_centrifugo():
    sizes = re.findall(r"^ +history_size: (\d+)$", CENTRIFUGO, re.MULTILINE)
    ttls = re.findall(r"^ +history_ttl: (\d+)s$", CENTRIFUGO, re.MULTILINE)
    size, minutes = sizes[0], int(ttls[0]) // 60

    assert len(sizes) == len(ttls) == 3
    assert len(set(sizes)) == len(set(ttls)) == 1
    assert f"giữ tối đa {size} tin gần nhất trong {minutes} phút" in PROSE
    assert f"lỡ quá {size} tin, kết nối lại sau quá {minutes} phút" in PROSE
    assert f"sub.history({{ limit: {size} }})" in README


def test_readme_example_of_allowed_origin_matches_init():
    url = "http://[2001:db8::1]:9080"

    assert f"địa chỉ `{url}` được ghi thành `{origin_pattern(url)}`" in PROSE


def duration(seconds):
    return f"{seconds // 60} phút" if seconds % 60 == 0 else f"{seconds} giây"


def test_readme_lists_every_delivery_status():
    rows = re.findall(r"^\| `([a-z]+)` \|", section("### Hàng đợi gửi tin"), re.MULTILINE)
    statuses = re.search(r"status IN \(([^)]+)\)", DELIVERIES)[1]

    assert rows == re.findall(r"'([a-z]+)'", statuses)


def test_readme_lists_every_telegram_setting():
    rows = re.findall(
        r"^\| `(TELEGRAM_[A-Z_]+)` \|", section("### Gửi thông báo qua Telegram"), re.MULTILINE
    )

    assert sorted(rows) == sorted(re.findall(r"\$\{(TELEGRAM_[A-Z_]+):-", COMPOSE))


def test_readme_lists_every_smtp_setting():
    cells = re.findall(r"^\| (`SMTP_[^|]*) \|", section("### Gửi email"), re.MULTILINE)
    names = re.findall(r"`(SMTP_[A-Z_]+)`", " ".join(cells))

    assert sorted(names) == sorted(re.findall(r"\$\{(SMTP_[A-Z_]+):-", COMPOSE))


def test_readme_states_default_ports_of_smtp():
    assert (
        f"Mặc định là {PORTS[STARTTLS]}, hoặc {PORTS[TLS]} khi `SMTP_SECURITY` là `{TLS}`, "
        f"hoặc {PORTS[NONE]} khi `SMTP_SECURITY` là `{NONE}`"
    ) in README
    assert f"Mặc định là `{TLS}` khi `SMTP_PORT` là {PORTS[TLS]}, và `{STARTTLS}`" in README


def test_readme_states_retry_rules_of_telegram():
    delays = [duration(seconds) for seconds in RETRY_DELAYS]

    assert f"gửi lại sau {', '.join(delays[:-1])} và {delays[-1]}." in PROSE
    assert f"Sau {MAX_ATTEMPTS} lần gửi lỗi, tin chuyển sang `failed`." in PROSE
    assert f"Tin được gửi lại trong vòng {POLL} giây." in PROSE


def write_app(folder, manifest):
    files = {"database/0001_don.sql": "", "processes/duyet.bpmn": PROCESS, "ui/index.html": ""}
    for name, text in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")
    (folder / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")


def test_readme_example_of_manifest_is_valid():
    manifest = Manifest.model_validate(MANIFEST_EXAMPLE)
    schema = MANIFEST_EXAMPLE["$schema"].split("/SaigonOS/main/", 1)[1]

    assert manifest.ui == "ui"
    assert (ROOT / schema).is_file()
    assert f"]({schema})" in README


def test_readme_lists_every_manifest_field():
    rows = re.findall(r"^\| `([^`]+)` \| (Có|Không) \|", section("### Bản khai"), re.MULTILINE)

    assert rows == [
        (field.alias or name, "Có" if field.is_required() else "Không")
        for name, field in Manifest.model_fields.items()
    ]


def test_readme_lists_names_reserved_by_core():
    [line] = [line for line in README.splitlines() if "Các tên đó gồm" in line]

    assert f"không bắt đầu bằng `{RESERVED_PREFIX}`" in line
    assert set(re.findall(r"`([a-z-]+)`", line.split("Các tên đó gồm", 1)[1])) == RESERVED_NAMES


def test_readme_states_limits_of_manifest():
    assert f"Tên bắt đầu bằng chữ cái và dài tối đa {NAME_LENGTH} ký tự." in PROSE
    assert f"Tên role dài tối đa {ROLE_LENGTH} ký tự" in PROSE
    assert (
        f"Tên hiển thị dài tối đa {TITLE_LENGTH} ký tự, "
        f"mô tả của role dài tối đa {DESCRIPTION_LENGTH} ký tự."
    ) in PROSE


def test_readme_shows_real_output_of_check(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(apps, "APPS", tmp_path)
    write_app(tmp_path / "dung", MANIFEST_EXAMPLE)
    roles = [MANIFEST_EXAMPLE["roles"][0], {"name": "don-tu.quan-ly", "description": "Duyệt đơn"}]
    write_app(tmp_path / "sai", MANIFEST_EXAMPLE | {"version": "1.0", "roles": roles})
    (tmp_path / "sai" / "ui" / "index.html").unlink()
    outputs = []

    for name in ("dung", "sai"):
        apps.main(["check", name])
        outputs.append(capsys.readouterr().out)

    assert outputs == CHECK_SAMPLES


def test_readme_shows_real_output_of_apply():
    [sample] = [sample for sample in SAMPLES if sample.startswith("Đã tạo schema")]
    data, sql_files = MANIFEST_EXAMPLE, ["0001_don.sql", "0002_duyet.sql"]
    key = re.search(r'<bpmn:process id="([^"]+)"', PROCESS)[1]

    assert sample.splitlines() == [
        CREATED.format(schema=data["name"].replace("-", "_")),
        *(RAN.format(name=sql_file) for sql_file in sql_files),
        *(ROLE_CREATED.format(role=role["name"]) for role in data["roles"]),
        CLIENT_CREATED.format(client=data["name"]),
        ROUTE_CREATED.format(route=route_of(data["name"])),
        DEPLOYED.format(file="duyet.bpmn", key=key, version=1),
        apps.INSTALLED.format(name=data["name"], version=data["version"]),
    ]
    assert f"Ví dụ file `database/{sql_files[0]}`" in PROSE
    assert f"File `database/{sql_files[1]}`" in PROSE
    assert "Ví dụ, file `processes/duyet.bpmn`" in PROSE


def test_readme_states_client_scopes_and_owner_attribute_of_app_clients():
    scopes = ", ".join(f"`{scope}`" for scope in DEFAULT_SCOPES)

    assert f"client scope mặc định {scopes} và không có client scope tùy chọn" in PROSE
    assert f"thuộc tính `{OWNER}` của client và realm role" in PROSE
