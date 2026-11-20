# SPDX-License-Identifier: Apache-2.0
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from saigonos_core.main import create_app
from saigonos_core.notifications import (
    DEFAULT_LIMIT,
    FIND,
    LIST,
    MARK_READ,
    MAX_LIMIT,
    MAX_OFFSET,
    NOT_FOUND,
)

CALLER = "người gọi"
SERVICE = "core_service"
START = datetime(2026, 11, 20, 3, 0, tzinfo=UTC)
OTHER = "nguoi-khac"
COLUMNS = ["id", "title", "body", "link", "created_at", "read_at"]
CALLS = [("GET", "/notifications"), ("POST", f"/notifications/{uuid4()}/read")]


class FakeConnection:
    def __init__(self, database, caller, kind):
        self.database = database
        self.caller = caller
        self.kind = kind

    def own(self):
        return [row for row in self.database.rows if row["recipient"] == self.caller.claims["sub"]]

    async def fetch(self, query, *arguments):
        self.database.calls.append((self.kind, query, arguments))
        assert query == LIST
        offset, limit = arguments
        rows = sorted(self.own(), key=lambda row: (row["created_at"], row["id"]), reverse=True)
        return [visible(row) for row in rows[offset : offset + limit]]

    async def fetchrow(self, query, *arguments):
        self.database.calls.append((self.kind, query, arguments))
        [notification_id] = arguments
        row = next((row for row in self.own() if row["id"] == notification_id), None)
        if row is None:
            return None
        if query == MARK_READ:
            if row["read_at"] is not None:
                return None
            row["read_at"] = self.database.now
        else:
            assert query == FIND
        return visible(row)


class FakeNotifications:
    def __init__(self):
        self.rows = []
        self.calls = []
        self.callers = []
        self.now = START + timedelta(hours=1)

    async def open(self):
        pass

    async def close(self):
        pass

    @asynccontextmanager
    async def session(self, caller):
        self.callers.append((CALLER, caller))
        yield FakeConnection(self, caller, CALLER)

    @asynccontextmanager
    async def service_session(self, caller):
        self.callers.append((SERVICE, caller))
        yield FakeConnection(self, caller, SERVICE)

    def add(self, recipient, minute, **fields):
        row = {"id": uuid4(), "recipient": recipient, "title": f"Thông báo phút {minute}"}
        row |= {"body": None, "link": None, "created_at": START + timedelta(minutes=minute)}
        row |= {"read_at": None, **fields}
        self.rows.append(row)
        return row


def visible(row):
    return {name: row[name] for name in COLUMNS}


def instant(value):
    return None if value is None else value.isoformat().replace("+00:00", "Z")


def as_json(row):
    shown = visible(row) | {"id": str(row["id"])}
    return shown | {"created_at": instant(row["created_at"]), "read_at": instant(row["read_at"])}


def bearer(realm, **changes):
    return {"Authorization": f"Bearer {realm.token(**changes)}"}


@pytest.fixture
def notifications():
    return FakeNotifications()


@pytest.fixture
def client(settings, notifications, scans, steps):
    app = create_app(settings, notifications, scans=scans, steps=steps)
    with TestClient(app) as client:
        yield client


def test_list_returns_notifications_of_caller_newest_first(client, notifications, realm):
    read = START + timedelta(minutes=2)
    older = notifications.add(realm.subject, 1, body="Đã thay cáp", link="/yeu-cau/1", read_at=read)
    newer = notifications.add(realm.subject, 3)
    notifications.add(OTHER, 5)

    reply = client.get("/notifications", headers=bearer(realm))

    assert reply.status_code == 200
    assert reply.json() == [as_json(newer), as_json(older)]


def test_list_reads_first_page_in_session_of_caller(client, notifications, realm):
    client.get("/notifications", headers=bearer(realm))

    [(kind, caller)] = notifications.callers
    assert (kind, caller.role, caller.claims["sub"]) == (CALLER, "authenticated", realm.subject)
    assert notifications.calls == [(CALLER, LIST, (0, DEFAULT_LIMIT))]
    assert (DEFAULT_LIMIT, MAX_LIMIT) == (50, 200)


def test_list_returns_requested_page(client, notifications, realm):
    rows = [notifications.add(realm.subject, minute) for minute in range(5)]

    reply = client.get("/notifications", params={"offset": 1, "limit": 2}, headers=bearer(realm))

    assert reply.json() == [as_json(rows[3]), as_json(rows[2])]
    assert notifications.calls == [(CALLER, LIST, (1, 2))]


def test_list_accepts_largest_page(client, notifications, realm):
    page = {"offset": MAX_OFFSET, "limit": MAX_LIMIT}

    reply = client.get("/notifications", params=page, headers=bearer(realm))

    assert (reply.status_code, reply.json()) == (200, [])
    assert notifications.calls == [(CALLER, LIST, (MAX_OFFSET, MAX_LIMIT))]


@pytest.mark.parametrize(
    ("offset", "limit"),
    [(-1, 1), (MAX_OFFSET + 1, 1), (0, 0), (0, MAX_LIMIT + 1)],
    ids=["offset-am", "offset-qua-bigint", "limit-0", "limit-qua-lon"],
)
def test_list_refuses_page_outside_limits(client, notifications, realm, offset, limit):
    page = {"offset": offset, "limit": limit}

    reply = client.get("/notifications", params=page, headers=bearer(realm))

    assert reply.status_code == 422
    assert notifications.calls == []


def test_mark_read_records_time_of_reading(client, notifications, realm):
    row = notifications.add(realm.subject, 1)

    reply = client.post(f"/notifications/{row['id']}/read", headers=bearer(realm))

    assert reply.status_code == 200
    assert reply.json() == as_json(row) | {"read_at": instant(notifications.now)}
    [(kind, caller)] = notifications.callers
    assert (kind, caller.role, caller.claims["sub"]) == (SERVICE, "authenticated", realm.subject)
    assert notifications.calls == [(SERVICE, MARK_READ, (row["id"],))]


def test_marking_read_notification_again_keeps_first_time(client, notifications, realm):
    first = START + timedelta(minutes=2)
    row = notifications.add(realm.subject, 1, read_at=first)

    reply = client.post(f"/notifications/{row['id']}/read", headers=bearer(realm))

    assert (reply.status_code, reply.json()["read_at"]) == (200, instant(first))
    assert notifications.calls == [
        (SERVICE, MARK_READ, (row["id"],)),
        (SERVICE, FIND, (row["id"],)),
    ]


@pytest.mark.parametrize("sent_to_other", [True, False], ids=["cua-nguoi-khac", "khong-ton-tai"])
def test_mark_read_of_notification_not_sent_to_caller_gives_404(
    client, notifications, realm, sent_to_other
):
    row = notifications.add(OTHER, 1)
    target = row["id"] if sent_to_other else uuid4()

    reply = client.post(f"/notifications/{target}/read", headers=bearer(realm))

    assert (reply.status_code, reply.json()) == (404, {"detail": NOT_FOUND})
    assert row["read_at"] is None


def test_mark_read_refuses_id_that_is_not_uuid(client, notifications, realm):
    reply = client.post("/notifications/khong-phai-uuid/read", headers=bearer(realm))

    assert reply.status_code == 422
    assert notifications.calls == []


@pytest.mark.parametrize(("method", "path"), CALLS, ids=["danh-sach", "danh-dau-da-doc"])
@pytest.mark.parametrize(
    "roles", [None, ["offline_access"]], ids=["khong-co-token", "khong-co-role-authenticated"]
)
def test_notification_calls_need_access_token_of_user(
    client, notifications, realm, method, path, roles
):
    headers = {} if roles is None else bearer(realm, realm_access={"roles": roles})

    reply = client.request(method, path, headers=headers)

    assert reply.status_code == 401
    assert notifications.calls == []


def test_openapi_document_describes_notification_calls(client):
    paths = client.get("/openapi.json").json()["paths"]

    listing = paths["/notifications"]["get"]
    reading = paths["/notifications/{notification_id}/read"]["post"]
    assert listing["security"] == reading["security"] == [{"HTTPBearer": []}]
    assert set(listing["responses"]) == {"200", "401", "422", "503"}
    assert set(reading["responses"]) == {"200", "401", "404", "422", "503"}
