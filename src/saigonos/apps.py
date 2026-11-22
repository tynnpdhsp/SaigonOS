# SPDX-License-Identifier: Apache-2.0
import fcntl
import json
import re
import shutil
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

MANIFEST = "saigonos-app.json"
FOLDER_KEYS = ("database", "processes", "ui")
NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
FOLDER = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_-][A-Za-z0-9_.-]*)*/?")
LOCK_FILE = ".apps.lock"


class AppFolderError(Exception):
    pass


def read_manifest(folder: Path) -> dict:
    data = json.loads((folder / MANIFEST).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise AppFolderError(f"File {MANIFEST} không còn là một đối tượng JSON.")
    return data


def app_name(folder: Path) -> str:
    name = read_manifest(folder).get("name")
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise AppFolderError(f"Tên ứng dụng trong file {MANIFEST} không còn hợp lệ.")
    return name


def readable_by_all(folder: Path) -> None:
    for path in [folder, *folder.rglob("*")]:
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() else 0o644)


def copy_app(source: Path, target: Path) -> None:
    target.mkdir()
    shutil.copyfile(source / MANIFEST, target / MANIFEST)
    manifest = read_manifest(target)
    for key in FOLDER_KEYS:
        value = manifest.get(key)
        if not isinstance(value, str) or not FOLDER.fullmatch(value):
            continue
        relative = value.rstrip("/")
        (target / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source / relative, target / relative, symlinks=True)
    readable_by_all(target)


@contextmanager
def locked(home: Path, waiting: Callable[[], None]) -> Iterator[None]:
    with (home / LOCK_FILE).open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            waiting()
            fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def put_in_place(source: Path, apps: Path, name: str) -> None:
    target, new, old = apps / name, apps / f".{name}.new", apps / f".{name}.old"
    apps.mkdir(mode=0o755, exist_ok=True)
    if old.exists():
        if target.exists():
            shutil.rmtree(target)
        old.rename(target)
    if new.exists():
        shutil.rmtree(new)
    try:
        copy_app(source, new)
    except BaseException:
        shutil.rmtree(new, ignore_errors=True)
        raise
    if target.exists():
        target.rename(old)
    new.rename(target)


def keep_new(apps: Path, name: str) -> None:
    old = apps / f".{name}.old"
    if old.exists():
        shutil.rmtree(old)


def restore_old(apps: Path, name: str) -> None:
    target, old = apps / name, apps / f".{name}.old"
    shutil.rmtree(target)
    if old.exists():
        old.rename(target)


def app_folders(apps: Path) -> list[Path]:
    if not apps.is_dir():
        return []
    return sorted(
        entry
        for entry in apps.iterdir()
        if entry.is_dir() and not entry.name.startswith(".") and (entry / MANIFEST).is_file()
    )


def remove_copy(apps: Path, name: str) -> None:
    for folder in (apps / name, apps / f".{name}.new", apps / f".{name}.old"):
        if folder.is_dir() and not folder.is_symlink():
            shutil.rmtree(folder)
