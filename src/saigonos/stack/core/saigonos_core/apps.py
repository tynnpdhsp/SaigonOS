# SPDX-License-Identifier: Apache-2.0
import argparse
import asyncio
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from saigonos_core.app_database import (
    ApplyError,
    apply_database,
    installed_apps,
    known_app,
    remove_database,
)
from saigonos_core.app_gateway import Apisix, apply_gateway, check_route, remove_gateway
from saigonos_core.app_keycloak import Keycloak, apply_keycloak, check_names, remove_keycloak
from saigonos_core.app_processes import (
    Operaton,
    activate_processes,
    apply_processes,
    check_operaton,
    delete_processes,
    suspend_processes,
)
from saigonos_core.manifest import NAME_PATTERN, Manifest, Problem, check_app, schema_text

APPS = Path("/apps")
INSTALLED = "Đã cài đặt ứng dụng {name} {version}."
NOTHING_CHANGED = "Không có gì thay đổi."
NO_APPS = "Chưa có ứng dụng nào được cài đặt."
NOT_INSTALLED = "Ứng dụng {name} chưa được cài đặt."
REMOVED = "Đã gỡ ứng dụng {name}. Schema, dữ liệu, role và việc gán role vẫn được giữ lại."
PURGED = "Đã xóa hẳn ứng dụng {name}."
CONFIRM = "Gõ tên ứng dụng {name} để xóa hẳn ứng dụng cùng toàn bộ dữ liệu: "
NOT_CONFIRMED = "Tên vừa gõ không khớp. Ứng dụng chưa bị xóa."
NEEDS_TERMINAL = (
    "Lệnh xóa hẳn ứng dụng cần được xác nhận trong terminal. "
    "Hãy chạy lại trong terminal hoặc thêm tùy chọn --yes."
)
SETTINGS = (
    "KEYCLOAK_URL",
    "KEYCLOAK_ADMIN_USERNAME",
    "KEYCLOAK_ADMIN_PASSWORD",
    "SAIGONOS_URL",
    "APISIX_ADMIN_URL",
    "APISIX_ADMIN_KEY",
    "OPERATON_URL",
    "CORE_OPERATON_PASSWORD",
)

Say = Callable[[str], None]


class Services(NamedTuple):
    keycloak: Keycloak
    site_url: str
    apisix: Apisix
    operaton: Operaton


def parser() -> argparse.ArgumentParser:
    commands = argparse.ArgumentParser(
        prog="docker compose run --rm apps",
        description="Làm việc với các ứng dụng trong thư mục apps của thư mục làm việc.",
    )
    actions = commands.add_subparsers(dest="command", required=True, metavar="LỆNH")
    check = actions.add_parser(
        "check",
        help="Soát bản khai báo và các thư mục của một ứng dụng.",
        description="Soát bản khai báo và các thư mục của một ứng dụng rồi in mọi lỗi tìm thấy.",
    )
    check.add_argument("folder", metavar="THƯ_MỤC", help="Thư mục của ứng dụng trong thư mục apps.")
    apply = actions.add_parser(
        "apply",
        help="Cài đặt một ứng dụng vào hệ thống.",
        description=(
            "Soát rồi cài đặt ứng dụng trong thư mục apps/TÊN vào hệ thống đang chạy. "
            "Với --all, cài đặt lại mọi ứng dụng đã cài đặt."
        ),
    )
    target = apply.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "name", nargs="?", metavar="TÊN", help="Tên ứng dụng, cũng là tên thư mục trong apps."
    )
    target.add_argument("--all", action="store_true", help="Cài đặt lại mọi ứng dụng đã cài đặt.")
    remove = actions.add_parser(
        "remove",
        help="Gỡ một ứng dụng khỏi hệ thống.",
        description=(
            "Gỡ client, route, giao diện và quy trình của ứng dụng TÊN. "
            "Schema, dữ liệu, role và việc gán role được giữ lại."
        ),
    )
    remove.add_argument("name", metavar="TÊN", help="Tên ứng dụng.")
    remove.add_argument(
        "--purge",
        action="store_true",
        help="Xóa hẳn ứng dụng cùng schema, dữ liệu, role và quy trình.",
    )
    remove.add_argument("--yes", action="store_true", help="Không hỏi lại khi xóa hẳn ứng dụng.")
    actions.add_parser("schema", help="In JSON Schema của bản khai báo.")
    return commands


def report(problems: list[Problem], say: Say = print) -> int:
    say(f"Ứng dụng có {len(problems)} lỗi:")
    for problem in problems:
        say(f"- {problem}")
    return 1


def warn(warnings: tuple[Problem, ...], say: Say = print) -> None:
    if warnings:
        say(f"Ứng dụng có {len(warnings)} cảnh báo:")
        for warning in warnings:
            say(f"- {warning}")


def check(folder: str) -> int:
    path = APPS / folder
    if not path.is_dir():
        print(f"Không tìm thấy thư mục {folder}.")
        return 1
    manifest, problems, warnings = check_app(path)
    warn(warnings)
    if manifest is None:
        return report(problems)
    print(f"Ứng dụng {manifest.name} {manifest.version} không có lỗi.")
    return 0


def admin_settings() -> Services:
    missing = [name for name in SETTINGS if not os.environ.get(name)]
    if missing:
        raise ApplyError(f"Service apps thiếu biến môi trường {', '.join(missing)}.")
    url, username, password, site_url, gateway, key, engine, secret = (
        os.environ[name] for name in SETTINGS
    )
    return Services(
        Keycloak(url, username, password), site_url, Apisix(gateway, key), Operaton(engine, secret)
    )


def check_services(services: Services, manifest: Manifest) -> None:
    check_names(services.keycloak, manifest)
    check_route(services.apisix, manifest)
    if manifest.processes is not None:
        check_operaton(services.operaton)


def configure_services(
    services: Services, manifest: Manifest, folder: Path, removed: bool, say: Say
) -> bool:
    changed = apply_keycloak(services.keycloak, manifest, services.site_url, say)
    changed = apply_gateway(services.apisix, manifest, say) or changed
    if manifest.processes is not None:
        changed = apply_processes(services.operaton, manifest, folder, say) or changed
        if removed:
            changed = activate_processes(services.operaton, manifest.name, say) or changed
    return changed


def install(name: str, services: Services | None, say: Say) -> bool:
    folder = APPS / name
    if not folder.is_dir():
        say(f"Không tìm thấy thư mục {name} trong thư mục apps.")
        return False
    manifest, problems, warnings = check_app(folder)
    warn(warnings, say)
    if manifest is None:
        report(problems, say)
        return False
    if manifest.name != name:
        say(
            f"Thư mục {name} chứa bản khai báo của ứng dụng {manifest.name}. "
            "Tên thư mục phải trùng tên ứng dụng."
        )
        return False
    changed: list[bool] = []
    try:
        services = services or admin_settings()
        check_services(services, manifest)
        finished = asyncio.run(
            apply_database(
                manifest,
                folder,
                say,
                lambda removed: changed.append(
                    configure_services(services, manifest, folder, removed, say)
                ),
            )
        )
    except ApplyError as error:
        say(str(error))
        return False
    if finished or any(changed):
        say(INSTALLED.format(name=manifest.name, version=manifest.version))
    else:
        say(NOTHING_CHANGED)
    return True


def apply(name: str) -> int:
    if not re.fullmatch(NAME_PATTERN, name):
        print(f"Tên ứng dụng {name} không hợp lệ.")
        return 1
    return 0 if install(name, None, print) else 1


def apply_all() -> int:
    try:
        services = admin_settings()
        names = asyncio.run(installed_apps())
    except ApplyError as error:
        print(error)
        return 1
    if not names:
        print(NO_APPS)
        return 0
    failed = 0
    for name in names:
        if not install(name, services, lambda line, name=name: print(f"{name}: {line}")):
            failed += 1
    return 1 if failed else 0


def confirmed(name: str) -> bool:
    if not sys.stdin.isatty():
        print(NEEDS_TERMINAL)
        return False
    try:
        answer = input(CONFIRM.format(name=name))
    except EOFError:
        answer = ""
    if answer.strip() != name:
        print(NOT_CONFIRMED)
        return False
    return True


def remove(name: str, purge: bool, yes: bool) -> int:
    if not re.fullmatch(NAME_PATTERN, name):
        print(f"Tên ứng dụng {name} không hợp lệ.")
        return 1
    try:
        services = admin_settings()
        if not asyncio.run(known_app(name)):
            print(NOT_INSTALLED.format(name=name))
            return 1
        if purge and not yes and not confirmed(name):
            return 1
        check_operaton(services.operaton)
        changed = remove_gateway(services.apisix, name, print)
        changed = remove_keycloak(services.keycloak, name, purge, print) or changed
        processes = delete_processes if purge else suspend_processes
        changed = processes(services.operaton, name, print) or changed
        changed = asyncio.run(remove_database(name, purge, print)) or changed
    except ApplyError as error:
        print(error)
        return 1
    if not changed:
        print(NOTHING_CHANGED)
    else:
        print((PURGED if purge else REMOVED).format(name=name))
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.command == "schema":
        sys.stdout.write(schema_text())
        return 0
    if arguments.command == "apply":
        return apply_all() if arguments.all else apply(arguments.name)
    if arguments.command == "remove":
        return remove(arguments.name, arguments.purge, arguments.yes)
    return check(arguments.folder)


if __name__ == "__main__":
    sys.exit(main())
