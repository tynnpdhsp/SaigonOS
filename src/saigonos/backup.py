# SPDX-License-Identifier: Apache-2.0
import gzip
import hashlib
import io
import json
import os
import shutil
import tarfile
from datetime import datetime
from pathlib import Path
from tempfile import mkdtemp

from saigonos import __version__, compose
from saigonos.home import APPS_FOLDER

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
