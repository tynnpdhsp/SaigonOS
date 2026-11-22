# SPDX-License-Identifier: Apache-2.0
import base64
import json
import secrets
from collections.abc import Callable
from http.client import HTTPConnection, HTTPException
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from saigonos_core.app_database import ApplyError
from saigonos_core.bpmn import bpmn_files
from saigonos_core.manifest import Manifest
from saigonos_core.operaton import USER, message_of

TIMEOUT = 30
SOURCE = "app:{name}"
DEPLOYED = "Đã triển khai file {file}: quy trình {key}, phiên bản {version}."
UNCHANGED = "Không có thay đổi trên Operaton."
REFUSED = (
    "Operaton từ chối tài khoản core. Hãy kiểm tra giá trị CORE_OPERATON_PASSWORD "
    "trong file .env. Sau mỗi lần đăng nhập sai, Operaton tạm khóa tài khoản này."
)


class Operaton:
    def __init__(self, url: str, password: str, timeout: float = TIMEOUT) -> None:
        parts = urlsplit(url)
        self.host = parts.hostname or ""
        self.port = parts.port
        self.base = parts.path.rstrip("/")
        self.authorization = "Basic " + base64.b64encode(f"{USER}:{password}".encode()).decode()
        self.timeout = timeout

    def call(
        self, method: str, path: str, body: bytes | None = None, content_type: str | None = None
    ) -> tuple[int, Any]:
        headers = {"Accept": "application/json", "Authorization": self.authorization}
        if content_type is not None:
            headers["Content-Type"] = content_type
        connection = HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            connection.request(method, f"{self.base}{path}", body, headers)
            response = connection.getresponse()
            content = response.read()
        except (OSError, HTTPException) as error:
            raise ApplyError(
                f"Không kết nối được REST API của Operaton: {error}. "
                "Hãy khởi động hệ thống bằng lệnh saigonos up rồi chạy lại."
            ) from error
        finally:
            connection.close()
        if response.status == 401:
            raise ApplyError(REFUSED)
        try:
            data = json.loads(content) if content else None
        except ValueError:
            data = content.decode(errors="replace")
        return response.status, data


def failure(text: str, data: Any) -> ApplyError:
    reason = "" if data in (None, "") else message_of(data).strip().rstrip(".")
    return ApplyError(f"{text}: {reason}." if reason else f"{text}.")


def check_operaton(operaton: Operaton) -> None:
    status, data = operaton.call("GET", "/version")
    if status != 200:
        raise failure(f"REST API của Operaton trả về mã {status}", data)


def multipart(fields: dict[str, str], name: str, content: bytes) -> tuple[bytes, str]:
    boundary = f"saigonos-{secrets.token_hex(16)}"
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
        for key, value in fields.items()
    ]
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="data"; filename="{name}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n".encode()
    )
    parts += [content, f"\r\n--{boundary}--\r\n".encode()]
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def deploy(operaton: Operaton, app: str, file: Path) -> list[dict[str, Any]]:
    fields = {
        "deployment-name": file.name,
        "deployment-source": SOURCE.format(name=app),
        "tenant-id": app,
        "enable-duplicate-filtering": "true",
        "deploy-changed-only": "true",
    }
    body, content_type = multipart(fields, file.name, file.read_bytes())
    status, data = operaton.call("POST", "/deployment/create", body, content_type)
    if status != 200:
        raise failure(f"Operaton không triển khai được file {file.name}", data)
    deployed = data.get("deployedProcessDefinitions") if isinstance(data, dict) else None
    if not isinstance(deployed, dict):
        return []
    return sorted(deployed.values(), key=lambda definition: definition["key"])


def apply_processes(
    operaton: Operaton, manifest: Manifest, folder: Path, say: Callable[[str], None]
) -> bool:
    if manifest.processes is None:
        return False
    changed = False
    for file in bpmn_files(folder / manifest.processes):
        for definition in deploy(operaton, manifest.name, file):
            key, version = definition["key"], definition["version"]
            say(DEPLOYED.format(file=file.name, key=key, version=version))
            changed = True
    if not changed:
        say(UNCHANGED)
    return changed
