# SPDX-License-Identifier: Apache-2.0
import json
import secrets
import shutil
import socket
import subprocess
import sys
from http.client import HTTPConnection
from typing import NamedTuple
from urllib.parse import urlencode, urlsplit

import pytest

REALM = "saigonos"
CLIENT = "kiem-thu"


class Reply(NamedTuple):
    status: int
    headers: dict
    body: bytes


class User(NamedTuple):
    id: str
    name: str
    password: str


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def send(method, url, token=None, form=None, body=None):
    parts = urlsplit(url)
    headers = {}
    payload = None
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        payload = urlencode(form)
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body)
    connection = HTTPConnection(parts.netloc, timeout=30)
    try:
        connection.request(method, parts.path, body=payload, headers=headers)
        response = connection.getresponse()
        return Reply(response.status, dict(response.getheaders()), response.read())
    finally:
        connection.close()


class Stack:
    def __init__(self, home):
        self.home = home
        self.docker = shutil.which("docker")

    def saigonos(self, *args):
        command = [sys.executable, "-m", "saigonos", *args, "--home", str(self.home)]
        return subprocess.run(command, check=False, capture_output=True, text=True, timeout=600)

    def compose(self, *args):
        command = [self.docker, "compose", *args]
        result = subprocess.run(
            command, cwd=self.home, check=False, capture_output=True, text=True, timeout=120
        )
        return result.stdout.strip()

    @property
    def env(self):
        lines = (self.home / ".env").read_text(encoding="utf-8").splitlines()
        return dict(line.split("=", 1) for line in lines)

    @property
    def url(self):
        return self.env["SAIGONOS_URL"]

    def admin(self, method, path, body=None):
        form = {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": "admin",
            "password": self.env["KEYCLOAK_ADMIN_PASSWORD"],
        }
        reply = send(
            "POST", f"{self.url}/auth/realms/master/protocol/openid-connect/token", form=form
        )
        assert reply.status == 200, reply.body
        token = json.loads(reply.body)["access_token"]
        return send(method, f"{self.url}/auth/admin/realms/{REALM}{path}", token=token, body=body)

    def create_client(self):
        client = {
            "clientId": CLIENT,
            "publicClient": True,
            "directAccessGrantsEnabled": True,
            "standardFlowEnabled": False,
        }
        reply = self.admin("POST", "/clients", client)
        assert reply.status == 201, reply.body

    def new_user(self):
        name = f"thu-{secrets.token_hex(4)}"
        password = secrets.token_urlsafe(12)
        user = {
            "username": name,
            "enabled": True,
            "firstName": "Người",
            "lastName": "Thử",
            "email": f"{name}@example.com",
            "emailVerified": True,
            "credentials": [{"type": "password", "value": password, "temporary": False}],
        }
        reply = self.admin("POST", "/users", user)
        assert reply.status == 201, reply.body
        return User(reply.headers["Location"].rsplit("/", 1)[1], name, password)

    def login(self, user):
        form = {
            "grant_type": "password",
            "client_id": CLIENT,
            "username": user.name,
            "password": user.password,
        }
        return send(
            "POST", f"{self.url}/auth/realms/{REALM}/protocol/openid-connect/token", form=form
        )

    def token(self, user):
        reply = self.login(user)
        assert reply.status == 200, reply.body
        return json.loads(reply.body)["access_token"]

    def api(self, token=None):
        return send("GET", f"{self.url}/api/", token=token)


@pytest.fixture(scope="session")
def stack(tmp_path_factory, request):
    stack = Stack(tmp_path_factory.getbasetemp() / f"saigonos-it-{secrets.token_hex(4)}")
    ports = ["--http-port", str(free_port()), "--admin-port", str(free_port())]
    created = stack.saigonos("init", *ports)
    assert created.returncode == 0, created.stdout + created.stderr
    try:
        started = stack.saigonos("up")
        if started.returncode != 0:
            pytest.fail(f"{started.stderr}\n{stack.compose('logs', '--tail', '50')}")
        stack.create_client()
        yield stack
        if request.session.testsfailed:
            capture = request.config.pluginmanager.getplugin("capturemanager")
            with capture.global_and_fixture_disabled():
                print(stack.compose("logs", "--tail", "50"))
    finally:
        stack.saigonos("down", "--volumes")
