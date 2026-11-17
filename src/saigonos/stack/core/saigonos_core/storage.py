# SPDX-License-Identifier: Apache-2.0
import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import HTTPConnection, HTTPException
from typing import BinaryIO
from urllib.parse import quote, urlsplit

ALGORITHM = "AWS4-HMAC-SHA256"
REGION = "us-east-1"
SERVICE = "s3"
TIMEOUT = 30
QUARANTINE = "quarantine"


class StorageError(Exception):
    pass


def signing_key(secret_key: str, date: str, region: str, service: str) -> bytes:
    key = f"AWS4{secret_key}".encode()
    for part in (date, region, service, "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    return key


def authorization(
    method: str,
    path: str,
    headers: dict[str, str],
    access_key: str,
    secret_key: str,
    region: str = REGION,
    service: str = SERVICE,
) -> str:
    names = sorted(headers)
    signed_headers = ";".join(names)
    canonical_request = "\n".join(
        [
            method,
            path,
            "",
            "".join(f"{name}:{headers[name]}\n" for name in names),
            signed_headers,
            headers["x-amz-content-sha256"],
        ]
    )
    timestamp = headers["x-amz-date"]
    date = timestamp[:8]
    scope = f"{date}/{region}/{service}/aws4_request"
    digest = hashlib.sha256(canonical_request.encode()).hexdigest()
    text = "\n".join([ALGORITHM, timestamp, scope, digest])
    key = signing_key(secret_key, date, region, service)
    signature = hmac.new(key, text.encode(), hashlib.sha256).hexdigest()
    return (
        f"{ALGORITHM} Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )


@dataclass(frozen=True)
class Storage:
    url: str
    access_key: str
    secret_key: str

    def put(
        self, bucket: str, key: str, body: BinaryIO, size: int, sha256: str, content_type: str
    ) -> None:
        headers = {"Content-Length": str(size), "Content-Type": content_type}
        self.send("PUT", f"/{bucket}/{key}", sha256, body, headers)

    def send(
        self,
        method: str,
        path: str,
        payload_hash: str,
        body: BinaryIO | None = None,
        headers: dict[str, str] | None = None,
    ) -> bytes:
        parts = urlsplit(self.url)
        path = quote(path)
        signed = {
            "host": parts.netloc,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        }
        sent = {
            **(headers or {}),
            **signed,
            "Authorization": authorization(method, path, signed, self.access_key, self.secret_key),
        }
        connection = HTTPConnection(parts.hostname or "", parts.port, timeout=TIMEOUT)
        try:
            connection.request(method, path, body=body, headers=sent)
            response = connection.getresponse()
            content = response.read()
        except (OSError, HTTPException) as error:
            raise StorageError(f"Không kết nối được kho file: {error}") from error
        finally:
            connection.close()
        if response.status != 200:
            raise StorageError(f"Kho file trả về mã {response.status}")
        return content
