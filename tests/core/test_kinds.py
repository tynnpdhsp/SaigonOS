# SPDX-License-Identifier: Apache-2.0
import re
import unicodedata

import pytest

from saigonos_core.kinds import DOCX, HEADER_SIZE, KINDS, MAX_NAME_LENGTH, XLSX, checked_name

HEADERS = {
    "application/pdf": b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj",
    "image/jpeg": b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01",
    "image/png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
    "image/webp": b"RIFF\x24\x00\x00\x00WEBPVP8 \x18\x00\x00\x00",
    "text/plain": "Máy 12 phòng I.201 không lên nguồn\n".encode(),
    "text/csv": unicodedata.normalize("NFD", "ma,ten\n1,Phòng I.102\n").encode("cp1258"),
    DOCX: b"PK\x03\x04\x14\x00\x06\x00\x08\x00\x00\x00!\x00",
    XLSX: b"PK\x03\x04\x14\x00\x06\x00\x08\x00\x00\x00!\x00",
}
FOREIGN = {
    "file-chay-windows": b"MZ\x90\x00\x03\x00\x00\x00\x04\x00",
    "file-chay-linux": b"\x7fELF\x02\x01\x01\x00\x00\x00",
    "file-am-thanh-wav": b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00",
    "van-ban-utf-16": "Xin chào".encode("utf-16"),
    "trang-html-co-byte-0": b"<html><script>alert(1)</script>\x00",
}
TEXT_TYPES = {"text/plain", "text/csv"}
ZIP_TYPES = {DOCX, XLSX}


def accepted_by(type):
    shared = next((group for group in [TEXT_TYPES, ZIP_TYPES] if type in group), {type})
    others = {name: header for name, header in HEADERS.items() if name not in shared}
    return [name for name, header in others.items() if KINDS[type].matches(header)]


@pytest.mark.parametrize("type", list(KINDS))
def test_header_of_declared_type_is_accepted(type):
    assert KINDS[type].matches(HEADERS[type])


@pytest.mark.parametrize("type", sorted(set(KINDS) - TEXT_TYPES))
def test_header_of_other_type_is_refused(type):
    assert accepted_by(type) == []


@pytest.mark.parametrize("type", sorted(TEXT_TYPES))
def test_text_accepts_any_header_without_zero_byte(type):
    assert accepted_by(type) == ["application/pdf"]


@pytest.mark.parametrize("type", list(KINDS))
@pytest.mark.parametrize("name", list(FOREIGN))
def test_header_of_program_or_unlisted_format_is_refused(type, name):
    assert not KINDS[type].matches(FOREIGN[name])


def test_text_check_reads_whole_header_sample():
    tail_zero = b"a" * (HEADER_SIZE - 1) + b"\0"

    assert not KINDS["text/plain"].matches(tail_zero)
    assert KINDS["text/plain"].matches(b"a" * HEADER_SIZE)


@pytest.mark.parametrize(
    ("type", "name"),
    [
        ("image/jpeg", "anh-may-hong.jpg"),
        ("image/jpeg", "ANH.JPEG"),
        ("application/pdf", "Biên bản bàn giao.pdf"),
        ("text/plain", "ghi chú.v2.txt"),
        (DOCX, "đơn xin nghỉ phép.docx"),
    ],
    ids=["jpg", "jpeg-viet-hoa", "pdf-ten-co-dau", "txt-nhieu-dau-cham", "docx-ten-co-dau"],
)
def test_name_with_extension_of_its_type_is_accepted(type, name):
    assert checked_name(name, type) == name


def test_name_is_stored_in_composed_form():
    decomposed = "a\u0300nh.png"

    assert checked_name(decomposed, "image/png") == "\u00e0nh.png"


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("", "Tên file không được để trống"),
        ("a" * (MAX_NAME_LENGTH - 3) + ".png", f"Tên file dài quá {MAX_NAME_LENGTH} ký tự"),
        ("anh\n.png", "ký tự điều khiển"),
        ("anh\x00.png", "ký tự điều khiển"),
        ("hoa-don\u202egnp.png", "ký tự điều khiển"),
        ("anh\u2028.png", "ký tự điều khiển"),
        ("thu-muc/anh.png", "dấu /"),
        ("thu-muc\\anh.png", "dấu /"),
        ("anh.png.exe", "phải có phần mở rộng .png"),
        ("anh.jpg", "phải có phần mở rộng .png"),
        ("anh", "phải có phần mở rộng .png"),
        (".png", "phải có phần mở rộng .png"),
        ("anh.png ", "phải có phần mở rộng .png"),
    ],
    ids=[
        "ten-rong",
        "qua-dai",
        "xuong-dong",
        "byte-0",
        "dao-chieu-chu",
        "phan-cach-dong",
        "gach-cheo",
        "gach-cheo-nguoc",
        "them-exe",
        "sai-phan-mo-rong",
        "thieu-phan-mo-rong",
        "chi-co-phan-mo-rong",
        "khoang-trang-cuoi",
    ],
)
def test_name_that_breaks_a_rule_is_refused(name, message):
    with pytest.raises(ValueError, match=re.escape(message)):
        checked_name(name, "image/png")


def test_name_at_length_limit_is_accepted():
    name = "a" * (MAX_NAME_LENGTH - 4) + ".png"

    assert checked_name(name, "image/png") == name


def test_refusal_lists_every_extension_of_type():
    with pytest.raises(ValueError, match=r"phần mở rộng \.jpg hoặc \.jpeg$"):
        checked_name("anh.png", "image/jpeg")
