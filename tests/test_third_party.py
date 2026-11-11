# SPDX-License-Identifier: Apache-2.0
import pytest
import third_party


@pytest.fixture
def table_file(monkeypatch, tmp_path):
    path = tmp_path / "THIRD-PARTY.md"
    monkeypatch.setattr(third_party, "TABLE_FILE", path)
    return path


def write_lock(tmp_path, content):
    lock_file = tmp_path / "requirements.txt"
    lock_file.write_text(content, encoding="utf-8")
    return lock_file


def test_read_lock_returns_pinned_versions(tmp_path):
    lock_file = write_lock(
        tmp_path,
        "# header\nClick==8.5.1\n    # via saigonos\nboolean.py==5.0 ; python_version < '3.13'\n",
    )

    assert third_party.read_lock(lock_file) == {"click": "8.5.1", "boolean-py": "5.0"}


@pytest.mark.parametrize("reported", ["MIT", "Apache-2.0 OR BSD-2-Clause", "(MIT AND ISC)"])
def test_allowed_license_is_kept(reported):
    assert third_party.resolve_license("demo", reported) == reported


@pytest.mark.parametrize(
    "reported", ["GPL-3.0-or-later", "BSD License", "UNKNOWN", "MIT OR Proprietary", ""]
)
def test_unknown_license_is_rejected(reported):
    with pytest.raises(third_party.ThirdPartyError, match="ngoài danh sách cho phép"):
        third_party.resolve_license("demo", reported)


def test_verified_license_replaces_reported_one(monkeypatch):
    monkeypatch.setitem(third_party.VERIFIED_LICENSES, "demo", "BSD-3-Clause")

    assert third_party.resolve_license("demo", "BSD License") == "BSD-3-Clause"


def test_table_lists_every_locked_package():
    table = third_party.build_table()

    locked = third_party.read_lock(third_party.LOCK_FILE)
    assert locked
    for name, version in locked.items():
        assert f"| {name} | {version} |" in table


def test_empty_lock_gives_table_without_rows(tmp_path):
    assert third_party.build_table(write_lock(tmp_path, "")) == third_party.HEADER


def test_lock_that_differs_from_environment_is_rejected(tmp_path):
    lock_file = write_lock(tmp_path, "click==0.0.1\n")

    with pytest.raises(third_party.ThirdPartyError, match=r"lock file ghi 0\.0\.1"):
        third_party.build_table(lock_file)


def test_package_that_is_not_installed_is_rejected(tmp_path):
    lock_file = write_lock(tmp_path, "khong-co-goi-nay==1.0\n")

    with pytest.raises(third_party.ThirdPartyError, match="chưa cài"):
        third_party.build_table(lock_file)


def test_generated_table_passes_check(table_file):
    assert third_party.main([]) == 0
    assert third_party.main(["--check"]) == 0


def test_check_fails_when_table_differs(table_file, capsys):
    table_file.write_text("bảng cũ\n", encoding="utf-8")

    assert third_party.main(["--check"]) == 1
    assert "không khớp với lock file" in capsys.readouterr().err
    assert table_file.read_text(encoding="utf-8") == "bảng cũ\n"


def test_check_fails_on_unknown_license(monkeypatch, table_file, capsys):
    monkeypatch.setattr(third_party, "ALLOWED_LICENSES", set())

    assert third_party.main(["--check"]) == 1
    assert "ngoài danh sách cho phép" in capsys.readouterr().err
    assert not table_file.exists()
