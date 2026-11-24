# SPDX-License-Identifier: Apache-2.0
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import time
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from tempfile import mkdtemp
from typing import BinaryIO, NamedTuple

from saigonos import __version__, compose
from saigonos.home import APPS_FOLDER, init_home

BACKUP_FOLDER = "backups"
MANIFEST = "manifest.json"
SUMS = "SHA256SUMS"
ENV = "env"
DATABASE = "postgres.sql"
FILES = "seaweedfs.tar"
APPS = "apps.tar"
CADDY = "caddy.tar"
CADDY_FOLDER = Path("data") / "caddy"
SEAWEEDFS = "seaweedfs"
COMPRESS_LEVEL = 6
CHUNK_SIZE = 1024 * 1024
HEALTH_WAIT = 90
HEALTH_POLL = 2
GZIP_HEADER = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff"
REQUIRED = (ENV, DATABASE, FILES, APPS)
KNOWN = {MANIFEST, SUMS, *REQUIRED, CADDY}
RESET_VOLUMES = ("postgres-data", "seaweedfs-data", "etcd-data")
EXPECTED_ERRORS = {"current user cannot be dropped", 'role "postgres" already exists'}


class BundleError(Exception):
    pass


class Manifest(NamedTuple):
    version: str
    created: str
    parts: list[str]


def bundle_name(moment: datetime) -> str:
    return f"saigonos-{moment:%Y%m%d-%H%M%S}.tar.gz"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def member(name: str, size: int, moment: datetime) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size, info.mode, info.mtime = size, 0o600, int(moment.timestamp())
    return info


def write_bundle(target: Path, parts: dict[str, Path], moment: datetime) -> None:
    manifest = json.dumps(
        {"saigonos": __version__, "created": moment.isoformat(), "parts": [*parts]},
        ensure_ascii=False,
        indent=2,
    ).encode()
    sums = f"{hashlib.sha256(manifest).hexdigest()}  {MANIFEST}\n"
    sums += "".join(f"{sha256(path)}  {name}\n" for name, path in parts.items())
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with (
            os.fdopen(descriptor, "wb") as raw,
            gzip.GzipFile(
                filename="", mode="wb", fileobj=raw, compresslevel=COMPRESS_LEVEL, mtime=0
            ) as packed,
            tarfile.open(fileobj=packed, mode="w|", format=tarfile.PAX_FORMAT) as tar,
        ):
            for name, data in ((MANIFEST, manifest), (SUMS, sums.encode())):
                tar.addfile(member(name, len(data), moment), io.BytesIO(data))
            for name, path in parts.items():
                with path.open("rb") as file:
                    tar.addfile(member(name, path.stat().st_size, moment), file)
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def pack_folder(folder: Path, target: Path) -> None:
    with tarfile.open(target, "w", format=tarfile.PAX_FORMAT) as tar:
        if folder.is_dir():
            tar.add(folder, arcname=".")


def wait_healthy(home: Path, service: str) -> None:
    deadline = time.monotonic() + HEALTH_WAIT
    while compose.containers(home).get(service, {}).get("Health") != "healthy":
        if time.monotonic() >= deadline:
            raise compose.ComposeError(
                f"Service {service} chưa đạt healthcheck sau {HEALTH_WAIT} giây kể từ lúc chạy lại."
            )
        time.sleep(HEALTH_POLL)


def collect(home: Path, work: Path) -> dict[str, Path]:
    parts = {ENV: work / ENV, DATABASE: work / DATABASE, FILES: work / FILES, APPS: work / APPS}
    shutil.copyfile(home / ".env", parts[ENV])
    pack_folder(home / APPS_FOLDER, parts[APPS])
    compose.to_file(
        home,
        parts[DATABASE],
        "exec",
        "-T",
        "postgres",
        "pg_dumpall",
        "--username=postgres",
        "--clean",
        "--if-exists",
    )
    compose.capture(home, "pause", SEAWEEDFS)
    try:
        compose.to_file(
            home, parts[FILES], "run", "--rm", "-T", "backup", "-C", "/seaweedfs", "-cf", "-", "."
        )
    finally:
        compose.capture(home, "unpause", SEAWEEDFS)
    wait_healthy(home, SEAWEEDFS)
    caddy = home / CADDY_FOLDER
    if caddy.is_dir():
        parts[CADDY] = work / CADDY
        compose.to_file(
            home,
            parts[CADDY],
            "run",
            "--rm",
            "-T",
            "--volume",
            f"{caddy}:/caddy:ro",
            "backup",
            "-C",
            "/caddy",
            "-cf",
            "-",
            ".",
        )
    return parts


def copy_out(source: BinaryIO, target: Path) -> str:
    digest = hashlib.sha256()
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        while chunk := source.read(CHUNK_SIZE):
            digest.update(chunk)
            output.write(chunk)
    return digest.hexdigest()


def read_members(bundle: Path, work: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    with bundle.open("rb") as raw:
        if raw.read(len(GZIP_HEADER)) != GZIP_HEADER:
            raise BundleError(
                "phần đầu của gói không đúng, gói đã bị sửa hoặc không phải gói sao lưu"
            )
        raw.seek(0)
        try:
            with gzip.GzipFile(fileobj=raw, mode="rb") as packed:
                with tarfile.open(fileobj=packed, mode="r|") as tar:
                    for item in tar:
                        source = tar.extractfile(item) if item.isfile() else None
                        if source is None or item.name not in KNOWN or item.name in found:
                            raise BundleError(f"gói có phần không hợp lệ {item.name}")
                        found[item.name] = copy_out(source, work / item.name)
                while packed.read(CHUNK_SIZE):
                    pass
        except (OSError, EOFError, tarfile.TarError, zlib.error) as error:
            raise BundleError("gói bị hỏng hoặc đã bị sửa") from error
    return found


def unpack_bundle(bundle: Path, work: Path) -> Manifest:
    found = read_members(bundle, work)
    if SUMS not in found or MANIFEST not in found:
        raise BundleError("gói thiếu manifest.json hoặc SHA256SUMS")
    try:
        lines = (work / SUMS).read_text(encoding="utf-8").splitlines()
        sums = {name: digest for digest, name in (line.split("  ", 1) for line in lines)}
        data = json.loads((work / MANIFEST).read_text(encoding="utf-8"))
        manifest = Manifest(str(data["saigonos"]), str(data["created"]), list(data["parts"]))
    except (ValueError, KeyError, TypeError) as error:
        raise BundleError("không đọc được manifest.json hoặc SHA256SUMS") from error
    for name, digest in found.items():
        if name != SUMS and sums.get(name) != digest:
            raise BundleError(f"mã băm của {name} không khớp với SHA256SUMS")
    missing = [name for name in (*REQUIRED, *sums) if name not in found]
    if missing or sorted(manifest.parts) != sorted(set(found) - {MANIFEST, SUMS}):
        raise BundleError(f"gói thiếu phần {', '.join(missing) or 'được ghi trong manifest.json'}")
    return manifest


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version.split("-")[0])[:3])


@contextmanager
def unpacked(home: Path, bundle: Path) -> Iterator[tuple[Path, Manifest]]:
    created = not home.exists()
    home.mkdir(parents=True, exist_ok=True)
    work = Path(mkdtemp(prefix=".khoi-phuc-", dir=home))
    try:
        yield work, unpack_bundle(bundle, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        if created and not any(home.iterdir()):
            home.rmdir()


def put_files(home: Path, work: Path) -> None:
    env = home / ".env"
    env.unlink(missing_ok=True)
    with os.fdopen(os.open(env, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as output:
        output.write((work / ENV).read_bytes())
    apps = home / APPS_FOLDER
    shutil.rmtree(apps, ignore_errors=True)
    apps.mkdir()
    with tarfile.open(work / APPS) as tar:
        tar.extractall(apps, filter="data")


def load_data(home: Path, work: Path) -> None:
    compose.remove_volumes(home, *RESET_VOLUMES)
    compose.capture(home, "up", "-d", "--wait", "postgres")
    errors = compose.from_file(
        home,
        work / DATABASE,
        "exec",
        "-T",
        "postgres",
        "psql",
        "--username=postgres",
        "--dbname=postgres",
        "--no-psqlrc",
        "--quiet",
    )
    unexpected = [
        line
        for line in errors.splitlines()
        if "ERROR:" in line and line.split("ERROR:", 1)[1].strip() not in EXPECTED_ERRORS
    ]
    if unexpected:
        raise BundleError(f"PostgreSQL báo lỗi khi nạp cơ sở dữ liệu: {unexpected[0]}")
    compose.from_file(
        home, work / FILES, "run", "--rm", "-T", "backup", "-C", "/seaweedfs", "-xf", "-"
    )
    if (work / CADDY).is_file():
        caddy = home / CADDY_FOLDER
        caddy.mkdir(parents=True, exist_ok=True)
        compose.from_file(
            home,
            work / CADDY,
            "run",
            "--rm",
            "-T",
            "--volume",
            f"{caddy}:/caddy",
            "backup",
            "-C",
            "/caddy",
            "-xf",
            "-",
        )


def restore_data(home: Path, work: Path) -> None:
    if (home / "compose.yaml").is_file() and (home / ".env").is_file():
        compose.capture(home, "down")
    put_files(home, work)
    init_home(home)
    load_data(home, work)


def create_backup(home: Path, folder: Path, moment: datetime) -> Path:
    compose.command(home)
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = folder / bundle_name(moment)
    work = Path(mkdtemp(prefix=".tam-", dir=folder))
    try:
        write_bundle(target, collect(home, work), moment)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return target
