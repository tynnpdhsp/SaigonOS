# SPDX-License-Identifier: Apache-2.0
import io
import socket
import struct
from threading import Event, Thread

import pytest

from saigonos_core.clamav import CHUNK_SIZE, ClamAV, ClamAVUnavailableError, ScanError

FOUND = b"stream: Eicar-Test-Signature FOUND\0"


class FakeClamd:
    def __init__(self):
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.port = self.listener.getsockname()[1]
        self.replies = {b"zPING": [b"PONG\0"], b"zINSTREAM": [b"stream: OK\0"]}
        self.commands = []
        self.chunks = []
        self.release = Event()
        self.release.set()
        Thread(target=self.serve, daemon=True).start()

    def serve(self):
        while True:
            try:
                connection, _ = self.listener.accept()
            except OSError:
                return
            with connection, connection.makefile("rb") as stream:
                self.answer(connection, stream)

    def answer(self, connection, stream):
        command = bytearray()
        while not command.endswith(b"\0"):
            command += stream.read(1)
        command = bytes(command[:-1])
        self.commands.append(command)
        if command == b"zINSTREAM":
            while size := struct.unpack(">I", stream.read(4))[0]:
                self.chunks.append(stream.read(size))
        self.release.wait()
        for part in self.replies[command]:
            connection.sendall(part)

    def client(self, timeout=5):
        return ClamAV("127.0.0.1", self.port, timeout)

    def close(self):
        self.release.set()
        self.listener.close()


@pytest.fixture
def clamd():
    fake = FakeClamd()
    yield fake
    fake.close()


def test_clean_content_has_no_malware(clamd):
    assert clamd.client().scan(io.BytesIO(b"noi dung binh thuong")) is None
    assert clamd.commands == [b"zINSTREAM"]
    assert clamd.chunks == [b"noi dung binh thuong"]


def test_content_is_sent_in_chunks(clamd):
    content = bytes(range(256)) * (CHUNK_SIZE * 5 // 512)

    clamd.client().scan(io.BytesIO(content))

    assert [len(chunk) for chunk in clamd.chunks] == [CHUNK_SIZE, CHUNK_SIZE, CHUNK_SIZE // 2]
    assert b"".join(clamd.chunks) == content


def test_empty_content_sends_only_end_of_stream(clamd):
    assert clamd.client().scan(io.BytesIO(b"")) is None
    assert clamd.chunks == []


def test_found_reply_gives_malware_name(clamd):
    clamd.replies[b"zINSTREAM"] = [FOUND]

    assert clamd.client().scan(io.BytesIO(b"x")) == "Eicar-Test-Signature"


def test_reply_split_in_parts_is_read_whole(clamd):
    clamd.replies[b"zINSTREAM"] = [FOUND[:10], FOUND[10:]]

    assert clamd.client().scan(io.BytesIO(b"x")) == "Eicar-Test-Signature"


@pytest.mark.parametrize(
    "reply",
    [b"INSTREAM size limit exceeded. ERROR\0", b"stream: Can't allocate memory ERROR\0"],
    ids=["vuot-gioi-han-kich-thuoc", "het-bo-nho"],
)
def test_error_reply_raises_scan_error(clamd, reply):
    clamd.replies[b"zINSTREAM"] = [reply]

    with pytest.raises(ScanError) as raised:
        clamd.client().scan(io.BytesIO(b"x"))

    assert str(raised.value) == f"ClamAV không quét được nội dung: {reply[:-1].decode()}"


def test_connection_closed_without_reply_means_unavailable(clamd):
    clamd.replies[b"zINSTREAM"] = []

    with pytest.raises(ClamAVUnavailableError, match="đóng kết nối"):
        clamd.client().scan(io.BytesIO(b"x"))


def test_slow_reply_means_unavailable(clamd):
    clamd.release.clear()

    with pytest.raises(ClamAVUnavailableError, match="Không kết nối được ClamAV"):
        clamd.client(timeout=0.2).scan(io.BytesIO(b"x"))


def test_refused_connection_means_unavailable():
    with socket.create_server(("127.0.0.1", 0)) as listener:
        port = listener.getsockname()[1]

    with pytest.raises(ClamAVUnavailableError, match="Không kết nối được ClamAV"):
        ClamAV("127.0.0.1", port).ping()


def test_ping_accepts_pong(clamd):
    clamd.client().ping()

    assert clamd.commands == [b"zPING"]


def test_ping_with_other_reply_means_unavailable(clamd):
    clamd.replies[b"zPING"] = [b"UNKNOWN COMMAND\0"]

    with pytest.raises(ClamAVUnavailableError, match="UNKNOWN COMMAND"):
        clamd.client().ping()
