# SPDX-License-Identifier: Apache-2.0
import base64
import secrets
import socket
import time

import jwt
import pytest

from saigonos_core.tokens import InvalidTokenError, KeysUnavailableError, TokenVerifier


@pytest.fixture
def verifier(realm):
    return TokenVerifier(realm.issuer, realm.url)


def test_token_signed_by_realm_key_gives_its_claims(realm, verifier):
    claims = verifier.verify(realm.token())

    assert claims["sub"] == realm.subject
    assert claims["unit"] == "khoa-a"
    assert claims["realm_access"] == {"roles": ["offline_access", "authenticated"]}


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
def test_forged_token_is_rejected(realm, verifier, name):
    with pytest.raises(InvalidTokenError):
        verifier.verify(realm.forged_tokens()[name])


@pytest.mark.parametrize(
    "changes",
    [
        {"exp": int(time.time()) - 1},
        {"exp": None},
        {"exp": "mai"},
        {"iat": int(time.time()) + 600},
        {"iss": "https://dx.example.com/auth/realms/master"},
        {"iss": None},
        {"sub": None},
        {"sub": 7},
        {"typ": "ID"},
        {"typ": "Refresh"},
        {"typ": None},
    ],
    ids=[
        "het-han",
        "thieu-exp",
        "exp-khong-phai-so",
        "iat-o-tuong-lai",
        "iss-cua-realm-khac",
        "thieu-iss",
        "thieu-sub",
        "sub-khong-phai-chuoi",
        "id-token",
        "refresh-token",
        "thieu-typ",
    ],
)
def test_token_with_wrong_claims_is_rejected(realm, verifier, changes):
    with pytest.raises(InvalidTokenError):
        verifier.verify(realm.token(**changes))


def test_token_without_key_id_is_rejected(realm, verifier):
    token = jwt.encode(realm.claims(), realm.keys["khoa-1"], algorithm="RS256")

    with pytest.raises(InvalidTokenError):
        verifier.verify(token)


@pytest.mark.parametrize("audience", ["account", ["account", "ung-dung"], None])
def test_token_is_accepted_whatever_its_audience(realm, verifier, audience):
    assert verifier.verify(realm.token(aud=audience))["sub"] == realm.subject


def test_token_signed_with_symmetric_key_from_jwks_is_rejected(realm, verifier):
    secret = secrets.token_bytes(32)
    key = {
        "kty": "oct",
        "kid": "doi-xung",
        "use": "sig",
        "alg": "HS256",
        "k": base64.urlsafe_b64encode(secret).rstrip(b"=").decode(),
    }
    realm.publish(key)
    token = jwt.encode(realm.claims(), secret, algorithm="HS256", headers={"kid": "doi-xung"})

    with pytest.raises(InvalidTokenError):
        verifier.verify(token)
    assert realm.fetches == 1


def test_keys_are_fetched_once_while_cache_is_fresh(realm, verifier):
    for _ in range(5):
        verifier.verify(realm.token())

    assert realm.fetches == 1


def test_new_signing_key_is_fetched_when_token_carries_unknown_key_id(realm):
    verifier = TokenVerifier(realm.issuer, realm.url, cooldown=0)
    verifier.verify(realm.token())

    realm.add_key("khoa-2")

    assert verifier.verify(realm.token("khoa-2"))["sub"] == realm.subject
    assert verifier.verify(realm.token())["sub"] == realm.subject
    assert realm.fetches == 2


def test_unknown_key_id_does_not_fetch_keys_again_during_cooldown(realm):
    verifier = TokenVerifier(realm.issuer, realm.url, cooldown=3600)
    verifier.verify(realm.token())
    realm.add_key("khoa-2")

    for _ in range(3):
        with pytest.raises(InvalidTokenError):
            verifier.verify(realm.token("khoa-2"))

    assert realm.fetches == 1


def test_key_removed_from_realm_is_rejected_after_cache_expires(realm):
    verifier = TokenVerifier(realm.issuer, realm.url, lifespan=0.05, cooldown=3600)
    realm.add_key("khoa-2")
    token = realm.token("khoa-2")
    verifier.verify(token)

    realm.remove_key("khoa-2")
    time.sleep(0.1)

    with pytest.raises(InvalidTokenError):
        verifier.verify(token)
    assert verifier.verify(realm.token())["sub"] == realm.subject


def test_fresh_cache_is_used_while_keycloak_is_down(realm, verifier):
    verifier.verify(realm.token())

    realm.stop()

    assert verifier.verify(realm.token())["sub"] == realm.subject


def test_expired_cache_is_not_used_while_keycloak_is_down(realm):
    verifier = TokenVerifier(realm.issuer, realm.url, lifespan=0.05)
    verifier.verify(realm.token())

    realm.stop()
    time.sleep(0.1)

    with pytest.raises(KeysUnavailableError):
        verifier.verify(realm.token())


def test_keys_are_unavailable_when_keycloak_cannot_be_reached(realm):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        closed = f"http://127.0.0.1:{listener.getsockname()[1]}/certs"
    verifier = TokenVerifier(realm.issuer, closed)

    with pytest.raises(KeysUnavailableError):
        verifier.verify(realm.token())


def test_keys_are_cached_for_one_minute_by_default(verifier):
    assert verifier.keys.jwk_set_cache.lifespan == 60
    assert verifier.keys.cooldown_duration == 1
