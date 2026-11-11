# SPDX-License-Identifier: Apache-2.0
from importlib.metadata import version

import dependencies
import pytest

DEV_ALLOWED = dependencies.ALLOWED_LICENSES | dependencies.DEV_ONLY_LICENSES


@pytest.fixture
def table_file(monkeypatch, tmp_path):
    path = tmp_path / "DEPENDENCIES.md"
    monkeypatch.setattr(dependencies, "TABLE_FILE", path)
    return path


def write_lock(tmp_path, content, name="requirements.txt"):
    lock_file = tmp_path / name
    lock_file.write_text(content, encoding="utf-8")
    return lock_file


def test_read_lock_returns_pinned_versions(tmp_path):
    lock_file = write_lock(
        tmp_path,
        "# header\nClick==8.5.1\n    # via saigonos\nboolean.py==5.0 ; python_version < '3.13'\n",
    )

    assert dependencies.read_lock(lock_file) == {"click": "8.5.1", "boolean-py": "5.0"}


def test_read_declared_splits_product_and_dev_dependencies():
    runtime, dev = dependencies.read_declared(dependencies.PROJECT_FILE)

    assert runtime == {"click"}
    assert {"pytest", "reuse", "ruff"} <= dev
    assert "click" not in dev


@pytest.mark.parametrize("reported", ["MIT", "Apache-2.0 OR BSD-2-Clause", "(MIT AND ISC)"])
def test_allowed_license_is_kept(reported):
    assert dependencies.resolve_license("demo", reported, dependencies.ALLOWED_LICENSES) == reported


@pytest.mark.parametrize(
    "reported", ["GPL-3.0-or-later", "BSD License", "UNKNOWN", "MIT OR Proprietary", ""]
)
def test_unknown_license_is_rejected(reported):
    with pytest.raises(dependencies.DependencyError, match="ngoài danh sách cho phép"):
        dependencies.resolve_license("demo", reported, dependencies.ALLOWED_LICENSES)


def test_dev_tool_may_use_dev_only_license():
    license_expression = dependencies.resolve_license("demo", "GPL-3.0-or-later", DEV_ALLOWED)

    assert license_expression == "GPL-3.0-or-later"


def test_verified_license_replaces_reported_one(monkeypatch):
    monkeypatch.setitem(dependencies.VERIFIED_LICENSES, "demo", "BSD-3-Clause")

    assert dependencies.resolve_license("demo", "BSD License", DEV_ALLOWED) == "BSD-3-Clause"


@pytest.mark.parametrize(
    ("items", "expected"),
    [([], ""), (["MIT"], "MIT"), (["MIT", "ISC"], "ISC và MIT"), (["c", "a", "b"], "a, b và c")],
)
def test_vietnamese_list_joins_last_item_with_va(items, expected):
    assert dependencies.vietnamese_list(items) == expected


def test_table_lists_every_product_library_and_dev_tool():
    table = dependencies.build_table()

    locked = dependencies.read_lock(dependencies.LOCK_FILE)
    dev_locked = dependencies.read_lock(dependencies.DEV_LOCK_FILE)
    _, dev = dependencies.read_declared(dependencies.PROJECT_FILE)
    assert locked
    for name, pinned in locked.items():
        assert f"| {name} | {pinned} |" in table
    for name in dev:
        assert f"| {name} | {dev_locked[name]} |" in table
    assert table.index(dependencies.RUNTIME_SECTION) < table.index(dependencies.DEV_SECTION)


def test_footer_states_allowed_licenses():
    table = dependencies.build_table()

    assert "Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, MIT và PSF-2.0" in table
    assert "CC-BY-SA-4.0, CC0-1.0 và GPL-3.0-or-later" in table


def test_empty_lock_gives_product_table_without_rows(tmp_path):
    table = dependencies.build_table(write_lock(tmp_path, ""))

    assert dependencies.RUNTIME_SECTION + dependencies.DEV_SECTION in table


def test_indirect_dependency_gets_generic_description(tmp_path):
    pinned = version("iniconfig")
    lock_file = write_lock(tmp_path, f"iniconfig=={pinned}\n")

    table = dependencies.build_table(lock_file)

    assert f"| iniconfig | {pinned} | MIT | {dependencies.INDIRECT} |" in table


def test_direct_dependency_without_description_is_rejected(monkeypatch):
    monkeypatch.delitem(dependencies.DESCRIPTIONS, "click")

    with pytest.raises(dependencies.DependencyError, match="click chưa có mô tả"):
        dependencies.build_table()


def test_dev_tool_missing_from_dev_lock_is_rejected(tmp_path):
    dev_lock_file = write_lock(tmp_path, "", "requirements-dev.txt")

    with pytest.raises(dependencies.DependencyError, match=r"chưa có trong requirements-dev\.txt"):
        dependencies.build_table(dev_lock_file=dev_lock_file)


def test_lock_that_differs_from_environment_is_rejected(tmp_path):
    lock_file = write_lock(tmp_path, "click==0.0.1\n")

    with pytest.raises(dependencies.DependencyError, match=r"lock file ghi 0\.0\.1"):
        dependencies.build_table(lock_file)


def test_package_that_is_not_installed_is_rejected(tmp_path):
    lock_file = write_lock(tmp_path, "khong-co-goi-nay==1.0\n")

    with pytest.raises(dependencies.DependencyError, match="chưa cài"):
        dependencies.build_table(lock_file)


def test_generated_table_passes_check(table_file):
    assert dependencies.main([]) == 0
    assert dependencies.main(["--check"]) == 0


def test_check_fails_when_table_differs(table_file, capsys):
    table_file.write_text("bảng cũ\n", encoding="utf-8")

    assert dependencies.main(["--check"]) == 1
    assert "không khớp với lock file" in capsys.readouterr().err
    assert table_file.read_text(encoding="utf-8") == "bảng cũ\n"


def test_check_fails_on_unknown_license(monkeypatch, table_file, capsys):
    monkeypatch.setattr(dependencies, "ALLOWED_LICENSES", set())

    assert dependencies.main(["--check"]) == 1
    assert "ngoài danh sách cho phép" in capsys.readouterr().err
    assert not table_file.exists()
