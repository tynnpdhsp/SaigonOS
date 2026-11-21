# SPDX-License-Identifier: Apache-2.0
import argparse
import sys
from pathlib import Path

from saigonos_core.manifest import check_app, schema_text

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
    actions.add_parser("schema", help="In JSON Schema của bản khai.")
    return commands


def check(folder: str) -> int:
    path = APPS / folder
    if not path.is_dir():
        print(f"Không tìm thấy thư mục {folder}.")
        return 1
    manifest, problems = check_app(path)
    if manifest is None:
        print(f"Ứng dụng có {len(problems)} lỗi:")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print(f"Ứng dụng {manifest.name} {manifest.version} không có lỗi.")
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.command == "schema":
        sys.stdout.write(schema_text())
        return 0
    return check(arguments.folder)


if __name__ == "__main__":
    sys.exit(main())
