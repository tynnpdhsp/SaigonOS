# SPDX-License-Identifier: Apache-2.0
import base64
import json
import secrets
from collections.abc import Callable
from http.client import HTTPConnection, HTTPException
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from saigonos_core.app_database import ApplyError
from saigonos_core.bpmn import bpmn_files
from saigonos_core.manifest import Manifest
from saigonos_core.operaton import USER, message_of

TIMEOUT = 30
SOURCE = "app:{name}"
DEPLOYED = "Đã triển khai file {file}: quy trình {key}, phiên bản {version}."
SUSPENDED = "Đã tạm dừng quy trình {key} trên Operaton."
ACTIVATED = "Đã chạy lại quy trình {key} trên Operaton."
DELETED = "Đã xóa {count} bản triển khai của ứng dụng trên Operaton."
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
    return changed


def listed(operaton: Operaton, path: str, app: str) -> list[dict[str, Any]]:
    status, data = operaton.call("GET", f"{path}?{urlencode({'tenantIdIn': app})}")
    if status != 200 or not isinstance(data, list):
        raise failure(f"Operaton trả về mã {status} cho lời gọi GET {path}", data)
    return [item for item in data if item.get("tenantId") == app]


def set_suspended(
    operaton: Operaton, app: str, suspended: bool, say: Callable[[str], None]
) -> bool:
    keys = set()
    for definition in listed(operaton, "/process-definition", app):
        if definition["suspended"] == suspended:
            continue
        body = json.dumps({"suspended": suspended, "includeProcessInstances": True}).encode()
        path = f"/process-definition/{quote(definition['id'], safe=':')}/suspended"
        status, data = operaton.call("PUT", path, body, "application/json")
        if status != 204:
            raise failure(
                f"Operaton không đổi được trạng thái của quy trình {definition['key']}", data
            )
        keys.add(definition["key"])
    for key in sorted(keys):
        say((SUSPENDED if suspended else ACTIVATED).format(key=key))
    return bool(keys)


def suspend_processes(operaton: Operaton, app: str, say: Callable[[str], None]) -> bool:
    return set_suspended(operaton, app, True, say)


def activate_processes(operaton: Operaton, app: str, say: Callable[[str], None]) -> bool:
    return set_suspended(operaton, app, False, say)


def delete_processes(operaton: Operaton, app: str, say: Callable[[str], None]) -> bool:
    deployments = listed(operaton, "/deployment", app)
    for deployment in deployments:
        path = f"/deployment/{quote(deployment['id'], safe='')}?cascade=true"
        status, data = operaton.call("DELETE", path)
        if status not in (204, 404):
            raise failure(f"Operaton không xóa được bản triển khai {deployment['name']}", data)
    if deployments:
        say(DELETED.format(count=len(deployments)))
    return bool(deployments)
