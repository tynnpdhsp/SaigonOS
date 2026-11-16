# SPDX-License-Identifier: Apache-2.0
import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

JWKS_PATH = "/auth/realms/saigonos/protocol/openid-connect/certs"
FIRST_KEY = "khoa-1"


def segment(data):
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


class Realm:
    issuer = "https://dx.example.com/auth/realms/saigonos"
    subject = "4f1b0c0e-nguoi-dung"

    def __init__(self, gateway, private_keys):
        self.gateway = gateway
        self.spare = list(private_keys)
        self.url = f"{gateway.url}{JWKS_PATH}"
        self.keys = {}
        self.add_key(FIRST_KEY)

    def add_key(self, key_id):
        self.keys[key_id] = self.spare.pop()
        self.publish()

    def remove_key(self, key_id):
        del self.keys[key_id]
        self.publish()

    def publish(self, *others):
        keys = [
            RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
            | {"kid": key_id, "use": "sig", "alg": "RS256"}
            for key_id, key in self.keys.items()
        ]
        document = json.dumps({"keys": [*keys, *others]}).encode()
        self.gateway.routes[JWKS_PATH, False] = (200, document)

    def stop(self):
        self.gateway.routes[JWKS_PATH, False] = (503, b"")

    @property
    def fetches(self):
        return self.gateway.requests.count(JWKS_PATH)

    def claims(self, **changes):
        now = int(time.time())
        claims = {
            "iss": self.issuer,
            "sub": self.subject,
            "iat": now,
            "exp": now + 60,
            "aud": "account",
            "typ": "Bearer",
            "realm_access": {"roles": ["offline_access", "authenticated"]},
            "unit": "khoa-a",
        } | changes
        return {name: value for name, value in claims.items() if value is not None}

    def token(self, key_id=FIRST_KEY, signer=None, **changes):
        key = signer or self.keys[key_id]
        return jwt.encode(self.claims(**changes), key, algorithm="RS256", headers={"kid": key_id})

    def tampered_token(self):
        header, _, signature = self.token().split(".")
        return f"{header}.{segment(self.claims(sub='nguoi-khac'))}.{signature}"

    def unsigned_token(self):
        return jwt.encode(self.claims(), None, algorithm="none", headers={"kid": FIRST_KEY})

    def token_signed_with_public_key(self):
        public_key = (
            self.keys[FIRST_KEY]
            .public_key()
            .public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
            )
        )
        header = {"alg": "HS256", "typ": "JWT", "kid": FIRST_KEY}
        content = f"{segment(header)}.{segment(self.claims())}"
        digest = hmac.new(public_key, content.encode(), hashlib.sha256).digest()
        return f"{content}.{base64.urlsafe_b64encode(digest).rstrip(b'=').decode()}"

    def forged_tokens(self):
        return {
            "không phải JWT": "khong-phai-token",
            "sửa nội dung": self.tampered_token(),
            "không ký": self.unsigned_token(),
            "ký HS256 bằng khóa công khai": self.token_signed_with_public_key(),
            "ký bằng khóa khác": self.token(signer=self.spare[0]),
            "kid không có trong JWKS": self.token("khoa-la", signer=self.spare[0]),
        }


@pytest.fixture(scope="session")
def private_keys():
    return [rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(3)]


@pytest.fixture
def realm(gateway, private_keys):
    return Realm(gateway, private_keys)
