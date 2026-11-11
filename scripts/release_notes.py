# SPDX-License-Identifier: Apache-2.0
import argparse
import re
import sys
import tomllib
from pathlib import Path

from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parent.parent
PROJECT_FILE = ROOT / "pyproject.toml"
CHANGELOG_FILE = ROOT / "CHANGELOG.md"

HEADING = re.compile(r"## \[([^\]]+)\]")
LINK_DEFINITION = re.compile(r"\[[^\]]+\]: \S+$")


class ReleaseError(Exception):
    pass


def parse_version(text: str) -> Version | None:
    try:
        return Version(text)
    except InvalidVersion:
        return None


def project_version() -> Version:
    with PROJECT_FILE.open("rb") as file:
        return Version(tomllib.load(file)["project"]["version"])


def released_versions(changelog: str) -> list[Version]:
    headings = (HEADING.match(line) for line in changelog.splitlines())
    versions = (parse_version(heading[1]) for heading in headings if heading)
    return [version for version in versions if version]


def find_notes(changelog: str, version: Version) -> str:
    notes: list[str] | None = None
    for line in changelog.splitlines():
        heading = HEADING.match(line)
        if heading and notes is not None:
            break
        if heading and parse_version(heading[1]) == version:
            notes = []
        elif notes is not None and not LINK_DEFINITION.match(line):
            notes.append(line)
    if notes is None:
        raise ReleaseError(f"CHANGELOG.md chưa có mục cho phiên bản {version}.")
    return "\n".join(notes).strip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="In release notes của một tag phiên bản.")
    parser.add_argument("tag", help="tag phiên bản, ví dụ v0.1.0")
    tag = parser.parse_args(argv).tag
    try:
        version = parse_version(tag)
        if version is None:
            raise ReleaseError(f"Tag {tag} không phải là số phiên bản hợp lệ.")
        if version != project_version():
            raise ReleaseError(
                f"Tag {tag} không khớp với phiên bản {project_version()} trong pyproject.toml."
            )
        notes = find_notes(CHANGELOG_FILE.read_text(encoding="utf-8"), version)
    except ReleaseError as error:
        print(error, file=sys.stderr)
        return 1
    sys.stdout.write(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
