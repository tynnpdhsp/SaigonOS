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
from typing import NamedTuple

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parent.parent
PROJECT_FILE = ROOT / "pyproject.toml"
LOCK_FILE = ROOT / "requirements.txt"
DEV_LOCK_FILE = ROOT / "requirements-dev.txt"
CORE_LOCK_FILE = ROOT / "src" / "saigonos" / "stack" / "core" / "requirements.txt"
STACK_FILE = ROOT / "src" / "saigonos" / "stack" / "compose.yaml"
DOCKERFILE = ROOT / "src" / "saigonos" / "stack" / "core" / "Dockerfile"
TABLE_FILE = ROOT / "DEPENDENCIES.md"

ALLOWED_LICENSES = {
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "MIT",
    "MIT-0",
    "PSF-2.0",
}
DEV_ONLY_LICENSES = {"CC-BY-SA-4.0", "CC0-1.0", "GPL-3.0-or-later"}
IMAGE_LICENSES = {"Apache-2.0", "GPL-2.0-only", "MIT", "PostgreSQL", "Python-2.0.1"}
VERIFIED_LICENSES = {
    "h11": "MIT",
    "reuse": "Apache-2.0 AND CC0-1.0 AND CC-BY-SA-4.0 AND GPL-3.0-or-later",
}
DESCRIPTIONS = {
    "asyncpg": "Kết nối service `core` với PostgreSQL",
    "click": "Xây dựng giao diện dòng lệnh cho lệnh `saigonos`",
    "fastapi": "Xây dựng REST API của service `core`",
    "httpx2": "Gọi service `core` trong kiểm thử",
    "packaging": "Đọc và so sánh số phiên bản",
    "pip-licenses": "Đọc giấy phép của các thư viện đã cài đặt",
    "pyjwt": "Kiểm tra chữ ký và thời hạn của access token",
    "pytest": "Chạy kiểm thử",
    "pytest-cov": "Đo coverage khi chạy kiểm thử",
    "reuse": "Kiểm tra thông tin giấy phép của mọi file",
    "ruff": "Kiểm tra lỗi và định dạng mã Python",
    "uv": "Tạo lock file từ `pyproject.toml`",
    "uvicorn": "Chạy service `core` trong container",
}
INDIRECT = "Phụ thuộc gián tiếp"


class Image(NamedTuple):
    license: str
    description: str
    source: str


IMAGES = {
    "apache/apisix:3.19.0-ubuntu": Image(
        "Apache-2.0",
        "Làm API Gateway cho mọi lời gọi từ bên ngoài",
        "https://github.com/apache/apisix/tree/3.19.0",
    ),
    "caddy:2.11.9-alpine": Image(
        "Apache-2.0",
        "Làm reverse proxy HTTPS và tự động lấy chứng chỉ khi được bật",
        "https://github.com/caddyserver/caddy/tree/v2.11.9",
    ),
    "centrifugo/centrifugo:v6.10.3": Image(
        "Apache-2.0",
        "Gửi cập nhật tức thời tới ứng dụng qua WebSocket",
        "https://github.com/centrifugal/centrifugo/tree/v6.10.3",
    ),
    "chrislusf/seaweedfs:4.54": Image(
        "Apache-2.0",
        "Lưu file của các ứng dụng theo chuẩn S3",
        "https://github.com/seaweedfs/seaweedfs/tree/4.54",
    ),
    "clamav/clamav-debian:1.5.4": Image(
        "GPL-2.0-only",
        "Quét mã độc trong file được tải lên",
        "https://github.com/Cisco-Talos/clamav/tree/clamav-1.5.4",
    ),
    "openpolicyagent/opa:1.22.4": Image(
        "Apache-2.0",
        "Kiểm tra luật truy cập chung trước khi API Gateway chuyển lời gọi đi",
        "https://github.com/open-policy-agent/opa/tree/v1.22.4",
    ),
    "operaton/operaton:2.2.1": Image(
        "Apache-2.0",
        "Chạy các quy trình BPMN, có Cockpit, Tasklist và Admin",
        "https://github.com/operaton/operaton/tree/v2.2.1",
    ),
    "postgres:18.6-alpine": Image(
        "PostgreSQL",
        "Lưu dữ liệu của Keycloak và của các ứng dụng",
        "https://github.com/postgres/postgres/tree/REL_18_6",
    ),
    "python:3.14.10-slim-trixie": Image(
        "Python-2.0.1",
        "Làm base image của service `core`",
        "https://github.com/python/cpython/tree/v3.14.10",
    ),
    "postgrest/postgrest:v16.5": Image(
        "MIT",
        "Tạo REST API từ cơ sở dữ liệu PostgreSQL",
        "https://github.com/PostgREST/postgrest/tree/v16.5",
    ),
    "quay.io/coreos/etcd:v3.6.16": Image(
        "Apache-2.0",
        "Lưu cấu hình của APISIX",
        "https://github.com/etcd-io/etcd/tree/v3.6.16",
    ),
    "quay.io/keycloak/keycloak:26.8.2": Image(
        "Apache-2.0",
        "Quản lý định danh và đăng nhập một lần",
        "https://github.com/keycloak/keycloak/tree/26.8.2",
    ),
}

PLUGINS = {
    "coraza-proxy-wasm:0.6.0": Image(
        "Apache-2.0",
        "Chặn tấn công web ở API Gateway. File .wasm gồm Coraza 3.3.3 và bộ luật OWASP CRS "
        "4.14.0, cả hai theo giấy phép Apache-2.0",
        "https://github.com/corazawaf/coraza-proxy-wasm/tree/0.6.0",
    ),
}
SPDX_TAG = "SPDX-License-Identifier"
HEADER = f"""\
<!-- {SPDX_TAG}: Apache-2.0 -->
# Thư viện và gói phụ thuộc

File này liệt kê các thư viện, phần mềm và công cụ mà SaigonOS sử dụng. Mỗi dòng ghi phiên bản, \
giấy phép, mô tả và nguồn. File do lệnh `make dependencies` tạo ra từ các lock file, các thư viện \
đã cài đặt và file `compose.yaml`. Không sửa trực tiếp file này.
"""
RUNTIME_SECTION = """
## Thư viện đi kèm sản phẩm

Các thư viện này được cài đặt cùng SaigonOS. Danh sách được lấy từ `requirements.txt`, kể cả \
phụ thuộc gián tiếp.

| Thư viện | Phiên bản | Giấy phép | Mô tả | Nguồn |
|---|---|---|---|---|
"""
CORE_SECTION = """
## Thư viện của service `core`

Các thư viện này được cài đặt vào image của service `core` khi Docker Compose build image trên \
máy cài đặt. Danh sách được lấy từ `src/saigonos/stack/core/requirements.txt`, kể cả phụ thuộc \
gián tiếp. Lock file này ghi mã băm của từng file. Khi cài đặt, pip từ chối file có mã băm khác.

| Thư viện | Phiên bản | Giấy phép | Mô tả | Nguồn |
|---|---|---|---|---|
"""
IMAGE_SECTION = """
## Phần mềm chạy trong container

Các phần mềm này chạy trong container riêng. Danh sách image được lấy từ file \
`src/saigonos/stack/compose.yaml` và dòng `FROM` của file `src/saigonos/stack/core/Dockerfile`. \
Image không ghi địa chỉ máy chủ được tải từ Docker Hub.

Cột giấy phép ghi giấy phép của phần mềm chính trong image. Giấy phép được kiểm tra tại mã \
nguồn của đúng phiên bản đó. Địa chỉ mã nguồn nằm ở cột nguồn. Hệ điều hành nền và các thư viện \
khác trong image giữ giấy phép riêng.

| Image | Phiên bản | Giấy phép | Mô tả | Nguồn |
|---|---|---|---|---|
"""
PLUGIN_SECTION = """
## Plugin của API Gateway

Plugin này không nằm trong image nào. Service `waf` tải file zip của plugin từ trang Releases \
của dự án, kiểm tra mã băm SHA-256 của file zip và của file `.wasm`, rồi đưa file `.wasm` cho \
APISIX. Phiên bản và hai mã băm được ghi trong service `waf` của file \
`src/saigonos/stack/compose.yaml`.

| Plugin | Phiên bản | Giấy phép | Mô tả | Nguồn |
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

- File release `saigonos-X.Y.Z.tar.gz` chỉ chứa mã nguồn của SaigonOS.
- Các thư viện đi kèm sản phẩm được pip tải từ PyPI khi cài đặt.
- Các image ở trên được Docker tải về khi khởi động lần đầu. Trừ image `python`, SaigonOS dùng \
nguyên image gốc. Việc cấu hình chỉ thực hiện qua biến môi trường và file cấu hình.
- Image `python` là base image của service `core`. Docker Compose build image của service này \
trên máy cài đặt và dùng pip để cài các thư viện của service `core` từ PyPI. File `Dockerfile` ghi \
digest của base image. Lock file ghi mã băm của từng thư viện. Do đó, mọi file được tải về khi \
build đều được đối chiếu mã băm. SaigonOS không phân phối image đã build.
- Plugin của API Gateway được service `waf` tải từ trang Releases của dự án khi khởi động lần \
đầu, rồi được đối chiếu mã băm. SaigonOS dùng nguyên file của dự án và không phân phối lại file \
này.
- SaigonOS không sao chép và không sửa mã nguồn của dự án khác.

## Quy tắc về giấy phép

- Mỗi thư viện và phần mềm giữ nguyên giấy phép gốc.
- Thư viện đi kèm sản phẩm và thư viện của service `core` chỉ được dùng các giấy phép \
{vietnamese_list(ALLOWED_LICENSES)}.
- Phần mềm chạy trong container và plugin của API Gateway chỉ được dùng các giấy phép \
{vietnamese_list(IMAGE_LICENSES)}. Các giấy phép này đều được OSI công nhận.
- Phần mềm theo giấy phép GPL-2.0-only chỉ được chạy trong container riêng. SaigonOS chỉ trao đổi \
với phần mềm này qua kết nối mạng và không phân phối lại image. Do đó, giấy phép này không ảnh \
hưởng đến giấy phép Apache-2.0 của SaigonOS.
- Công cụ phát triển được dùng thêm {vietnamese_list(DEV_ONLY_LICENSES)}. Các công cụ này không \
được phân phối cùng SaigonOS nên không ảnh hưởng đến giấy phép Apache-2.0 của dự án.
- Lệnh `make lint` báo lỗi khi gặp giấy phép khác, gặp image hoặc plugin chưa được khai báo hoặc \
gặp base image chưa ghi digest.
"""


def read_lock(path: Path) -> dict[str, str]:
    pins = re.findall(
        r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)", path.read_text(encoding="utf-8"), re.MULTILINE
    )
    return {normalize(name): version for name, version in pins}


def read_declared(project_file: Path) -> tuple[set[str], set[str], set[str]]:
    with project_file.open("rb") as file:
        project = tomllib.load(file)
    groups = project.get("dependency-groups", {})
    runtime, core, dev = (
        {normalize(Requirement(spec).name) for spec in specs}
        for specs in (
            project["project"].get("dependencies", []),
            groups.get("core", []),
            groups.get("dev", []),
        )
    )
    return runtime, core, dev


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
    if name not in direct:
        return INDIRECT
    if name not in DESCRIPTIONS:
        raise DependencyError(
            f"{name} chưa có mô tả. Hãy thêm vào DESCRIPTIONS trong scripts/dependencies.py."
        )
    return DESCRIPTIONS[name]


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


def read_images(stack_file: Path) -> list[str]:
    text = stack_file.read_text(encoding="utf-8")
    return sorted(set(re.findall(r"^[ \t]+image:[ \t]*(\S+)[ \t]*$", text, re.MULTILINE)))


def read_base_images(dockerfile: Path) -> list[str]:
    text = dockerfile.read_text(encoding="utf-8")
    images = []
    for reference in re.findall(r"^FROM[ \t]+(\S+)", text, re.MULTILINE):
        image, _, digest = reference.partition("@")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise DependencyError(f"Base image {reference} trong Dockerfile chưa ghi digest.")
        images.append(image)
    return images


def build_image_rows(references: list[str]) -> str:
    rows = []
    for reference in references:
        name, separator, tag = reference.rpartition(":")
        if not separator or "/" in tag or tag == "latest":
            raise DependencyError(f"Image {reference} chưa cố định phiên bản.")
        if reference not in IMAGES:
            raise DependencyError(
                f"Image {reference} chưa được khai báo. Hãy kiểm tra giấy phép của đúng phiên bản "
                "này rồi thêm vào IMAGES trong scripts/dependencies.py."
            )
        image = IMAGES[reference]
        version = re.search(r"\d+(?:\.\d+)*", tag)
        if not version or not re.search(version[0].replace(".", "[._]"), image.source):
            raise DependencyError(
                f"Nguồn của image {reference} không dẫn tới mã nguồn của phiên bản này."
            )
        license_expression = resolve_license(reference, image.license, IMAGE_LICENSES)
        rows.append(
            f"| {name} | {tag} | {license_expression} | {image.description} | {image.source} |\n"
        )
    unused = sorted(IMAGES.keys() - set(references))
    if unused:
        raise DependencyError(
            f"{', '.join(unused)} không còn trong compose.yaml và Dockerfile. "
            "Hãy xóa khỏi IMAGES trong scripts/dependencies.py."
        )
    return "".join(rows)


def read_plugins(stack_file: Path) -> list[str]:
    text = stack_file.read_text(encoding="utf-8")
    versions = re.findall(r'^[ \t]+CORAZA_VERSION:[ \t]*"([^"]+)"[ \t]*$', text, re.MULTILINE)
    return [f"coraza-proxy-wasm:{version}" for version in versions]


def build_plugin_rows(references: list[str]) -> str:
    rows = []
    for reference in references:
        name, _, version = reference.rpartition(":")
        if reference not in PLUGINS:
            raise DependencyError(
                f"Plugin {name} {version} chưa được khai báo. Hãy kiểm tra giấy phép của đúng "
                "phiên bản này rồi thêm vào PLUGINS trong scripts/dependencies.py."
            )
        plugin = PLUGINS[reference]
        if version not in plugin.source:
            raise DependencyError(
                f"Nguồn của plugin {name} không dẫn tới mã nguồn của phiên bản {version}."
            )
        license_expression = resolve_license(reference, plugin.license, IMAGE_LICENSES)
        rows.append(
            f"| {name} | {version} | {license_expression} | {plugin.description} "
            f"| {plugin.source} |\n"
        )
    unused = sorted(PLUGINS.keys() - set(references))
    if unused:
        raise DependencyError(
            f"{', '.join(unused)} không còn trong compose.yaml. "
            "Hãy xóa khỏi PLUGINS trong scripts/dependencies.py."
        )
    return "".join(rows)


def build_table(
    lock_file: Path = LOCK_FILE,
    dev_lock_file: Path = DEV_LOCK_FILE,
    project_file: Path = PROJECT_FILE,
    stack_file: Path = STACK_FILE,
    core_lock_file: Path = CORE_LOCK_FILE,
    dockerfile: Path = DOCKERFILE,
) -> str:
    runtime, core, dev = read_declared(project_file)
    locked = read_lock(lock_file)
    core_locked = read_lock(core_lock_file)
    dev_locked = read_lock(dev_lock_file)
    missing = sorted(dev - dev_locked.keys())
    if missing:
        raise DependencyError(
            f"{', '.join(missing)} chưa có trong requirements-dev.txt. Hãy chạy make lock."
        )
    dev_pins = {name: dev_locked[name] for name in dev}
    installed = read_installed(sorted(locked.keys() | core_locked.keys() | dev_pins.keys()))
    return (
        HEADER
        + RUNTIME_SECTION
        + build_rows(locked, runtime, installed, ALLOWED_LICENSES)
        + CORE_SECTION
        + build_rows(core_locked, core, installed, ALLOWED_LICENSES)
        + IMAGE_SECTION
        + build_image_rows(sorted({*read_images(stack_file), *read_base_images(dockerfile)}))
        + PLUGIN_SECTION
        + build_plugin_rows(read_plugins(stack_file))
        + DEV_SECTION
        + build_rows(dev_pins, dev, installed, ALLOWED_LICENSES | DEV_ONLY_LICENSES)
        + footer()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Tạo DEPENDENCIES.md từ các lock file và file compose.yaml."
    )
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
    print(
        "DEPENDENCIES.md không khớp với lock file hoặc file compose.yaml. "
        "Hãy chạy make dependencies.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
