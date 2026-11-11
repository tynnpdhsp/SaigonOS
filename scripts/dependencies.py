# SPDX-License-Identifier: Apache-2.0
import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK_FILE = ROOT / "requirements.txt"
TABLE_FILE = ROOT / "DEPENDENCIES.md"

ALLOWED_LICENSES = {"Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MIT", "PSF-2.0"}
VERIFIED_LICENSES: dict[str, str] = {}

SPDX_TAG = "SPDX-License-Identifier"
HEADER = f"""\
<!-- {SPDX_TAG}: Apache-2.0 -->
# Thư viện và gói phụ thuộc

File này do lệnh `make dependencies` tạo ra. Không sửa trực tiếp file này.

SaigonOS không sao chép mã nguồn của dự án khác vào repo. Bảng dưới đây liệt kê mọi thư viện \
được cài đặt cùng SaigonOS. Danh sách được lấy từ `requirements.txt`. Các công cụ phát triển \
trong `requirements-dev.txt` chỉ dùng khi phát triển và khi chạy CI. Các công cụ này không được \
cài đặt cùng SaigonOS.

## Thư viện Python

| Tên | Phiên bản | Giấy phép | Nguồn |
|---|---|---|---|
"""


class DependencyError(Exception):
    pass


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def read_lock(path: Path) -> dict[str, str]:
    pins = re.findall(
        r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)", path.read_text(encoding="utf-8"), re.MULTILINE
    )
    return {normalize(name): version for name, version in pins}


def read_installed(names: list[str]) -> dict[str, dict[str, str]]:
    if not names:
        return {}
    command = [sys.executable, "-m", "piplicenses", "--format=json", "--with-system"]
    output = subprocess.run(
        [*command, "--packages", *names], check=True, capture_output=True, text=True
    ).stdout
    return {normalize(package["Name"]): package for package in json.loads(output)}


def resolve_license(name: str, reported: str) -> str:
    license_expression = VERIFIED_LICENSES.get(name, reported)
    identifiers = set(re.findall(r"[^\s()]+", license_expression)) - {"AND", "OR", "WITH"}
    if not identifiers or not identifiers <= ALLOWED_LICENSES:
        raise DependencyError(f"Giấy phép ngoài danh sách cho phép: {name} khai báo '{reported}'.")
    return license_expression


def build_table(lock_file: Path = LOCK_FILE) -> str:
    locked = read_lock(lock_file)
    installed = read_installed(sorted(locked))
    rows = []
    for name, version in sorted(locked.items()):
        found = installed.get(name, {}).get("Version", "chưa cài đặt")
        if found != version:
            raise DependencyError(
                f"{name}: lock file ghi {version} nhưng môi trường có {found}. "
                "Hãy chạy pip install -r requirements-dev.txt."
            )
        license_expression = resolve_license(name, installed[name]["License"])
        source = f"https://pypi.org/project/{name}/{version}/"
        rows.append(f"| {name} | {version} | {license_expression} | {source} |\n")
    return HEADER + "".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tạo bảng giấy phép phần mềm bên thứ ba.")
    parser.add_argument("--check", action="store_true", help="chỉ so sánh, không ghi file")
    arguments = parser.parse_args(argv)
    try:
        table = build_table()
    except DependencyError as error:
        print(error, file=sys.stderr)
        return 1
    if not arguments.check:
        TABLE_FILE.write_text(table, encoding="utf-8")
        return 0
    current = TABLE_FILE.read_text(encoding="utf-8") if TABLE_FILE.exists() else ""
    if current == table:
        return 0
    sys.stderr.writelines(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            table.splitlines(keepends=True),
            "DEPENDENCIES.md",
            "bảng tạo lại",
        )
    )
    print("DEPENDENCIES.md không khớp với lock file. Hãy chạy make dependencies.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
