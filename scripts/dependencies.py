# SPDX-License-Identifier: Apache-2.0
import argparse
import difflib
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Iterable
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parent.parent
PROJECT_FILE = ROOT / "pyproject.toml"
LOCK_FILE = ROOT / "requirements.txt"
DEV_LOCK_FILE = ROOT / "requirements-dev.txt"
TABLE_FILE = ROOT / "DEPENDENCIES.md"

ALLOWED_LICENSES = {"Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MIT", "PSF-2.0"}
DEV_ONLY_LICENSES = {"CC-BY-SA-4.0", "CC0-1.0", "GPL-3.0-or-later"}
VERIFIED_LICENSES = {"reuse": "Apache-2.0 AND CC0-1.0 AND CC-BY-SA-4.0 AND GPL-3.0-or-later"}
DESCRIPTIONS = {
    "click": "Xây dựng giao diện dòng lệnh cho lệnh `saigonos`",
    "packaging": "Đọc và so sánh số phiên bản",
    "pip-licenses": "Đọc giấy phép của các thư viện đã cài đặt",
    "pytest": "Chạy kiểm thử",
    "pytest-cov": "Đo coverage khi chạy kiểm thử",
    "reuse": "Kiểm tra thông tin giấy phép của mọi file",
    "ruff": "Kiểm tra lỗi và định dạng mã Python",
    "uv": "Tạo lock file từ `pyproject.toml`",
}
INDIRECT = "Phụ thuộc gián tiếp"

SPDX_TAG = "SPDX-License-Identifier"
HEADER = f"""\
<!-- {SPDX_TAG}: Apache-2.0 -->
# Thư viện và gói phụ thuộc

File này liệt kê các thư viện và công cụ mà SaigonOS sử dụng. Mỗi dòng ghi phiên bản, giấy phép, \
mô tả và nguồn tải. File do lệnh `make dependencies` tạo ra từ lock file và các thư viện đã cài \
đặt. Không sửa trực tiếp file này.
"""
RUNTIME_SECTION = """
## Thư viện đi kèm sản phẩm

Các thư viện này được cài đặt cùng SaigonOS. Danh sách được lấy từ `requirements.txt`, kể cả \
phụ thuộc gián tiếp.

| Thư viện | Phiên bản | Giấy phép | Mô tả | Nguồn |
|---|---|---|---|---|
"""
DEV_SECTION = """
## Công cụ phát triển

Các công cụ này chỉ dùng khi phát triển và khi chạy CI. Chúng không được cài đặt cùng SaigonOS. \
Bảng chỉ liệt kê công cụ khai báo trực tiếp trong `pyproject.toml`. Phụ thuộc gián tiếp của \
chúng nằm trong `requirements-dev.txt`.

| Công cụ | Phiên bản | Giấy phép | Mô tả | Nguồn |
|---|---|---|---|---|
"""


class DependencyError(Exception):
    pass


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def vietnamese_list(items: Iterable[str]) -> str:
    ordered = sorted(items)
    if len(ordered) < 2:
        return "".join(ordered)
    return ", ".join(ordered[:-1]) + " và " + ordered[-1]


def footer() -> str:
    return f"""
## Gói đính kèm

- Bản phát hành `saigonos-X.Y.Z.tar.gz` chỉ chứa mã nguồn của SaigonOS.
- Các thư viện ở trên được pip tải từ PyPI khi cài đặt.
- SaigonOS không sao chép và không sửa mã nguồn của dự án khác.

## Quy tắc về giấy phép

- Mỗi thư viện giữ nguyên giấy phép gốc.
- Thư viện đi kèm sản phẩm chỉ được dùng các giấy phép {vietnamese_list(ALLOWED_LICENSES)}.
- Công cụ phát triển được dùng thêm {vietnamese_list(DEV_ONLY_LICENSES)}. Các công cụ này không \
được phân phối cùng SaigonOS nên không ảnh hưởng đến giấy phép Apache-2.0 của dự án.
- Lệnh `make lint` báo lỗi khi gặp giấy phép khác.
"""


def read_lock(path: Path) -> dict[str, str]:
    pins = re.findall(
        r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)", path.read_text(encoding="utf-8"), re.MULTILINE
    )
    return {normalize(name): version for name, version in pins}


def read_declared(project_file: Path) -> tuple[set[str], set[str]]:
    with project_file.open("rb") as file:
        project = tomllib.load(file)
    runtime = project["project"].get("dependencies", [])
    dev = project.get("dependency-groups", {}).get("dev", [])
    return (
        {normalize(Requirement(spec).name) for spec in runtime},
        {normalize(Requirement(spec).name) for spec in dev},
    )


def read_installed(names: list[str]) -> dict[str, dict[str, str]]:
    if not names:
        return {}
    command = [sys.executable, "-m", "piplicenses", "--format=json", "--with-system"]
    output = subprocess.run(
        [*command, "--packages", *names], check=True, capture_output=True, text=True
    ).stdout
    return {normalize(package["Name"]): package for package in json.loads(output)}


def resolve_license(name: str, reported: str, allowed: set[str]) -> str:
    license_expression = VERIFIED_LICENSES.get(name, reported)
    identifiers = set(re.findall(r"[^\s()]+", license_expression)) - {"AND", "OR", "WITH"}
    if not identifiers or not identifiers <= allowed:
        raise DependencyError(f"Giấy phép ngoài danh sách cho phép: {name} khai báo '{reported}'.")
    return license_expression


def describe(name: str, direct: set[str]) -> str:
    if name in DESCRIPTIONS:
        return DESCRIPTIONS[name]
    if name in direct:
        raise DependencyError(
            f"{name} chưa có mô tả. Hãy thêm vào DESCRIPTIONS trong scripts/dependencies.py."
        )
    return INDIRECT


def build_rows(
    pins: dict[str, str],
    direct: set[str],
    installed: dict[str, dict[str, str]],
    allowed: set[str],
) -> str:
    rows = []
    for name, version in sorted(pins.items()):
        found = installed.get(name, {}).get("Version", "chưa cài đặt")
        if found != version:
            raise DependencyError(
                f"{name}: lock file ghi {version} nhưng môi trường có {found}. "
                "Hãy chạy pip install -r requirements-dev.txt."
            )
        license_expression = resolve_license(name, installed[name]["License"], allowed)
        description = describe(name, direct)
        source = f"https://pypi.org/project/{name}/{version}/"
        rows.append(f"| {name} | {version} | {license_expression} | {description} | {source} |\n")
    return "".join(rows)


def build_table(
    lock_file: Path = LOCK_FILE,
    dev_lock_file: Path = DEV_LOCK_FILE,
    project_file: Path = PROJECT_FILE,
) -> str:
    runtime, dev = read_declared(project_file)
    locked = read_lock(lock_file)
    dev_locked = read_lock(dev_lock_file)
    missing = sorted(dev - dev_locked.keys())
    if missing:
        raise DependencyError(
            f"{', '.join(missing)} chưa có trong requirements-dev.txt. Hãy chạy make lock."
        )
    dev_pins = {name: dev_locked[name] for name in dev}
    installed = read_installed(sorted(locked.keys() | dev_pins.keys()))
    return (
        HEADER
        + RUNTIME_SECTION
        + build_rows(locked, runtime, installed, ALLOWED_LICENSES)
        + DEV_SECTION
        + build_rows(dev_pins, dev, installed, ALLOWED_LICENSES | DEV_ONLY_LICENSES)
        + footer()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tạo DEPENDENCIES.md từ lock file.")
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
