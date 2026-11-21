# SPDX-License-Identifier: Apache-2.0
import argparse
import asyncio
import re
import sys
from pathlib import Path

from saigonos_core.app_database import ApplyError, apply_database
from saigonos_core.manifest import NAME_PATTERN, Problem, check_app, schema_text

APPS = Path("/apps")


def parser() -> argparse.ArgumentParser:
    commands = argparse.ArgumentParser(
        prog="docker compose run --rm apps",
        description="Làm việc với các ứng dụng trong thư mục apps của thư mục làm việc.",
    )
    actions = commands.add_subparsers(dest="command", required=True, metavar="LỆNH")
    check = actions.add_parser(
        "check",
        help="Soát bản khai và các thư mục của một ứng dụng.",
        description="Soát bản khai và các thư mục của một ứng dụng rồi in mọi lỗi tìm thấy.",
    )
    check.add_argument("folder", metavar="THƯ_MỤC", help="Thư mục của ứng dụng trong thư mục apps.")
    apply = actions.add_parser(
        "apply",
        help="Cắm một ứng dụng vào hệ thống.",
        description="Soát rồi cắm ứng dụng trong thư mục apps/TÊN vào hệ thống đang chạy.",
    )
    apply.add_argument("name", metavar="TÊN", help="Tên ứng dụng, cũng là tên thư mục trong apps.")
    actions.add_parser("schema", help="In JSON Schema của bản khai.")
    return commands


def report(problems: list[Problem]) -> int:
    print(f"Ứng dụng có {len(problems)} lỗi:")
    for problem in problems:
        print(f"- {problem}")
    return 1


def check(folder: str) -> int:
    path = APPS / folder
    if not path.is_dir():
        print(f"Không tìm thấy thư mục {folder}.")
        return 1
    manifest, problems = check_app(path)
    if manifest is None:
        return report(problems)
    print(f"Ứng dụng {manifest.name} {manifest.version} không có lỗi.")
    return 0


def apply(name: str) -> int:
    if not re.fullmatch(NAME_PATTERN, name):
        print(f"Tên ứng dụng {name} không hợp lệ.")
        return 1
    folder = APPS / name
    if not folder.is_dir():
        print(f"Không tìm thấy thư mục {name} trong thư mục apps.")
        return 1
    manifest, problems = check_app(folder)
    if manifest is None:
        return report(problems)
    if manifest.name != name:
        print(
            f"Thư mục {name} chứa bản khai của ứng dụng {manifest.name}. "
            "Tên thư mục phải trùng tên ứng dụng."
        )
        return 1
    try:
        asyncio.run(apply_database(manifest, folder, print))
    except ApplyError as error:
        print(error)
        return 1
    print(f"Đã cắm ứng dụng {manifest.name} {manifest.version}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.command == "schema":
        sys.stdout.write(schema_text())
        return 0
    if arguments.command == "apply":
        return apply(arguments.name)
    return check(arguments.folder)


if __name__ == "__main__":
    sys.exit(main())
