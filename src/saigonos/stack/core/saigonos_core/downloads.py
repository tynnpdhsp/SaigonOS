# SPDX-License-Identifier: Apache-2.0
import hashlib
import hmac
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import quote, urlencode
from uuid import UUID

LIFETIME = 60
LETTERS = str.maketrans({"đ": "d", "Đ": "D"})
UNSAFE = {'"', "\\"}


class InvalidLinkError(Exception):
    pass


class ExpiredLinkError(Exception):
    pass


@dataclass(frozen=True)
class DownloadLinks:
    key: str = field(repr=False)
    lifetime: int = LIFETIME
    clock: Callable[[], float] = field(default=time.time, compare=False)

    def signature(self, file_id: UUID, expires: str) -> str:
        message = f"{file_id}:{expires}".encode()
        return hmac.new(self.key.encode(), message, hashlib.sha256).hexdigest()

    def query(self, file_id: UUID) -> tuple[str, int]:
        expires = int(self.clock()) + self.lifetime
        signature = self.signature(file_id, str(expires))
        return urlencode({"expires": expires, "signature": signature}), expires

    def check(self, file_id: UUID, expires: str, signature: str) -> None:
        expected = self.signature(file_id, expires)
        if not hmac.compare_digest(signature.encode(), expected.encode()):
            raise InvalidLinkError
        if self.clock() > int(expires):
            raise ExpiredLinkError


def ascii_name(name: str) -> str:
    letters = unicodedata.normalize("NFKD", name.translate(LETTERS))
    kept = (character for character in letters if not unicodedata.combining(character))
    return "".join(
        character if character.isascii() and character not in UNSAFE else "_" for character in kept
    )


def attachment(name: str) -> str:
    return f"attachment; filename=\"{ascii_name(name)}\"; filename*=UTF-8''{quote(name, safe='')}"
