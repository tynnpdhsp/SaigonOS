# SPDX-License-Identifier: Apache-2.0
import hashlib
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from saigonos_core.files import (
    CREATE,
    FIND,
    FIND_OWN,
    FINISH_UPLOAD,
    LOCK_PENDING,
    MB,
    SPOOL_SIZE,
)
from saigonos_core.kinds import KINDS
from saigonos_core.main import create_app
from saigonos_core.storage import QUARANTINE, StorageError

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
PNG_SIZE = len(PNG)
COLUMNS = ["id", "name", "type", "size", "sha256", "status", "created_at", "uploaded_at"]


class FakeConnection:
    def __init__(self, files, caller, kind):
        self.files = files
        self.caller = caller
        self.kind = kind

    async def fetchrow(self, query, *arguments):
        self.files.queries.append((self.kind, query))
        return self.files.answer(query, arguments, self.caller.claims.get("sub"))


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
        yield FakeConnection(self, caller, "người gọi")

    @asynccontextmanager
    async def service_session(self, caller):
        yield FakeConnection(self, caller, "core_service")

    def answer(self, query, arguments, subject):
        if query == CREATE:
            name, type, size = arguments
            row = {"id": uuid4(), "owner": subject, "name": name, "type": type, "size": size}
            row |= {"sha256": None, "status": "pending_upload", "uploaded_at": None}
            row["created_at"] = datetime.now(UTC)
            self.rows[row["id"]] = row
            return self.visible(row)
        row = self.rows.get(arguments[0])
        if row is None or (query != FINISH_UPLOAD and row["owner"] != subject):
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
        self.failure = None

    def put(self, bucket, key, body, size, sha256, content_type):
        if self.failure:
            raise self.failure
        self.objects[bucket, key] = (body.read(), size, sha256, content_type)


@pytest.fixture
def files():
    return FakeFiles()


@pytest.fixture
def storage():
    return FakeStorage()


@pytest.fixture
def client(settings, files, storage):
    with TestClient(create_app(settings, files, storage)) as client:
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
    assert files.queries == [("core_service", CREATE)]


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


@pytest.mark.parametrize("method", ["post", "put", "get"])
def test_file_calls_need_token_of_logged_in_user(client, files, method):
    path = "/files" if method == "post" else f"/files/{uuid4()}"
    path += "/content" if method == "put" else ""

    reply = getattr(client, method)(path)

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
        ("core_service", FIND_OWN),
        ("core_service", LOCK_PENDING),
        ("core_service", FINISH_UPLOAD),
    ]


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
    assert files.queries[-1] == ("người gọi", FIND)


def test_file_hidden_from_caller_is_not_found(client, owner, stranger):
    file = declared(client, owner)

    reply = client.get(f"/files/{file['id']}", headers=stranger)

    assert (reply.status_code, reply.json()) == (404, {"detail": "Không tìm thấy file"})


def test_api_document_describes_file_calls(client):
    paths = client.get("/openapi.json").json()["paths"]

    upload_body = paths["/files/{file_id}/content"]["put"]["requestBody"]
    assert set(paths["/files"]["post"]["responses"]) >= {"201", "401", "413", "415", "422"}
    assert set(paths["/files/{file_id}/content"]["put"]["responses"]) >= {"200", "404", "409"}
    assert upload_body["content"] == {
        "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
    }
    assert set(paths["/files/{file_id}"]["get"]["responses"]) >= {"200", "401", "404"}
