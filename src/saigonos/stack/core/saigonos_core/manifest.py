# SPDX-License-Identifier: Apache-2.0
import json
import os
from fnmatch import fnmatchcase
from itertools import combinations
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, NamedTuple

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
    field_validator,
)
from pydantic.json_schema import GenerateJsonSchema
from pydantic_core import InitErrorDetails, PydanticCustomError, core_schema

from saigonos_core.bpmn import Finding, check_processes

MANIFEST = "saigonos-app.json"
DIALECT = "https://json-schema.org/draft/2020-12/schema"
WORD = "[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
NAME_PATTERN = f"^{WORD}$"
ROLE_PATTERN = rf"^{WORD}\.{WORD}$"
NAME_LENGTH = 32
ROLE_LENGTH = 64
TITLE_LENGTH = 100
DESCRIPTION_LENGTH = 255
VERSION_LENGTH = 64
FOLDER_LENGTH = 255
RESERVED_PREFIX = "pg-"
RESERVED_NAMES = frozenset(
    {
        "account",
        "account-console",
        "admin-cli",
        "anon",
        "api",
        "apps",
        "auth",
        "authenticated",
        "authenticator",
        "broker",
        "centrifugo",
        "core",
        "core-service",
        "information-schema",
        "keycloak",
        "operaton",
        "postgres",
        "public",
        "realm-management",
        "realtime",
        "saigonos",
        "security-admin-console",
        "workflow",
    }
)
CONTROL = r"\x00-\x1f\x7f-\x9f"
TEXT_PATTERN = rf"^[^\s{CONTROL}](?:[^{CONTROL}]*[^\s{CONTROL}])?$"
NUMBER = "(?:0|[1-9][0-9]*)"
IDENTIFIER = f"(?:{NUMBER}|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
VERSION_PATTERN = (
    rf"^{NUMBER}\.{NUMBER}\.{NUMBER}"
    rf"(?:-{IDENTIFIER}(?:\.{IDENTIFIER})*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
SEGMENT = "[A-Za-z0-9_-][A-Za-z0-9_.-]*"
FOLDER_PATTERN = f"^{SEGMENT}(?:/{SEGMENT})*/?$"
REQUIRED_FILES = {
    "database": ("*.sql", "không có file .sql nào"),
    "processes": ("*.bpmn", "không có file .bpmn nào"),
    "ui": ("index.html", "không có file index.html"),
}
TEXT_RULE = (
    "Giá trị không được để trống, không có khoảng trắng ở đầu hoặc cuối "
    "và không chứa ký tự điều khiển."
)
FOLDER_RULE = (
    "Đường dẫn tính từ thư mục ứng dụng, ví dụ ui hoặc web/dist. "
    "Mỗi cấp gồm chữ cái không dấu, chữ số, dấu chấm, dấu gạch ngang, dấu gạch dưới "
    "và không bắt đầu bằng dấu chấm."
)
RULES = {
    ("name",): (
        "Tên ứng dụng gồm các cụm chữ thường không dấu và chữ số, nối với nhau bằng "
        "một dấu gạch ngang. Tên bắt đầu bằng chữ cái. Ví dụ: nghi-phep."
    ),
    ("title",): TEXT_RULE,
    ("version",): "Phiên bản phải theo Semantic Versioning, ví dụ 1.0.0 hoặc 1.0.0-beta.1.",
    ("roles", "name"): (
        "Tên role có dạng <tên ứng dụng>.<vai trò>. Vai trò viết theo quy tắc của "
        "tên ứng dụng. Ví dụ: nghi-phep.quan-ly."
    ),
    ("roles", "description"): TEXT_RULE,
    ("database",): FOLDER_RULE,
    ("processes",): FOLDER_RULE,
    ("ui",): FOLDER_RULE,
}
MESSAGES = {
    "missing": "Thiếu trường bắt buộc.",
    "extra_forbidden": "Không có trường này. Hãy kiểm tra lỗi chính tả.",
    "string_type": "Giá trị phải là một chuỗi.",
    "list_type": "Giá trị phải là một danh sách.",
    "model_type": "Giá trị phải là một đối tượng JSON.",
    "too_short": "Danh sách phải có ít nhất {min_length} phần tử.",
    "string_too_long": "Giá trị dài tối đa {max_length} ký tự.",
}
CUSTOM_ERRORS = {"reserved_prefix", "reserved_name", "role_prefix", "duplicate_role"}
JSON_MESSAGES = {
    "Expecting value": "thiếu giá trị",
    "Expecting ',' delimiter": "thiếu dấu phẩy",
    "Expecting ':' delimiter": "thiếu dấu hai chấm",
    "Expecting property name enclosed in double quotes": "tên trường phải nằm trong dấu nháy kép",
    "Unterminated string starting at": "chuỗi thiếu dấu nháy kép đóng",
    "Invalid control character at": "chuỗi chứa ký tự điều khiển",
    "Extra data": "có nội dung thừa sau đối tượng JSON",
    "Illegal trailing comma before end of object": "thừa dấu phẩy trước dấu }",
    "Illegal trailing comma before end of array": "thừa dấu phẩy trước dấu ]",
}

Folder = Annotated[str, Field(pattern=FOLDER_PATTERN, max_length=FOLDER_LENGTH)]
RoleName = Annotated[str, Field(pattern=ROLE_PATTERN, max_length=ROLE_LENGTH)]


class Role(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: RoleName = Field(
        description="Tên realm role, có dạng <tên ứng dụng>.<vai trò>. Ví dụ: nghi-phep.quan-ly."
    )
    description: str = Field(
        pattern=TEXT_PATTERN, max_length=DESCRIPTION_LENGTH, description="Mô tả của role."
    )


FOLDER = TypeAdapter(Folder)
ROLE_NAME = TypeAdapter(RoleName)


def valid(adapter: TypeAdapter[str], value: Any) -> str | None:
    try:
        return adapter.validate_python(value)
    except ValidationError:
        return None


def role_errors(items: list[Any], app: str | None) -> list[InitErrorDetails]:
    errors = []
    seen = set()
    for index, item in enumerate(items):
        name = valid(ROLE_NAME, item.get("name")) if isinstance(item, dict) else None
        if name is None:
            continue
        if app is not None and not name.startswith(f"{app}."):
            error = PydanticCustomError(
                "role_prefix", 'Tên role phải bắt đầu bằng "{prefix}".', {"prefix": f"{app}."}
            )
        elif name in seen:
            error = PydanticCustomError(
                "duplicate_role", 'Role "{role}" được khai báo hai lần.', {"role": name}
            )
        else:
            seen.add(name)
            continue
        errors.append(InitErrorDetails(type=error, loc=(index, "name"), input=name))
    return errors


class Manifest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        title="Bản khai ứng dụng SaigonOS",
        json_schema_extra={"description": f"Nội dung của file {MANIFEST}."},
    )

    schema_url: str | None = Field(
        None,
        alias="$schema",
        description=(
            "Địa chỉ JSON Schema của bản khai. "
            "Trình soạn thảo dùng địa chỉ này để kiểm tra và gợi ý khi viết bản khai."
        ),
    )
    name: str = Field(
        pattern=NAME_PATTERN,
        max_length=NAME_LENGTH,
        description=(
            "Tên ứng dụng, gồm các cụm chữ thường không dấu và chữ số nối với nhau bằng "
            "một dấu gạch ngang, bắt đầu bằng chữ cái. Ví dụ: nghi-phep."
        ),
        json_schema_extra={
            "not": {
                "anyOf": [
                    {"enum": sorted(RESERVED_NAMES)},
                    {"pattern": f"^{RESERVED_PREFIX}"},
                ]
            }
        },
    )
    title: str = Field(
        pattern=TEXT_PATTERN, max_length=TITLE_LENGTH, description="Tên hiển thị của ứng dụng."
    )
    version: str = Field(
        pattern=VERSION_PATTERN,
        max_length=VERSION_LENGTH,
        description="Phiên bản của ứng dụng theo Semantic Versioning, ví dụ 1.0.0.",
    )
    roles: list[Role] = Field(min_length=1, description="Các realm role của ứng dụng.")
    database: Folder | None = Field(
        None, description="Thư mục chứa file SQL, tính từ thư mục ứng dụng."
    )
    processes: Folder | None = Field(
        None, description="Thư mục chứa file BPMN, tính từ thư mục ứng dụng."
    )
    ui: Folder | None = Field(
        None,
        description=(
            "Thư mục chứa giao diện, tính từ thư mục ứng dụng. Thư mục phải có file index.html."
        ),
    )

    @field_validator("name")
    @classmethod
    def name_is_free(cls, name: str) -> str:
        if name.startswith(RESERVED_PREFIX):
            raise PydanticCustomError(
                "reserved_prefix",
                'Tên ứng dụng không được bắt đầu bằng "{prefix}".',
                {"prefix": RESERVED_PREFIX},
            )
        if name in RESERVED_NAMES:
            raise PydanticCustomError(
                "reserved_name",
                'Tên "{name}" đã được lõi dùng. Hãy chọn tên khác.',
                {"name": name},
            )
        return name

    @field_validator("roles", mode="wrap")
    @classmethod
    def roles_belong_to_app(
        cls, value: Any, handler: ValidatorFunctionWrapHandler, info: ValidationInfo
    ) -> list[Role]:
        errors: list[InitErrorDetails] = []
        try:
            roles = handler(value)
        except ValidationError as error:
            errors = [
                InitErrorDetails(
                    type=detail["type"],
                    loc=detail["loc"],
                    input=detail["input"],
                    ctx=detail.get("ctx", {}),
                )
                for detail in error.errors()
            ]
        if isinstance(value, list):
            errors += role_errors(value, info.data.get("name"))
        if errors:
            errors.sort(key=lambda error: error["loc"][:1])
            raise ValidationError.from_exception_data("roles", errors)
        return roles


class Problem(NamedTuple):
    location: str
    message: str

    def __str__(self) -> str:
        return f"{self.location}: {self.message}" if self.location else self.message


class Checked(NamedTuple):
    manifest: Manifest | None
    problems: list[Problem]
    warnings: tuple[Problem, ...] = ()


class DuplicateKeyError(ValueError):
    pass


class WithoutTitles(GenerateJsonSchema):
    def field_title_should_be_set(self, schema: core_schema.CoreSchemaType) -> bool:
        return False


def schema() -> dict[str, Any]:
    return {"$schema": DIALECT, **Manifest.model_json_schema(schema_generator=WithoutTitles)}


def schema_text() -> str:
    return json.dumps(schema(), ensure_ascii=False, indent=2) + "\n"


def location(loc: tuple[str | int, ...]) -> str:
    text = ""
    for part in loc:
        if isinstance(part, int):
            text += f"[{part}]"
        else:
            text += f".{part}" if text else part
    return text


def message(error: Any) -> str:
    kind = error["type"]
    if kind in CUSTOM_ERRORS:
        return error["msg"]
    if kind == "model_type" and not error["loc"]:
        return "Nội dung của bản khai phải là một đối tượng JSON."
    if kind == "string_pattern_mismatch":
        return RULES[tuple(part for part in error["loc"] if isinstance(part, str))]
    return MESSAGES.get(kind, "Giá trị không hợp lệ.").format(**error.get("ctx", {}))


def without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(key)
        result[key] = value
    return result


def json_problem(error: json.JSONDecodeError) -> Problem:
    text = f"File {MANIFEST} không phải JSON hợp lệ ở dòng {error.lineno}, cột {error.colno}"
    detail = JSON_MESSAGES.get(error.msg)
    return Problem("", f"{text}: {detail}." if detail else f"{text}.")


def read_manifest(folder: Path) -> tuple[Any, Problem | None]:
    path = folder / MANIFEST
    if path.is_symlink():
        return None, Problem("", f"File {MANIFEST} là symlink. Hãy dùng file thật.")
    if not path.exists():
        return None, Problem("", f"Không tìm thấy file {MANIFEST} trong thư mục ứng dụng.")
    if not path.is_file():
        return None, Problem("", f"{MANIFEST} không phải file thường.")
    try:
        content = path.read_bytes()
    except OSError:
        return None, Problem("", f"Không đọc được file {MANIFEST}.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, Problem("", f"File {MANIFEST} phải được lưu bằng bảng mã UTF-8.")
    try:
        return json.loads(text, object_pairs_hook=without_duplicates), None
    except DuplicateKeyError as error:
        return None, Problem(
            "", f'Trường "{error}" được khai báo hai lần trong cùng một đối tượng.'
        )
    except json.JSONDecodeError as error:
        return None, json_problem(error)


def scan(path: Path | str) -> list[os.DirEntry[str]]:
    with os.scandir(path) as found:
        return sorted(found, key=lambda entry: entry.name)


def content_problems(relative: PurePosixPath, entries: list[os.DirEntry[str]]) -> list[str]:
    problems = []
    for entry in entries:
        path = relative / entry.name
        if entry.is_symlink():
            problems.append(f'"{path}" là symlink. Thư mục đã khai không được chứa symlink.')
        elif entry.is_dir(follow_symlinks=False):
            if os.access(entry.path, os.R_OK | os.X_OK):
                problems += content_problems(path, scan(entry.path))
            else:
                problems.append(f'Không mở được thư mục "{path}".')
        elif not entry.is_file(follow_symlinks=False):
            problems.append(f'"{path}" không phải file thường hay thư mục.')
        elif not os.access(entry.path, os.R_OK):
            problems.append(f'Không đọc được file "{path}".')
    return problems


def folder_problems(root: Path, field: str, value: str) -> list[str]:
    relative = PurePosixPath(value.rstrip("/"))
    current = PurePosixPath()
    for part in relative.parts:
        current /= part
        path = root / current
        if path.is_symlink():
            return [f'"{current}" là symlink. Thư mục đã khai không được là symlink.']
        if not path.exists():
            return [f'Không tìm thấy thư mục "{relative}".']
        if not path.is_dir():
            return [f'"{current}" không phải thư mục.']
    if not os.access(root / relative, os.R_OK | os.X_OK):
        return [f'Không mở được thư mục "{relative}".']
    entries = scan(root / relative)
    problems = content_problems(relative, entries)
    pattern, missing = REQUIRED_FILES[field]
    files = [entry.name for entry in entries if not entry.is_dir(follow_symlinks=False)]
    if not any(fnmatchcase(name, pattern) for name in files):
        problems.append(f'Thư mục "{relative}" {missing}.')
    return problems


def overlap(first: PurePosixPath, second: PurePosixPath) -> bool:
    return first == second or first in second.parents or second in first.parents


def process_problem(folder: PurePosixPath, finding: Finding) -> Problem:
    where = f'"{folder / finding.file}"'
    if finding.line is not None:
        where += f", dòng {finding.line}"
    return Problem("processes", f"{where}: {finding.message}")


def check_app(folder: Path) -> Checked:
    data, problem = read_manifest(folder)
    if problem is not None:
        return Checked(None, [problem])
    manifest = None
    problems = []
    try:
        manifest = Manifest.model_validate(data)
    except ValidationError as error:
        problems += [Problem(location(detail["loc"]), message(detail)) for detail in error.errors()]
    if not isinstance(data, dict):
        return Checked(None, problems)
    folders = {}
    for field in REQUIRED_FILES:
        value = valid(FOLDER, data.get(field))
        if value is not None:
            folders[field] = PurePosixPath(value.rstrip("/"))
            problems += [Problem(field, text) for text in folder_problems(folder, field, value)]
    for (first, first_path), (second, second_path) in combinations(folders.items(), 2):
        if overlap(first_path, second_path):
            text = f"Thư mục của {first} và {second} trùng nhau hoặc nằm trong nhau."
            problems.append(Problem(second, text))
    warnings: list[Problem] = []
    processes = folders.get("processes")
    if processes is not None and all(problem.location != "processes" for problem in problems):
        app = None if manifest is None else manifest.name
        roles = None if manifest is None else [role.name for role in manifest.roles]
        report = check_processes(folder / processes, app, roles)
        problems += [process_problem(processes, finding) for finding in report.problems]
        warnings += [process_problem(processes, finding) for finding in report.warnings]
    return Checked(None if problems else manifest, problems, tuple(warnings))
