# SPDX-License-Identifier: Apache-2.0
import json
import runpy
import sys

import pytest

from saigonos_core import apps
from saigonos_core.manifest import MANIFEST, schema_text

VALID = {
    "name": "don-tu",
    "title": "Đơn từ",
    "version": "1.2.0",
    "roles": [{"name": "don-tu.can-bo", "description": "Xử lý đơn"}],
    "ui": "ui",
}


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
