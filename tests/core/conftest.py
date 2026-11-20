# SPDX-License-Identifier: Apache-2.0
import asyncio
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

from saigonos_core.main import Settings

JWKS_PATH = "/auth/realms/saigonos/protocol/openid-connect/certs"
PUBLIC_URL = "https://dx.example.com/core"
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
            "khong-phai-jwt": "khong-phai-token",
            "sua-noi-dung": self.tampered_token(),
            "khong-ky": self.unsigned_token(),
            "ky-hs256-bang-khoa-cong-khai": self.token_signed_with_public_key(),
            "ky-bang-khoa-khac": self.token(signer=self.spare[0]),
            "kid-khong-co-trong-jwks": self.token("khoa-la", signer=self.spare[0]),
        }


class FakeWorker:
    def __init__(self):
        self.state = "chưa chạy"

    async def run(self):
        self.state = "đang chạy"
        try:
            await asyncio.Event().wait()
        finally:
            self.state = "đã dừng"


class FakeScans(FakeWorker):
    def __init__(self):
        super().__init__()
        self.notified = 0

    def notify(self):
        self.notified += 1


class FakeOperaton:
    def __init__(self):
        self.definitions = {}
        self.by_id = {}
        self.documents = {}
        self.looked_up = []
        self.read = []
        self.started = []
        self.queries = []
        self.found = []
        self.items = {}
        self.groups = {}
        self.claims = []
        self.submitted = []
        self.race = None
        self.external = []
        self.locks = []
        self.completed = []
        self.failed = []
        self.errors = {}
        self.failure = None

    def deploy(self, key, xml, version=1, suspended=False):
        definition = {"id": f"{key}:{version}:{version:04d}", "key": key, "version": version}
        definition["suspended"] = suspended
        self.definitions[key] = definition
        self.by_id[definition["id"]] = definition
        self.documents[definition["id"]] = xml
        return definition

    def check(self):
        if self.failure:
            raise self.failure

    def latest_definition(self, key):
        self.check()
        return self.definitions.get(key)

    def definition(self, definition_id):
        self.check()
        self.looked_up.append(definition_id)
        return self.by_id[definition_id]

    def definition_xml(self, definition_id):
        self.check()
        self.read.append(definition_id)
        return self.documents[definition_id]

    def submit_start_form(self, definition_id, variables):
        self.check()
        self.started.append((definition_id, variables))
        return {"id": f"quy-trinh-{len(self.started)}", "definitionId": definition_id}

    def add_task(self, task_id="viec-1", groups=("nhan-vien",), **fields):
        self.groups[task_id] = frozenset(groups)
        self.items[task_id] = {
            "id": task_id,
            "assignee": None,
            "suspended": False,
            "processDefinitionId": "yeu_cau:1:0001",
            "taskDefinitionKey": "xu_ly",
        } | fields

    def tasks(self, query, offset, limit):
        self.check()
        self.queries.append((query, offset, limit))
        if "taskId" not in query:
            return self.found
        task = self.items.get(query["taskId"])
        if task is None or not self.groups[task["id"]] & set(query["candidateGroups"]):
            return []
        return [dict(task)]

    def task(self, task_id):
        self.check()
        task = self.items.get(task_id)
        return None if task is None else dict(task)

    def claim(self, task_id, user):
        self.check()
        self.claims.append((task_id, user))
        if self.race:
            self.race(task_id)
        self.items[task_id]["assignee"] = user

    def submit_task_form(self, task_id, variables):
        self.check()
        self.submitted.append((task_id, variables))
        if self.race:
            self.race(task_id)
        del self.items[task_id]

    def refuse(self, call):
        error = self.errors.get(call)
        if error:
            raise error

    def lock_external_tasks(self, worker, topic, lock, wait):
        self.locks.append((worker, topic, lock, wait))
        self.refuse("lock")
        if not self.external:
            time.sleep(0.01)
            return []
        return [self.external.pop(0)]

    def complete_external_task(self, task_id, worker, variables):
        self.completed.append((task_id, worker, variables))
        self.refuse("complete")

    def fail_external_task(self, task_id, worker, message, details, retries, delay):
        self.failed.append((task_id, worker, message, details, retries, delay))
        self.refuse("fail")


@pytest.fixture
def scans():
    return FakeScans()


@pytest.fixture
def steps():
    return FakeWorker()


@pytest.fixture
def deliveries():
    return FakeWorker(), FakeWorker()


@pytest.fixture
def operaton():
    return FakeOperaton()


@pytest.fixture(scope="session")
def private_keys():
    return [rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(3)]


@pytest.fixture
def realm(gateway, private_keys):
    return Realm(gateway, private_keys)


@pytest.fixture
def settings(realm):
    storage = ("http://seaweedfs:8333", "khoa-truy-cap", "khoa-bi-mat")
    return Settings(
        realm.issuer,
        realm.url,
        PUBLIC_URL,
        *storage,
        max_file_size=10,
        clamav_host="clamav",
        clamav_port=3310,
        download_key="khoa-ky-duong-dan-tai-ve",
        operaton_url="http://operaton:8080/operaton/engine-rest",
        operaton_password="mat-khau-tai-khoan-core",
        subscription_key="khoa-ky-token-kenh-cua-centrifugo",
        site_url="https://dx.example.com",
    )
