# SPDX-License-Identifier: Apache-2.0
import pytest
import release_notes
from packaging.version import Version

CHANGELOG = """\
# Nhật ký thay đổi

## [Chưa phát hành]

### Thêm

- Việc đang làm.

## [0.2.0] - 2026-11-18

### Thêm

- Lưu trữ file.

### Sửa

- Lỗi đăng nhập.

## [0.1.0] - 2026-11-13

### Thêm

- Cổng API.

[Chưa phát hành]: https://example.org/compare/v0.2.0...HEAD
[0.2.0]: https://example.org/releases/tag/v0.2.0
[0.1.0]: https://example.org/releases/tag/v0.1.0
"""


@pytest.fixture
def project(monkeypatch, tmp_path):
    def write(version, changelog=CHANGELOG):
        project_file = tmp_path / "pyproject.toml"
        project_file.write_text(f'[project]\nversion = "{version}"\n', encoding="utf-8")
        changelog_file = tmp_path / "CHANGELOG.md"
        changelog_file.write_text(changelog, encoding="utf-8")
        monkeypatch.setattr(release_notes, "PROJECT_FILE", project_file)
        monkeypatch.setattr(release_notes, "CHANGELOG_FILE", changelog_file)

    return write


def test_released_versions_skip_unreleased_section():
    assert release_notes.released_versions(CHANGELOG) == [Version("0.2.0"), Version("0.1.0")]


def test_notes_stop_at_next_version():
    notes = release_notes.find_notes(CHANGELOG, Version("0.2.0"))

    assert notes == "### Thêm\n\n- Lưu trữ file.\n\n### Sửa\n\n- Lỗi đăng nhập.\n"


def test_notes_of_last_section_leave_out_link_definitions():
    assert release_notes.find_notes(CHANGELOG, Version("0.1.0")) == "### Thêm\n\n- Cổng API.\n"


def test_version_without_section_is_rejected():
    with pytest.raises(release_notes.ReleaseError, match=r"chưa có mục cho phiên bản 0\.3\.0"):
        release_notes.find_notes(CHANGELOG, Version("0.3.0"))


def test_matching_tag_prints_notes(project, capsys):
    project("0.2.0")

    assert release_notes.main(["v0.2.0"]) == 0
    assert capsys.readouterr().out.startswith("### Thêm\n\n- Lưu trữ file.")


def test_prerelease_tag_matches_normalized_version(project, capsys):
    project("1.0.0rc1", CHANGELOG.replace("[0.2.0]", "[1.0.0-rc.1]"))

    assert release_notes.main(["v1.0.0-rc.1"]) == 0
    assert capsys.readouterr().out.startswith("### Thêm\n\n- Lưu trữ file.")


@pytest.mark.parametrize(
    ("version", "tag", "message"),
    [
        ("0.2.0", "v0.1.0", "không khớp với phiên bản 0.2.0"),
        ("0.3.0.dev0", "v0.3.0", "không khớp với phiên bản 0.3.0.dev0"),
        ("0.3.0", "v0.3.0", "chưa có mục cho phiên bản 0.3.0"),
        ("0.2.0", "moi-nhat", "không phải là số phiên bản hợp lệ"),
    ],
)
def test_wrong_tag_is_rejected(project, capsys, version, tag, message):
    project(version)

    assert release_notes.main([tag]) == 1
    captured = capsys.readouterr()
    assert message in captured.err
    assert captured.out == ""


def test_changelog_matches_project_version():
    version = release_notes.project_version()
    changelog = release_notes.CHANGELOG_FILE.read_text(encoding="utf-8")
    released = release_notes.released_versions(changelog)

    if version.is_devrelease:
        assert Version(version.base_version) not in released
    else:
        assert released[0] == version
