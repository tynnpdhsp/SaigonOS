# SPDX-License-Identifier: Apache-2.0
import os
from contextlib import asynccontextmanager

import asyncpg
import pytest
from fastapi.testclient import TestClient

from saigonos_core.main import create_app
from saigonos_core.ui import FIND, POLICY

INDEX = "<!doctype html><title>Nghỉ phép</title>\n"
SCRIPT = "console.log('nghỉ phép');\n"
MANIFEST = '{"name": "nghi-phep"}'


class FakeConnection:
    def __init__(self, database):
        self.database = database

    async def fetchval(self, query, name):
        self.database.queries.append((query, name))
        if self.database.down:
            raise asyncpg.CannotConnectNowError("the database system is starting up")
        return self.database.installed.get(name)


class FakeDatabase:
    def __init__(self):
        self.installed = {"nghi-phep": "web/dist/", "khong-giao-dien": None}
        self.queries = []
        self.down = False

    async def open(self):
        pass

    async def close(self):
        pass

    @asynccontextmanager
    async def transaction(self):
        yield FakeConnection(self)


@pytest.fixture
def database():
    return FakeDatabase()


@pytest.fixture
def apps(tmp_path):
    root = tmp_path / "apps"
    app = root / "nghi-phep"
    ui = app / "web" / "dist"
    (ui / "css").mkdir(parents=True)
    (ui / "con" / "sau").mkdir(parents=True)
    (ui / "index.html").write_text(INDEX, encoding="utf-8")
    (ui / "app.js").write_text(SCRIPT, encoding="utf-8")
    (ui / "css" / "site.css").write_text("body { margin: 0; }\n")
    (ui / "LOGO.PNG").write_bytes(b"\x89PNG")
    (ui / "du-lieu.bin").write_bytes(b"\x00\x01")
    (ui / "con" / "sau" / "trang.html").write_text("<p>Trang</p>\n")
    (ui / ".an.js").write_text("bí mật\n")
    (app / "saigonos-app.json").write_text(MANIFEST)
    (tmp_path / "ngoai.js").write_text("ngoài thư mục\n")
    (ui / "lien-ket.js").symlink_to(tmp_path / "ngoai.js")
    (ui / "thu-muc-lien-ket").symlink_to(app, target_is_directory=True)
    os.mkfifo(ui / "ong.js")
    return root


@pytest.fixture
def client(settings, database, scans, steps, deliveries, apps):
    app = create_app(settings, database, scans=scans, steps=steps, deliveries=deliveries)
    app.state.apps_folder = apps
    with TestClient(app) as client:
        yield client


def assert_secured(reply):
    assert reply.headers["Content-Security-Policy"] == POLICY
    assert reply.headers["X-Content-Type-Options"] == "nosniff"
    assert reply.headers["Referrer-Policy"] == "same-origin"


def test_root_of_app_serves_index_without_caching(client, database):
    reply = client.get("/apps/nghi-phep/")

    assert (reply.status_code, reply.text) == (200, INDEX)
    assert reply.headers["Content-Type"] == "text/html; charset=utf-8"
    assert reply.headers["Cache-Control"] == "no-store"
    assert_secured(reply)
    assert database.queries == [(FIND, "nghi-phep")]


def test_address_without_slash_moves_to_root_of_app(client):
    reply = client.get("/apps/nghi-phep", follow_redirects=False)

    assert (reply.status_code, reply.headers["Location"]) == (308, "/apps/nghi-phep/")
    assert_secured(reply)


@pytest.mark.parametrize(
    ("path", "kind", "content"),
    [
        ("app.js", "text/javascript; charset=utf-8", SCRIPT.encode()),
        ("css/site.css", "text/css; charset=utf-8", b"body { margin: 0; }\n"),
        ("LOGO.PNG", "image/png", b"\x89PNG"),
        ("du-lieu.bin", "application/octet-stream", b"\x00\x01"),
        ("con/sau/trang.html", "text/html; charset=utf-8", b"<p>Trang</p>\n"),
    ],
    ids=["js", "css", "png", "khong-ro-loai", "thu-muc-con"],
)
def test_file_of_app_is_served_with_its_type_and_revalidated(client, path, kind, content):
    reply = client.get(f"/apps/nghi-phep/{path}")

    assert (reply.status_code, reply.content) == (200, content)
    assert reply.headers["Content-Type"] == kind
    assert reply.headers["Cache-Control"] == "no-cache"
    assert reply.headers["ETag"]
    assert reply.headers["Last-Modified"].endswith(" GMT")
    assert_secured(reply)


def test_unchanged_file_answers_304(client):
    tag = client.get("/apps/nghi-phep/app.js").headers["ETag"]

    same = client.get("/apps/nghi-phep/app.js", headers={"If-None-Match": tag})
    weak = client.get("/apps/nghi-phep/app.js", headers={"If-None-Match": f'"x", W/{tag}'})
    other = client.get("/apps/nghi-phep/app.js", headers={"If-None-Match": '"khac"'})

    assert (same.status_code, same.content) == (304, b"")
    assert weak.status_code == 304
    assert (other.status_code, other.text) == (200, SCRIPT)


def test_changed_file_gets_new_tag(client, apps):
    first = client.get("/apps/nghi-phep/app.js").headers["ETag"]
    (apps / "nghi-phep" / "web" / "dist" / "app.js").write_text(SCRIPT + "// mới\n")

    reply = client.get("/apps/nghi-phep/app.js", headers={"If-None-Match": first})

    assert reply.status_code == 200
    assert reply.headers["ETag"] != first


@pytest.mark.parametrize("path", ["don/12", "don/", "css", "con/sau/"])
def test_address_without_extension_serves_index(client, path):
    reply = client.get(f"/apps/nghi-phep/{path}")

    assert (reply.status_code, reply.text) == (200, INDEX)
    assert reply.headers["Cache-Control"] == "no-store"


def test_index_is_not_answered_with_304(client):
    tag = client.get("/apps/nghi-phep/").headers["ETag"]

    reply = client.get("/apps/nghi-phep/", headers={"If-None-Match": tag})

    assert (reply.status_code, reply.text) == (200, INDEX)


@pytest.mark.parametrize(
    "path",
    [
        "thieu.js",
        "css/thieu.css",
        "%2e%2e/saigonos-app.json",
        "..%2fsaigonos-app.json",
        "%2e%2e%2f%2e%2e%2fngoai.js",
        "con/%2e%2e/%2e%2e/%2e%2e/saigonos-app.json",
        "%2e/index.html",
        "%2ean.js",
        "css//site.css",
        "css%5csite.css",
        "app.js%00.html",
        "lien-ket.js",
        "thu-muc-lien-ket/saigonos-app.json",
        "ong.js",
        "api/notes",
        "api",
    ],
)
def test_path_outside_ui_or_through_links_is_not_found(client, path):
    reply = client.get(f"/apps/nghi-phep/{path}")

    assert reply.status_code == 404
    assert "nghi-phep" not in reply.text
    assert "ngoài thư mục" not in reply.text
    assert_secured(reply)


@pytest.mark.parametrize("name", ["chua-cai-dat", "khong-giao-dien"])
def test_app_not_installed_or_without_ui_is_not_found(client, name):
    reply = client.get(f"/apps/{name}/")
    moved = client.get(f"/apps/{name}", follow_redirects=False)

    assert (reply.status_code, reply.json()) == (
        404,
        {"detail": "Không tìm thấy giao diện của ứng dụng"},
    )
    assert moved.status_code == 404


@pytest.mark.parametrize("name", ["Nghi-Phep", "nghi_phep", "%2e%2e", "-nghi"])
def test_invalid_name_is_not_looked_up(client, database, name):
    reply = client.get(f"/apps/{name}/index.html")

    assert (reply.status_code, reply.json()) == (404, {"detail": "Không tìm thấy ứng dụng"})
    assert database.queries == []


def test_missing_index_is_reported(client, apps):
    (apps / "nghi-phep" / "web" / "dist" / "index.html").unlink()

    reply = client.get("/apps/nghi-phep/don/12")

    assert (reply.status_code, reply.json()) == (
        404,
        {"detail": "Không tìm thấy file index.html của ứng dụng"},
    )


def test_unreachable_database_gives_503(client, database):
    database.down = True

    reply = client.get("/apps/nghi-phep/")

    assert reply.status_code == 503
    assert reply.json() == {"detail": "Không kết nối được cơ sở dữ liệu"}


def test_missing_apps_folder_gives_404(client, apps):
    client.app.state.apps_folder = apps / "khong-co"

    reply = client.get("/apps/nghi-phep/")

    assert (reply.status_code, reply.json()) == (
        404,
        {"detail": "Không tìm thấy file index.html của ứng dụng"},
    )


def test_head_is_answered(client):
    reply = client.head("/apps/nghi-phep/app.js")

    assert reply.status_code == 200
    assert reply.headers["Content-Type"] == "text/javascript; charset=utf-8"


def test_other_methods_are_refused(client):
    assert client.post("/apps/nghi-phep/app.js").status_code == 405


def test_ui_routes_stay_out_of_api_document(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert not [path for path in paths if path.startswith("/apps")]
