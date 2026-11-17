# SPDX-License-Identifier: Apache-2.0
import hashlib
import time
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import get_args
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from saigonos_core.downloads import LIFETIME, attachment
from saigonos_core.files import (
    CREATE,
    FIND,
    FIND_OWN,
    FINISH_UPLOAD,
    LOCK_PENDING,
    MB,
    NOT_DOWNLOADABLE,
    SPOOL_SIZE,
    FileInfo,
)
from saigonos_core.kinds import KINDS
from saigonos_core.main import create_app
from saigonos_core.storage import CLEAN, QUARANTINE, StorageError

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
PNG_SIZE = len(PNG)
CALLER = "người gọi"
SERVICE = "core_service"
BACKGROUND = "core_service, không có người gọi"
COLUMNS = [
    "id",
    "name",
    "type",
    "size",
    "sha256",
    "status",
    "malware",
    "created_at",
    "uploaded_at",
    "scanned_at",
]


class FakeConnection:
    def __init__(self, files, caller, kind):
        self.files = files
        self.caller = caller
        self.kind = kind

    async def fetchrow(self, query, *arguments):
        self.files.queries.append((self.kind, query))
        subject = self.caller.claims.get("sub") if self.caller else None
        return self.files.answer(query, arguments, subject, self.kind)


class FakeFiles:
    def __init__(self):
        self.rows = {}
        self.queries = []
        self.taken_by_other = False

    async def open(self):
        pass

    async def close(self):
        pass

    @asynccontextmanager
    async def session(self, caller):
        yield FakeConnection(self, caller, CALLER)

    @asynccontextmanager
    async def service_session(self, caller):
        yield FakeConnection(self, caller, SERVICE)

    @asynccontextmanager
    async def transaction(self):
        yield FakeConnection(self, None, BACKGROUND)

    def answer(self, query, arguments, subject, kind):
        if query == CREATE:
            name, type, size = arguments
            row = {"id": uuid4(), "owner": subject, "name": name, "type": type, "size": size}
            row |= {"sha256": None, "status": "pending_upload", "malware": None}
            row |= {"created_at": datetime.now(UTC), "uploaded_at": None, "scanned_at": None}
            self.rows[row["id"]] = row
            return self.visible(row)
        row = self.rows.get(arguments[0])
        owned_only = kind == CALLER or query in {FIND_OWN, LOCK_PENDING}
        if row is None or (owned_only and row["owner"] != subject):
            return None
        if query == LOCK_PENDING:
            pending = row["status"] == "pending_upload" and not self.taken_by_other
            return {"id": row["id"]} if pending else None
        if query == FINISH_UPLOAD:
            row |= {"status": "pending_scan", "sha256": arguments[1]}
            row["uploaded_at"] = datetime.now(UTC)
        assert query in {FIND, FIND_OWN, FINISH_UPLOAD}
        return self.visible(row)

    @staticmethod
    def visible(row):
        return {name: row[name] for name in COLUMNS}


class FakeStorage:
    def __init__(self):
        self.objects = {}
        self.reads = []
        self.failure = None

    def put(self, bucket, key, body, size, sha256, content_type):
        if self.failure:
            raise self.failure
        self.objects[bucket, key] = (body.read(), size, sha256, content_type)

    def get(self, bucket, key, sink):
        self.reads.append((bucket, key))
        if self.failure:
            raise self.failure
        if (bucket, key) not in self.objects:
            raise StorageError("Kho file trả về mã 404")
        content = self.objects[bucket, key][0]
        sink.write(content)
        return hashlib.sha256(content).hexdigest()


@pytest.fixture
def files():
    return FakeFiles()


@pytest.fixture
def storage():
    return FakeStorage()


@pytest.fixture
def client(settings, files, storage, scans):
    with TestClient(create_app(settings, files, storage, scans)) as client:
        yield client


@pytest.fixture
def owner(realm):
    return {"Authorization": f"Bearer {realm.token()}"}


@pytest.fixture
def stranger(realm):
    return {"Authorization": f"Bearer {realm.token(sub='nguoi-khac')}"}


def declare(client, headers, name="anh-may-hong.png", type="image/png", size=PNG_SIZE):
    return client.post("/files", headers=headers, json={"name": name, "type": type, "size": size})


def declared(client, headers, content=PNG, **fields):
    reply = declare(client, headers, size=len(content), **fields)
    assert reply.status_code == 201, reply.text
    return reply.json()


def upload(client, headers, file, content=PNG):
    return client.put(f"/files/{file['id']}/content", headers=headers, content=content)


def scanned(files, storage, file, status, malware=None):
    files.rows[UUID(file["id"])] |= {
        "status": status,
        "malware": malware,
        "scanned_at": datetime.now(UTC),
    }
    if status == "clean":
        storage.objects[CLEAN, file["id"]] = storage.objects.pop((QUARANTINE, file["id"]))


def clean_file(client, files, storage, headers, content=PNG, **fields):
    file = declared(client, headers, content, **fields)
    assert upload(client, headers, file, content).status_code == 200
    scanned(files, storage, file, "clean")
    return file


def link_for(client, headers, file):
    return client.post(f"/files/{file['id']}/download-url", headers=headers)


def parts_of(url):
    parts = urlsplit(url)
    query = {name: value for name, [value] in parse_qs(parts.query).items()}
    return parts.path.removeprefix("/core"), query


def download(client, url, **changes):
    path, query = parts_of(url)
    return client.get(path, params=query | changes)


def test_declared_file_waits_for_upload_and_belongs_to_caller(client, files, owner, settings):
    reply = declare(client, owner)

    body = reply.json()
    row = files.rows[next(iter(files.rows))]
    assert reply.status_code == 201
    assert body["status"] == "pending_upload"
    assert (body["name"], body["type"], body["size"]) == ("anh-may-hong.png", "image/png", PNG_SIZE)
    assert (body["sha256"], body["uploaded_at"]) == (None, None)
    assert body["upload_url"] == f"{settings.public_url}/files/{row['id']}/content"
    assert row["owner"] == "4f1b0c0e-nguoi-dung"
    assert files.queries == [(SERVICE, CREATE)]


def test_declared_type_is_stored_in_lower_case(client, files, owner):
    body = declared(client, owner, type="IMAGE/PNG")

    assert body["type"] == "image/png"


def test_declared_name_is_stored_in_composed_form(client, owner):
    body = declared(client, owner, name="a\u0300nh.png")

    assert body["name"] == "\u00e0nh.png"


@pytest.mark.parametrize("type", ["application/x-msdownload", "text/html", "image/svg+xml", ""])
def test_type_outside_list_is_refused(client, files, owner, type):
    reply = declare(client, owner, name="a.png", type=type)

    assert reply.status_code == 415
    assert reply.json()["detail"].endswith(f"Các loại file được phép gồm {', '.join(KINDS)}")
    assert files.rows == {}


def test_size_up_to_limit_is_accepted(client, owner, settings):
    reply = declare(client, owner, size=settings.max_file_size * MB)

    assert reply.status_code == 201


def test_size_over_limit_is_refused(client, files, owner, settings):
    reply = declare(client, owner, size=settings.max_file_size * MB + 1)

    assert reply.status_code == 413
    assert reply.json() == {"detail": "File vượt quá dung lượng tối đa 10 MB"}
    assert files.rows == {}


@pytest.mark.parametrize("size", [0, -1])
def test_size_must_be_positive(client, files, owner, size):
    assert declare(client, owner, size=size).status_code == 422
    assert files.rows == {}


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("anh.exe", "Tên file có loại image/png phải có phần mở rộng .png"),
        ("thu-muc/anh.png", "Tên file chứa ký tự điều khiển, dấu / hoặc dấu \\"),
        ("", "Tên file không được để trống"),
    ],
)
def test_name_that_breaks_a_rule_is_refused(client, files, owner, name, message):
    reply = declare(client, owner, name=name)

    assert (reply.status_code, reply.json()) == (422, {"detail": message})
    assert files.rows == {}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/files"),
        ("PUT", "/files/{id}/content"),
        ("GET", "/files/{id}"),
        ("POST", "/files/{id}/download-url"),
    ],
)
def test_file_calls_need_token_of_logged_in_user(client, files, method, path):
    reply = client.request(method, path.format(id=uuid4()))

    assert reply.status_code == 401
    assert files.queries == []


def test_upload_puts_content_in_quarantine_and_waits_for_scan(client, files, storage, owner):
    file = declared(client, owner)

    reply = upload(client, owner, file)

    body = reply.json()
    digest = hashlib.sha256(PNG).hexdigest()
    assert reply.status_code == 200
    assert (body["status"], body["sha256"]) == ("pending_scan", digest)
    assert body["uploaded_at"] is not None
    assert storage.objects == {(QUARANTINE, file["id"]): (PNG, len(PNG), digest, "image/png")}
    assert files.queries[1:] == [
        (SERVICE, FIND_OWN),
        (SERVICE, LOCK_PENDING),
        (SERVICE, FINISH_UPLOAD),
    ]


def test_upload_asks_for_scan_once_content_is_stored(client, scans, owner):
    file = declared(client, owner)

    rejected = upload(client, owner, file, b"\x00" * len(PNG))
    asked_before = scans.notified
    accepted = upload(client, owner, file)

    assert (rejected.status_code, accepted.status_code) == (422, 200)
    assert (asked_before, scans.notified) == (0, 1)


def test_upload_larger_than_memory_buffer_is_kept_whole(client, storage, owner):
    content = PNG + b"\x01" * (SPOOL_SIZE * 2)
    file = declared(client, owner, content=content)

    assert upload(client, owner, file, content).status_code == 200
    assert storage.objects[QUARANTINE, file["id"]][0] == content


@pytest.mark.parametrize("change", [1, -1], ids=["dài hơn", "ngắn hơn"])
def test_content_with_other_size_is_refused(client, files, storage, owner, change):
    content = PNG + b"\x00" * 100
    file = declared(client, owner, content=content)

    reply = upload(client, owner, file, content[:change] if change < 0 else content + b"\x00")

    assert reply.status_code == 422
    assert reply.json() == {
        "detail": f"Dung lượng của nội dung khác dung lượng đã khai báo là {len(content)} byte"
    }
    assert storage.objects == {}
    assert files.rows[next(iter(files.rows))]["status"] == "pending_upload"


@pytest.mark.parametrize(
    "content",
    [b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00\xb8\x00", b"GIF89a" + PNG[6:]],
    ids=["file chạy Windows", "ảnh GIF"],
)
def test_content_of_other_type_is_refused(client, files, storage, owner, content):
    file = declared(client, owner, content=content)

    reply = upload(client, owner, file, content)

    assert (reply.status_code, reply.json()) == (
        422,
        {"detail": "Phần đầu của nội dung không đúng định dạng image/png"},
    )
    assert storage.objects == {}
    assert files.rows[next(iter(files.rows))]["status"] == "pending_upload"


def test_rejected_upload_can_be_sent_again(client, storage, owner):
    file = declared(client, owner)

    first = upload(client, owner, file, b"\x00" * len(PNG))
    second = upload(client, owner, file)

    assert (first.status_code, second.status_code) == (422, 200)
    assert storage.objects[QUARANTINE, file["id"]][0] == PNG


def test_file_of_other_user_cannot_be_uploaded(client, storage, owner, stranger):
    file = declared(client, owner)

    reply = upload(client, stranger, file)

    assert (reply.status_code, reply.json()) == (404, {"detail": "Không tìm thấy file"})
    assert storage.objects == {}


def test_unknown_file_cannot_be_uploaded(client, owner):
    reply = upload(client, owner, {"id": uuid4()})

    assert reply.status_code == 404


def test_uploaded_file_cannot_be_replaced(client, storage, owner):
    file = declared(client, owner)
    upload(client, owner, file)

    reply = upload(client, owner, file, PNG[:-1] + b"X")

    assert (reply.status_code, reply.json()) == (409, {"detail": "File đã được tải lên"})
    assert storage.objects[QUARANTINE, file["id"]][0] == PNG


def test_upload_that_loses_race_writes_nothing(client, files, storage, owner):
    file = declared(client, owner)
    files.taken_by_other = True

    reply = upload(client, owner, file)

    assert reply.status_code == 409
    assert storage.objects == {}


def test_upload_waits_when_storage_is_down(client, files, storage, owner):
    file = declared(client, owner)
    storage.failure = StorageError("Không kết nối được kho file")

    reply = upload(client, owner, file)
    storage.failure = None

    assert (reply.status_code, reply.json()) == (
        503,
        {"detail": "Chưa lưu được file vì kho file chưa sẵn sàng"},
    )
    assert files.rows[next(iter(files.rows))]["status"] == "pending_upload"
    assert upload(client, owner, file).status_code == 200


def test_owner_reads_file_as_caller(client, files, owner):
    file = declared(client, owner)
    upload(client, owner, file)

    reply = client.get(f"/files/{file['id']}", headers=owner)

    assert reply.status_code == 200
    assert reply.json()["status"] == "pending_scan"
    assert files.queries[-1] == (CALLER, FIND)


def test_owner_sees_name_of_malware_found_in_file(client, files, owner):
    file = declared(client, owner)
    upload(client, owner, file)
    scanned_at = datetime.now(UTC)
    files.rows[next(iter(files.rows))] |= {
        "status": "infected",
        "malware": "Eicar-Test-Signature",
        "scanned_at": scanned_at,
    }

    body = client.get(f"/files/{file['id']}", headers=owner).json()

    assert (body["status"], body["malware"]) == ("infected", "Eicar-Test-Signature")
    assert datetime.fromisoformat(body["scanned_at"]) == scanned_at


def test_file_hidden_from_caller_is_not_found(client, owner, stranger):
    file = declared(client, owner)

    reply = client.get(f"/files/{file['id']}", headers=stranger)

    assert (reply.status_code, reply.json()) == (404, {"detail": "Không tìm thấy file"})


def test_owner_gets_download_link_of_clean_file(client, files, storage, owner, settings):
    file = clean_file(client, files, storage, owner)
    before = time.time()

    reply = link_for(client, owner, file)

    body = reply.json()
    _, query = parts_of(body["download_url"])
    expires = datetime.fromisoformat(body["expires_at"]).timestamp()
    assert reply.status_code == 200
    assert body["download_url"].startswith(f"{settings.public_url}/files/{file['id']}/content?")
    assert set(query) == {"expires", "signature"}
    assert int(query["expires"]) == expires
    assert before + LIFETIME - 1 < expires <= time.time() + LIFETIME
    assert files.queries[-1] == (CALLER, FIND)
    assert storage.reads == []


@pytest.mark.parametrize(
    ("status", "message"),
    [
        ("pending_upload", "File chưa có nội dung nên chưa tải về được"),
        ("pending_scan", "File đang chờ quét mã độc nên chưa tải về được"),
        ("infected", "File có mã độc nên không tải về được"),
    ],
)
def test_file_that_is_not_clean_has_no_download_link(
    client, files, storage, owner, status, message
):
    file = declared(client, owner)
    if status != "pending_upload":
        upload(client, owner, file)
    if status == "infected":
        scanned(files, storage, file, "infected", "Eicar-Test-Signature")

    reply = link_for(client, owner, file)

    assert (reply.status_code, reply.json()) == (409, {"detail": message})


def test_every_status_except_clean_has_a_reason_for_no_download():
    statuses = set(get_args(FileInfo.model_fields["status"].annotation))

    assert set(NOT_DOWNLOADABLE) == statuses - {"clean"}


def test_file_hidden_from_caller_has_no_download_link(client, files, storage, owner, stranger):
    file = clean_file(client, files, storage, owner)

    reply = link_for(client, stranger, file)

    assert (reply.status_code, reply.json()) == (404, {"detail": "Không tìm thấy file"})
    assert files.queries[-1] == (CALLER, FIND)


def test_download_link_sends_file_without_token(client, files, storage, owner):
    name = "ảnh máy hỏng.png"
    file = clean_file(client, files, storage, owner, name=name)
    url = link_for(client, owner, file).json()["download_url"]

    reply = download(client, url)

    assert reply.status_code == 200
    assert reply.content == PNG
    assert reply.headers["content-type"] == "image/png"
    assert reply.headers["content-length"] == str(PNG_SIZE)
    assert reply.headers["content-disposition"] == attachment(name)
    assert reply.headers["x-content-type-options"] == "nosniff"
    assert reply.headers["cache-control"] == "no-store"
    assert files.queries[-1] == (BACKGROUND, FIND)
    assert storage.reads == [(CLEAN, file["id"])]


def test_text_file_is_sent_with_declared_type_only(client, files, storage, owner):
    content = "Máy 12 không lên màn hình\n".encode()
    file = clean_file(client, files, storage, owner, content, name="ghi-chu.txt", type="text/plain")
    url = link_for(client, owner, file).json()["download_url"]

    reply = download(client, url)

    assert reply.content == content
    assert reply.headers["content-type"] == "text/plain"


def test_download_link_opens_again_until_it_expires(client, files, storage, owner):
    file = clean_file(client, files, storage, owner)
    link = link_for(client, owner, file).json()
    expires = datetime.fromisoformat(link["expires_at"]).timestamp()
    links = client.app.state.downloads

    first = download(client, link["download_url"])
    client.app.state.downloads = replace(links, clock=lambda: expires)
    last_second = download(client, link["download_url"])
    client.app.state.downloads = replace(links, clock=lambda: expires + 0.001)
    expired = download(client, link["download_url"])

    assert (first.status_code, last_second.status_code) == (200, 200)
    assert (expired.status_code, expired.json()) == (403, {"detail": "Đường dẫn tải về đã hết hạn"})


@pytest.mark.parametrize(
    "changes",
    [
        {"expires": "9999999999"},
        {"signature": "0" * 64},
        {"signature": ""},
        {"expires": "", "signature": ""},
    ],
    ids=["kéo dài hạn", "sửa chữ ký", "thiếu chữ ký", "thiếu cả hai"],
)
def test_changed_download_link_is_refused(client, files, storage, owner, changes):
    file = clean_file(client, files, storage, owner)
    url = link_for(client, owner, file).json()["download_url"]

    reply = download(client, url, **changes)

    assert (reply.status_code, reply.json()) == (403, {"detail": "Đường dẫn tải về không hợp lệ"})
    assert (BACKGROUND, FIND) not in files.queries
    assert storage.reads == []


def test_download_link_of_one_file_does_not_open_another(client, files, storage, owner, stranger):
    mine = clean_file(client, files, storage, stranger)
    other = clean_file(client, files, storage, owner)
    url = link_for(client, stranger, mine).json()["download_url"]

    reply = download(client, url.replace(mine["id"], other["id"]))

    assert (reply.status_code, reply.json()) == (403, {"detail": "Đường dẫn tải về không hợp lệ"})
    assert storage.reads == []


@pytest.mark.parametrize(
    ("status", "message"),
    [
        ("pending_scan", "File đang chờ quét mã độc nên chưa tải về được"),
        ("infected", "File có mã độc nên không tải về được"),
    ],
)
def test_signed_link_of_file_that_is_not_clean_sends_nothing(
    client, files, storage, owner, status, message
):
    file = declared(client, owner)
    upload(client, owner, file)
    if status == "infected":
        scanned(files, storage, file, "infected", "Eicar-Test-Signature")
    query, _ = client.app.state.downloads.query(UUID(file["id"]))

    reply = client.get(f"/files/{file['id']}/content?{query}")

    assert (reply.status_code, reply.json()) == (409, {"detail": message})
    assert storage.reads == []


def test_download_waits_when_storage_is_down(client, files, storage, owner):
    file = clean_file(client, files, storage, owner)
    url = link_for(client, owner, file).json()["download_url"]
    storage.failure = StorageError("Không kết nối được kho file")

    refused = download(client, url)
    storage.failure = None
    accepted = download(client, url)

    assert (refused.status_code, refused.json()) == (
        503,
        {"detail": "Chưa tải được file vì kho file chưa sẵn sàng"},
    )
    assert accepted.status_code == 200


def test_content_that_does_not_match_hash_is_not_sent(client, files, storage, owner, caplog):
    file = clean_file(client, files, storage, owner)
    url = link_for(client, owner, file).json()["download_url"]
    storage.objects[CLEAN, file["id"]] = (PNG[:-1] + b"X", PNG_SIZE, "", "image/png")

    reply = download(client, url)

    assert (reply.status_code, reply.json()) == (
        500,
        {"detail": "Nội dung của file không khớp mã băm đã ghi"},
    )
    assert f"Nội dung của file {file['id']} trong bucket clean không khớp mã băm" in caplog.text


def test_download_larger_than_memory_buffer_is_sent_whole(client, files, storage, owner):
    content = PNG + b"\x01" * (SPOOL_SIZE * 2)
    file = clean_file(client, files, storage, owner, content)
    url = link_for(client, owner, file).json()["download_url"]

    reply = download(client, url)

    assert reply.content == content
    assert reply.headers["content-length"] == str(len(content))


def test_api_document_describes_file_calls(client):
    paths = client.get("/openapi.json").json()["paths"]

    upload_body = paths["/files/{file_id}/content"]["put"]["requestBody"]
    assert set(paths["/files"]["post"]["responses"]) >= {"201", "401", "413", "415", "422"}
    assert set(paths["/files/{file_id}/content"]["put"]["responses"]) >= {"200", "404", "409"}
    assert upload_body["content"] == {
        "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
    }
    assert set(paths["/files/{file_id}"]["get"]["responses"]) >= {"200", "401", "404"}


def test_api_document_describes_download_calls(client):
    paths = client.get("/openapi.json").json()["paths"]

    link = paths["/files/{file_id}/download-url"]["post"]
    sent = paths["/files/{file_id}/content"]["get"]
    assert set(link["responses"]) >= {"200", "401", "404", "409"}
    assert "security" in link
    assert set(sent["responses"]) >= {"200", "403", "404", "409", "500", "503"}
    assert sent["responses"]["200"]["content"] == {
        "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
    }
    assert {parameter["name"] for parameter in sent["parameters"]} == {
        "file_id",
        "expires",
        "signature",
    }
    assert "security" not in sent
