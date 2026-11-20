# SPDX-License-Identifier: Apache-2.0
import socket
import struct
from contextlib import suppress

NAME_ERROR = 3


def answer(query):
    ident, flags = struct.unpack(">HH", query[:4])
    end = 12
    while query[end]:
        end += query[end] + 1
    flags = 0x8000 | (flags & 0x7900) | 0x0080 | NAME_ERROR
    return struct.pack(">HHHHHH", ident, flags, 1, 0, 0, 0) + query[12 : end + 5]


server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server.bind(("", 53))
while True:
    query, sender = server.recvfrom(4096)
    with suppress(IndexError, struct.error):
        server.sendto(answer(query), sender)
