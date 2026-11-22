# SPDX-License-Identifier: Apache-2.0
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from saigonos_core.main import create_app
from saigonos_core.realtime import (
    ALGORITHM,
    DENIED,
    FORBIDDEN,
    LIFETIME,
    NOT_OWN,
    SubscriptionTokens,
)

KEY = "khoa-ky-token-kenh-dung-trong-kiem-thu"
NOW = 1_763_380_000.0
CHANNEL = "role:quan-ly"
ROLE = "quan-ly"
NOT_ROLE_CHANNELS = {
    "public": "public:thong-bao",
    "user": "user:#4f1b0c0e-nguoi-dung",
    "khong-namespace": "quan-ly",
    "namespace-khac": "khac:quan-ly",
    "chu-hoa": "ROLE:quan-ly",
    "role-rong": "role:",
    "khoang-trang": "role:quan ly",
    "co-dau": "role:quản-lý",
    "hai-role": "role:quan-ly,admin",
    "dau-thang": "role:#quan-ly",
    "qua-dai": "role:" + "a" * 251,
}


class IdleDatabase:
    async def open(self):
        pass

    async def close(self):
        pass


@pytest.fixture
def client(settings, scans, steps, deliveries, scopes):
    app = create_app(
        settings, IdleDatabase(), scans=scans, steps=steps, deliveries=deliveries, scopes=scopes
    )
    with TestClient(app) as client:
        yield client


def request_token(client, realm, channel, roles=(ROLE,), **changes):
    token = realm.token(realm_access={"roles": ["authenticated", *roles]}, **changes)
    headers = {"Authorization": f"Bearer {token}"}
    return client.post("/realtime/token", headers=headers, json={"channel": channel})


def claims_of(token, key):
    return jwt.decode(token, key, algorithms=[ALGORITHM], options={"verify_exp": False})


def test_token_lives_sixty_seconds_when_access_token_lives_longer():
    tokens = SubscriptionTokens(KEY, clock=lambda: NOW + 0.9)

    token = tokens.issue("nguoi-a", CHANNEL, int(NOW) + 600)

    assert LIFETIME == 60
    assert claims_of(token, KEY) == {"sub": "nguoi-a", "channel": CHANNEL, "exp": NOW + LIFETIME}


def test_token_expires_with_access_token_that_expires_sooner():
    tokens = SubscriptionTokens(KEY, clock=lambda: NOW)

    token = tokens.issue("nguoi-a", CHANNEL, int(NOW) + 20)

    assert claims_of(token, KEY)["exp"] == NOW + 20


def test_token_is_signed_with_hs256_and_key_of_settings(client, realm, settings):
    reply = request_token(client, realm, CHANNEL)

    token = reply.json()["token"]
    assert reply.status_code == 200
    assert reply.json() == {"token": token}
    assert jwt.get_unverified_header(token) == {"alg": "HS256", "typ": "JWT"}
    assert claims_of(token, settings.subscription_key)["channel"] == CHANNEL
    with pytest.raises(jwt.InvalidSignatureError):
        claims_of(token, KEY)


def test_caller_with_role_gets_token_for_own_user_and_role_channel(client, realm, settings):
    started = int(time.time())

    reply = request_token(client, realm, CHANNEL, exp=started + 600)

    claims = claims_of(reply.json()["token"], settings.subscription_key)
    assert set(claims) == {"sub", "channel", "exp"}
    assert (claims["sub"], claims["channel"]) == (realm.subject, CHANNEL)
    assert started + LIFETIME <= claims["exp"] <= int(time.time()) + LIFETIME


def test_token_does_not_outlive_access_token(client, realm, settings):
    expires = int(time.time()) + 20

    reply = request_token(client, realm, CHANNEL, exp=expires)

    assert claims_of(reply.json()["token"], settings.subscription_key)["exp"] == expires


@pytest.mark.parametrize(
    "roles",
    [(), ("Quan-ly",), ("quan-ly-khoa",), ("admin",)],
    ids=["khong-role", "khac-chu-hoa", "role-khac-ten", "admin"],
)
def test_caller_without_role_of_channel_gets_no_token(client, realm, roles):
    reply = request_token(client, realm, CHANNEL, roles)

    assert reply.status_code == 403
    assert reply.json() == {"detail": FORBIDDEN}


def test_role_of_client_does_not_count(client, realm):
    reply = request_token(client, realm, CHANNEL, (), resource_access={"app": {"roles": [ROLE]}})

    assert reply.status_code == 403


@pytest.mark.parametrize("channel", NOT_ROLE_CHANNELS.values(), ids=NOT_ROLE_CHANNELS.keys())
def test_token_is_given_only_for_role_channel(client, realm, channel):
    reply = request_token(client, realm, channel, (ROLE, "admin", "a" * 251))

    assert reply.status_code == 422
    assert reply.json()["detail"][0]["loc"] == ["body", "channel"]


def test_longest_role_channel_is_accepted(client, realm):
    role = "a" * 250

    reply = request_token(client, realm, f"role:{role}", (role,))

    assert reply.status_code == 200


@pytest.mark.parametrize("body", [None, {}, {"channel": None}], ids=["khong-body", "rong", "null"])
def test_channel_is_required(client, realm, body):
    token = realm.token(realm_access={"roles": ["authenticated", ROLE]})

    reply = client.post("/realtime/token", headers={"Authorization": f"Bearer {token}"}, json=body)

    assert reply.status_code == 422


def test_token_needs_access_token(client):
    reply = client.post("/realtime/token", json={"channel": CHANNEL})

    assert reply.status_code == 401
    assert reply.json() == {"detail": "Lời gọi này cần access token của người dùng đã đăng nhập"}


def test_openapi_document_describes_token_call(client):
    call = client.get("/openapi.json").json()["paths"]["/realtime/token"]["post"]

    assert call["security"] == [{"HTTPBearer": []}]
    assert call["responses"]["403"]["description"] == DENIED
    assert set(call["responses"]) == {"200", "401", "403", "422"}


APP = "nghi-phep"


def test_token_of_app_gets_channel_token_for_own_personal_channel_of_app(
    client, realm, settings, scopes
):
    scopes.apps.add(APP)
    channel = f"user:{APP}.{realm.subject}"

    reply = request_token(client, realm, channel, (), azp=APP)

    assert reply.status_code == 200
    claims = claims_of(reply.json()["token"], settings.subscription_key)
    assert (claims["sub"], claims["channel"]) == (realm.subject, channel)


@pytest.mark.parametrize(
    ("channel", "client_id"),
    [
        (f"user:{APP}.4f1b0c0e-nguoi-dung", "khac"),
        (f"user:{APP}.4f1b0c0e-nguoi-dung", "kiem-thu"),
        (f"user:{APP}.nguoi-khac", APP),
        ("user:khac.4f1b0c0e-nguoi-dung", APP),
    ],
    ids=["ung-dung-khac", "client-khac", "nguoi-khac", "kenh-cua-ung-dung-khac"],
)
def test_personal_channel_of_app_needs_token_of_that_app_and_user(
    client, realm, scopes, channel, client_id
):
    scopes.apps |= {APP, "khac"}

    reply = request_token(client, realm, channel, (), azp=client_id)

    assert (reply.status_code, reply.json()) == (403, {"detail": NOT_OWN})


@pytest.mark.parametrize(
    "channel",
    ["user:Nghi-Phep.a", "user:nghi_phep.a", "user:nghi-phep", "user:nghi-phep.", "user:.a"],
    ids=["chu-hoa", "gach-duoi", "thieu-sub", "sub-rong", "thieu-ung-dung"],
)
def test_personal_channel_of_app_follows_name_rules(client, realm, channel):
    reply = request_token(client, realm, channel, (), azp=APP)

    assert reply.status_code == 422
