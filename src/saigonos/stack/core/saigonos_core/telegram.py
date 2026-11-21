# SPDX-License-Identifier: Apache-2.0
import json
import re
import ssl
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from typing import Any
from urllib.parse import urlsplit

from saigonos_core.outcome import FAILED, RETRY, SENT, UNKNOWN, WAIT, Outcome, describe

DEFAULT_API_URL = "https://api.telegram.org"
TIMEOUT = 10
TOKEN = re.compile(r"[0-9]+:[A-Za-z0-9_-]+")
CHAT = re.compile(r"-?[0-9]+|@[A-Za-z0-9_]+")
TOPIC = re.compile(r"[1-9][0-9]{0,15}")


class TelegramSettingsError(Exception):
    pass


def utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def message_of(title: str, body: str | None, link: str | None, site_url: str) -> dict[str, Any]:
    heading = title.strip()
    lines = [heading]
    if body and body.strip():
        lines.append(body.strip())
    if link:
        lines.append(site_url + link)
    return {
        "text": "\n".join(lines),
        "entities": [{"type": "bold", "offset": 0, "length": utf16_length(heading)}],
        "link_preview_options": {"is_disabled": True},
    }


def number(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def outcome_of(status: int, content: bytes) -> Outcome:
    try:
        data = json.loads(content)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        data = {}
    description = data.get("description")
    detail = f"Telegram trả về mã {status}"
    if isinstance(description, str) and description:
        detail += f": {description}"
    if 200 <= status < 300:
        result = data.get("result")
        if data.get("ok") is True and isinstance(result, dict):
            return Outcome(SENT, str(result.get("message_id", "")))
        return Outcome(UNKNOWN, f"{detail} nhưng nội dung trả về không cho biết tin đã được gửi")
    parameters = data.get("parameters")
    if not isinstance(parameters, dict):
        parameters = {}
    if status == 429:
        retry_after = number(parameters.get("retry_after"))
        if retry_after is not None and retry_after >= 0:
            return Outcome(WAIT, detail, retry_after)
        return Outcome(RETRY, detail)
    if status >= 500:
        return Outcome(RETRY, detail)
    if status >= 400:
        moved = number(parameters.get("migrate_to_chat_id"))
        if moved is not None:
            detail += (
                f". Nhóm đã được chuyển thành supergroup. Hãy đổi TELEGRAM_CHAT_ID thành {moved}"
            )
        return Outcome(FAILED, detail)
    return Outcome(UNKNOWN, detail)


class Telegram:
    def __init__(
        self,
        api_url: str,
        token: str,
        chat_id: str,
        topic_id: int | None = None,
        timeout: float = TIMEOUT,
    ) -> None:
        parts = urlsplit(api_url)
        self.secure = parts.scheme == "https"
        self.host = parts.hostname or ""
        self.port = parts.port
        self.path = f"{parts.path.rstrip('/')}/bot{token}/sendMessage"
        self.chat_id: int | str = int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id
        self.topic_id = topic_id
        self.timeout = timeout

    def connection(self) -> HTTPConnection:
        if self.secure:
            context = ssl.create_default_context()
            return HTTPSConnection(self.host, self.port, timeout=self.timeout, context=context)
        return HTTPConnection(self.host, self.port, timeout=self.timeout)

    def send(self, message: dict[str, Any]) -> Outcome:
        body = {"chat_id": self.chat_id, **message}
        if self.topic_id is not None:
            body["message_thread_id"] = self.topic_id
        payload = json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
        connection = self.connection()
        try:
            try:
                connection.connect()
                connection.request("POST", self.path, body=payload, headers=headers)
            except (OSError, HTTPException) as error:
                return Outcome(RETRY, f"Không gửi được lời gọi tới Telegram: {describe(error)}")
            try:
                response = connection.getresponse()
                content = response.read()
            except (OSError, HTTPException) as error:
                return Outcome(UNKNOWN, f"Mất kết nối khi chờ Telegram trả lời: {describe(error)}")
        finally:
            connection.close()
        return outcome_of(response.status, content)


def configured(api_url: str, token: str, chat_id: str, topic_id: str) -> Telegram | None:
    if not (token or chat_id or topic_id):
        return None
    if not token:
        raise TelegramSettingsError("thiếu TELEGRAM_BOT_TOKEN")
    if not chat_id:
        raise TelegramSettingsError("thiếu TELEGRAM_CHAT_ID")
    if not TOKEN.fullmatch(token):
        raise TelegramSettingsError(
            "TELEGRAM_BOT_TOKEN không có dạng <số>:<chuỗi> như token do BotFather cấp"
        )
    if not CHAT.fullmatch(chat_id):
        raise TelegramSettingsError(
            "TELEGRAM_CHAT_ID phải là mã nhóm dạng số, ví dụ -1001234567890, "
            "hoặc tên nhóm dạng @ten_nhom"
        )
    if topic_id and not TOPIC.fullmatch(topic_id):
        raise TelegramSettingsError("TELEGRAM_TOPIC_ID phải là số nguyên dương")
    try:
        parts = urlsplit(api_url)
        valid = parts.scheme in ("http", "https") and bool(parts.hostname)
        valid = valid and parts.port != 0 and not (parts.query or parts.fragment)
        valid = valid and re.fullmatch(r"[!-~]+", api_url) is not None
    except ValueError:
        valid = False
    if not valid:
        raise TelegramSettingsError("TELEGRAM_API_URL phải có dạng https://tên-máy")
    return Telegram(api_url, token, chat_id, int(topic_id) if topic_id else None)
