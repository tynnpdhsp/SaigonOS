# SPDX-License-Identifier: Apache-2.0
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


class ComposeError(Exception):
    pass


def command(home: Path, *args: str) -> list[str]:
    if not (home / "compose.yaml").is_file() or not (home / ".env").is_file():
        raise ComposeError(
            f"Chưa có thư mục làm việc tại {home}. Hãy chạy lệnh saigonos init trước."
        )
    docker = shutil.which("docker")
    if docker is None:
        raise ComposeError("Không tìm thấy lệnh docker. Hãy cài đặt Docker kèm Docker Compose.")
    return [docker, "compose", *args]


def run(home: Path, *args: str) -> int:
    return subprocess.run(command(home, *args), cwd=home, check=False).returncode


def to_file(home: Path, target: Path, *args: str) -> None:
    with target.open("wb") as output:
        result = subprocess.run(
            command(home, *args), cwd=home, check=False, stdout=output, stderr=subprocess.PIPE
        )
    if result.returncode != 0:
        reason = result.stderr.decode(errors="replace").strip() or f"mã thoát {result.returncode}"
        raise ComposeError(f"Lệnh docker compose {args[0]} không chạy được: {reason}")


def from_file(home: Path, source: Path, *args: str) -> str:
    with source.open("rb") as data:
        result = subprocess.run(
            command(home, *args), cwd=home, check=False, stdin=data, capture_output=True
        )
    errors = result.stderr.decode(errors="replace")
    if result.returncode != 0:
        reason = errors.strip() or f"mã thoát {result.returncode}"
        raise ComposeError(f"Lệnh docker compose {args[0]} không chạy được: {reason}")
    return errors


def remove_volumes(home: Path, *names: str) -> None:
    declared = json.loads(capture(home, "config", "--format", "json")).get("volumes") or {}
    volumes = [declared[name]["name"] for name in names if name in declared]
    if not volumes:
        return
    docker = command(home)[0]
    result = subprocess.run(
        [docker, "volume", "rm", "--force", *volumes], check=False, capture_output=True, text=True
    )
    if result.returncode != 0:
        reason = result.stderr.strip() or f"mã thoát {result.returncode}"
        raise ComposeError(f"Không xóa được volume {', '.join(volumes)}: {reason}")


def containers(home: Path) -> dict[str, dict[str, Any]]:
    output = capture(home, "ps", "--all", "--format", "json").strip()
    if output.startswith("["):
        rows = json.loads(output)
    else:
        rows = [json.loads(line) for line in output.splitlines()]
    return {row["Service"]: row for row in rows}


def capture(home: Path, *args: str) -> str:
    result = subprocess.run(
        command(home, *args), cwd=home, check=False, capture_output=True, text=True
    )
    if result.returncode != 0:
        reason = result.stderr.strip() or f"mã thoát {result.returncode}"
        raise ComposeError(f"Lệnh docker compose {args[0]} không chạy được: {reason}")
    return result.stdout
