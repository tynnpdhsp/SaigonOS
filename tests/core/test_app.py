# SPDX-License-Identifier: Apache-2.0
import socket
from contextlib import asynccontextmanager
from dataclasses import replace
from importlib.metadata import version

import pytest
from fastapi.testclient import TestClient

import saigonos_core
from saigonos_core.clamav import ClamAV
from saigonos_core.downloads import DownloadLinks
from saigonos_core.main import ME, create_app
from saigonos_core.realtime import SubscriptionTokens
from saigonos_core.storage import Storage

LOGIN_NEEDED = "Lời gọi này cần access token của người dùng đã đăng nhập"


class FakeConnection:
    def __init__(self, database):
        self.database = database

    async def fetchrow(self, query):
        self.database.queries.append(query)
        return self.database.row


class FakeDatabase:
    def __init__(self):
        self.up = True
        self.state = "chưa mở"
        self.callers = []
        self.queries = []
        self.row = {"uid": "4f1b0c0e-nguoi-dung", "unit": "khoa-a", "role": "authenticated"}

    async def open(self):
        self.state = "đang mở"

    async def close(self):
        self.state = "đã đóng"

    async def available(self):
        return self.up

    @asynccontextmanager
    async def session(self, caller):
        self.callers.append(caller)
        yield FakeConnection(self)


@pytest.fixture
def database():
    return FakeDatabase()


@pytest.fixture
def client(settings, database, scans, steps, deliveries):
    app = create_app(settings, database, scans=scans, steps=steps, deliveries=deliveries)
    with TestClient(app) as client:
        yield client


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_database_is_open_only_while_app_runs(settings, database, scans, steps, deliveries):
    app = create_app(settings, database, scans=scans, steps=steps, deliveries=deliveries)

    with TestClient(app):
        running = database.state

    assert (running, database.state) == ("đang mở", "đã đóng")


def test_scans_run_only_while_app_runs(settings, database, scans, steps, deliveries):
    app = create_app(settings, database, scans=scans, steps=steps, deliveries=deliveries)

    with TestClient(app) as client:
        client.get("/health")
        running = scans.state

    assert (running, scans.state) == ("đang chạy", "đã dừng")


def test_steps_run_only_while_app_runs(settings, database, scans, steps, deliveries):
    app = create_app(settings, database, scans=scans, steps=steps, deliveries=deliveries)

    with TestClient(app) as client:
        client.get("/health")
        running = steps.state

    assert (running, steps.state) == ("đang chạy", "đã dừng")


def test_deliveries_run_only_while_app_runs(settings, database, scans, steps, deliveries):
    app = create_app(settings, database, scans=scans, steps=steps, deliveries=deliveries)

    with TestClient(app) as client:
        client.get("/health")
        running = deliveries.state

    assert (running, deliveries.state) == ("đang chạy", "đã dừng")


def test_health_follows_database(client, database):
    healthy = client.get("/health")
    database.up = False
    broken = client.get("/health")

    assert (healthy.status_code, healthy.json()) == (200, {"status": "ok"})
    assert broken.status_code == 503
    assert broken.json() == {"detail": "Không kết nối được cơ sở dữ liệu"}


def test_me_returns_what_database_sees_for_caller(client, database, realm):
    reply = client.get("/me", headers=bearer(realm.token()))

    [caller] = database.callers
    assert reply.status_code == 200
    assert reply.json() == database.row
    assert database.queries == [ME]
    assert (caller.role, caller.claims["role"]) == ("authenticated", "authenticated")
    assert (caller.claims["sub"], caller.claims["unit"]) == (realm.subject, "khoa-a")


def test_me_accepts_user_without_unit(client, database, realm):
    database.row = database.row | {"unit": None}

    reply = client.get("/me", headers=bearer(realm.token(unit=None)))

    assert reply.status_code == 200
    assert reply.json()["unit"] is None


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Basic YWRtaW46YWRtaW4="}, bearer("")])
def test_me_needs_access_token(client, database, headers):
    reply = client.get("/me", headers=headers)

    assert reply.status_code == 401
    assert reply.json() == {"detail": LOGIN_NEEDED}
    assert reply.headers["WWW-Authenticate"] == "Bearer"
    assert database.callers == []


@pytest.mark.parametrize(
    "name",
    [
        "khong-phai-jwt",
        "sua-noi-dung",
        "khong-ky",
        "ky-hs256-bang-khoa-cong-khai",
        "ky-bang-khoa-khac",
        "kid-khong-co-trong-jwks",
    ],
)
def test_me_rejects_forged_token(client, database, realm, name):
    reply = client.get("/me", headers=bearer(realm.forged_tokens()[name]))

    assert reply.status_code == 401
    assert reply.json() == {"detail": "Access token không hợp lệ"}
    assert reply.headers["WWW-Authenticate"] == 'Bearer error="invalid_token"'
    assert database.callers == []


def test_me_rejects_expired_token(client, database, realm):
    reply = client.get("/me", headers=bearer(realm.token(exp=1)))

    assert reply.status_code == 401
    assert reply.json() == {"detail": "Access token không hợp lệ"}
    assert database.callers == []


def test_me_treats_token_without_role_authenticated_as_call_without_token(client, database, realm):
    token = realm.token(realm_access={"roles": ["offline_access"]})

    reply = client.get("/me", headers=bearer(token))

    assert reply.status_code == 401
    assert reply.json() == {"detail": LOGIN_NEEDED}
    assert database.callers == []


def test_me_answers_503_when_keys_cannot_be_fetched(client, database, realm):
    realm.stop()

    reply = client.get("/me", headers=bearer(realm.token()))

    assert reply.status_code == 503
    assert "không lấy được khóa ký của Keycloak" in reply.json()["detail"]
    assert database.callers == []


def test_openapi_document_describes_api_behind_gateway(client, settings):
    document = client.get("/openapi.json").json()

    assert document["info"]["title"] == "SaigonOS Core API"
    assert document["info"]["version"] == version("saigonos")
    assert document["servers"] == [{"url": settings.public_url}]
    assert document["components"]["securitySchemes"] == {
        "HTTPBearer": {
            "type": "http",
            "scheme": "bearer",
            "description": "Access token do Keycloak cấp",
        }
    }
    assert document["paths"]["/me"]["get"]["security"] == [{"HTTPBearer": []}]
    assert "security" not in document["paths"]["/health"]["get"]


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/"])
def test_app_serves_no_page_that_loads_scripts_from_other_sites(client, path):
    assert client.get(path).status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/health/"), ("GET", "/me/"), ("POST", "/files/"), ("GET", "/notifications/")],
)
def test_path_with_trailing_slash_is_not_redirected_outside_gateway_prefix(client, method, path):
    reply = client.request(method, path, follow_redirects=False)

    assert reply.status_code == 404
    assert "location" not in reply.headers


def test_core_version_matches_project_version():
    assert saigonos_core.__version__ == version("saigonos")


TELEGRAM_VARIABLES = (
    "TELEGRAM_API_URL",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_TOPIC_ID",
)
TELEGRAM_TOKEN = "123456789:AAH-khoa_cua-bot"


@pytest.fixture
def environment(monkeypatch, settings):
    values = {
        "JWT_ISSUER": settings.issuer,
        "JWKS_URL": settings.jwks_url,
        "PUBLIC_URL": settings.public_url,
        "S3_URL": settings.storage_url,
        "S3_ACCESS_KEY": settings.storage_access_key,
        "S3_SECRET_KEY": settings.storage_secret_key,
        "MAX_FILE_SIZE": "25",
        "CLAMAV_HOST": settings.clamav_host,
        "CLAMAV_PORT": "3311",
        "DOWNLOAD_KEY": "khoa-khac",
        "OPERATON_URL": "http://may-khac:8080/operaton/engine-rest",
        "OPERATON_PASSWORD": "mat-khau-khac",
        "SUBSCRIPTION_KEY": "khoa-ky-token-kenh-khac-cua-centrifugo",
        "SAIGONOS_URL": "https://dx-khac.example.com",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    for name in TELEGRAM_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def test_settings_come_from_environment(environment, settings):
    database = FakeDatabase()

    app = create_app(database=database)

    assert app.state.settings == replace(
        settings,
        max_file_size=25,
        clamav_port=3311,
        download_key="khoa-khac",
        operaton_url="http://may-khac:8080/operaton/engine-rest",
        operaton_password="mat-khau-khac",
        subscription_key="khoa-ky-token-kenh-khac-cua-centrifugo",
        site_url="https://dx-khac.example.com",
    )
    assert app.state.downloads == DownloadLinks("khoa-khac")
    assert app.state.subscription_tokens == SubscriptionTokens(
        "khoa-ky-token-kenh-khac-cua-centrifugo"
    )
    assert app.state.tokens.issuer == settings.issuer
    assert app.state.tokens.keys.uri == settings.jwks_url
    assert app.state.storage == Storage(
        settings.storage_url, settings.storage_access_key, settings.storage_secret_key
    )
    assert app.state.scans.database is database
    assert app.state.scans.storage is app.state.storage
    assert app.state.scans.clamav == ClamAV(settings.clamav_host, 3311)
    assert app.state.operaton.url == "http://may-khac:8080/operaton/engine-rest"
    assert app.state.operaton.authorization == "Basic Y29yZTptYXQta2hhdS1raGFj"
    assert app.state.processes.operaton is app.state.operaton
    assert app.state.steps.database is database
    assert app.state.steps.operaton is app.state.operaton
    assert app.state.steps.processes is app.state.processes
    assert app.state.steps.worker == f"saigonos-core-{socket.gethostname()}"
    assert app.state.deliveries.database is database
    assert app.state.deliveries.site_url == "https://dx-khac.example.com"
    assert (app.state.deliveries.telegram, app.state.deliveries.problem) == (None, None)
    assert app.servers == [{"url": settings.public_url}]


def test_telegram_settings_come_from_environment_without_spaces(environment, monkeypatch):
    values = ["http://bot-api:8081 ", f" {TELEGRAM_TOKEN}", " -1001234567890 ", "7 "]
    for name, value in zip(TELEGRAM_VARIABLES, values, strict=True):
        monkeypatch.setenv(name, value)

    app = create_app(database=FakeDatabase())

    telegram = app.state.deliveries.telegram
    assert app.state.settings.telegram_api_url == "http://bot-api:8081"
    assert (app.state.settings.telegram_bot_token, app.state.settings.telegram_topic_id) == (
        TELEGRAM_TOKEN,
        "7",
    )
    assert (telegram.host, telegram.port, telegram.path) == (
        "bot-api",
        8081,
        f"/bot{TELEGRAM_TOKEN}/sendMessage",
    )
    assert (telegram.chat_id, telegram.topic_id) == (-1001234567890, 7)
    assert app.state.deliveries.problem is None


def test_empty_api_url_falls_back_to_telegram(environment, monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_URL", " ")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TELEGRAM_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@nhom_ky_thuat")

    app = create_app(database=FakeDatabase())

    assert app.state.settings.telegram_api_url == "https://api.telegram.org"
    assert app.state.deliveries.telegram.host == "api.telegram.org"


def test_invalid_telegram_settings_turn_telegram_off_and_keep_core_running(
    environment, monkeypatch
):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TELEGRAM_TOKEN)

    app = create_app(database=FakeDatabase())

    assert app.state.deliveries.telegram is None
    assert app.state.deliveries.problem == "thiếu TELEGRAM_CHAT_ID"
