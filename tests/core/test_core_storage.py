# SPDX-License-Identifier: Apache-2.0
import hashlib
import io
import re
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from saigonos_core.storage import (
    CHUNK_SIZE,
    CLEAN,
    QUARANTINE,
    Storage,
    StorageError,
    authorization,
    signing_key,
)

EXAMPLE_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
EMPTY_HASH = hashlib.sha256(b"").hexdigest()
TIMESTAMP = re.compile(r"\d{8}T\d{6}Z")
MISSING = b"<Error><Code>NoSuchKey</Code></Error>"


class FakeS3:
    def __init__(self, server):
        self.server = server
        self.url = f"http://127.0.0.1:{server.server_port}"
        self.status = 200
        self.requests = []
        self.objects = {}
        self.cut = 0

    def storage(self):
        return Storage(self.url, "khoa-truy-cap", "khoa-bi-mat")


def signed_by_storage(method, path, headers):
    signed = {
        "host": headers["host"],
        "x-amz-content-sha256": headers["x-amz-content-sha256"],
        "x-amz-date": headers["x-amz-date"],
    }
    return headers["Authorization"] == authorization(
        method, path, signed, "khoa-truy-cap", "khoa-bi-mat"
    )


@pytest.fixture
def s3():
    class Handler(BaseHTTPRequestHandler):
        def do_PUT(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            fake.requests.append((self.command, self.path, dict(self.headers), body))
            self.send_response(fake.status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            fake.requests.append((self.command, self.path, dict(self.headers), b""))
            content = fake.objects.get(self.path)
            status = fake.status if content is not None else 404
            body = content if status == 200 else MISSING
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body[: len(body) - fake.cut])

        def do_DELETE(self):
            fake.requests.append((self.command, self.path, dict(self.headers), b""))
            fake.objects.pop(self.path, None)
            self.send_response(204)
            self.end_headers()

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    fake = FakeS3(server)
    Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    yield fake
    server.shutdown()
    server.server_close()


def test_signing_key_matches_aws_example():
    key = signing_key("wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY", "20120215", "us-east-1", "iam")

    assert key.hex() == "f4780e2d9f65fa895f9c67b32ce1baf0b0d8a43505a000a1a9e090d414db404d"


def test_authorization_matches_aws_example_of_get_object():
    headers = {
        "host": "examplebucket.s3.amazonaws.com",
        "range": "bytes=0-9",
        "x-amz-content-sha256": EMPTY_HASH,
        "x-amz-date": "20130524T000000Z",
    }

    value = authorization(
        "GET", "/test.txt", headers, EXAMPLE_ACCESS_KEY, "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    )

    assert value == (
        "AWS4-HMAC-SHA256 "
        "Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, "
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    )


def test_put_sends_signed_request_with_content_and_its_hash(s3):
    content = b"%PDF-1.7 noi dung"
    digest = hashlib.sha256(content).hexdigest()
    body = io.BytesIO(content)

    s3.storage().put(QUARANTINE, "2f0b1c3e", body, len(content), digest, "application/pdf")

    [(method, path, headers, body)] = s3.requests
    assert (method, path, body) == ("PUT", "/quarantine/2f0b1c3e", content)
    assert headers["host"] == s3.url.removeprefix("http://")
    assert headers["Content-Type"] == "application/pdf"
    assert headers["x-amz-content-sha256"] == digest
    assert TIMESTAMP.fullmatch(headers["x-amz-date"])
    assert signed_by_storage(method, path, headers)


def test_put_fails_when_storage_refuses(s3):
    s3.status = 403
    storage = Storage(s3.url, "khoa-truy-cap", "khoa-sai")

    with pytest.raises(StorageError, match="mã 403"):
        storage.put(QUARANTINE, "a", io.BytesIO(b"x"), 1, hashlib.sha256(b"x").hexdigest(), "t/t")


def test_get_writes_content_to_sink_and_returns_its_hash(s3):
    content = bytes(range(256)) * (CHUNK_SIZE // 64)
    s3.objects["/quarantine/2f0b1c3e"] = content
    sink = io.BytesIO()

    digest = s3.storage().get(QUARANTINE, "2f0b1c3e", sink)

    [(method, path, headers, _)] = s3.requests
    assert (method, path) == ("GET", "/quarantine/2f0b1c3e")
    assert headers["x-amz-content-sha256"] == EMPTY_HASH
    assert signed_by_storage(method, path, headers)
    assert sink.getvalue() == content
    assert digest == hashlib.sha256(content).hexdigest()


@pytest.mark.parametrize("status", [403, 503])
def test_get_writes_nothing_when_storage_refuses(s3, status):
    s3.objects["/quarantine/a"] = b"noi dung"
    s3.status = status
    sink = io.BytesIO()

    with pytest.raises(StorageError, match=f"mã {status}"):
        s3.storage().get(QUARANTINE, "a", sink)

    assert sink.getvalue() == b""


def test_get_fails_when_content_is_cut_short(s3):
    s3.objects["/quarantine/a"] = b"noi dung day du"
    s3.cut = 5

    with pytest.raises(StorageError, match="Kho file chỉ gửi 10 trong 15 byte của nội dung"):
        s3.storage().get(QUARANTINE, "a", io.BytesIO())


def test_get_of_missing_object_fails(s3):
    sink = io.BytesIO()

    with pytest.raises(StorageError, match="mã 404"):
        s3.storage().get(CLEAN, "khong-co", sink)

    assert sink.getvalue() == b""


def test_delete_sends_signed_request_and_accepts_no_content(s3):
    s3.objects["/quarantine/2f0b1c3e"] = b"noi dung"

    s3.storage().delete(QUARANTINE, "2f0b1c3e")

    [(method, path, headers, _)] = s3.requests
    assert (method, path) == ("DELETE", "/quarantine/2f0b1c3e")
    assert headers["x-amz-content-sha256"] == EMPTY_HASH
    assert signed_by_storage(method, path, headers)
    assert s3.objects == {}


def test_put_fails_when_storage_cannot_be_reached():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    storage = Storage(f"http://127.0.0.1:{port}", "khoa-truy-cap", "khoa-bi-mat")

    with pytest.raises(StorageError, match="Không kết nối được kho file"):
        storage.put(QUARANTINE, "a", io.BytesIO(b"x"), 1, hashlib.sha256(b"x").hexdigest(), "t/t")
