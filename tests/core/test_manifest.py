# SPDX-License-Identifier: Apache-2.0
import json
import os
import re
from importlib.resources import files
from pathlib import Path

import pytest

from saigonos_core.manifest import (
    ACCESS_RULES,
    ARCHIVE_TABLES,
    KEEP_DAYS,
    LABEL_LENGTH,
    MANIFEST,
    NAME_LENGTH,
    QUALITY_RULES,
    RELATION_LENGTH,
    RESERVED_NAMES,
    RESERVED_PREFIX,
    ROLE_LENGTH,
    RULE_COLUMNS,
    SEARCH_COLUMNS,
    SEARCH_TABLES,
    SNAPSHOTS,
    TABLE_LENGTH,
    check_app,
    schema_text,
)

CONFIG = files("saigonos") / "stack" / "config"
SCHEMA_FILE = Path(__file__).resolve().parents[2] / "schemas" / "saigonos-app.schema.json"
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
PROCESS = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                  xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
                  xmlns:operaton="http://operaton.org/schema/1.0/bpmn"
                  id="duyet_dinh_nghia" targetNamespace="https://dx.example.com/bpmn">
  <bpmn:process id="nghi_phep.duyet" isExecutable="true" operaton:historyTimeToLive="P30D"
                operaton:candidateStarterGroups="nghi-phep.nhan-vien">
    <bpmn:startEvent id="bat_dau" />
    <bpmn:sequenceFlow id="luong_1" sourceRef="bat_dau" targetRef="ket_thuc" />
    <bpmn:endEvent id="ket_thuc" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="hinh">
    <bpmndi:BPMNPlane id="mat_phang" bpmnElement="nghi_phep.duyet">
      <bpmndi:BPMNShape id="bat_dau_hinh" bpmnElement="bat_dau">
        <dc:Bounds x="100" y="80" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNEdge id="luong_1_hinh" bpmnElement="luong_1">
        <di:waypoint x="136" y="98" />
        <di:waypoint x="200" y="98" />
      </bpmndi:BPMNEdge>
      <bpmndi:BPMNShape id="ket_thuc_hinh" bpmnElement="ket_thuc">
        <dc:Bounds x="200" y="80" width="36" height="36" />
      </bpmndi:BPMNShape>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>
"""
FILES = {
    "database/0001_don.sql": "CREATE TABLE nghi_phep.don (id bigint);\n",
    "processes/duyet.bpmn": PROCESS,
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
    assert checked.manifest.model_dump(exclude_defaults=True) == VALID


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
    clients = re.findall(r'^local (?:OPERATON|GRAFANA) = "([a-z-]+)"$', realm, re.MULTILINE)

    assert created
    assert clients == ["operaton", "grafana"]
    assert {name.replace("_", "-") for name in created} | set(routes) | set(clients) <= (
        RESERVED_NAMES
    )


def test_schema_file_matches_model():
    assert SCHEMA_FILE.read_text(encoding="utf-8") == schema_text(), "Hãy chạy lệnh make schema"


def test_schema_lists_rules_of_manifest():
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    name = schema["properties"]["name"]

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["required"] == ["name", "title", "version", "roles"]
    assert schema["additionalProperties"] is False
    assert name["not"]["anyOf"] == [
        {"enum": sorted(RESERVED_NAMES)},
        {"pattern": f"^{RESERVED_PREFIX}"},
    ]


def test_problem_of_bpmn_file_names_file_and_line(app):
    script = '<bpmn:scriptTask id="chay" />\n    <bpmn:startEvent'
    text = PROCESS.replace("<bpmn:startEvent", script)
    (app / "processes" / "duyet.bpmn").write_text(text, encoding="utf-8")

    assert problems(app) == [
        'processes: "processes/duyet.bpmn", dòng 10: '
        "Thẻ scriptTask chạy script trong Operaton nên không được dùng."
    ]


def test_bpmn_checks_use_name_and_roles_of_manifest(app):
    roles = [role("nghi-phep.nhan-vien", "Gửi đơn")]

    assert problems(app, VALID | {"roles": roles}) == []
    assert problems(app, VALID | {"name": "don-tu", "roles": [role("don-tu.quan-ly")]}) == [
        'processes: "processes/duyet.bpmn", dòng 8: Mã quy trình nghi_phep.duyet phải có dạng '
        "don_tu.<tên quy trình>. Tên quy trình gồm chữ thường không dấu, chữ số và dấu gạch dưới.",
        'processes: "processes/duyet.bpmn", dòng 8: Thuộc tính operaton:candidateStarterGroups '
        "của quy trình nghi_phep.duyet có nghi-phep.nhan-vien không phải role của ứng dụng.",
    ]


def test_bpmn_files_are_read_only_when_folder_is_fine(app):
    (app / "processes" / "duyet.bpmn").write_text("không phải XML", encoding="utf-8")
    (app / "processes" / "lien-ket").symlink_to("duyet.bpmn")

    assert problems(app) == [f'processes: "processes/lien-ket" {SYMLINK}']


def test_drawing_warning_keeps_app_valid(app):
    text = re.sub(r"  <bpmndi:BPMNDiagram.*</bpmndi:BPMNDiagram>\n", "", PROCESS, flags=re.DOTALL)
    (app / "processes" / "duyet.bpmn").write_text(text, encoding="utf-8")

    checked = check_app(app)

    assert checked.manifest is not None
    assert [str(warning) for warning in checked.warnings] == [
        'processes: "processes/duyet.bpmn": File không có phần hình vẽ (BPMNDI) '
        "nên Cockpit của Operaton không vẽ được quy trình."
    ]


PATH_RULE = (
    "Đường dẫn bắt đầu bằng dấu /, tính từ /apps/<tên ứng dụng>/api. Đường dẫn gồm chữ cái "
    "không dấu, chữ số, dấu chấm, dấu gạch ngang, dấu gạch dưới, dấu / và dấu *. "
    "Ví dụ: /rpc/duyet_don hoặc /don*."
)
APPROVE = {
    "methods": ["POST"],
    "paths": ["/rpc/duyet_don"],
    "roles": ["nghi-phep.quan-ly"],
    "otp": True,
}


@pytest.mark.parametrize(
    "rules",
    [
        [APPROVE],
        [{"networks": ["192.168.1.0/24", "2001:db8::/32", "203.0.113.7/32"]}],
        [{"methods": ["DELETE", "PATCH"], "paths": ["/don*", "/rpc/**"], "otp": True}],
        [{"roles": ["nghi-phep.nhan-vien", "nghi-phep.quan-ly"]}],
        [],
    ],
    ids=["duyet-don", "dai-mang", "glob", "hai-role", "khong-co-luat"],
)
def test_access_rules_are_accepted(app, rules):
    write(app, VALID | {"access": rules})

    checked = check_app(app)

    assert checked.problems == []
    assert [rule.model_dump(exclude_defaults=True) for rule in checked.manifest.access] == rules


def test_rule_is_written_to_route_label_as_compact_json(app):
    write(app, VALID | {"access": [APPROVE]})

    [rule] = check_app(app).manifest.access

    assert rule.label() == json.dumps(APPROVE, separators=(",", ":"))


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        (
            {"methods": ["POST"]},
            "access[0]: Luật phải có ít nhất một điều kiện roles, networks hoặc otp.",
        ),
        ({"otp": False}, "access[0]: Luật phải có ít nhất một điều kiện roles, networks hoặc otp."),
        ({"otp": "true"}, "access[0].otp: Giá trị phải là true hoặc false."),
        (
            {"methods": ["OPTIONS"], "otp": True},
            "access[0].methods[0]: Phương thức phải là GET, POST, PATCH, PUT hoặc DELETE.",
        ),
        ({"methods": [], "otp": True}, "access[0].methods: Danh sách phải có ít nhất 1 phần tử."),
        ({"paths": ["rpc/duyet_don"], "otp": True}, f"access[0].paths[0]: {PATH_RULE}"),
        ({"paths": ["/đơn"], "otp": True}, f"access[0].paths[0]: {PATH_RULE}"),
        ({"paths": ["/don?id=1"], "otp": True}, f"access[0].paths[0]: {PATH_RULE}"),
        (
            {"paths": ["/" + "a" * 200], "otp": True},
            "access[0].paths[0]: Giá trị dài tối đa 200 ký tự.",
        ),
        ({"roles": ["quan-ly"]}, f"access[0].roles[0]: {ROLE_RULE}"),
        (
            {"roles": ["nghi-phep.truong-phong"]},
            'access[0].roles[0]: Role "nghi-phep.truong-phong" chưa được khai báo trong roles '
            "của ứng dụng.",
        ),
        (
            {"networks": ["192.168.1.5/24"]},
            'access[0].networks: Dải mạng "192.168.1.5/24" không hợp lệ. Hãy viết theo dạng '
            "CIDR, ví dụ 192.168.1.0/24.",
        ),
        (
            {"networks": ["203.0.113.7"]},
            'access[0].networks: Dải mạng "203.0.113.7" không hợp lệ. Hãy viết theo dạng '
            "CIDR, ví dụ 192.168.1.0/24.",
        ),
        (
            {"networks": ["mang-noi-bo"]},
            'access[0].networks: Dải mạng "mang-noi-bo" không hợp lệ. Hãy viết theo dạng '
            "CIDR, ví dụ 192.168.1.0/24.",
        ),
        (
            {"otp": True, "message": "Không được"},
            "access[0].message: Không có trường này. Hãy kiểm tra lỗi chính tả.",
        ),
    ],
    ids=[
        "khong-co-dieu-kien",
        "otp-false",
        "otp-la-chuoi",
        "phuong-thuc-la",
        "phuong-thuc-rong",
        "duong-dan-thieu-gach-cheo",
        "duong-dan-co-dau",
        "duong-dan-co-query",
        "duong-dan-qua-dai",
        "role-sai-dang",
        "role-chua-khai",
        "dai-mang-co-bit-may",
        "dai-mang-thieu-do-dai",
        "dai-mang-khong-phai-ip",
        "truong-la",
    ],
)
def test_each_invalid_access_rule_has_its_own_message(app, rule, expected):
    assert problems(app, VALID | {"access": [rule]}) == [expected]


def test_rule_too_long_for_route_label_is_refused(app):
    paths = [f"/rpc/ham_so_{index:02d}_cua_ung_dung" for index in range(12)]
    label = json.dumps({"paths": paths, "otp": True}, separators=(",", ":"))

    found = problems(app, VALID | {"access": [{"paths": paths, "otp": True}]})

    assert len(label) > LABEL_LENGTH
    assert found == [
        f"access[0]: Luật dài {len(label)} ký tự khi ghi vào route của APISIX, tối đa "
        f"{LABEL_LENGTH} ký tự. Hãy tách thành nhiều luật."
    ]


def test_too_many_access_rules_are_refused(app):
    rules = [{"otp": True}] * (ACCESS_RULES + 1)

    assert problems(app, VALID | {"access": rules}) == [
        f"access: Danh sách có tối đa {ACCESS_RULES} phần tử."
    ]


TABLE_RULE = (
    "Tên bảng gồm chữ thường không dấu, chữ số và dấu gạch dưới, bắt đầu bằng chữ cái "
    "hoặc dấu gạch dưới. Ví dụ: don_nghi."
)
COLUMN_RULE = (
    "Tên cột gồm chữ thường không dấu, chữ số và dấu gạch dưới, bắt đầu bằng chữ cái "
    "hoặc dấu gạch dưới. Ví dụ: ly_do."
)


@pytest.mark.parametrize(
    "search",
    [
        [{"table": "don", "columns": ["ly_do"]}],
        [
            {"table": "don_nghi", "columns": ["ly_do", "ghi_chu"]},
            {"table": "_nhap", "columns": ["noi_dung_2"]},
        ],
        [],
    ],
    ids=["mot-bang", "hai-bang", "khong-co-bang"],
)
def test_search_tables_are_accepted(app, search):
    write(app, VALID | {"search": search})

    checked = check_app(app)

    assert checked.problems == []
    assert [table.model_dump() for table in checked.manifest.search] == search


@pytest.mark.parametrize(
    ("search", "expected"),
    [
        ([{"table": "Don", "columns": ["ly_do"]}], f"search[0].table: {TABLE_RULE}"),
        ([{"table": "don-nghi", "columns": ["ly_do"]}], f"search[0].table: {TABLE_RULE}"),
        ([{"table": "2don", "columns": ["ly_do"]}], f"search[0].table: {TABLE_RULE}"),
        (
            [{"table": "d" * (TABLE_LENGTH + 1), "columns": ["ly_do"]}],
            f"search[0].table: Giá trị dài tối đa {TABLE_LENGTH} ký tự.",
        ),
        (
            [{"table": "don", "columns": []}],
            "search[0].columns: Danh sách phải có ít nhất 1 phần tử.",
        ),
        ([{"table": "don", "columns": ["lý_do"]}], f"search[0].columns[0]: {COLUMN_RULE}"),
        (
            [{"table": "don", "columns": ["ly_do", "ly_do"]}],
            'search[0].columns: Cột "ly_do" được khai báo hai lần.',
        ),
        (
            [{"table": "don", "columns": ["ly_do"]}, {"table": "don", "columns": ["ghi_chu"]}],
            'search[1].table: Bảng "don" được khai báo hai lần.',
        ),
        ([{"table": "don"}], "search[0].columns: Thiếu trường bắt buộc."),
        (
            [{"table": "don", "columns": ["ly_do"], "language": "vi"}],
            "search[0].language: Không có trường này. Hãy kiểm tra lỗi chính tả.",
        ),
    ],
    ids=[
        "bang-chu-hoa",
        "bang-gach-ngang",
        "bang-bat-dau-bang-so",
        "bang-qua-dai",
        "khong-co-cot",
        "cot-co-dau",
        "cot-trung",
        "bang-trung",
        "thieu-cot",
        "truong-la",
    ],
)
def test_each_invalid_search_table_has_its_own_message(app, search, expected):
    assert problems(app, VALID | {"search": search}) == [expected]


def test_too_many_search_tables_or_columns_are_refused(app):
    tables = [
        {"table": f"bang_{index}", "columns": ["noi_dung"]} for index in range(SEARCH_TABLES + 1)
    ]
    columns = [f"cot_{index}" for index in range(SEARCH_COLUMNS + 1)]

    assert problems(app, VALID | {"search": tables}) == [
        f"search: Danh sách có tối đa {SEARCH_TABLES} phần tử."
    ]
    assert problems(app, VALID | {"search": [{"table": "don", "columns": columns}]}) == [
        f"search[0].columns: Danh sách có tối đa {SEARCH_COLUMNS} phần tử."
    ]


def test_role_check_of_access_waits_for_valid_roles(app):
    change = {"roles": "nghi-phep.quan-ly", "access": [{"roles": ["nghi-phep.khac"]}]}

    assert problems(app, VALID | change) == ["roles: Giá trị phải là một danh sách."]


ARCHIVED = {"table": "don", "column": "tao_luc", "keep_days": 365}
SNAPSHOT = {"view": "chot_don", "column": "tao_luc"}
RULES = [
    {"rule": "not_null", "columns": ["ma", "ly_do"]},
    {"rule": "unique", "columns": ["ma"]},
    {"rule": "range", "column": "so_ngay", "min": 0.5, "max": 30},
    {"rule": "range", "column": "so_ngay", "min": 1},
]
VIEW_RULE = (
    "Tên view hoặc bảng gồm chữ thường không dấu, chữ số và dấu gạch dưới, bắt đầu bằng chữ cái "
    "hoặc dấu gạch dưới. Ví dụ: chot_don."
)


@pytest.mark.parametrize(
    ("archive", "snapshots"),
    [
        ([ARCHIVED], []),
        ([ARCHIVED | {"rules": RULES}], [SNAPSHOT | {"rules": RULES}]),
        (
            [ARCHIVED, ARCHIVED | {"table": "_nhat_ky", "keep_days": 1}],
            [{"view": "don", **SNAPSHOT}],
        ),
        ([], []),
    ],
    ids=["mot-bang", "co-luat", "bang-vua-luu-vua-chot", "khong-co-gi"],
)
def test_archive_and_snapshots_are_accepted(app, archive, snapshots):
    write(app, VALID | {"archive": archive, "snapshots": snapshots})

    checked = check_app(app)

    assert checked.problems == []
    assert [
        entry.model_dump(exclude_defaults=True) for entry in checked.manifest.archive
    ] == archive
    assert [
        entry.model_dump(exclude_defaults=True) for entry in checked.manifest.snapshots
    ] == snapshots


def test_bounds_of_range_rule_are_kept_as_numbers(app):
    write(app, VALID | {"snapshots": [SNAPSHOT | {"rules": RULES}]})

    [snapshot] = check_app(app).manifest.snapshots

    assert [(rule.rule, getattr(rule, "min", None)) for rule in snapshot.rules] == [
        ("not_null", None),
        ("unique", None),
        ("range", 0.5),
        ("range", 1.0),
    ]
    assert snapshot.rules[3].max is None


@pytest.mark.parametrize(
    ("archive", "expected"),
    [
        ([ARCHIVED | {"table": "Don"}], f"archive[0].table: {TABLE_RULE}"),
        (
            [ARCHIVED | {"table": "d" * (RELATION_LENGTH + 1)}],
            f"archive[0].table: Giá trị dài tối đa {RELATION_LENGTH} ký tự.",
        ),
        ([ARCHIVED | {"column": "tạo_lúc"}], f"archive[0].column: {COLUMN_RULE}"),
        ([ARCHIVED | {"keep_days": 0}], "archive[0].keep_days: Giá trị phải lớn hơn hoặc bằng 1."),
        (
            [ARCHIVED | {"keep_days": KEEP_DAYS + 1}],
            f"archive[0].keep_days: Giá trị phải nhỏ hơn hoặc bằng {KEEP_DAYS}.",
        ),
        ([ARCHIVED | {"keep_days": "30"}], "archive[0].keep_days: Giá trị phải là một số nguyên."),
        ([ARCHIVED | {"keep_days": 30.0}], "archive[0].keep_days: Giá trị phải là một số nguyên."),
        ([ARCHIVED | {"keep_days": True}], "archive[0].keep_days: Giá trị phải là một số nguyên."),
        ([{"table": "don", "column": "tao_luc"}], "archive[0].keep_days: Thiếu trường bắt buộc."),
        (
            [ARCHIVED, ARCHIVED | {"keep_days": 30}],
            'archive[1].table: Bảng "don" được khai báo hai lần.',
        ),
        (
            [ARCHIVED | {"days": 30}],
            "archive[0].days: Không có trường này. Hãy kiểm tra lỗi chính tả.",
        ),
        (["don"], "archive[0]: Giá trị phải là một đối tượng JSON."),
    ],
    ids=[
        "bang-chu-hoa",
        "bang-qua-dai",
        "cot-co-dau",
        "giu-0-ngay",
        "giu-qua-lau",
        "so-ngay-la-chuoi",
        "so-ngay-la-so-thuc",
        "so-ngay-la-true",
        "thieu-so-ngay",
        "bang-trung",
        "truong-la",
        "khong-phai-doi-tuong",
    ],
)
def test_each_invalid_archive_table_has_its_own_message(app, archive, expected):
    assert problems(app, VALID | {"archive": archive}) == [expected]


@pytest.mark.parametrize(
    ("snapshots", "expected"),
    [
        ([SNAPSHOT | {"view": "chot-don"}], f"snapshots[0].view: {VIEW_RULE}"),
        ([SNAPSHOT | {"column": "Ngay"}], f"snapshots[0].column: {COLUMN_RULE}"),
        ([{"view": "chot_don"}], "snapshots[0].column: Thiếu trường bắt buộc."),
        ([SNAPSHOT, SNAPSHOT], 'snapshots[1].view: View "chot_don" được khai báo hai lần.'),
        (
            [SNAPSHOT | {"period": "month"}],
            "snapshots[0].period: Không có trường này. Hãy kiểm tra lỗi chính tả.",
        ),
    ],
    ids=["view-gach-ngang", "cot-chu-hoa", "thieu-cot", "view-trung", "truong-la"],
)
def test_each_invalid_snapshot_has_its_own_message(app, snapshots, expected):
    assert problems(app, VALID | {"snapshots": snapshots}) == [expected]


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ({"rule": "not_null", "columns": []}, "columns: Danh sách phải có ít nhất 1 phần tử."),
        ({"rule": "not_null", "columns": ["Ma"]}, f"columns[0]: {COLUMN_RULE}"),
        ({"rule": "unique", "columns": ["ma", "ma"]}, 'columns: Cột "ma" được khai báo hai lần.'),
        ({"rule": "unique"}, "columns: Thiếu trường bắt buộc."),
        (
            {"rule": "range", "column": "so_ngay"},
            ": Luật range phải có ít nhất một trong hai giá trị min và max.",
        ),
        (
            {"rule": "range", "column": "so_ngay", "min": 5, "max": 1},
            ": Giá trị min phải nhỏ hơn hoặc bằng max.",
        ),
        ({"rule": "range", "column": "so_ngay", "min": "1"}, "min: Giá trị phải là một số."),
        ({"rule": "range", "column": "so_ngay", "max": True}, "max: Giá trị phải là một số."),
        (
            {"rule": "range", "column": "so_ngay", "max": float("inf")},
            "max: Giá trị phải là một số hữu hạn.",
        ),
        ({"rule": "range", "column": "Đ", "min": 1}, f"column: {COLUMN_RULE}"),
        (
            {"rule": "range", "column": "so_ngay", "min": 1, "step": 1},
            "step: Không có trường này. Hãy kiểm tra lỗi chính tả.",
        ),
        ({"rule": "check", "sql": "so_ngay > 0"}, ": Luật phải là not_null, unique hoặc range."),
        (
            {"columns": ["ma"]},
            ": Thiếu trường rule. Luật phải là not_null, unique hoặc range.",
        ),
        ("not_null", ": Giá trị phải là một đối tượng JSON."),
    ],
    ids=[
        "khong-co-cot",
        "cot-chu-hoa",
        "cot-trung",
        "thieu-cot",
        "range-khong-co-gioi-han",
        "range-nguoc",
        "min-la-chuoi",
        "max-la-true",
        "max-vo-han",
        "range-cot-co-dau",
        "truong-la",
        "luat-la",
        "thieu-rule",
        "khong-phai-doi-tuong",
    ],
)
def test_each_invalid_quality_rule_has_its_own_message(app, rule, expected):
    where, text = expected.split(": ", 1)
    suffix = f".{where}" if where else ""

    archived = problems(app, VALID | {"archive": [ARCHIVED | {"rules": [rule]}]})
    snapshot = problems(app, VALID | {"snapshots": [SNAPSHOT | {"rules": [rule]}]})

    assert archived == [f"archive[0].rules[0]{suffix}: {text}"]
    assert snapshot == [f"snapshots[0].rules[0]{suffix}: {text}"]


def test_too_many_archive_tables_snapshots_rules_or_rule_columns_are_refused(app):
    tables = [ARCHIVED | {"table": f"bang_{index}"} for index in range(ARCHIVE_TABLES + 1)]
    views = [SNAPSHOT | {"view": f"view_{index}"} for index in range(SNAPSHOTS + 1)]
    rules = [{"rule": "unique", "columns": ["ma"]}] * (QUALITY_RULES + 1)
    columns = [f"cot_{index}" for index in range(RULE_COLUMNS + 1)]

    assert problems(app, VALID | {"archive": tables}) == [
        f"archive: Danh sách có tối đa {ARCHIVE_TABLES} phần tử."
    ]
    assert problems(app, VALID | {"snapshots": views}) == [
        f"snapshots: Danh sách có tối đa {SNAPSHOTS} phần tử."
    ]
    assert problems(app, VALID | {"archive": [ARCHIVED | {"rules": rules}]}) == [
        f"archive[0].rules: Danh sách có tối đa {QUALITY_RULES} phần tử."
    ]
    assert problems(
        app,
        VALID | {"snapshots": [SNAPSHOT | {"rules": [{"rule": "not_null", "columns": columns}]}]},
    ) == [f"snapshots[0].rules[0].columns: Danh sách có tối đa {RULE_COLUMNS} phần tử."]


def test_schema_describes_quality_rules_by_their_kind():
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    rules = schema["$defs"]["ArchiveTable"]["properties"]["rules"]["items"]

    assert rules["discriminator"]["propertyName"] == "rule"
    assert sorted(rules["discriminator"]["mapping"]) == ["not_null", "range", "unique"]
    assert schema["$defs"]["ArchiveTable"]["required"] == ["table", "column", "keep_days"]
    assert schema["$defs"]["Snapshot"]["required"] == ["view", "column"]
