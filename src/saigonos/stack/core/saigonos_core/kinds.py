# SPDX-License-Identifier: Apache-2.0
import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath

HEADER_SIZE = 8192
MAX_NAME_LENGTH = 255
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TEXT = re.compile(rb"[^\x00]*\Z")
ZIP = re.compile(rb"PK\x03\x04")
FORBIDDEN_CATEGORIES = {"Zl", "Zp"}
FORBIDDEN_CHARACTERS = {"/", "\\"}


@dataclass(frozen=True)
class Kind:
    extensions: tuple[str, ...]
    header: re.Pattern[bytes]

    def matches(self, header: bytes) -> bool:
        return self.header.match(header) is not None


KINDS = {
    "application/pdf": Kind((".pdf",), re.compile(rb"%PDF-")),
    "image/jpeg": Kind((".jpg", ".jpeg"), re.compile(rb"\xff\xd8\xff")),
    "image/png": Kind((".png",), re.compile(rb"\x89PNG\r\n\x1a\n")),
    "image/webp": Kind((".webp",), re.compile(rb"RIFF.{4}WEBP", re.DOTALL)),
    "text/plain": Kind((".txt",), TEXT),
    "text/csv": Kind((".csv",), TEXT),
    DOCX: Kind((".docx",), ZIP),
    XLSX: Kind((".xlsx",), ZIP),
}


def forbidden(character: str) -> bool:
    category = unicodedata.category(character)
    return (
        character in FORBIDDEN_CHARACTERS
        or category.startswith("C")
        or category in FORBIDDEN_CATEGORIES
    )


def checked_name(name: str, type: str) -> str:
    name = unicodedata.normalize("NFC", name)
    if not name:
        raise ValueError("Tên file không được để trống")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"Tên file dài quá {MAX_NAME_LENGTH} ký tự")
    if any(forbidden(character) for character in name):
        raise ValueError("Tên file chứa ký tự điều khiển, dấu / hoặc dấu \\")
    extensions = KINDS[type].extensions
    if PurePosixPath(name).suffix.lower() not in extensions:
        raise ValueError(
            f"Tên file có loại {type} phải có phần mở rộng {' hoặc '.join(extensions)}"
        )
    return name
