# SPDX-License-Identifier: Apache-2.0
import json
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from saigonos_core.outcome import FAILED, RETRY, SENT, UNKNOWN, WAIT, Outcome
from saigonos_core.telegram import (
    DEFAULT_API_URL,
    Telegram,
    TelegramSettingsError,
    configured,
    message_of,
    outcome_of,
)

TOKEN = "123456789:AAH-khoa_cua-bot"
CHAT = "-1001234567890"
SITE = "https://dx.example.com"
SENT_REPLY = (200, {"ok": True, "result": {"message_id": 1}})
REPLIES = {
    "da-gui": ((200, {"ok": True, "result": {"message_id": 42}}), Outcome(SENT, "42")),
    "200-khong-phai-json": (
        (200, b"<html></html>"),
        Outcome(
            UNKNOWN, "Telegram trả về mã 200 nhưng nội dung trả về không cho biết tin đã được gửi"
        ),
    ),
    "200-ok-false": (
        (200, {"ok": False}),
        Outcome(
            UNKNOWN, "Telegram trả về mã 200 nhưng nội dung trả về không cho biết tin đã được gửi"
        ),
    ),
    "500": (
        (500, {"ok": False, "error_code": 500, "description": "Internal Server Error"}),
        Outcome(RETRY, "Telegram trả về mã 500: Internal Server Error"),
    ),
    "502-khong-phai-json": ((502, b"Bad Gateway"), Outcome(RETRY, "Telegram trả về mã 502")),
    "429": (
        (
            429,
            {
                "ok": False,
                "error_code": 429,
                "description": "Too Many Requests: retry after 3",
                "parameters": {"retry_after": 3},
            },
        ),
        Outcome(WAIT, "Telegram trả về mã 429: Too Many Requests: retry after 3", 3),
    ),
    "429-khong-co-retry-after": (
        (429, {"ok": False, "description": "Too Many Requests"}),
        Outcome(RETRY, "Telegram trả về mã 429: Too Many Requests"),
    ),
    "429-retry-after-khong-phai-so": (
        (429, {"ok": False, "parameters": {"retry_after": True}}),
        Outcome(RETRY, "Telegram trả về mã 429"),
    ),
    "400": (
        (400, {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"}),
        Outcome(FAILED, "Telegram trả về mã 400: Bad Request: chat not found"),
    ),
    "400-nhom-da-chuyen": (
        (
            400,
            {
                "ok": False,
                "description": "Bad Request: group chat was upgraded to a supergroup chat",
                "parameters": {"migrate_to_chat_id": -1009876543210},
            },
        ),
        Outcome(
            FAILED,
            "Telegram trả về mã 400: Bad Request: group chat was upgraded to a supergroup chat. "
            "Nhóm đã được chuyển thành supergroup. Hãy đổi TELEGRAM_CHAT_ID thành -1009876543210",
        ),
    ),
    "401": (
        (401, {"ok": False, "error_code": 401, "description": "Unauthorized"}),
        Outcome(FAILED, "Telegram trả về mã 401: Unauthorized"),
    ),
    "403": (
        (403, {"ok": False, "description": "Forbidden: bot was kicked from the supergroup chat"}),
        Outcome(
            FAILED, "Telegram trả về mã 403: Forbidden: bot was kicked from the supergroup chat"
        ),
    ),
    "302": ((302, b""), Outcome(UNKNOWN, "Telegram trả về mã 302")),
}
INVALID_SETTINGS = {
    "thieu-token": (("", CHAT, ""), "thiếu TELEGRAM_BOT_TOKEN"),
    "chi-co-chu-de": (("", "", "7"), "thiếu TELEGRAM_BOT_TOKEN"),
    "thieu-nhom": ((TOKEN, "", ""), "thiếu TELEGRAM_CHAT_ID"),
    "token-khong-co-hai-cham": (("123456789", CHAT, ""), "TELEGRAM_BOT_TOKEN không có dạng"),
    "token-thieu-so": ((":AAH", CHAT, ""), "TELEGRAM_BOT_TOKEN không có dạng"),
    "token-thieu-chuoi": (("123456789:", CHAT, ""), "TELEGRAM_BOT_TOKEN không có dạng"),
    "token-co-khoang-trang": (("123456789:AA H", CHAT, ""), "TELEGRAM_BOT_TOKEN không có dạng"),
    "token-co-gach-cheo": (("123456789:AA/H", CHAT, ""), "TELEGRAM_BOT_TOKEN không có dạng"),
    "nhom-la-chu": ((TOKEN, "nhom", ""), "TELEGRAM_CHAT_ID phải là mã nhóm"),
    "nhom-chi-co-dau-tru": ((TOKEN, "-", ""), "TELEGRAM_CHAT_ID phải là mã nhóm"),
    "nhom-co-chu": ((TOKEN, "-100123a", ""), "TELEGRAM_CHAT_ID phải là mã nhóm"),
    "nhom-chi-co-a-con": ((TOKEN, "@", ""), "TELEGRAM_CHAT_ID phải là mã nhóm"),
    "chu-de-0": ((TOKEN, CHAT, "0"), "TELEGRAM_TOPIC_ID phải là số nguyên dương"),
    "chu-de-am": ((TOKEN, CHAT, "-7"), "TELEGRAM_TOPIC_ID phải là số nguyên dương"),
    "chu-de-la-chu": ((TOKEN, CHAT, "chung"), "TELEGRAM_TOPIC_ID phải là số nguyên dương"),
}
INVALID_API_URLS = {
    "giao-thuc-khac": "ftp://api.telegram.org",
    "thieu-giao-thuc": "api.telegram.org",
    "thieu-ten-may": "https://",
    "cong-qua-lon": "https://api.telegram.org:70000",
    "cong-khong-phai-so": "https://api.telegram.org:abc",
    "cong-0": "https://api.telegram.org:0",
    "co-khoang-trang": "https://api.telegram.org/duong dan",
    "co-query": "https://api.telegram.org/?a=1",
    "co-fragment": "https://api.telegram.org/#a",
}


class BotApi:
    def __init__(self, server):
        self.url = f"http://127.0.0.1:{server.server_port}"
        self.replies = []
        self.requests = []


@pytest.fixture
def bot_api():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            content = self.rfile.read(int(self.headers["Content-Length"]))
            api.requests.append((self.path, self.headers["Content-Type"], json.loads(content)))
            action = api.replies.pop(0) if api.replies else SENT_REPLY
            if action == "ngat":
                self.close_connection = True
                return
            if action == "treo":
                time.sleep(1)
                self.close_connection = True
                return
            status, data = action
            body = data if isinstance(data, bytes) else json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    api = BotApi(server)
    Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    yield api
    server.shutdown()
    server.server_close()


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def bot(url, chat=CHAT, topic=None, timeout=5):
    return Telegram(url, TOKEN, chat, topic, timeout)


def message():
    return message_of("Yêu cầu YC-001", "Máy 12 hỏng", "/yeu-cau/YC-001", SITE)


def test_message_is_posted_as_json_to_send_message_of_bot(bot_api):
    outcome = bot(bot_api.url, topic=7).send(message())

    [(path, kind, body)] = bot_api.requests
    assert outcome == Outcome(SENT, "1")
    assert (path, kind) == (f"/bot{TOKEN}/sendMessage", "application/json")
    assert body == {
        "chat_id": -1001234567890,
        "text": "Yêu cầu YC-001\nMáy 12 hỏng\nhttps://dx.example.com/yeu-cau/YC-001",
        "entities": [{"type": "bold", "offset": 0, "length": 14}],
        "link_preview_options": {"is_disabled": True},
        "message_thread_id": 7,
    }


def test_message_without_topic_goes_to_chat(bot_api):
    bot(bot_api.url).send(message())

    [(_, _, body)] = bot_api.requests
    assert "message_thread_id" not in body


def test_chat_name_is_sent_as_text(bot_api):
    bot(bot_api.url, chat="@nhom_ky_thuat").send(message())

    [(_, _, body)] = bot_api.requests
    assert body["chat_id"] == "@nhom_ky_thuat"


def test_path_of_api_url_is_kept(bot_api):
    bot(f"{bot_api.url}/telegram/").send(message())

    [(path, _, _)] = bot_api.requests
    assert path == f"/telegram/bot{TOKEN}/sendMessage"


@pytest.mark.parametrize(
    ("title", "text", "length"),
    [
        ("Máy 12 hỏng", "Máy 12 hỏng", 11),
        ("Cảnh báo 🔥", "Cảnh báo 🔥", 11),
        ("  Có khoảng trắng ", "Có khoảng trắng", 15),
    ],
    ids=["co-dau", "bieu-tuong", "khoang-trang-hai-dau"],
)
def test_title_is_bold_with_length_in_utf16_code_units(title, text, length):
    built = message_of(title, None, None, SITE)

    assert built["text"] == text
    assert built["entities"] == [{"type": "bold", "offset": 0, "length": length}]


@pytest.mark.parametrize(
    ("body", "link", "text"),
    [
        (None, None, "Tiêu đề"),
        ("Dòng 1\nDòng 2", None, "Tiêu đề\nDòng 1\nDòng 2"),
        (None, "/", "Tiêu đề\nhttps://dx.example.com/"),
        (" \n ", "/yeu-cau", "Tiêu đề\nhttps://dx.example.com/yeu-cau"),
    ],
    ids=["chi-tieu-de", "noi-dung-nhieu-dong", "chi-duong-dan", "noi-dung-chi-co-khoang-trang"],
)
def test_message_has_one_line_for_each_part_given(body, link, text):
    assert message_of("Tiêu đề", body, link, SITE)["text"] == text


@pytest.mark.parametrize(("reply", "outcome"), REPLIES.values(), ids=REPLIES.keys())
def test_reply_of_telegram_gives_outcome(bot_api, reply, outcome):
    bot_api.replies.append(reply)

    assert bot(bot_api.url).send(message()) == outcome


def test_status_and_content_give_outcome_without_connection():
    content = json.dumps({"ok": True, "result": {"message_id": 7}}).encode()

    assert outcome_of(200, content) == Outcome(SENT, "7")
    assert outcome_of(200, b"[1]").result == UNKNOWN
    assert outcome_of(503, b"null") == Outcome(RETRY, "Telegram trả về mã 503")


def test_refused_connection_is_sent_again_later():
    outcome = bot(f"http://127.0.0.1:{free_port()}").send(message())

    assert outcome.result == RETRY
    assert outcome.detail.startswith("Không gửi được lời gọi tới Telegram: ")
    assert "Connection refused" in outcome.detail


def test_failed_tls_handshake_is_sent_again_later(bot_api):
    outcome = bot(bot_api.url.replace("http://", "https://")).send(message())

    assert outcome.result == RETRY
    assert outcome.detail.startswith("Không gửi được lời gọi tới Telegram: ")
    assert bot_api.requests == []


def test_connection_closed_after_request_gives_unknown_outcome(bot_api):
    bot_api.replies.append("ngat")

    outcome = bot(bot_api.url).send(message())

    assert outcome == Outcome(
        UNKNOWN,
        "Mất kết nối khi chờ Telegram trả lời: Remote end closed connection without response",
    )
    assert len(bot_api.requests) == 1


def test_reply_slower_than_timeout_gives_unknown_outcome(bot_api):
    bot_api.replies.append("treo")

    outcome = bot(bot_api.url, timeout=0.2).send(message())

    assert outcome == Outcome(UNKNOWN, "Mất kết nối khi chờ Telegram trả lời: timed out")


def test_details_never_contain_token(bot_api):
    bot_api.replies += ["ngat", (400, {"ok": False, "description": "Bad Request"})]
    outcomes = [
        bot(bot_api.url).send(message()),
        bot(bot_api.url).send(message()),
        bot(f"http://127.0.0.1:{free_port()}").send(message()),
    ]

    assert [outcome.result for outcome in outcomes] == [UNKNOWN, FAILED, RETRY]
    assert all(TOKEN not in outcome.detail for outcome in outcomes)


def test_nothing_configured_gives_no_bot():
    assert configured(DEFAULT_API_URL, "", "", "") is None


def test_configured_bot_uses_https_api_of_telegram():
    telegram = configured(DEFAULT_API_URL, TOKEN, CHAT, "7")

    assert (telegram.secure, telegram.host, telegram.port) == (True, "api.telegram.org", None)
    assert telegram.path == f"/bot{TOKEN}/sendMessage"
    assert (telegram.chat_id, telegram.topic_id) == (-1001234567890, 7)


def test_configured_bot_without_topic_may_use_own_api_server():
    telegram = configured("http://bot-api:8081/telegram", TOKEN, "@nhom_ky_thuat", "")

    assert (telegram.secure, telegram.host, telegram.port) == (False, "bot-api", 8081)
    assert telegram.path == f"/telegram/bot{TOKEN}/sendMessage"
    assert (telegram.chat_id, telegram.topic_id) == ("@nhom_ky_thuat", None)


@pytest.mark.parametrize(
    ("values", "message"), INVALID_SETTINGS.values(), ids=INVALID_SETTINGS.keys()
)
def test_incomplete_or_invalid_settings_are_refused_without_showing_token(values, message):
    token, chat, topic = values

    with pytest.raises(TelegramSettingsError) as refused:
        configured(DEFAULT_API_URL, token, chat, topic)

    assert str(refused.value).startswith(message)
    assert not token or token not in str(refused.value)


@pytest.mark.parametrize("url", INVALID_API_URLS.values(), ids=INVALID_API_URLS.keys())
def test_invalid_api_url_is_refused(url):
    with pytest.raises(TelegramSettingsError, match="TELEGRAM_API_URL phải có dạng"):
        configured(url, TOKEN, CHAT, "")
