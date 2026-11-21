# SPDX-License-Identifier: Apache-2.0
import json
import os
import re
from importlib.resources import files

import pytest

from saigonos_core.manifest import (
    MANIFEST,
    NAME_LENGTH,
    RESERVED_NAMES,
    RESERVED_PREFIX,
    ROLE_LENGTH,
    check_app,
)

STACK = files("saigonos") / "stack"
CONFIG = STACK / "config"
VALID = {
    "name": "nghi-phep",
    "title": "Nghỉ phép",
    "version": "0.1.0",
    "roles": [
        {"name": "nghi-phep.nhan-vien", "description": "Gửi đơn và xem đơn của mình"},
        {"name": "nghi-phep.quan-ly", "description": "Duyệt đơn của nhân viên"},
    ],
    "database": "database",
    "processes": "processes",
    "ui": "ui",
}
FILES = {
    "database/0001_don.sql": "CREATE TABLE nghi_phep.don (id bigint);\n",
    "processes/duyet.bpmn": "<definitions/>\n",
    "ui/index.html": "<!doctype html>\n",
    "ui/assets/app.js": "console.log(1);\n",
}
NAME_RULE = (
    "name: Tên ứng dụng gồm các cụm chữ thường không dấu và chữ số, nối với nhau bằng một "
    "dấu gạch ngang. Tên bắt đầu bằng chữ cái. Ví dụ: nghi-phep."
)
ROLE_RULE = (
    "Tên role có dạng <tên ứng dụng>.<vai trò>. Vai trò viết theo quy tắc của tên ứng dụng. "
    "Ví dụ: nghi-phep.quan-ly."
)
TEXT_RULE = (
    "Giá trị không được để trống, không có khoảng trắng ở đầu hoặc cuối "
    "và không chứa ký tự điều khiển."
)
VERSION_RULE = "version: Phiên bản phải theo Semantic Versioning, ví dụ 1.0.0 hoặc 1.0.0-beta.1."
FOLDER_RULE = (
    "Đường dẫn tính từ thư mục ứng dụng, ví dụ ui hoặc web/dist. Mỗi cấp gồm chữ cái không dấu, "
    "chữ số, dấu chấm, dấu gạch ngang, dấu gạch dưới và không bắt đầu bằng dấu chấm."
)
SYMLINK = "là symlink. Thư mục đã khai không được chứa symlink."
as_root = pytest.mark.skipif(os.geteuid() == 0, reason="root đọc được mọi file")


def write(folder, data):
    text = data if isinstance(data, str) else json.dumps(data)
    (folder / MANIFEST).write_text(text, encoding="utf-8")


@pytest.fixture
def app(tmp_path):
    folder = tmp_path / "nghi-phep"
    for name, text in FILES.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")
    write(folder, json.dumps(VALID, ensure_ascii=False, indent=2))
    return folder


def problems(folder, data=None):
    if data is not None:
        write(folder, data)
    return [str(problem) for problem in check_app(folder).problems]


def role(name="nghi-phep.quan-ly", description="Duyệt đơn"):
    return {"name": name, "description": description}


def test_valid_app_has_no_problem(app):
    checked = check_app(app)

    assert checked.problems == []
    assert checked.manifest.model_dump(exclude={"schema_url"}) == VALID


@pytest.mark.parametrize(
    "change",
    [
        {"database": None, "processes": None, "ui": None},
        {"$schema": "https://example.com/saigonos-app.schema.json"},
        {"ui": "ui/"},
        {"version": "1.0.0-beta.1+build.7"},
        {"title": "Đơn nghỉ phép (bản thử)"},
    ],
    ids=["bo-thu-muc", "co-schema", "dau-gach-cheo-cuoi", "phien-ban-day-du", "tieu-de-co-dau"],
)
def test_optional_and_flexible_values_are_accepted(app, change):
    assert problems(app, VALID | change) == []


def test_folders_may_be_left_out(app):
    data = {key: VALID[key] for key in ("name", "title", "version", "roles")}

    assert problems(app, data) == []


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"name": None}, "name: Giá trị phải là một chuỗi."),
        ({"title": 5}, "title: Giá trị phải là một chuỗi."),
        ({"proceses": "processes"}, "proceses: Không có trường này. Hãy kiểm tra lỗi chính tả."),
        ({"name": "Nghi-Phep"}, NAME_RULE),
        ({"name": "nghi_phep"}, NAME_RULE),
        ({"name": "2-nghi"}, NAME_RULE),
        ({"name": "nghi-"}, NAME_RULE),
        ({"name": "nghi--phep"}, NAME_RULE),
        ({"name": "nghỉ-phép"}, NAME_RULE),
        ({"name": ""}, NAME_RULE),
        ({"name": "a" * (NAME_LENGTH + 1)}, f"name: Giá trị dài tối đa {NAME_LENGTH} ký tự."),
        ({"name": "pg-nghi"}, f'name: Tên ứng dụng không được bắt đầu bằng "{RESERVED_PREFIX}".'),
        ({"name": json.loads('"\\ud800"')}, "name: Giá trị không hợp lệ."),
        ({"title": " Nghỉ phép"}, f"title: {TEXT_RULE}"),
        ({"title": "Nghỉ phép "}, f"title: {TEXT_RULE}"),
        ({"title": "   "}, f"title: {TEXT_RULE}"),
        ({"title": ""}, f"title: {TEXT_RULE}"),
        ({"title": "Nghỉ\nphép"}, f"title: {TEXT_RULE}"),
        ({"title": "Nghỉ\tphép"}, f"title: {TEXT_RULE}"),
        ({"title": "Nghỉ\x85phép"}, f"title: {TEXT_RULE}"),
        ({"title": "a" * 101}, "title: Giá trị dài tối đa 100 ký tự."),
        ({"version": "1.0"}, VERSION_RULE),
        ({"version": "v1.0.0"}, VERSION_RULE),
        ({"version": "01.0.0"}, VERSION_RULE),
        ({"version": "1.0.0-01"}, VERSION_RULE),
        ({"version": "1.0.0-"}, VERSION_RULE),
        ({"roles": "nghi-phep.quan-ly"}, "roles: Giá trị phải là một danh sách."),
        ({"roles": []}, "roles: Danh sách phải có ít nhất 1 phần tử."),
        ({"roles": ["nghi-phep.quan-ly"]}, "roles[0]: Giá trị phải là một đối tượng JSON."),
        (
            {"roles": [{"name": "nghi-phep.quan-ly"}]},
            "roles[0].description: Thiếu trường bắt buộc.",
        ),
        (
            {"roles": [role() | {"title": "Quản lý"}]},
            "roles[0].title: Không có trường này. Hãy kiểm tra lỗi chính tả.",
        ),
        ({"roles": [role("quan-ly")]}, f"roles[0].name: {ROLE_RULE}"),
        ({"roles": [role("nghi-phep.Quan-ly")]}, f"roles[0].name: {ROLE_RULE}"),
        ({"roles": [role("nghi-phep.quan.ly")]}, f"roles[0].name: {ROLE_RULE}"),
        (
            {"roles": [role("nghi-phep." + "a" * (ROLE_LENGTH - 9))]},
            f"roles[0].name: Giá trị dài tối đa {ROLE_LENGTH} ký tự.",
        ),
        ({"roles": [role(description=" ")]}, f"roles[0].description: {TEXT_RULE}"),
        (
            {"roles": [role(description="a" * 256)]},
            "roles[0].description: Giá trị dài tối đa 255 ký tự.",
        ),
        ({"ui": 1}, "ui: Giá trị phải là một chuỗi."),
        ({"ui": "/srv/ui"}, f"ui: {FOLDER_RULE}"),
        ({"ui": ".."}, f"ui: {FOLDER_RULE}"),
        ({"ui": "../ui"}, f"ui: {FOLDER_RULE}"),
        ({"ui": "web/../ui"}, f"ui: {FOLDER_RULE}"),
        ({"ui": "."}, f"ui: {FOLDER_RULE}"),
        ({"ui": ".web"}, f"ui: {FOLDER_RULE}"),
        ({"ui": "web\\dist"}, f"ui: {FOLDER_RULE}"),
        ({"ui": "web//dist"}, f"ui: {FOLDER_RULE}"),
        ({"ui": ""}, f"ui: {FOLDER_RULE}"),
        ({"ui": "a" * 256}, "ui: Giá trị dài tối đa 255 ký tự."),
    ],
    ids=[
        "ten-khong-phai-chuoi",
        "tieu-de-khong-phai-chuoi",
        "truong-sai-chinh-ta",
        "ten-chu-hoa",
        "ten-gach-duoi",
        "ten-bat-dau-bang-so",
        "ten-gach-ngang-cuoi",
        "ten-hai-gach-ngang",
        "ten-co-dau",
        "ten-rong",
        "ten-qua-dai",
        "ten-bat-dau-bang-pg",
        "ten-loi-unicode",
        "tieu-de-khoang-trang-dau",
        "tieu-de-khoang-trang-cuoi",
        "tieu-de-chi-co-khoang-trang",
        "tieu-de-rong",
        "tieu-de-xuong-dong",
        "tieu-de-tab",
        "tieu-de-ky-tu-dieu-khien-c1",
        "tieu-de-qua-dai",
        "phien-ban-thieu-so",
        "phien-ban-co-chu-v",
        "phien-ban-so-0-dau",
        "phien-ban-dinh-danh-so-0-dau",
        "phien-ban-gach-ngang-cuoi",
        "roles-la-chuoi",
        "roles-rong",
        "role-la-chuoi",
        "role-thieu-mo-ta",
        "role-thua-truong",
        "role-thieu-ten-ung-dung",
        "role-chu-hoa",
        "role-hai-dau-cham",
        "role-qua-dai",
        "mo-ta-chi-co-khoang-trang",
        "mo-ta-qua-dai",
        "thu-muc-khong-phai-chuoi",
        "thu-muc-tuyet-doi",
        "thu-muc-cha",
        "thu-muc-ra-ngoai",
        "thu-muc-vong-ra-ngoai",
        "thu-muc-chinh-no",
        "thu-muc-an",
        "thu-muc-gach-cheo-nguoc",
        "thu-muc-hai-gach-cheo",
        "thu-muc-rong",
        "thu-muc-qua-dai",
    ],
)
def test_each_invalid_value_has_its_own_message(app, change, expected):
    assert problems(app, VALID | change) == [expected]


@pytest.mark.parametrize("name", sorted(RESERVED_NAMES))
def test_name_used_by_core_is_refused(app, name):
    data = VALID | {"name": name, "roles": [role(f"{name}.quan-ly")]}

    assert problems(app, data) == [f'name: Tên "{name}" đã được lõi dùng. Hãy chọn tên khác.']


def test_missing_fields_are_listed_in_order(app):
    assert problems(app, {"roles": [role()]}) == [
        "name: Thiếu trường bắt buộc.",
        "title: Thiếu trường bắt buộc.",
        "version: Thiếu trường bắt buộc.",
    ]


def test_role_must_start_with_name_of_app(app):
    data = VALID | {"roles": [role("nghi-phep.nhan-vien"), role("don-tu.quan-ly")]}

    assert problems(app, data) == ['roles[1].name: Tên role phải bắt đầu bằng "nghi-phep.".']


def test_role_declared_twice_is_refused(app):
    data = VALID | {"roles": [role(), role("nghi-phep.nhan-vien"), role()]}

    assert problems(app, data) == ['roles[2].name: Role "nghi-phep.quan-ly" được khai báo hai lần.']


def test_every_problem_is_listed_in_one_run(app):
    data = VALID | {
        "version": "1.0",
        "roles": [
            role("don-tu.quan-ly"),
            role("nghi-phep.nhan-vien") | {"extra": 1},
            role("nghi-phep.nhan-vien"),
            role("Nghi-phep.X", ""),
        ],
        "database": "../database",
        "proceses": "processes",
    }

    assert problems(app, data) == [
        VERSION_RULE,
        'roles[0].name: Tên role phải bắt đầu bằng "nghi-phep.".',
        "roles[1].extra: Không có trường này. Hãy kiểm tra lỗi chính tả.",
        'roles[2].name: Role "nghi-phep.nhan-vien" được khai báo hai lần.',
        f"roles[3].name: {ROLE_RULE}",
        f"roles[3].description: {TEXT_RULE}",
        f"database: {FOLDER_RULE}",
        "proceses: Không có trường này. Hãy kiểm tra lỗi chính tả.",
    ]


def test_role_check_waits_for_valid_name_of_app(app):
    data = VALID | {"name": "Nghi-Phep", "roles": [role("don-tu.quan-ly")]}

    assert problems(app, data) == [NAME_RULE]


def test_manifest_must_be_json_object(app):
    assert problems(app, [VALID]) == ["Nội dung của bản khai phải là một đối tượng JSON."]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", "ở dòng 1, cột 1: thiếu giá trị."),
        ('{\n  "name": "nghi-phep"\n  "title": "Nghỉ phép"\n}', "ở dòng 3, cột 3: thiếu dấu phẩy."),
        ('{"name" "nghi-phep"}', "ở dòng 1, cột 9: thiếu dấu hai chấm."),
        ("{'name': 'nghi-phep'}", "ở dòng 1, cột 2: tên trường phải nằm trong dấu nháy kép."),
        ('{"name": "nghi-phep', "ở dòng 1, cột 10: chuỗi thiếu dấu nháy kép đóng."),
        ('{"name": "nghi\nphep"}', "ở dòng 1, cột 15: chuỗi chứa ký tự điều khiển."),
        ("{} {}", "ở dòng 1, cột 4: có nội dung thừa sau đối tượng JSON."),
        ('{"name": "\\q"}', "ở dòng 1, cột 11."),
    ],
    ids=[
        "file-rong",
        "thieu-dau-phay",
        "thieu-dau-hai-cham",
        "nhay-don",
        "chuoi-chua-dong",
        "xuong-dong-trong-chuoi",
        "noi-dung-thua",
        "loi-khac",
    ],
)
def test_invalid_json_shows_line_and_column(app, text, expected):
    assert problems(app, text) == [f"File {MANIFEST} không phải JSON hợp lệ {expected}"]


def test_trailing_comma_is_reported(app):
    [problem] = problems(app, '{"name": "nghi-phep",}')

    assert problem.startswith(f"File {MANIFEST} không phải JSON hợp lệ ở dòng 1, cột ")


def test_key_written_twice_is_refused(app):
    text = json.dumps(VALID)[:-1] + ', "roles": []}'

    assert problems(app, text) == ['Trường "roles" được khai báo hai lần trong cùng một đối tượng.']


def test_manifest_with_byte_order_mark_is_read(app):
    (app / MANIFEST).write_bytes(b"\xef\xbb\xbf" + json.dumps(VALID).encode())

    assert problems(app) == []


def test_manifest_must_be_utf_8(app):
    (app / MANIFEST).write_bytes(json.dumps(VALID, ensure_ascii=False).encode("utf-16"))

    assert problems(app) == [f"File {MANIFEST} phải được lưu bằng bảng mã UTF-8."]


def test_missing_manifest_is_reported(app):
    (app / MANIFEST).unlink()

    assert problems(app) == [f"Không tìm thấy file {MANIFEST} trong thư mục ứng dụng."]


def test_manifest_cannot_be_symlink(app, tmp_path):
    (tmp_path / "khac.json").write_text(json.dumps(VALID), encoding="utf-8")
    (app / MANIFEST).unlink()
    (app / MANIFEST).symlink_to(tmp_path / "khac.json")

    assert problems(app) == [f"File {MANIFEST} là symlink. Hãy dùng file thật."]


def test_manifest_must_be_regular_file(app):
    (app / MANIFEST).unlink()
    (app / MANIFEST).mkdir()

    assert problems(app) == [f"{MANIFEST} không phải file thường."]


@as_root
def test_unreadable_manifest_is_reported(app):
    (app / MANIFEST).chmod(0)

    assert problems(app) == [f"Không đọc được file {MANIFEST}."]


@pytest.mark.parametrize("field", ["database", "processes", "ui"])
def test_missing_folder_is_reported(app, field):
    data = VALID | {field: f"{field}/khong-co"}

    assert problems(app, data) == [f'{field}: Không tìm thấy thư mục "{field}/khong-co".']


def test_folder_can_be_nested(app):
    (app / "ui").rename(app / "dist")
    (app / "web").mkdir()
    (app / "dist").rename(app / "web" / "dist")

    assert problems(app, VALID | {"ui": "web/dist"}) == []


def test_declared_path_must_be_folder(app):
    (app / "web").write_text("", encoding="utf-8")

    assert problems(app, VALID | {"ui": "web/dist"}) == ['ui: "web" không phải thư mục.']


def test_declared_folder_cannot_be_symlink(app, tmp_path):
    (app / "ui").rename(tmp_path / "ui")
    (app / "ui").symlink_to(tmp_path / "ui")

    assert problems(app) == ['ui: "ui" là symlink. Thư mục đã khai không được là symlink.']


def test_part_of_declared_path_cannot_be_symlink(app):
    (app / "web").symlink_to(app)

    assert problems(app, VALID | {"ui": "web/ui"}) == [
        'ui: "web" là symlink. Thư mục đã khai không được là symlink.'
    ]


@pytest.mark.parametrize(
    "target",
    ["/etc/passwd", "../../database", "app.js", "khong-co"],
    ids=["ra-ngoai", "thu-muc-khac", "ben-trong", "khong-ton-tai"],
)
def test_symlink_inside_folder_is_refused(app, target):
    (app / "ui" / "assets" / "link").symlink_to(target)

    assert problems(app) == [f'ui: "ui/assets/link" {SYMLINK}']


def test_special_file_inside_folder_is_refused(app):
    os.mkfifo(app / "ui" / "pipe")

    assert problems(app) == ['ui: "ui/pipe" không phải file thường hay thư mục.']


@as_root
def test_unreadable_file_is_reported(app):
    (app / "ui" / "assets" / "app.js").chmod(0)

    assert problems(app) == ['ui: Không đọc được file "ui/assets/app.js".']


@as_root
def test_unreadable_subfolder_is_reported(app):
    (app / "ui" / "assets").chmod(0o600)

    assert problems(app) == ['ui: Không mở được thư mục "ui/assets".']


@as_root
def test_unreadable_declared_folder_is_reported(app):
    (app / "ui").chmod(0)

    assert problems(app) == ['ui: Không mở được thư mục "ui".']


@pytest.mark.parametrize(
    ("field", "path", "replacement", "missing"),
    [
        ("database", "database/0001_don.sql", "0001_don.SQL", "không có file .sql nào"),
        ("database", "database/0001_don.sql", "sql/0001_don.sql", "không có file .sql nào"),
        ("processes", "processes/duyet.bpmn", "duyet.xml", "không có file .bpmn nào"),
        ("ui", "ui/index.html", "trang/index.html", "không có file index.html"),
    ],
    ids=["sql-chu-hoa", "sql-trong-thu-muc-con", "khong-co-bpmn", "index-trong-thu-muc-con"],
)
def test_folder_needs_its_main_file(app, field, path, replacement, missing):
    source = app / path
    target = source.parent / replacement
    target.parent.mkdir(exist_ok=True)
    source.rename(target)

    assert problems(app) == [f'{field}: Thư mục "{field}" {missing}.']


def test_index_html_must_not_be_folder(app):
    (app / "ui" / "index.html").unlink()
    (app / "ui" / "index.html").mkdir()

    assert problems(app) == ['ui: Thư mục "ui" không có file index.html.']


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"ui": "database"}, "ui: Thư mục của database và ui trùng nhau hoặc nằm trong nhau."),
        (
            {"database": "ui/sql"},
            "ui: Thư mục của database và ui trùng nhau hoặc nằm trong nhau.",
        ),
        (
            {"processes": "database/"},
            "processes: Thư mục của database và processes trùng nhau hoặc nằm trong nhau.",
        ),
    ],
    ids=["trung-nhau", "nam-trong-ui", "trung-sau-dau-gach-cheo"],
)
def test_folders_cannot_overlap(app, change, expected):
    (app / "database" / "index.html").write_text("", encoding="utf-8")
    (app / "database" / "duyet.bpmn").write_text("", encoding="utf-8")
    (app / "ui" / "sql").mkdir()
    (app / "ui" / "sql" / "0001_don.sql").write_text("", encoding="utf-8")

    assert problems(app, VALID | change) == [expected]


def test_names_used_by_core_are_reserved():
    sql = [CONFIG / "postgres" / "init.sql", CONFIG / "postgres" / "databases.sql"]
    sql += list((CONFIG / "postgres" / "migrations").iterdir())
    text = "\n".join(path.read_text(encoding="utf-8") for path in sql)
    created = re.findall(r"CREATE (?:SCHEMA|ROLE)(?: IF NOT EXISTS)? (\w+)", text)
    routes = [path.name.removesuffix(".json") for path in (CONFIG / "apisix" / "routes").iterdir()]
    realm = (CONFIG / "keycloak" / "setup-realm.lua").read_text(encoding="utf-8")
    clients = re.findall(r'^local OPERATON = "([a-z-]+)"$', realm, re.MULTILINE)

    assert created
    assert clients == ["operaton"]
    assert {name.replace("_", "-") for name in created} | set(routes) | set(clients) <= (
        RESERVED_NAMES
    )
