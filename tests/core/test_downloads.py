# SPDX-License-Identifier: Apache-2.0
from urllib.parse import parse_qs, unquote
from uuid import uuid4

import pytest

from saigonos_core.downloads import (
    LIFETIME,
    DownloadLinks,
    ExpiredLinkError,
    InvalidLinkError,
    attachment,
)

KEY = "khoa-ky-duong-dan"
NOW = 1_763_380_000.0


def links_at(now, key=KEY):
    return DownloadLinks(key, clock=lambda: now)


def issued(file_id, now=NOW):
    query, expires = links_at(now).query(file_id)
    fields = {name: value for name, [value] in parse_qs(query, strict_parsing=True).items()}
    return fields, expires


def flipped(signature):
    return signature[:-1] + ("1" if signature.endswith("0") else "0")


def test_link_lives_at_most_sixty_seconds():
    file_id = uuid4()

    fields, expires = issued(file_id, NOW + 0.9)

    assert LIFETIME == 60
    assert expires == NOW + LIFETIME
    assert fields["expires"] == str(expires)
    assert len(fields["signature"]) == 64


@pytest.mark.parametrize("later", [0, 30, LIFETIME], ids=["ngay", "giua", "giay-cuoi"])
def test_link_signed_by_service_is_accepted_until_it_expires(later):
    file_id = uuid4()
    fields, _ = issued(file_id)

    links_at(NOW + later).check(file_id, fields["expires"], fields["signature"])


@pytest.mark.parametrize("later", [LIFETIME + 0.001, 3600])
def test_link_is_refused_after_it_expires(later):
    file_id = uuid4()
    fields, _ = issued(file_id)

    with pytest.raises(ExpiredLinkError):
        links_at(NOW + later).check(file_id, fields["expires"], fields["signature"])


@pytest.mark.parametrize(
    "change",
    [
        lambda file_id, fields: (uuid4(), fields["expires"], fields["signature"]),
        lambda file_id, fields: (file_id, str(int(fields["expires"]) + 3600), fields["signature"]),
        lambda file_id, fields: (file_id, f"0{fields['expires']}", fields["signature"]),
        lambda file_id, fields: (file_id, fields["expires"], flipped(fields["signature"])),
        lambda file_id, fields: (file_id, fields["expires"], fields["signature"].upper()),
        lambda file_id, fields: (file_id, fields["expires"], ""),
        lambda file_id, fields: (file_id, "", fields["signature"]),
        lambda file_id, fields: (file_id, fields["expires"], "chữ-ký-giả"),
    ],
    ids=[
        "file-khac",
        "keo-dai-han",
        "them-so-0",
        "sua-chu-ky",
        "chu-ky-viet-hoa",
        "thieu-chu-ky",
        "thieu-thoi-han",
        "chu-ky-khong-phai-ascii",
    ],
)
def test_changed_link_is_refused(change):
    file_id = uuid4()
    fields, _ = issued(file_id)

    with pytest.raises(InvalidLinkError):
        links_at(NOW).check(*change(file_id, fields))


def test_link_signed_with_other_key_is_refused():
    file_id = uuid4()
    fields, _ = issued(file_id)

    with pytest.raises(InvalidLinkError):
        links_at(NOW, "khoa-moi").check(file_id, fields["expires"], fields["signature"])


def test_forged_link_is_refused_before_its_expiry_is_read():
    file_id = uuid4()
    fields, _ = issued(file_id)

    with pytest.raises(InvalidLinkError):
        links_at(NOW + 3600).check(file_id, fields["expires"], "0" * 64)


def test_key_is_not_shown_when_links_are_printed():
    assert KEY not in repr(links_at(NOW))


@pytest.mark.parametrize(
    ("name", "fallback"),
    [
        ("bao-cao.pdf", "bao-cao.pdf"),
        ("ảnh máy hỏng.png", "anh may hong.png"),
        ('Đơn "nghỉ phép" đợt 2.docx', "Don _nghi phep_ dot 2.docx"),
        ("报告.pdf", "__.pdf"),
    ],
    ids=["ten-ascii", "ten-tieng-viet", "ten-co-dau-ngoac-kep", "ten-tieng-trung"],
)
def test_attachment_keeps_name_and_gives_ascii_fallback(name, fallback):
    value = attachment(name)

    first, second, third = value.split("; ")
    assert value.isascii()
    assert first == "attachment"
    assert second == f'filename="{fallback}"'
    assert third.startswith("filename*=UTF-8''")
    assert unquote(third.removeprefix("filename*=UTF-8''")) == name


def test_attachment_encodes_separators_inside_name():
    value = attachment("a;b,c d%20.txt")

    assert value.endswith("filename*=UTF-8''a%3Bb%2Cc%20d%2520.txt")
