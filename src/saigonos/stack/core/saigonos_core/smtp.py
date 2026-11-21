# SPDX-License-Identifier: Apache-2.0
import ipaddress
import re
import smtplib
import ssl
from contextlib import suppress
from datetime import UTC, datetime
from email.headerregistry import Address
from email.message import EmailMessage
from email.policy import SMTP as SMTP_POLICY
from email.utils import format_datetime, make_msgid

from saigonos_core.outcome import FAILED, RETRY, SENT, UNKNOWN, Outcome, describe

TIMEOUT = 10
STARTTLS = "starttls"
TLS = "tls"
NONE = "none"
PORTS = {STARTTLS: 587, TLS: 465, NONE: 25}
ADDRESS = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*"
)
HOST = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
POLICY = SMTP_POLICY.clone(cte_type="7bit")


class SmtpSettingsError(Exception):
    pass


def is_address(value: str) -> bool:
    return len(value) <= 254 and ADDRESS.fullmatch(value) is not None


def message_of(
    address: str, title: str, body: str | None, link: str | None, site_url: str
) -> EmailMessage:
    message = EmailMessage(policy=POLICY)
    message["To"] = address
    message["Subject"] = title.strip()
    parts = [body.strip() if body and body.strip() else title.strip()]
    if link:
        parts.append(site_url + link)
    message.set_content("\n\n".join(parts))
    return message


def payload_of(message: EmailMessage) -> bytes:
    data = re.sub(rb"(?m)^\.", b"..", message.as_bytes(policy=POLICY))
    if not data.endswith(b"\r\n"):
        data += b"\r\n"
    return data + b".\r\n"


def text_of(reply: bytes | str) -> str:
    text = reply.decode("utf-8", "replace") if isinstance(reply, bytes) else reply
    return " ".join(text.split())


def replied(code: int, reply: bytes | str, step: str) -> Outcome:
    detail = f"Máy chủ SMTP trả về mã {code} {step}: {text_of(reply)}"
    return Outcome(FAILED if 500 <= code < 600 else RETRY, detail)


class Smtp:
    def __init__(
        self,
        host: str,
        port: int,
        security: str,
        username: str,
        password: str,
        sender: str,
        name: str = "",
        timeout: float = TIMEOUT,
        context: ssl.SSLContext | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.security = security
        self.username = username
        self.password = password
        self.sender = sender
        self.name = name
        self.timeout = timeout
        self.context = context

    def tls_context(self) -> ssl.SSLContext:
        return self.context or ssl.create_default_context()

    def connect(self) -> smtplib.SMTP:
        if self.security == TLS:
            return smtplib.SMTP_SSL(
                self.host, self.port, timeout=self.timeout, context=self.tls_context()
            )
        return smtplib.SMTP(self.host, self.port, timeout=self.timeout)

    def send(self, message: EmailMessage) -> Outcome:
        message_id = make_msgid(domain=self.sender.rpartition("@")[2])
        message["From"] = Address(self.name, addr_spec=self.sender) if self.name else self.sender
        message["Date"] = format_datetime(datetime.now(UTC))
        message["Message-ID"] = message_id
        message["Auto-Submitted"] = "auto-generated"
        payload = payload_of(message)
        try:
            client = self.connect()
        except smtplib.SMTPConnectError as error:
            return replied(error.smtp_code, error.smtp_error, "khi kết nối")
        except (OSError, smtplib.SMTPException) as error:
            return Outcome(RETRY, f"Không kết nối được máy chủ SMTP: {describe(error)}")
        try:
            outcome = self.deliver(client, message["To"].addresses[0].addr_spec, payload)
        finally:
            client.close()
        return Outcome(SENT, message_id) if outcome is None else outcome

    def deliver(self, client: smtplib.SMTP, recipient: str, payload: bytes) -> Outcome | None:
        command = "EHLO"
        try:
            client.ehlo_or_helo_if_needed()
            if self.security == STARTTLS:
                command = "STARTTLS"
                client.starttls(context=self.tls_context())
                command = "EHLO"
                client.ehlo_or_helo_if_needed()
            if self.username:
                command = "AUTH"
                client.login(self.username, self.password)
            command = "MAIL FROM"
            code, reply = client.mail(self.sender)
            if code != 250:
                return replied(code, reply, f"cho lệnh {command}")
            command = "RCPT TO"
            code, reply = client.rcpt(recipient)
            if code not in (250, 251):
                return replied(code, reply, f"cho lệnh {command}")
            command = "DATA"
            code, reply = client.docmd(command)
            if code != 354:
                return replied(code, reply, f"cho lệnh {command}")
        except smtplib.SMTPNotSupportedError:
            missing = "STARTTLS" if command == "STARTTLS" else "đăng nhập (AUTH)"
            return Outcome(FAILED, f"Máy chủ SMTP không hỗ trợ {missing}")
        except smtplib.SMTPResponseException as error:
            return replied(error.smtp_code, error.smtp_error, f"cho lệnh {command}")
        except smtplib.SMTPServerDisconnected as error:
            return Outcome(
                RETRY, f"Mất kết nối với máy chủ SMTP ở lệnh {command}: {describe(error)}"
            )
        except smtplib.SMTPException as error:
            return Outcome(FAILED, f"Lỗi ở lệnh {command}: {describe(error)}")
        except OSError as error:
            return Outcome(
                RETRY, f"Lỗi kết nối với máy chủ SMTP ở lệnh {command}: {describe(error)}"
            )
        try:
            client.send(payload)
        except smtplib.SMTPServerDisconnected as error:
            return Outcome(RETRY, f"Mất kết nối khi gửi nội dung email: {describe(error)}")
        try:
            code, reply = client.getreply()
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPResponseException) as error:
            return Outcome(UNKNOWN, f"Mất kết nối khi chờ máy chủ SMTP trả lời: {describe(error)}")
        if 200 <= code < 300:
            with suppress(OSError, smtplib.SMTPException):
                client.quit()
            return None
        if 400 <= code < 600:
            return replied(code, reply, "sau khi nhận nội dung email")
        return Outcome(UNKNOWN, "Máy chủ SMTP trả lời không đúng dạng sau khi nhận nội dung email")


def port_of(value: str, security: str) -> int:
    if not value:
        return PORTS[security]
    if not value.isdigit() or not 1 <= int(value) <= 65535:
        raise SmtpSettingsError("SMTP_PORT phải là số từ 1 đến 65535")
    return int(value)


def host_of(value: str) -> str:
    if HOST.fullmatch(value):
        return value
    with suppress(ValueError):
        return str(ipaddress.IPv6Address(value))
    raise SmtpSettingsError(
        "SMTP_HOST chỉ gồm tên hoặc địa chỉ IP của máy chủ SMTP, ví dụ smtp.gmail.com. "
        "Cổng được đặt bằng SMTP_PORT"
    )


def configured(
    host: str,
    port: str,
    security: str,
    username: str,
    password: str,
    sender: str,
    name: str,
) -> Smtp | None:
    if not any((host, port, security, username, password, sender, name)):
        return None
    if not host:
        raise SmtpSettingsError("thiếu SMTP_HOST")
    if not sender:
        raise SmtpSettingsError("thiếu SMTP_FROM")
    if not security:
        security = TLS if port == str(PORTS[TLS]) else STARTTLS
    if security not in PORTS:
        raise SmtpSettingsError("SMTP_SECURITY phải là starttls, tls hoặc none")
    number = port_of(port, security)
    if not is_address(sender):
        raise SmtpSettingsError("SMTP_FROM phải là một địa chỉ email, ví dụ thong-bao@example.com")
    if CONTROL.search(name):
        raise SmtpSettingsError("SMTP_FROM_NAME không được chứa ký tự điều khiển")
    if username and not password:
        raise SmtpSettingsError("thiếu SMTP_PASSWORD")
    if password and not username:
        raise SmtpSettingsError("thiếu SMTP_USERNAME")
    if password and security == NONE:
        raise SmtpSettingsError(
            "mật khẩu không được gửi khi SMTP_SECURITY là none. Hãy dùng starttls hoặc tls"
        )
    return Smtp(host_of(host), number, security, username, password, sender, name)
