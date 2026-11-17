# SPDX-License-Identifier: Apache-2.0
import socket
import struct
from dataclasses import dataclass
from typing import BinaryIO

CHUNK_SIZE = 64 * 1024
TIMEOUT = 180
CLEAN = "stream: OK"
PREFIX = "stream: "
SUFFIX = " FOUND"
END = struct.pack(">I", 0)


class ClamAVUnavailableError(Exception):
    pass


class ScanError(Exception):
    pass


def receive(connection: socket.socket) -> str:
    reply = bytearray()
    while not reply.endswith(b"\0"):
        chunk = connection.recv(4096)
        if not chunk:
            raise ClamAVUnavailableError("ClamAV đóng kết nối mà không trả lời")
        reply += chunk
    return reply[:-1].decode(errors="replace")


@dataclass(frozen=True)
class ClamAV:
    host: str
    port: int
    timeout: float = TIMEOUT

    def ping(self) -> None:
        reply = self.send(b"zPING\0")
        if reply != "PONG":
            raise ClamAVUnavailableError(f"ClamAV trả lời {reply} cho lệnh PING")

    def scan(self, content: BinaryIO) -> str | None:
        reply = self.send(b"zINSTREAM\0", content)
        if reply == CLEAN:
            return None
        if reply.startswith(PREFIX) and reply.endswith(SUFFIX):
            return reply.removeprefix(PREFIX).removesuffix(SUFFIX)
        raise ScanError(f"ClamAV không quét được nội dung: {reply}")

    def send(self, command: bytes, content: BinaryIO | None = None) -> str:
        try:
            with socket.create_connection((self.host, self.port), self.timeout) as connection:
                connection.sendall(command)
                if content is not None:
                    while chunk := content.read(CHUNK_SIZE):
                        connection.sendall(struct.pack(">I", len(chunk)) + chunk)
                    connection.sendall(END)
                return receive(connection)
        except OSError as error:
            raise ClamAVUnavailableError(f"Không kết nối được ClamAV: {error}") from error
