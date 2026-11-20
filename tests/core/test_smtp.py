# SPDX-License-Identifier: Apache-2.0
import email
import importlib.util
import smtplib
import socket
import ssl
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.policy import default
from email.utils import parsedate_to_datetime
from pathlib import Path

import pytest

from saigonos_core.outcome import FAILED, RETRY, SENT, UNKNOWN, Outcome
from saigonos_core.smtp import (
    NONE,
    STARTTLS,
    TLS,
    Smtp,
    SmtpSettingsError,
    configured,
    message_of,
    payload_of,
)

USERNAME = "thong-bao@example.com"
PASSWORD = "matkhauungdungthu"
SENDER = "thong-bao@example.com"
NAME = "Phòng Kỹ thuật"
ADDRESS = "nguyen.van.a@example.com"
SITE = "https://dx.example.com"
TITLE = "Đã nhận yêu cầu YC-001"
BODY = "Cảm ơn bạn đã gửi yêu cầu.\nMã tra cứu là YC-001."
LINK = "/tra-cuu/YC-001"
FULL_SESSION = ["EHLO", "STARTTLS", "EHLO", "AUTH", "MAIL", "RCPT", "DATA", "QUIT"]
LOST = "Connection unexpectedly closed"
REPLIES = {
    "chao-421": (
        {"greeting": "421 4.3.2 Service not available"},
        Outcome(RETRY, "Máy chủ SMTP trả về mã 421 khi kết nối: 4.3.2 Service not available"),
    ),
    "chao-554": (
        {"greeting": "554 5.3.2 No SMTP service here"},
        Outcome(FAILED, "Máy chủ SMTP trả về mã 554 khi kết nối: 5.3.2 No SMTP service here"),
    ),
    "starttls-454": (
        {"starttls": "454 4.7.0 TLS not available"},
        Outcome(RETRY, "Máy chủ SMTP trả về mã 454 cho lệnh STARTTLS: 4.7.0 TLS not available"),
    ),
    "auth-454": (
        {"auth": "454 4.7.0 Try again later"},
        Outcome(RETRY, "Máy chủ SMTP trả về mã 454 cho lệnh AUTH: 4.7.0 Try again later"),
    ),
    "mail-451": (
        {"mail": "451 4.3.0 Try again later"},
        Outcome(RETRY, "Máy chủ SMTP trả về mã 451 cho lệnh MAIL FROM: 4.3.0 Try again later"),
    ),
    "mail-553": (
        {"mail": "553 5.7.1 Sender address rejected"},
        Outcome(
            FAILED, "Máy chủ SMTP trả về mã 553 cho lệnh MAIL FROM: 5.7.1 Sender address rejected"
        ),
    ),
    "rcpt-450": (
        {"rcpt": "450 4.2.1 Mailbox busy"},
        Outcome(RETRY, "Máy chủ SMTP trả về mã 450 cho lệnh RCPT TO: 4.2.1 Mailbox busy"),
    ),
    "rcpt-550": (
        {"rcpt": "550 5.1.1 The email account does not exist"},
        Outcome(
            FAILED,
            "Máy chủ SMTP trả về mã 550 cho lệnh RCPT TO: 5.1.1 The email account does not exist",
        ),
    ),
    "data-451": (
        {"data": "451 4.3.0 Try again later"},
        Outcome(RETRY, "Máy chủ SMTP trả về mã 451 cho lệnh DATA: 4.3.0 Try again later"),
    ),
    "data-554": (
        {"data": "554 5.5.1 No valid recipients"},
        Outcome(FAILED, "Máy chủ SMTP trả về mã 554 cho lệnh DATA: 5.5.1 No valid recipients"),
    ),
    "noi-dung-452": (
        {"content": "452 4.3.1 Insufficient system storage"},
        Outcome(
            RETRY,
            "Máy chủ SMTP trả về mã 452 sau khi nhận nội dung email: "
            "4.3.1 Insufficient system storage",
        ),
    ),
    "noi-dung-552": (
        {"content": "552 5.3.4 Message size exceeds fixed limit"},
        Outcome(
            FAILED,
            "Máy chủ SMTP trả về mã 552 sau khi nhận nội dung email: "
            "5.3.4 Message size exceeds fixed limit",
        ),
    ),
    "noi-dung-sai-dang": (
        {"content": "OK"},
        Outcome(UNKNOWN, "Máy chủ SMTP trả lời không đúng dạng sau khi nhận nội dung email"),
    ),
}
DROPS = {
    "khi-chao": (
        {"greeting": "drop"},
        Outcome(RETRY, f"Không kết nối được máy chủ SMTP: {LOST}"),
    ),
    "o-lenh-rcpt": (
        {"rcpt": "drop"},
        Outcome(RETRY, f"Mất kết nối với máy chủ SMTP ở lệnh RCPT TO: {LOST}"),
    ),
    "sau-noi-dung": (
        {"content": "drop"},
        Outcome(UNKNOWN, f"Mất kết nối khi chờ máy chủ SMTP trả lời: {LOST}"),
    ),
}
HOST_RULE = (
    "SMTP_HOST chỉ gồm tên hoặc địa chỉ IP của máy chủ SMTP, ví dụ smtp.gmail.com. "
    "Cổng được đặt bằng SMTP_PORT"
)
PORT_RULE = "SMTP_PORT phải là số từ 1 đến 65535"
INVALID_SETTINGS = {
    "thieu-may-chu": ({"host": ""}, "thiếu SMTP_HOST"),
    "chi-co-mat-khau": (
        dict.fromkeys(("host", "username", "sender"), ""),
        "thiếu SMTP_HOST",
    ),
    "thieu-dia-chi-gui": ({"sender": ""}, "thiếu SMTP_FROM"),
    "che-do-la": ({"security": "ssl"}, "SMTP_SECURITY phải là starttls, tls hoặc none"),
    "cong-la-chu": ({"port": "abc"}, PORT_RULE),
    "cong-0": ({"port": "0"}, PORT_RULE),
    "cong-qua-lon": ({"port": "65536"}, PORT_RULE),
    "may-chu-kem-cong": ({"host": "smtp.gmail.com:587"}, HOST_RULE),
    "may-chu-kem-giao-thuc": ({"host": "smtp://smtp.gmail.com"}, HOST_RULE),
    "dia-chi-gui-kem-ten": (
        {"sender": "SaigonOS <thong-bao@example.com>"},
        "SMTP_FROM phải là một địa chỉ email, ví dụ thong-bao@example.com",
    ),
    "ten-gui-xuong-dong": (
        {"name": "SaigonOS\nBcc: khac@example.com"},
        "SMTP_FROM_NAME không được chứa ký tự điều khiển",
    ),
    "thieu-mat-khau": ({"password": ""}, "thiếu SMTP_PASSWORD"),
    "thieu-tai-khoan": ({"username": ""}, "thiếu SMTP_USERNAME"),
    "mat-khau-khong-ma-hoa": (
        {"security": "none"},
        "mật khẩu không được gửi khi SMTP_SECURITY là none. Hãy dùng starttls hoặc tls",
    ),
}
DEFAULTS = {
    "gmail": ({}, (587, STARTTLS)),
    "cong-465": ({"port": "465"}, (465, TLS)),
    "che-do-tls": ({"security": "tls"}, (465, TLS)),
    "cong-rieng": ({"port": "2525"}, (2525, STARTTLS)),
    "khong-ma-hoa": ({"security": "none", "username": "", "password": ""}, (25, NONE)),
    "starttls-cong-465": ({"port": "465", "security": "starttls"}, (465, STARTTLS)),
}


def load(name):
    path = Path(__file__).parents[1] / "integration" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fake_smtp = load("fake_smtp")


@pytest.fixture(scope="module")
def certificates(tmp_path_factory):
    return fake_smtp.make_certificates(tmp_path_factory.mktemp("smtp"), "localhost")


@pytest.fixture(scope="module")
def trusted(certificates):
    return ssl.create_default_context(cafile=str(certificates[0]))


def server_context(certificates):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificates[1], certificates[2])
    return context


def running(certificates, implicit_tls=False):
    mailbox = fake_smtp.Mailbox(USERNAME, PASSWORD, server_context(certificates), implicit_tls)
    server = fake_smtp.serve(mailbox)
    mailbox.port = server.server_address[1]
    return mailbox, server


@pytest.fixture
def mailbox(certificates):
    mailbox, server = running(certificates)
    yield mailbox
    server.shutdown()
    server.server_close()


def mailer(port, context, security=STARTTLS, password=PASSWORD, host="localhost", timeout=5):
    username = "" if security == NONE else USERNAME
    password = "" if security == NONE else password
    return Smtp(host, port, security, username, password, SENDER, NAME, timeout, context)


def message(body=BODY, link=LINK):
    return message_of(ADDRESS, TITLE, body, link, SITE)


def verbs(mailbox, index=-1):
    return [command.split(" ")[0] for command, _ in mailbox.sessions[index]["commands"]]


def received(mailbox, index=-1):
    return email.message_from_string(mailbox.sessions[index]["content"], policy=default)


def text_of(message):
    return message.get_content().replace("\r\n", "\n")


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def test_email_is_sent_after_starttls_and_login(mailbox, trusted):
    outcome = mailer(mailbox.port, trusted).send(message())

    [session] = mailbox.sessions
    commands = session["commands"]
    assert outcome.result == SENT
    assert [command.split(" ")[0] for command, _ in commands] == FULL_SESSION
    assert [secure for _, secure in commands] == [False, False] + [True] * 6
    assert (commands[4][0], commands[5][0]) == (f"MAIL FROM:<{SENDER}>", f"RCPT TO:<{ADDRESS}>")
    assert session["user"] == USERNAME


def test_email_has_headers_and_plain_text_with_full_link(mailbox, trusted):
    outcome = mailer(mailbox.port, trusted).send(message())

    content = mailbox.sessions[0]["content"]
    sent = received(mailbox)
    [sender] = sent["From"].addresses
    assert (sender.display_name, sender.addr_spec) == (NAME, SENDER)
    assert (str(sent["To"]), str(sent["Subject"])) == (ADDRESS, TITLE)
    assert sent["Message-ID"] == outcome.detail
    assert outcome.detail.startswith("<")
    assert outcome.detail.endswith("@example.com>")
    assert sent["Auto-Submitted"] == "auto-generated"
    assert abs(parsedate_to_datetime(sent["Date"]) - datetime.now(UTC)) < timedelta(minutes=1)
    assert (sent.get_content_type(), sent.get_content_charset()) == ("text/plain", "utf-8")
    assert text_of(sent) == f"{BODY}\n\n{SITE}{LINK}\n"
    assert content.isascii()
    assert max(len(line) for line in content.split("\r\n")) <= 78


def test_each_email_gets_new_message_id(mailbox, trusted):
    first = mailer(mailbox.port, trusted).send(message())
    second = mailer(mailbox.port, trusted).send(message())

    assert first.detail != second.detail


def test_lines_starting_with_dot_reach_recipient_unchanged(mailbox, trusted):
    body = ".\n..hai cham\n.mot cham"

    outcome = mailer(mailbox.port, trusted).send(message_of(ADDRESS, TITLE, body, None, SITE))

    assert outcome.result == SENT
    assert verbs(mailbox) == FULL_SESSION
    assert text_of(received(mailbox)) == body + "\n"


@pytest.mark.parametrize(
    ("body", "link", "text"),
    [
        (None, None, TITLE),
        ("   ", LINK, f"{TITLE}\n\n{SITE}{LINK}"),
        (f"  {BODY}  ", None, BODY),
    ],
    ids=["chi-tieu-de", "noi-dung-trong", "bo-khoang-trang"],
)
def test_text_is_body_or_title_then_full_link(body, link, text):
    built = message_of(ADDRESS, f" {TITLE} ", body, link, SITE)

    assert (str(built["Subject"]), text_of(built)) == (TITLE, text + "\n")


def test_server_without_starttls_never_gets_password(mailbox, trusted):
    mailbox.plan = [{"no_starttls": True}]

    outcome = mailer(mailbox.port, trusted).send(message())

    assert outcome == Outcome(FAILED, "Máy chủ SMTP không hỗ trợ STARTTLS")
    assert verbs(mailbox) == ["EHLO"]


def test_server_without_login_fails_at_once(mailbox, trusted):
    mailbox.plan = [{"no_auth": True}]

    outcome = mailer(mailbox.port, trusted).send(message())

    assert outcome == Outcome(FAILED, "Máy chủ SMTP không hỗ trợ đăng nhập (AUTH)")
    assert verbs(mailbox) == ["EHLO", "STARTTLS", "EHLO"]


def test_untrusted_certificate_is_refused_before_login(mailbox):
    outcome = mailer(mailbox.port, None).send(message())

    assert outcome.result == RETRY
    assert outcome.detail.startswith("Lỗi kết nối với máy chủ SMTP ở lệnh STARTTLS: ")
    assert "CERTIFICATE_VERIFY_FAILED" in outcome.detail
    assert verbs(mailbox) == ["EHLO", "STARTTLS"]
    assert mailbox.sessions[0]["user"] is None


def test_certificate_of_other_host_is_refused(mailbox, trusted):
    outcome = mailer(mailbox.port, trusted, host="127.0.0.1").send(message())

    assert outcome.result == RETRY
    assert "CERTIFICATE_VERIFY_FAILED" in outcome.detail
    assert mailbox.sessions[0]["user"] is None


def test_implicit_tls_sends_without_starttls(certificates, trusted):
    mailbox, server = running(certificates, implicit_tls=True)
    try:
        outcome = mailer(mailbox.port, trusted, security=TLS).send(message())
    finally:
        server.shutdown()
        server.server_close()

    commands = mailbox.sessions[0]["commands"]
    assert outcome.result == SENT
    assert [command.split(" ")[0] for command, _ in commands] == [
        "EHLO",
        "AUTH",
        "MAIL",
        "RCPT",
        "DATA",
        "QUIT",
    ]
    assert all(secure for _, secure in commands)


def test_plain_connection_sends_without_tls_or_login(mailbox, trusted):
    outcome = mailer(mailbox.port, trusted, security=NONE).send(message())

    assert outcome.result == SENT
    assert verbs(mailbox) == ["EHLO", "MAIL", "RCPT", "DATA", "QUIT"]
    assert not any(secure for _, secure in mailbox.sessions[0]["commands"])


def test_server_without_known_login_method_fails_at_once(mailbox, trusted):
    mailbox.plan = [{"auth_line": "AUTH XOAUTH2"}]

    outcome = mailer(mailbox.port, trusted).send(message())

    assert outcome == Outcome(FAILED, "Lỗi ở lệnh AUTH: No suitable authentication method found.")
    assert "AUTH" not in verbs(mailbox)


class Unsent:
    def ehlo_or_helo_if_needed(self):
        pass

    def starttls(self, context):
        pass

    def login(self, username, password):
        pass

    def mail(self, sender):
        return 250, b"2.1.0 OK"

    def rcpt(self, recipient):
        return 250, b"2.1.5 OK"

    def docmd(self, command):
        return 354, b"Go ahead"

    def send(self, payload):
        raise smtplib.SMTPServerDisconnected("Server not connected")


def test_content_not_fully_sent_is_sent_again_later(trusted):
    outcome = mailer(25, trusted).deliver(Unsent(), ADDRESS, b"Subject: x\r\n\r\nx\r\n.\r\n")

    assert outcome == Outcome(RETRY, "Mất kết nối khi gửi nội dung email: Server not connected")


def test_payload_ends_with_line_break_and_dot():
    built = EmailMessage()
    built.set_payload("Dong cuoi khong co dau xuong dong")

    assert payload_of(built).endswith(b"\r\n.\r\n")
    assert payload_of(message()).endswith(b"\r\n.\r\n")
    assert not payload_of(message()).endswith(b"\r\n\r\n.\r\n")


def test_wrong_password_fails_at_once_without_showing_it(mailbox, trusted):
    wrong = "mat-khau-sai-cua-ban"

    outcome = mailer(mailbox.port, trusted, password=wrong).send(message())

    assert outcome == Outcome(
        FAILED,
        "Máy chủ SMTP trả về mã 535 cho lệnh AUTH: 5.7.8 Username and Password not accepted",
    )
    assert "MAIL" not in verbs(mailbox)


@pytest.mark.parametrize(("step", "outcome"), REPLIES.values(), ids=REPLIES.keys())
def test_reply_of_server_gives_outcome(mailbox, trusted, step, outcome):
    mailbox.plan = [step]

    assert mailer(mailbox.port, trusted).send(message()) == outcome


@pytest.mark.parametrize(("step", "outcome"), DROPS.values(), ids=DROPS.keys())
def test_lost_connection_gives_outcome(mailbox, trusted, step, outcome):
    mailbox.plan = [step]

    assert mailer(mailbox.port, trusted).send(message()) == outcome


def test_reply_slower_than_timeout_after_content_gives_unknown(mailbox, trusted):
    mailbox.plan = [{"delay": 1}]

    outcome = mailer(mailbox.port, trusted, timeout=0.3).send(message())

    assert outcome.result == UNKNOWN
    assert outcome.detail.startswith(f"Mất kết nối khi chờ máy chủ SMTP trả lời: {LOST}: ")
    assert outcome.detail.endswith("timed out")
    assert mailbox.sessions[0]["content"] is not None


def test_lost_connection_after_accepted_email_still_counts_as_sent(mailbox, trusted):
    mailbox.plan = [{"quit": "drop"}]

    assert mailer(mailbox.port, trusted).send(message()).result == SENT


def test_refused_connection_is_sent_again_later():
    outcome = mailer(free_port(), None, security=NONE, host="127.0.0.1").send(message())

    assert outcome.result == RETRY
    assert outcome.detail.startswith("Không kết nối được máy chủ SMTP: ")


def settings(**values):
    base = {
        "host": "smtp.gmail.com",
        "port": "",
        "security": "",
        "username": USERNAME,
        "password": PASSWORD,
        "sender": SENDER,
        "name": "",
    }
    return configured(**(base | values))


def test_nothing_configured_gives_no_sender():
    assert configured("", "", "", "", "", "", "") is None


def test_settings_of_gmail_use_starttls_on_port_587():
    smtp = settings(name=NAME)

    assert (smtp.host, smtp.port, smtp.security) == ("smtp.gmail.com", 587, STARTTLS)
    assert (smtp.username, smtp.password, smtp.sender, smtp.name) == (
        USERNAME,
        PASSWORD,
        SENDER,
        NAME,
    )
    assert (smtp.timeout, smtp.context) == (10, None)


@pytest.mark.parametrize(("values", "expected"), DEFAULTS.values(), ids=DEFAULTS.keys())
def test_port_and_security_have_defaults(values, expected):
    smtp = settings(**values)

    assert (smtp.port, smtp.security) == expected


def test_ipv6_address_may_be_host():
    assert settings(host="2001:db8::25").host == "2001:db8::25"


@pytest.mark.parametrize(
    ("values", "message"), INVALID_SETTINGS.values(), ids=INVALID_SETTINGS.keys()
)
def test_incomplete_or_invalid_settings_are_refused_without_showing_password(values, message):
    with pytest.raises(SmtpSettingsError) as refused:
        settings(**values)

    assert str(refused.value) == message
    assert PASSWORD not in message
