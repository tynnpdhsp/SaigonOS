# SPDX-License-Identifier: Apache-2.0
import json

import pytest

from saigonos.audit import CHAIN

LAST_HASH = "1df5c68192da0b9f077c8e6dd77ad3196de0d1d42fae945e2e31f4ad1c5710f9"
UNBROKEN = f"Audit log có 8 dòng. Chuỗi mã băm khớp.\nMã băm của dòng cuối: {LAST_HASH}\n"
CHANGED = (
    "Dòng {row} của audit log không khớp mã băm. Nội dung hoặc mã băm của dòng này đã bị sửa.\n"
)
MISSING = "Audit log thiếu dòng {row}. Dòng này đã bị xóa hoặc bị đổi số thứ tự.\n"


@pytest.fixture
def home(tmp_path, cli):
    path = tmp_path / "home"
    cli("init", "--home", path)
    return path


def chain(**values):
    return json.dumps(
        {"rows": 8, "last_hash": LAST_HASH, "missing": None, "changed": None} | values
    )


def test_verify_reads_audit_log_as_superuser_inside_postgres_container(home, cli, docker):
    docker.reply("exec", chain())

    cli("audit", "verify", "--home", home)

    assert "\n".join(docker.calls) == (
        f"{home.resolve()}: compose exec -T postgres psql --username=postgres --dbname=saigonos "
        f"--no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 --command={CHAIN}"
    )


def test_verify_computes_hash_without_function_stored_in_database():
    assert "FROM core.audit_log" in CHAIN
    assert "audit_hash" not in CHAIN


@pytest.mark.parametrize(
    ("state", "exit_code", "output"),
    [
        ({}, 0, UNBROKEN),
        ({"rows": 0, "last_hash": None}, 0, "Audit log chưa có dòng nào.\n"),
        ({"changed": 4}, 1, CHANGED.format(row=4)),
        ({"rows": 7, "missing": 3}, 1, MISSING.format(row=3)),
        ({"rows": 7, "missing": 3, "changed": 4}, 1, MISSING.format(row=3)),
        ({"rows": 7, "missing": 6, "changed": 2}, 1, CHANGED.format(row=2)),
        ({"rows": 7, "missing": 1, "changed": 2}, 1, MISSING.format(row=1)),
    ],
    ids=[
        "nguyen-ven",
        "chua-co-dong",
        "dong-bi-sua",
        "thieu-dong",
        "thieu-truoc-sua",
        "sua-truoc-thieu",
        "thieu-dong-dau",
    ],
)
def test_verify_reports_first_broken_row(home, cli, docker, state, exit_code, output):
    docker.reply("exec", chain(**state))

    result = cli("audit", "verify", "--home", home)

    assert result.exit_code == exit_code
    assert result.output == output


def test_verify_stops_when_database_cannot_be_read(home, cli, docker):
    docker.reply("exec", error='service "postgres" is not running\n', code=1)

    result = cli("audit", "verify", "--home", home)

    assert result.exit_code == 1
    assert result.output == (
        'Error: Lệnh docker compose exec không chạy được: service "postgres" is not running\n'
    )
