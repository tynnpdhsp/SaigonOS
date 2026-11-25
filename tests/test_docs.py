# SPDX-License-Identifier: Apache-2.0
import json
import re
import shlex
import shutil
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
from saigonos_core.lake import BUCKET
from saigonos_core.manifest import (
    DESCRIPTION_LENGTH,
    MANIFEST,
    NAME_LENGTH,
    QUALITY_RULES,
    RESERVED_NAMES,
    RESERVED_PREFIX,
    ROLE_LENGTH,
    RULE_COLUMNS,
    SEARCH_COLUMNS,
    SEARCH_TABLES,
    TABLE_LENGTH,
    TITLE_LENGTH,
    Manifest,
    SearchTable,
)
from saigonos_core.notifications import Notification
from saigonos_core.processes import rules_of
from saigonos_core.smtp import NONE, PORTS, STARTTLS, TLS
from saigonos_core.tasks import Task

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
REPO = "https://github.com/tynnpdhsp/SaigonOS/blob/main/"
TREE = "https://github.com/tynnpdhsp/SaigonOS/tree/main/"
TAG = "SPDX-License-Identifier"
SPDX = f"<!-- {TAG}: Apache-2.0 -->"
PAGES = {
    path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
    for path in [ROOT / "README.md", *sorted(DOCS.rglob("*.md"))]
}
TEXT = "\n".join(PAGES.values())
GUIDES = "\n".join(text for name, text in PAGES.items() if not name.startswith("docs/development/"))


def bash_lines(text):
    return [
        line.strip()
        for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL)
        for line in block.splitlines()
    ]


def prose_of(text):
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


BLOCK_LINES = bash_lines(GUIDES)
INLINE = re.findall(r"`([^`\n]+)`", GUIDES)
COMMANDS = sorted({text for text in [*BLOCK_LINES, *INLINE] if text.startswith("saigonos ")})
SAMPLES = re.findall(r"```text\n(.*?)```", TEXT, re.DOTALL)
DOCTOR_SAMPLE = next(sample for sample in SAMPLES if sample.startswith("BÌNH THƯỜNG    apisix"))
VERIFY_SAMPLES = [sample for sample in SAMPLES if "audit log" in sample.lower()]
PROSE = prose_of(TEXT)
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
JSON_BLOCKS = re.findall(r"```json\n(.*?)```", TEXT, re.DOTALL)
MANIFEST_EXAMPLE = next(json.loads(block) for block in JSON_BLOCKS if '"$schema"' in block)
CHECK_SAMPLES = [sample for sample in SAMPLES if sample.startswith("Ứng dụng")]
EXAMPLE = ROOT / "examples" / "phong-may"
EXAMPLE_MANIFEST = json.loads((EXAMPLE / "saigonos-app.json").read_text(encoding="utf-8"))
EXAMPLE_PROCESS = (EXAMPLE / "processes" / "dat-phong.bpmn").read_text(encoding="utf-8")


def section(page, title):
    found = re.split(rf"^#+ {re.escape(title)}\n", PAGES[page], flags=re.MULTILINE)[1:]
    assert len(found) == 1, title
    return found[0].split("\n#", 1)[0]


def anchor(heading):
    return re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")


def leaf_commands(group):
    for command in group.commands.values():
        if isinstance(command, click.Group):
            yield from leaf_commands(command)
        else:
            yield command


def test_readme_shows_the_whole_install_path():
    lines = set(bash_lines(PAGES["README.md"]))

    assert {"pip install .", "saigonos init", "saigonos up", "saigonos doctor"} <= lines


@pytest.mark.parametrize("line", COMMANDS)
def test_docs_command_is_accepted_by_cli(line):
    command, arguments = main, shlex.split(line)[1:]
    while isinstance(command, click.Group):
        name, *arguments = arguments
        assert name in command.commands
        command = command.commands[name]

    with command.make_context(command.name, arguments) as context:
        assert context.command is command


def test_docs_options_exist_in_cli():
    documented = {text for text in INLINE if text.startswith("--")}
    known = {"--help"} | {
        option
        for command in leaf_commands(main)
        for parameter in command.params
        for option in [*parameter.opts, *parameter.secondary_opts]
    }

    assert documented
    assert documented <= known


def test_docs_shows_real_output_of_doctor(tmp_path, cli, docker, gateway):
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


def test_docs_shows_real_output_of_audit_verify(tmp_path, cli, docker):
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


def test_docs_lists_ports_that_http_port_cannot_use():
    *first, last = APISIX_INTERNAL_PORTS

    assert f"Cổng HTTP không được trùng các cổng {', '.join(first)} và {last}." in TEXT


def test_docs_lists_ports_used_by_default():
    ports = [
        DEFAULT_HTTP_PORT,
        DEFAULT_ADMIN_PORT,
        DEFAULT_KEYCLOAK_PORT,
        DEFAULT_SEAWEEDFS_PORT,
        DEFAULT_CENTRIFUGO_PORT,
    ]
    *first, last = map(str, ports)

    assert f"Hệ thống dùng các cổng {', '.join(first)} và {last}." in TEXT
    assert f"Centrifugo nằm ở cổng {DEFAULT_CENTRIFUGO_PORT}," in TEXT


def test_docs_states_file_size_limits():
    assert f"tính bằng MB, từ 1 đến {LARGEST_FILE_SIZE}." in TEXT
    assert f"Mỗi file có dung lượng tối đa {DEFAULT_MAX_FILE_SIZE} MB" in TEXT
    assert f"client_max_body_size {DEFAULT_MAX_FILE_SIZE}m;" in TEXT


def test_docs_lists_every_allowed_file_type():
    rows = re.findall(
        r"^\| `([a-z]+/[^`]+)` \| ([^|]+) \|", PAGES["docs/apps/files.md"], re.MULTILINE
    )

    assert {kind: re.findall(r"`(\.[a-z]+)`", extensions) for kind, extensions in rows} == {
        kind: list(rule.extensions) for kind, rule in KINDS.items()
    }


def test_docs_lists_every_file_status():
    rows = re.findall(
        r"^\| `([a-z_]+)` \|", section("docs/apps/files.md", "Tải file lên"), re.MULTILINE
    )

    assert rows == list(get_args(FileInfo.model_fields["status"].annotation))


def test_docs_lists_every_task_field():
    rows = re.findall(
        r"^\| (`[^|]+) \|", section("docs/apps/workflow.md", "Danh sách việc"), re.MULTILINE
    )

    assert [name for row in rows for name in re.findall(r"`(\w+)`", row)] == list(Task.model_fields)


def test_docs_lists_every_notification_field():
    rows = re.findall(
        r"^\| (`[^|]+) \|", section("docs/apps/notifications.md", "Đọc thông báo"), re.MULTILINE
    )

    assert [name for row in rows for name in re.findall(r"`(\w+)`", row)] == list(
        Notification.model_fields
    )


def test_docs_lists_every_form_field_type():
    kinds = section("docs/apps/workflow.md", "Form").split("| Ràng buộc |")[0]

    assert set(re.findall(r"^\| `([a-z]+)` \|", kinds, re.MULTILINE)) == set(CHECKS)


def test_docs_sample_process_accepts_values_of_examples():
    page = PAGES["docs/apps/workflow.md"]
    blocks = re.findall(r"```json\n(.*?)```", page, re.DOTALL)
    started, completed = (
        json.loads(block)["variables"] for block in blocks if '"variables"' in block
    )
    rules = rules_of(EXAMPLE_PROCESS, "phong_may.dat_phong")

    with pytest.raises(HTTPException) as refused:
        submitted(rules.task_forms["duyet"], {}, TASK_FORM)

    assert submitted(rules.start_form, started, START_FORM)["ma_phong"]["value"] == "PM1"
    assert (
        submitted(rules.task_forms["duyet"], completed, TASK_FORM)["ket_qua"]["value"]
        == (completed["ket_qua"])
    )
    assert [json.loads(block) for block in blocks if '"detail"' in block] == [
        {"detail": refused.value.detail}
    ]


def stripped(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def contains(lines, part):
    return any(lines[index : index + len(part)] == part for index in range(len(lines)))


def excerpts():
    for name in ["docs/first-app.md", *(name for name in PAGES if name.startswith("docs/apps/"))]:
        if name not in PAGES:
            continue
        before = ""
        for part in re.split(r"(```[^\n]*\n.*?```)", PAGES[name], flags=re.DOTALL):
            if not part.startswith("```"):
                before = part.strip().split("\n\n")[-1]
                continue
            files = {
                EXAMPLE / token
                for token in re.findall(r"`([\w./-]+)`", before)
                if (EXAMPLE / token).is_file()
            }
            if len(files) == 1:
                yield name, files.pop(), part.split("\n", 1)[1].rsplit("```", 1)[0]


EXCERPTS = list(excerpts())


def test_first_app_walks_through_every_file_of_sample_app():
    page = PAGES["docs/first-app.md"]
    files = {path.relative_to(EXAMPLE).as_posix() for path in EXAMPLE.rglob("*") if path.is_file()}
    mentioned = set(re.findall(r"`((?:database|processes|ui)/[\w.-]+|saigonos-app\.json)`", page))
    tree = next(block for block in SAMPLES if block.startswith("examples/phong-may/"))

    assert mentioned == files
    assert sorted(re.findall(r"── ([\w-]+\.\w+)$", tree, re.MULTILINE)) == sorted(
        path.rsplit("/", 1)[-1] for path in files
    )


def test_docs_have_excerpts_of_sample_app():
    assert len(EXCERPTS) >= 6


@pytest.mark.parametrize(("name", "file", "block"), EXCERPTS)
def test_docs_excerpt_of_sample_app_matches_its_file(name, file, block):
    assert contains(stripped(file.read_text(encoding="utf-8")), stripped(block))


def targets_of(text):
    prose = re.sub(r"`[^`\n]*`", "", prose_of(text))
    return re.findall(r"\]\(([^)\s]+)\)", prose)


def anchors_of(text):
    return [
        anchor(heading) for heading in re.findall(r"^#{1,6} (.+)$", prose_of(text), re.MULTILINE)
    ]


@pytest.mark.parametrize("name", PAGES)
def test_docs_links_point_to_existing_pages_and_sections(name):
    for target in targets_of(PAGES[name]):
        if target.startswith(TREE):
            assert (ROOT / target.removeprefix(TREE)).is_dir(), target
            continue
        if target.startswith(("http://", "https://")) and not target.startswith(REPO):
            continue
        path, _, fragment = target.removeprefix(REPO).partition("#")
        if target.startswith(REPO):
            file = ROOT / path
        else:
            file = ((ROOT / name).parent / path if path else ROOT / name).resolve()
            assert not name.startswith("docs/") or file.is_relative_to(DOCS), target
        assert file.is_file(), target
        if fragment:
            assert fragment in anchors_of(file.read_text(encoding="utf-8")), target


@pytest.mark.parametrize("name", PAGES)
def test_docs_headings_are_unique_within_page(name):
    anchors = anchors_of(PAGES[name])

    assert len(anchors) == len(set(anchors))


def test_docs_index_lists_every_page_once():
    listed = re.findall(r"^- \[[^\]]+\]\(([^)]+)\)$", PAGES["docs/README.md"], re.MULTILINE)
    pages = [name.removeprefix("docs/") for name in PAGES if name.startswith("docs/")]

    assert sorted(listed) == sorted(page for page in pages if page != "README.md")


@pytest.mark.parametrize("name", [name for name in PAGES if name.startswith("docs/")])
def test_docs_page_starts_with_licence_and_title_and_has_no_mdx_syntax_in_prose(name):
    text = PAGES[name]
    prose = re.sub(r"`[^`\n]*`", "", prose_of(text).removeprefix(SPDX))

    assert text.startswith(f"{SPDX}\n# ")
    assert not re.search(r"[<{}]", prose)


def test_docs_states_the_default_values():
    assert f"| `--http-host` | `{DEFAULT_HTTP_HOST}` |" in TEXT
    assert f"| `--http-port` | `{DEFAULT_HTTP_PORT}` |" in TEXT
    assert f"| `--admin-port` | `{DEFAULT_ADMIN_PORT}` |" in TEXT
    assert f"| `--keycloak-port` | `{DEFAULT_KEYCLOAK_PORT}` |" in TEXT
    assert f"| `--seaweedfs-port` | `{DEFAULT_SEAWEEDFS_PORT}` |" in TEXT
    assert f"| `--centrifugo-port` | `{DEFAULT_CENTRIFUGO_PORT}` |" in TEXT
    assert f"| `--url` | `http://localhost:{DEFAULT_HTTP_PORT}` |" in TEXT
    assert f"| `--max-file-size` | `{DEFAULT_MAX_FILE_SIZE}` |" in TEXT
    assert "| `--home` | `~/saigonos` |" in TEXT
    assert "| `--caddy`, `--no-caddy` | Tắt |" in TEXT


def test_docs_states_job_settings_of_operaton():
    wait = int(re.search(r"^ +max-wait: (\d+)$", OPERATON, re.MULTILINE)[1])
    begin, end = re.findall(r'batch-window-(?:start|end)-time: "(\d\d:\d\d)\+0700"', OPERATON)

    assert f"{wait // 1000} giây một lần" in PROSE
    assert f"từ {begin} đến {end} giờ Việt Nam" in PROSE


def test_docs_states_history_of_centrifugo():
    sizes = re.findall(r"^ +history_size: (\d+)$", CENTRIFUGO, re.MULTILINE)
    ttls = re.findall(r"^ +history_ttl: (\d+)s$", CENTRIFUGO, re.MULTILINE)
    size, minutes = sizes[0], int(ttls[0]) // 60

    assert len(sizes) == len(ttls) == 3
    assert len(set(sizes)) == len(set(ttls)) == 1
    assert f"giữ tối đa {size} tin gần nhất trong {minutes} phút" in PROSE
    assert f"lỡ quá {size} tin, kết nối lại sau quá {minutes} phút" in PROSE
    assert f"sub.history({{ limit: {size} }})" in TEXT


def test_docs_example_of_allowed_origin_matches_init():
    url = "http://[2001:db8::1]:9080"

    assert f"địa chỉ `{url}` được ghi thành `{origin_pattern(url)}`" in PROSE


def duration(seconds):
    return f"{seconds // 60} phút" if seconds % 60 == 0 else f"{seconds} giây"


def test_docs_lists_every_delivery_status():
    rows = re.findall(
        r"^\| `([a-z]+)` \|",
        section("docs/admin/notifications.md", "Hàng đợi gửi tin"),
        re.MULTILINE,
    )
    statuses = re.search(r"status IN \(([^)]+)\)", DELIVERIES)[1]

    assert rows == re.findall(r"'([a-z]+)'", statuses)


def test_docs_lists_every_telegram_setting():
    rows = re.findall(
        r"^\| `(TELEGRAM_[A-Z_]+)` \|",
        section("docs/admin/notifications.md", "Telegram"),
        re.MULTILINE,
    )

    assert sorted(rows) == sorted(re.findall(r"\$\{(TELEGRAM_[A-Z_]+):-", COMPOSE))


def test_docs_lists_every_smtp_setting():
    cells = re.findall(
        r"^\| (`SMTP_[^|]*) \|", section("docs/admin/notifications.md", "Email"), re.MULTILINE
    )
    names = re.findall(r"`(SMTP_[A-Z_]+)`", " ".join(cells))

    assert sorted(names) == sorted(re.findall(r"\$\{(SMTP_[A-Z_]+):-", COMPOSE))


def test_docs_states_default_ports_of_smtp():
    assert (
        f"Mặc định là {PORTS[STARTTLS]}, hoặc {PORTS[TLS]} khi `SMTP_SECURITY` là `{TLS}`, "
        f"hoặc {PORTS[NONE]} khi `SMTP_SECURITY` là `{NONE}`"
    ) in TEXT
    assert f"Mặc định là `{TLS}` khi `SMTP_PORT` là {PORTS[TLS]}, và `{STARTTLS}`" in TEXT


def test_docs_states_retry_rules_of_telegram():
    delays = [duration(seconds) for seconds in RETRY_DELAYS]

    assert f"gửi lại sau {', '.join(delays[:-1])} và {delays[-1]}." in PROSE
    assert f"Sau {MAX_ATTEMPTS} lần gửi lỗi, tin chuyển sang `failed`." in PROSE
    assert f"Tin được gửi lại trong vòng {POLL} giây." in PROSE


def test_docs_example_of_manifest_is_valid():
    manifest = Manifest.model_validate(MANIFEST_EXAMPLE)
    schema = MANIFEST_EXAMPLE["$schema"].split("/SaigonOS/main/", 1)[1]

    assert manifest.ui == "ui"
    assert (ROOT / schema).is_file()
    assert f"]({REPO}{schema})" in TEXT


def test_docs_lists_every_manifest_field():
    rows = re.findall(
        r"^\| `([^`]+)` \| (Có|Không) \|",
        section("docs/apps/manifest.md", "Bản khai"),
        re.MULTILINE,
    )

    assert rows == [
        (field.alias or name, "Có" if field.is_required() else "Không")
        for name, field in Manifest.model_fields.items()
    ]


def test_docs_lists_names_reserved_by_core():
    [line] = [line for line in TEXT.splitlines() if "Các tên đó gồm" in line]

    assert f"không bắt đầu bằng `{RESERVED_PREFIX}`" in line
    assert set(re.findall(r"`([a-z-]+)`", line.split("Các tên đó gồm", 1)[1])) == RESERVED_NAMES


def test_docs_states_limits_of_manifest():
    assert f"Tên bắt đầu bằng chữ cái và dài tối đa {NAME_LENGTH} ký tự." in PROSE
    assert f"Tên role dài tối đa {ROLE_LENGTH} ký tự" in PROSE
    assert (
        f"Tên hiển thị dài tối đa {TITLE_LENGTH} ký tự, "
        f"mô tả của role dài tối đa {DESCRIPTION_LENGTH} ký tự."
    ) in PROSE


def test_docs_example_and_limits_of_search_match_manifest():
    [block] = [block for block in JSON_BLOCKS if block.startswith('"search"')]
    tables = json.loads("{" + block + "}")["search"]

    assert [SearchTable.model_validate(table).model_dump() for table in tables] == tables
    assert f"tối đa {SEARCH_TABLES} bảng" in TEXT
    assert (
        f"Tên bảng dài tối đa {TABLE_LENGTH} ký tự. Mỗi bảng có từ 1 tới {SEARCH_COLUMNS} cột"
    ) in PROSE


def test_docs_example_and_limits_of_lake_entries_match_manifest():
    [block] = [block for block in JSON_BLOCKS if block.startswith('"archive"')]
    example = json.loads("{" + block + "}")

    manifest = Manifest.model_validate(MANIFEST_EXAMPLE | example)

    assert [entry.model_dump(exclude_defaults=True) for entry in manifest.archive] == (
        example["archive"]
    )
    assert [entry.view for entry in manifest.snapshots] == ["lich"]
    assert f"tối đa {QUALITY_RULES} luật. Mỗi luật có tối đa {RULE_COLUMNS} cột" in PROSE
    assert f"bucket `{BUCKET}` của SeaweedFS" in PROSE
    assert f"S3_BUCKET: quarantine,clean,{BUCKET}" in COMPOSE


def test_docs_shows_real_output_of_check(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(apps, "APPS", tmp_path)
    shutil.copytree(EXAMPLE, tmp_path / "dung")
    shutil.copytree(EXAMPLE, tmp_path / "sai")
    roles = [*EXAMPLE_MANIFEST["roles"], {"name": "don-tu.quan-ly", "description": "Duyệt đơn"}]
    wrong = EXAMPLE_MANIFEST | {"version": "1.0", "roles": roles}
    (tmp_path / "sai" / MANIFEST).write_text(json.dumps(wrong), encoding="utf-8")
    (tmp_path / "sai" / "ui" / "index.html").unlink()
    outputs = []

    for name in ("dung", "sai"):
        apps.main(["check", name])
        outputs.append(capsys.readouterr().out)

    assert outputs == CHECK_SAMPLES


def test_docs_shows_real_output_of_apply():
    [sample] = [sample for sample in SAMPLES if sample.startswith("Đã tạo schema")]
    data = EXAMPLE_MANIFEST
    sql_files = sorted(path.name for path in (EXAMPLE / "database").glob("*.sql"))
    processes = sorted((EXAMPLE / "processes").glob("*.bpmn"))
    keys = [re.search(r'<bpmn:process id="([^"]+)"', path.read_text())[1] for path in processes]

    assert sample.splitlines() == [
        CREATED.format(schema=data["name"].replace("-", "_")),
        *(RAN.format(name=sql_file) for sql_file in sql_files),
        *(ROLE_CREATED.format(role=role["name"]) for role in data["roles"]),
        CLIENT_CREATED.format(client=data["name"]),
        ROUTE_CREATED.format(route=route_of(data["name"])),
        *(
            DEPLOYED.format(file=path.name, key=key, version=1)
            for path, key in zip(processes, keys, strict=True)
        ),
        apps.INSTALLED.format(name=data["name"], version=data["version"]),
    ]


def test_docs_states_client_scopes_and_owner_attribute_of_app_clients():
    scopes = ", ".join(f"`{scope}`" for scope in DEFAULT_SCOPES)

    assert f"client scope mặc định {scopes} và không có client scope tùy chọn" in PROSE
    assert f"thuộc tính `{OWNER}` của client và realm role" in PROSE
