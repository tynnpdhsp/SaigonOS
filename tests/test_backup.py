# SPDX-License-Identifier: Apache-2.0
import hashlib
import io
import json
import stat
import tarfile

import pytest

from saigonos import __version__

GZIP_HEADER = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff"
DUMP = "pg_dumpall --username=postgres --clean --if-exists"
COPY = "run --rm -T backup -C /seaweedfs -cf - ."


@pytest.fixture
def home(tmp_path, cli):
    path = tmp_path / "home"
    cli("init", "--home", path)
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


def test_backup_needs_a_working_folder(tmp_path, cli, docker):
    result = cli("backup", "--home", tmp_path / "khong-co")

    assert result.exit_code == 1
    assert "Chưa có thư mục làm việc" in result.output
    assert not (tmp_path / "khong-co").exists()
