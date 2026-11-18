# SPDX-License-Identifier: Apache-2.0
import base64
import json
import logging
import time
from collections.abc import Callable
from http.client import HTTPConnection, HTTPException
from threading import Lock
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

USER = "core"
TIMEOUT = 30
PAUSE = 60
MAX_REFUSALS = 5

logger = logging.getLogger(__name__)


class OperatonUnavailableError(Exception):
    pass


class OperatonError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Operaton trả về mã {status}: {message}")
        self.status = status


def segment(value: str) -> str:
    return quote(value, safe=":")


def message_of(data: Any) -> str:
    if isinstance(data, dict) and isinstance(data.get("message"), str):
        return data["message"]
    return str(data)


class Operaton:
    def __init__(
        self,
        url: str,
        password: str,
        pause: float = PAUSE,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.url = url
        self.authorization = "Basic " + base64.b64encode(f"{USER}:{password}".encode()).decode()
        self.pause = pause
        self.clock = clock
        self.lock = Lock()
        self.generation = 0
        self.refusals = 0
        self.paused_until: float | None = None

    def latest_definition(self, key: str) -> dict[str, Any] | None:
        status, data = self.call("GET", f"/process-definition/key/{segment(key)}")
        if status == 404:
            return None
        return self.result(status, data)

    def definition_xml(self, definition_id: str) -> str:
        status, data = self.call("GET", f"/process-definition/{segment(definition_id)}/xml")
        return self.result(status, data)["bpmn20Xml"]

    def submit_start_form(
        self, definition_id: str, variables: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        path = f"/process-definition/{segment(definition_id)}/submit-form"
        return self.result(*self.call("POST", path, {"variables": variables}))

    def tasks(self, query: dict[str, Any], offset: int, limit: int) -> list[dict[str, Any]]:
        paging = {"firstResult": offset, "maxResults": limit}
        return self.result(*self.call("POST", "/task", query, paging))

    @staticmethod
    def result(status: int, data: Any) -> Any:
        if status != 200:
            raise OperatonError(status, message_of(data))
        return data

    def call(
        self,
        method: str,
        path: str,
        body: Any = None,
        query: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        generation = self.admit()
        status, data = self.send(method, path, body, query)
        if status == 401:
            self.refused(generation)
            raise OperatonUnavailableError("Operaton từ chối tài khoản core")
        self.accepted(generation)
        return status, data

    def admit(self) -> int:
        with self.lock:
            if self.refusals >= MAX_REFUSALS:
                raise OperatonUnavailableError(
                    "Service core đã ngừng gọi Operaton vì Operaton từ chối tài khoản core"
                )
            if self.paused_until is not None and self.clock() < self.paused_until:
                raise OperatonUnavailableError(
                    "Service core đang tạm ngừng gọi Operaton vì Operaton từ chối tài khoản core"
                )
            return self.generation

    def refused(self, generation: int) -> None:
        with self.lock:
            if generation != self.generation:
                return
            self.generation += 1
            self.refusals += 1
            self.paused_until = self.clock() + self.pause
            refusals = self.refusals
        if refusals >= MAX_REFUSALS:
            logger.error(
                "Operaton từ chối tài khoản core %s lần liên tiếp. "
                "Service core ngừng gọi Operaton cho tới khi khởi động lại. "
                "Hãy khôi phục giá trị đúng của CORE_OPERATON_PASSWORD trong file .env "
                "rồi chạy saigonos up",
                refusals,
            )
        else:
            logger.warning(
                "Operaton từ chối tài khoản core. Service core ngừng gọi Operaton trong %s giây. "
                "Hãy kiểm tra giá trị CORE_OPERATON_PASSWORD trong file .env",
                self.pause,
            )

    def accepted(self, generation: int) -> None:
        with self.lock:
            if generation == self.generation:
                self.refusals = 0

    def send(
        self, method: str, path: str, body: Any, query: dict[str, Any] | None
    ) -> tuple[int, Any]:
        parts = urlsplit(self.url)
        target = parts.path + path + (f"?{urlencode(query)}" if query else "")
        headers = {"Authorization": self.authorization, "Accept": "application/json"}
        payload = None
        if body is not None:
            payload = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        connection = HTTPConnection(parts.hostname or "", parts.port, timeout=TIMEOUT)
        try:
            connection.request(method, target, body=payload, headers=headers)
            response = connection.getresponse()
            content = response.read()
        except (OSError, HTTPException) as error:
            raise OperatonUnavailableError(f"Không kết nối được Operaton: {error}") from error
        finally:
            connection.close()
        try:
            data = json.loads(content) if content else None
        except ValueError:
            data = content.decode(errors="replace")
        return response.status, data
