# SPDX-License-Identifier: Apache-2.0
import shutil
import subprocess
from pathlib import Path


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


def capture(home: Path, *args: str) -> str:
    result = subprocess.run(
        command(home, *args), cwd=home, check=False, capture_output=True, text=True
    )
    if result.returncode != 0:
        reason = result.stderr.strip() or f"mã thoát {result.returncode}"
        raise ComposeError(f"Lệnh docker compose {args[0]} không chạy được: {reason}")
    return result.stdout
