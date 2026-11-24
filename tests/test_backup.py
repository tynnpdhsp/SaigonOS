# SPDX-License-Identifier: Apache-2.0
import hashlib
import io
import json
import stat
import tarfile

import pytest
from click.testing import CliRunner

from saigonos import __version__
from saigonos.cli import main

GZIP_HEADER = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff"
DUMP = "pg_dumpall --username=postgres --clean --if-exists"
COPY = "run --rm -T backup -C /seaweedfs -cf - ."


@pytest.fixture
def home(tmp_path, cli, docker):
    path = tmp_path / "home"
    cli("init", "--home", path)
    docker.reply("ps", json.dumps({"Service": "seaweedfs", "Health": "healthy"}))
    (path / "apps" / "nghi-phep").mkdir(parents=True)
    (path / "apps" / "nghi-phep" / "saigonos-app.json").write_text("{}", encoding="utf-8")
    return path


def read_bundle(path):
    with tarfile.open(path, "r:gz") as tar:
        return {item.name: tar.extractfile(item).read() for item in tar}


def calls_of(docker, home):
    prefix = f"{home.resolve()}: compose "
    return [call.removeprefix(prefix) for call in docker.calls]


def test_backup_packs_database_files_env_and_apps_with_hashes(home, cli, docker):
    docker.reply("exec", output="-- ban sao co so du lieu\n")
    docker.reply("run", output="tep-seaweedfs")

    result = cli("backup", "--home", home)

    assert result.exit_code == 0, result.output
    [bundle] = (home / "backups").iterdir()
    assert bundle.name.startswith("saigonos-") and bundle.name.endswith(".tar.gz")
    assert stat.S_IMODE(bundle.stat().st_mode) == 0o600
    assert stat.S_IMODE((home / "backups").stat().st_mode) == 0o700
    assert bundle.read_bytes()[:10] == GZIP_HEADER
    parts = read_bundle(bundle)
    assert [*parts] == [
        "manifest.json",
        "SHA256SUMS",
        "env",
        "postgres.sql",
        "seaweedfs.tar",
        "apps.tar",
    ]
    assert parts["env"] == (home / ".env").read_bytes()
    assert parts["postgres.sql"] == b"-- ban sao co so du lieu\n"
    assert parts["seaweedfs.tar"] == b"tep-seaweedfs"
    with tarfile.open(fileobj=io.BytesIO(parts["apps.tar"])) as apps:
        assert "./nghi-phep/saigonos-app.json" in apps.getnames()
    sums = {name: hashlib.sha256(data).hexdigest() for name, data in parts.items()}
    lines = parts["SHA256SUMS"].decode().splitlines()
    assert lines == [f"{sums[name]}  {name}" for name in parts if name != "SHA256SUMS"]
    manifest = json.loads(parts["manifest.json"])
    assert manifest["saigonos"] == __version__
    assert manifest["parts"] == ["env", "postgres.sql", "seaweedfs.tar", "apps.tar"]
    assert f"Đã tạo gói sao lưu {bundle}" in result.output
    assert calls_of(docker, home) == [
        f"exec -T postgres {DUMP}",
        "pause seaweedfs",
        COPY,
        "unpause seaweedfs",
        "ps --all --format json",
    ]


def test_backup_adds_caddy_certificates_when_caddy_has_data(home, cli, docker):
    (home / "data" / "caddy").mkdir(parents=True)
    docker.reply("run", output="du-lieu")
    output = home.parent / "ngoai"

    result = cli("backup", "--home", home, "--output", output)

    assert result.exit_code == 0, result.output
    [bundle] = output.iterdir()
    assert read_bundle(bundle)["caddy.tar"] == b"du-lieu"
    caddy = f"run --rm -T --volume {home.resolve()}/data/caddy:/caddy:ro backup -C /caddy -cf - ."
    assert calls_of(docker, home)[-1] == caddy


def test_backup_resumes_seaweedfs_and_keeps_nothing_when_copy_fails(home, cli, docker):
    docker.reply("run", error="khong doc duoc volume", code=1)

    result = cli("backup", "--home", home)

    assert result.exit_code == 1
    assert "Lệnh docker compose run không chạy được: khong doc duoc volume" in result.output
    assert calls_of(docker, home)[-2:] == [COPY, "unpause seaweedfs"]
    assert [*(home / "backups").iterdir()] == []


def test_backup_fails_when_seaweedfs_stays_unhealthy(home, cli, docker, monkeypatch):
    docker.reply("ps", json.dumps({"Service": "seaweedfs", "Health": "unhealthy"}))
    monkeypatch.setattr("saigonos.backup.HEALTH_WAIT", 0)

    result = cli("backup", "--home", home)

    assert result.exit_code == 1
    assert "Service seaweedfs chưa đạt healthcheck sau 0 giây kể từ lúc chạy lại." in result.output
    assert [*(home / "backups").iterdir()] == []


def test_backup_needs_a_working_folder(tmp_path, cli, docker):
    result = cli("backup", "--home", tmp_path / "khong-co")

    assert result.exit_code == 1
    assert "Chưa có thư mục làm việc" in result.output
    assert not (tmp_path / "khong-co").exists()


VOLUMES = ("postgres-data", "seaweedfs-data", "etcd-data", "clamav-data")
CONFIG = {"services": {}, "volumes": {name: {"name": f"moi_{name}"} for name in VOLUMES}}
EXPECTED = (
    "psql:<stdin>:3: ERROR:  current user cannot be dropped\n"
    'psql:<stdin>:9: ERROR:  role "postgres" already exists\n'
)
LOAD = "exec -T postgres psql --username=postgres --dbname=postgres --no-psqlrc --quiet"


@pytest.fixture
def bundle(home, cli, docker):
    docker.reply("exec", output="-- ban sao\n")
    docker.reply("run", output="tep-seaweedfs")
    assert cli("backup", "--home", home).exit_code == 0
    [path] = (home / "backups").iterdir()
    docker.reply("exec", error=EXPECTED)
    docker.reply("run")
    docker.reply("config", output=json.dumps(CONFIG))
    (docker.directory / "calls").unlink()
    return path


def restore_calls(docker):
    return [call.split(": ", 1)[1].removeprefix("compose ") for call in docker.calls]


def test_restore_builds_a_new_working_folder_from_the_bundle(bundle, home, cli, docker, tmp_path):
    target = tmp_path / "moi"

    result = cli("restore", "--home", target, "--yes", bundle)

    assert result.exit_code == 0, result.output
    assert (target / ".env").read_bytes() == (home / ".env").read_bytes()
    assert stat.S_IMODE((target / ".env").stat().st_mode) == 0o600
    assert (target / "apps" / "nghi-phep" / "saigonos-app.json").is_file()
    assert (target / "compose.yaml").is_file()
    assert (docker.directory / "exec.in").read_bytes() == b"-- ban sao\n"
    assert (docker.directory / "run.in").read_bytes() == b"tep-seaweedfs"
    calls = restore_calls(docker)
    assert calls[:5] == [
        "config --format json",
        "volume rm --force moi_postgres-data moi_seaweedfs-data moi_etcd-data",
        "up -d --wait postgres",
        LOAD,
        "run --rm -T backup -C /seaweedfs -xf -",
    ]
    assert calls[-2:] == ["up -d --wait", "run --rm apps apply --all"]
    assert not [path for path in target.iterdir() if path.name.startswith(".khoi-phuc-")]
    assert "Đã khôi phục." in result.output


def test_restore_asks_before_replacing_and_stops_the_running_system(bundle, home, cli, docker):
    env = (home / ".env").read_text(encoding="utf-8")
    (home / ".env").write_text(env + "THEM=1\n", encoding="utf-8")

    refused = cli("restore", "--home", home, bundle)

    assert refused.exit_code == 1
    assert "sẽ bị thay bằng dữ liệu của gói" in refused.output
    assert docker.calls == []
    assert "THEM=1" in (home / ".env").read_text(encoding="utf-8")

    accepted = CliRunner().invoke(main, ["restore", "--home", str(home), str(bundle)], input="y\n")

    assert accepted.exit_code == 0, accepted.output
    assert restore_calls(docker)[0] == "down"
    assert (home / ".env").read_text(encoding="utf-8") == env


@pytest.mark.parametrize(
    "position", [5, 9, None, -9, -1], ids=["mtime", "os", "giua", "crc", "cuoi"]
)
def test_restore_refuses_a_bundle_changed_by_one_byte(bundle, cli, docker, tmp_path, position):
    data = bytearray(bundle.read_bytes())
    data[len(data) // 2 if position is None else position] ^= 0x01
    bundle.write_bytes(bytes(data))
    target = tmp_path / "moi"

    result = cli("restore", "--home", target, "--yes", bundle)

    assert result.exit_code == 1
    assert f"Không khôi phục được từ gói {bundle}" in result.output
    assert docker.calls == []
    assert not target.exists()


def test_restore_refuses_a_bundle_of_a_newer_version(home, cli, docker, monkeypatch, tmp_path):
    monkeypatch.setattr("saigonos.backup.__version__", "99.0.0")
    assert cli("backup", "--home", home).exit_code == 0
    [bundle] = (home / "backups").iterdir()

    result = cli("restore", "--home", tmp_path / "moi", "--yes", bundle)

    assert result.exit_code == 1
    assert f"Gói được tạo bởi SaigonOS 99.0.0, mới hơn bản đang cài {__version__}" in result.output


def test_restore_stops_when_postgres_reports_another_error(bundle, cli, docker, tmp_path):
    docker.reply("exec", error=EXPECTED + 'psql:<stdin>:20: ERROR:  syntax error at or near "x"\n')

    result = cli("restore", "--home", tmp_path / "moi", "--yes", bundle)

    assert result.exit_code == 1
    assert (
        "PostgreSQL báo lỗi khi nạp cơ sở dữ liệu: psql:<stdin>:20: ERROR:  syntax" in result.output
    )
    assert "up -d --wait" not in restore_calls(docker)
