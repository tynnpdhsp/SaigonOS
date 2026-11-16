# SPDX-License-Identifier: Apache-2.0
from contextlib import asynccontextmanager
from importlib.metadata import version

import pytest
from fastapi.testclient import TestClient

import saigonos_core
from saigonos_core.main import ME, Settings, create_app

PUBLIC_URL = "https://dx.example.com/core"
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
def client(realm, database):
    app = create_app(Settings(realm.issuer, realm.url, PUBLIC_URL), database)
    with TestClient(app) as client:
        yield client


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_database_is_open_only_while_app_runs(realm, database):
    app = create_app(Settings(realm.issuer, realm.url, PUBLIC_URL), database)

    with TestClient(app):
        running = database.state

    assert (running, database.state) == ("đang mở", "đã đóng")


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
        "không phải JWT",
        "sửa nội dung",
        "không ký",
        "ký HS256 bằng khóa công khai",
        "ký bằng khóa khác",
        "kid không có trong JWKS",
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


def test_openapi_document_describes_api_behind_gateway(client):
    document = client.get("/openapi.json").json()

    assert document["info"]["title"] == "SaigonOS Core API"
    assert document["info"]["version"] == version("saigonos")
    assert document["servers"] == [{"url": PUBLIC_URL}]
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


def test_core_version_matches_project_version():
    assert saigonos_core.__version__ == version("saigonos")


def test_settings_come_from_environment(monkeypatch, realm):
    monkeypatch.setenv("JWT_ISSUER", realm.issuer)
    monkeypatch.setenv("JWKS_URL", realm.url)
    monkeypatch.setenv("PUBLIC_URL", PUBLIC_URL)

    app = create_app(database=FakeDatabase())

    assert app.state.tokens.issuer == realm.issuer
    assert app.state.tokens.keys.uri == realm.url
    assert app.servers == [{"url": PUBLIC_URL}]
