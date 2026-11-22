# SPDX-License-Identifier: Apache-2.0
import json
import runpy
import sys

import pytest

from saigonos_core import apps
from saigonos_core.app_database import ApplyError
from saigonos_core.manifest import MANIFEST, schema_text

VALID = {
    "name": "don-tu",
    "title": "Đơn từ",
    "version": "1.2.0",
    "roles": [{"name": "don-tu.can-bo", "description": "Xử lý đơn"}],
    "ui": "ui",
}
PROCESS = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:operaton="http://operaton.org/schema/1.0/bpmn"
                  id="xu_ly_dinh_nghia" targetNamespace="https://dx.example.com/bpmn">
  <bpmn:process id="don_tu.xu_ly" isExecutable="true" operaton:historyTimeToLive="P30D">
    <bpmn:startEvent id="bat_dau" />
  </bpmn:process>
</bpmn:definitions>
"""


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(apps, "APPS", tmp_path)
    app = tmp_path / "don-tu"
    (app / "ui").mkdir(parents=True)
    (app / "ui" / "index.html").write_text("<!doctype html>\n", encoding="utf-8")
    (app / MANIFEST).write_text(json.dumps(VALID), encoding="utf-8")
    return app


def test_check_reports_valid_app(folder, capsys):
    assert apps.main(["check", "don-tu"]) == 0
    assert capsys.readouterr().out == "Ứng dụng don-tu 1.2.0 không có lỗi.\n"


def test_check_lists_every_problem_and_fails(folder, capsys):
    (folder / "ui" / "index.html").unlink()
    data = VALID | {"version": "1.2", "processes": "processes"}
    (folder / MANIFEST).write_text(json.dumps(data), encoding="utf-8")

    assert apps.main(["check", "don-tu"]) == 1
    assert capsys.readouterr().out == (
        "Ứng dụng có 3 lỗi:\n"
        "- version: Phiên bản phải theo Semantic Versioning, ví dụ 1.0.0 hoặc 1.0.0-beta.1.\n"
        '- processes: Không tìm thấy thư mục "processes".\n'
        '- ui: Thư mục "ui" không có file index.html.\n'
    )


def test_check_accepts_absolute_folder(folder, capsys):
    assert apps.main(["check", str(folder)]) == 0
    assert "không có lỗi" in capsys.readouterr().out


def test_check_reports_missing_folder(folder, capsys):
    assert apps.main(["check", "khong-co"]) == 1
    assert capsys.readouterr().out == "Không tìm thấy thư mục khong-co.\n"


def test_schema_prints_json_schema_of_manifest(capsys):
    assert apps.main(["schema"]) == 0
    assert capsys.readouterr().out == schema_text()


def test_command_is_required(capsys):
    with pytest.raises(SystemExit) as exit_info:
        apps.main([])

    assert exit_info.value.code == 2
    assert "docker compose run --rm apps" in capsys.readouterr().err


def test_module_runs_with_python_m(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["apps", "schema"])
    monkeypatch.delitem(sys.modules, "saigonos_core.apps")

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("saigonos_core.apps", run_name="__main__")

    assert exit_info.value.code == 0
    assert json.loads(capsys.readouterr().out)["title"] == "Bản khai ứng dụng SaigonOS"


SETTINGS = {
    "KEYCLOAK_URL": "http://keycloak:8080/auth",
    "KEYCLOAK_ADMIN_USERNAME": "admin",
    "KEYCLOAK_ADMIN_PASSWORD": "mat-khau-quan-tri",
    "SAIGONOS_URL": "https://dx.example.com",
    "APISIX_ADMIN_URL": "http://apisix:9180",
    "APISIX_ADMIN_KEY": "khoa-quan-tri",
    "OPERATON_URL": "http://operaton:8080/operaton/engine-rest",
    "CORE_OPERATON_PASSWORD": "mat-khau-tai-khoan-core",
}


class FakeApply:
    def __init__(self):
        self.calls = []
        self.events = []
        self.failure = None
        self.taken = None
        self.refusal = None
        self.route_taken = None
        self.engine_refusal = None

    async def database(self, manifest, folder, say, before_finish):
        self.calls.append((manifest.name, folder))
        say("Đã chạy file 0001_don.sql.")
        if self.failure:
            raise self.failure
        before_finish()
        self.events.append("finish")
        return True

    def check_names(self, keycloak, manifest):
        admin = (keycloak.host, keycloak.port, keycloak.base, keycloak.username, keycloak.password)
        self.events.append(("check", *admin, manifest.name))
        if self.taken:
            raise self.taken

    def apply_keycloak(self, keycloak, manifest, site_url, say):
        self.events.append(("keycloak", site_url, manifest.name))
        say("Đã tạo client don-tu.")
        if self.refusal:
            raise self.refusal
        return True

    def check_route(self, apisix, manifest):
        admin = (apisix.host, apisix.port, apisix.base, apisix.key)
        self.events.append(("check route", *admin, manifest.name))
        if self.route_taken:
            raise self.route_taken

    def apply_gateway(self, apisix, manifest, say):
        self.events.append(("gateway", manifest.name))
        say("Đã tạo route app-don-tu.")
        return True

    def check_operaton(self, operaton):
        self.events.append(("check operaton", operaton.host, operaton.port, operaton.base))
        if self.engine_refusal:
            raise self.engine_refusal

    def apply_processes(self, operaton, manifest, folder, say):
        self.events.append(("processes", manifest.name, folder))
        say("Đã triển khai file xu-ly.bpmn: quy trình don_tu.xu_ly, phiên bản 1.")
        return True


@pytest.fixture
def applied(monkeypatch):
    fake = FakeApply()
    for name, value in SETTINGS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(apps, "apply_database", fake.database)
    monkeypatch.setattr(apps, "check_names", fake.check_names)
    monkeypatch.setattr(apps, "apply_keycloak", fake.apply_keycloak)
    monkeypatch.setattr(apps, "check_route", fake.check_route)
    monkeypatch.setattr(apps, "apply_gateway", fake.apply_gateway)
    monkeypatch.setattr(apps, "check_operaton", fake.check_operaton)
    monkeypatch.setattr(apps, "apply_processes", fake.apply_processes)
    return fake


def test_apply_plugs_checked_app(folder, applied, capsys):
    assert apps.main(["apply", "don-tu"]) == 0
    assert applied.calls == [("don-tu", folder)]
    assert applied.events == [
        ("check", "keycloak", 8080, "/auth", "admin", "mat-khau-quan-tri", "don-tu"),
        ("check route", "apisix", 9180, "", "khoa-quan-tri", "don-tu"),
        ("keycloak", "https://dx.example.com", "don-tu"),
        ("gateway", "don-tu"),
        "finish",
    ]
    assert capsys.readouterr().out == (
        "Đã chạy file 0001_don.sql.\nĐã tạo client don-tu.\nĐã tạo route app-don-tu.\n"
        "Đã cài đặt ứng dụng don-tu 1.2.0.\n"
    )


def test_route_taken_on_apisix_stops_apply_before_database(folder, applied, capsys):
    applied.route_taken = ApplyError("Route app-don-tu đã có trong APISIX.")

    assert apps.main(["apply", "don-tu"]) == 1
    assert applied.calls == []
    assert capsys.readouterr().out == "Route app-don-tu đã có trong APISIX.\n"


def test_names_taken_on_keycloak_stop_apply_before_database(folder, applied, capsys):
    applied.taken = ApplyError("Client don-tu đã có trong Keycloak.")

    assert apps.main(["apply", "don-tu"]) == 1
    assert applied.calls == []
    assert capsys.readouterr().out == "Client don-tu đã có trong Keycloak.\n"


def test_error_of_keycloak_stops_apply_before_finish(folder, applied, capsys):
    applied.refusal = ApplyError("Keycloak trả về mã 500 cho lời gọi POST /clients.")

    assert apps.main(["apply", "don-tu"]) == 1
    assert "finish" not in applied.events
    assert ("gateway", "don-tu") not in applied.events
    assert capsys.readouterr().out.splitlines() == [
        "Đã chạy file 0001_don.sql.",
        "Đã tạo client don-tu.",
        "Keycloak trả về mã 500 cho lời gọi POST /clients.",
    ]


def test_apply_needs_settings_of_keycloak_and_apisix(folder, applied, capsys, monkeypatch):
    monkeypatch.delenv("KEYCLOAK_ADMIN_PASSWORD")
    monkeypatch.setenv("SAIGONOS_URL", "")
    monkeypatch.delenv("APISIX_ADMIN_KEY")

    assert apps.main(["apply", "don-tu"]) == 1
    assert (applied.calls, applied.events) == ([], [])
    assert capsys.readouterr().out == (
        "Service apps thiếu biến môi trường KEYCLOAK_ADMIN_PASSWORD, SAIGONOS_URL, "
        "APISIX_ADMIN_KEY.\n"
    )


def test_apply_reports_error_of_database(folder, applied, capsys):
    applied.failure = ApplyError("Không chạy được file 0001_don.sql: lỗi.")

    assert apps.main(["apply", "don-tu"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "Đã chạy file 0001_don.sql.",
        "Không chạy được file 0001_don.sql: lỗi.",
    ]


def test_apply_checks_app_first(folder, applied, capsys):
    (folder / "ui" / "index.html").unlink()

    assert apps.main(["apply", "don-tu"]) == 1
    assert applied.calls == []
    assert capsys.readouterr().out == (
        'Ứng dụng có 1 lỗi:\n- ui: Thư mục "ui" không có file index.html.\n'
    )


def test_apply_needs_folder_named_after_app(folder, applied, capsys):
    folder.rename(folder.with_name("don-tu-cu"))

    assert apps.main(["apply", "don-tu-cu"]) == 1
    assert applied.calls == []
    assert capsys.readouterr().out == (
        "Thư mục don-tu-cu chứa bản khai của ứng dụng don-tu. "
        "Tên thư mục phải trùng tên ứng dụng.\n"
    )


@pytest.mark.parametrize("name", ["../etc", "Don-Tu", "don_tu", "don-tu/ui", ""])
def test_apply_refuses_invalid_name(folder, applied, capsys, name):
    assert apps.main(["apply", name]) == 1
    assert applied.calls == []
    assert capsys.readouterr().out == f"Tên ứng dụng {name} không hợp lệ.\n"


def test_apply_reports_missing_folder(folder, applied, capsys):
    assert apps.main(["apply", "khong-co"]) == 1
    assert capsys.readouterr().out == "Không tìm thấy thư mục khong-co trong thư mục apps.\n"


def test_check_prints_warnings_before_result(folder, capsys):
    (folder / "processes").mkdir()
    (folder / "processes" / "xu-ly.bpmn").write_text(PROCESS, encoding="utf-8")
    data = VALID | {"processes": "processes"}
    (folder / MANIFEST).write_text(json.dumps(data), encoding="utf-8")

    assert apps.main(["check", "don-tu"]) == 0
    assert capsys.readouterr().out == (
        "Ứng dụng có 1 cảnh báo:\n"
        '- processes: "processes/xu-ly.bpmn": File không có phần hình vẽ (BPMNDI) '
        "nên Cockpit của Operaton không vẽ được quy trình.\n"
        "Ứng dụng don-tu 1.2.0 không có lỗi.\n"
    )


def with_processes(folder):
    (folder / "processes").mkdir()
    (folder / "processes" / "xu-ly.bpmn").write_text(PROCESS, encoding="utf-8")
    data = VALID | {"processes": "processes"}
    (folder / MANIFEST).write_text(json.dumps(data), encoding="utf-8")


def test_apply_deploys_processes_after_gateway(folder, applied, capsys):
    with_processes(folder)

    assert apps.main(["apply", "don-tu"]) == 0
    assert applied.events == [
        ("check", "keycloak", 8080, "/auth", "admin", "mat-khau-quan-tri", "don-tu"),
        ("check route", "apisix", 9180, "", "khoa-quan-tri", "don-tu"),
        ("check operaton", "operaton", 8080, "/operaton/engine-rest"),
        ("keycloak", "https://dx.example.com", "don-tu"),
        ("gateway", "don-tu"),
        ("processes", "don-tu", folder),
        "finish",
    ]
    assert capsys.readouterr().out.splitlines()[-2:] == [
        "Đã triển khai file xu-ly.bpmn: quy trình don_tu.xu_ly, phiên bản 1.",
        "Đã cài đặt ứng dụng don-tu 1.2.0.",
    ]


def test_operaton_refusing_core_stops_apply_before_database(folder, applied, capsys):
    with_processes(folder)
    applied.engine_refusal = ApplyError("Operaton từ chối tài khoản core.")

    assert apps.main(["apply", "don-tu"]) == 1
    assert applied.calls == []
    assert capsys.readouterr().out.splitlines()[-1] == "Operaton từ chối tài khoản core."
