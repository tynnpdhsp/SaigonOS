# SPDX-License-Identifier: Apache-2.0
import base64
import hashlib
import hmac
import html
import ipaddress
import json
import re
import secrets
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.client import HTTPConnection, HTTPException, HTTPMessage
from typing import NamedTuple
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import pytest

from saigonos.doctor import REALTIME_PATH, caddy_root_certificate, websocket_accept

REALM = "saigonos"
CLIENT = "kiem-thu"
OUTSIDE_SUBNETS = [f"198.51.100.{start}/28" for start in range(0, 256, 16)]
PUBLIC_SUBNETS = {"IPv4": "192.0.2.0/28", "IPv6": "2001:db8:5a1:9::/64"}
ROUTES = ("/auth/realms/saigonos/.well-known/openid-configuration", "/api/", "/core/health")
ATTEMPT_TIMEOUT = 5
REDIRECTS = {301, 302, 303, 307}
TOTP_SECRET = re.compile(r'name="totpSecret" value="([^"]+)"')
TEXT, CLOSE, PING, PONG = 1, 8, 9, 10


class Reply(NamedTuple):
    status: int
    headers: HTTPMessage
    body: bytes


class User(NamedTuple):
    id: str
    name: str
    password: str


class Connection(HTTPConnection):
    def __init__(self, url, context=None, address=None, timeout=30):
        parts = urlsplit(url)
        secure = parts.scheme == "https"
        self.default_port = 443 if secure else 80
        super().__init__(parts.hostname, parts.port or self.default_port, timeout=timeout)
        self.context = (context or ssl.create_default_context()) if secure else None
        self.address = address

    def connect(self):
        self.sock = socket.create_connection((self.address or self.host, self.port), self.timeout)
        if self.context is not None:
            self.sock = self.context.wrap_socket(self.sock, server_hostname=self.host)


class Closed(NamedTuple):
    code: int | None
    reason: str


class Realtime:
    def __init__(self, url, context=None, headers=None, timeout=30):
        parts = urlsplit(url)
        key = base64.b64encode(secrets.token_bytes(16)).decode()
        lines = [
            f"GET {parts.path} HTTP/1.1",
            f"Host: {parts.netloc}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
            *(f"{name}: {value}" for name, value in (headers or {}).items()),
        ]
        self.connection = Connection(url, context, timeout=timeout)
        self.connection.connect()
        self.buffer = b""
        self.queue = deque()
        self.pushes = []
        self.last_id = 0
        self.connection.sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        status, *fields = self.read_until(b"\r\n\r\n").decode("latin-1").split("\r\n")
        self.status = int(status.split()[1])
        pairs = (field.partition(":") for field in fields)
        self.headers = {name.strip().lower(): value.strip() for name, _, value in pairs}
        accept = self.headers.get("sec-websocket-accept")
        self.accepted = self.status == 101 and accept == websocket_accept(key)

    def __enter__(self):
        return self

    def __exit__(self, *details):
        self.connection.close()

    def fill(self):
        chunk = self.connection.sock.recv(65536)
        if not chunk:
            raise ConnectionError("Centrifugo đã đóng kết nối")
        self.buffer += chunk

    def read_until(self, marker):
        while marker not in self.buffer:
            self.fill()
        head, _, self.buffer = self.buffer.partition(marker)
        return head

    def read(self, size):
        while len(self.buffer) < size:
            self.fill()
        data, self.buffer = self.buffer[:size], self.buffer[size:]
        return data

    def write(self, opcode, payload):
        mask = secrets.token_bytes(4)
        size = len(payload)
        if size < 126:
            length = struct.pack(">B", 0x80 | size)
        elif size < 1 << 16:
            length = struct.pack(">BH", 0x80 | 126, size)
        else:
            length = struct.pack(">BQ", 0x80 | 127, size)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.connection.sock.sendall(struct.pack(">B", 0x80 | opcode) + length + mask + masked)

    def frame(self):
        first, second = self.read(2)
        size = second & 0x7F
        if size == 126:
            size = struct.unpack(">H", self.read(2))[0]
        elif size == 127:
            size = struct.unpack(">Q", self.read(8))[0]
        return first & 0x0F, self.read(size)

    def send(self, message):
        self.write(TEXT, json.dumps(message).encode())

    def receive(self):
        while not self.queue:
            opcode, payload = self.frame()
            if opcode == CLOSE:
                self.write(CLOSE, payload[:2])
                code = struct.unpack(">H", payload[:2])[0] if len(payload) >= 2 else None
                return Closed(code, payload[2:].decode())
            if opcode == PING:
                self.write(PONG, payload)
            elif opcode == TEXT:
                for line in filter(None, payload.decode().splitlines()):
                    message = json.loads(line)
                    if message == {}:
                        self.send({})
                    else:
                        self.queue.append(message)
        return self.queue.popleft()

    def command(self, name, body):
        self.last_id += 1
        self.send({"id": self.last_id, name: body})
        while True:
            message = self.receive()
            if isinstance(message, Closed) or message.get("id") == self.last_id:
                return message
            self.pushes.append(message)

    def connect(self, token=None):
        return self.command("connect", {} if token is None else {"token": token})


def encode(data):
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def decode(segment):
    return json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))


def cookies_of(reply):
    return "; ".join(cookie.split(";", 1)[0] for cookie in reply.headers.get_all("Set-Cookie", []))


def totp(secret, step=0):
    counter = struct.pack(">Q", int(time.time() // 30) + step)
    digest = hmac.new(secret.encode(), counter, hashlib.sha1).digest()
    offset = digest[-1] & 15
    code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{code % 1_000_000:06d}"


def form_action(reply):
    return html.unescape(re.search(r'action="([^"]+)"', reply.body.decode())[1])


def http_status(result):
    status = re.search(r"HTTP/\S+ (\d{3})", result.stderr)
    assert status, result.stderr
    return int(status[1])


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def free_ports():
    options = (
        "--http-port",
        "--admin-port",
        "--keycloak-port",
        "--seaweedfs-port",
        "--centrifugo-port",
    )
    return [value for option in options for value in (option, str(free_port()))]


def send(
    method,
    url,
    token=None,
    form=None,
    body=None,
    headers=None,
    context=None,
    address=None,
    content=None,
    timeout=30,
):
    parts = urlsplit(url)
    headers = dict(headers or {})
    payload = None
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        payload = urlencode(form)
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body)
    if content is not None:
        headers.setdefault("Content-Type", "application/octet-stream")
        payload = content
    target = parts.path + (f"?{parts.query}" if parts.query else "")
    connection = Connection(url, context, address, timeout)
    try:
        connection.request(method, target or "/", body=payload, headers=headers)
        response = connection.getresponse()
        return Reply(response.status, response.headers, response.read())
    finally:
        connection.close()


class Stack:
    def __init__(self, home):
        self.home = home
        self.docker = shutil.which("docker")
        self.context = None

    def saigonos(self, *args):
        command = [sys.executable, "-m", "saigonos", *args, "--home", str(self.home)]
        return subprocess.run(command, check=False, capture_output=True, text=True, timeout=600)

    def up(self):
        started = self.saigonos("up")
        if started.returncode == 0:
            if "caddy" in self.compose("config", "--services").split():
                self.trust_caddy()
            self.wait_until_answers(*ROUTES)
        return started

    def answers(self, path, token=None):
        try:
            reply = self.call("GET", f"{self.url}{path}", token=token, timeout=ATTEMPT_TIMEOUT)
        except (OSError, HTTPException):
            return False
        return reply.status == 200

    def wait_until_answers(self, *paths, token=None, timeout=60):
        deadline = time.monotonic() + timeout
        for path in paths:
            while not self.answers(path, token):
                assert time.monotonic() < deadline, f"API Gateway chưa trả lời {path}"
                time.sleep(0.5)

    def compose_result(self, *args, timeout=120, input=None):
        return subprocess.run(
            [self.docker, "compose", *args],
            cwd=self.home,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input,
        )

    def compose(self, *args):
        return self.compose_result(*args).stdout.strip()

    def exec(self, service, *command):
        return self.compose_result("exec", "-T", service, *command)

    def network(self, name):
        return json.loads(self.compose("config", "--format", "json"))["networks"][name]["name"]

    @property
    def env(self):
        lines = (self.home / ".env").read_text(encoding="utf-8").splitlines()
        return dict(line.split("=", 1) for line in lines)

    @property
    def url(self):
        return self.env["SAIGONOS_URL"]

    @property
    def keycloak(self):
        return f"http://localhost:{self.env['SAIGONOS_KEYCLOAK_PORT']}/auth"

    def call(self, method, url, **options):
        return send(method, url, context=self.context, **options)

    def master_login(self, username, password, base=None):
        form = {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": username,
            "password": password,
        }
        url = f"{base or self.keycloak}/realms/master/protocol/openid-connect/token"
        return self.call("POST", url, form=form)

    def admin(self, method, path, body=None, realm=REALM):
        reply = self.master_login("admin", self.env["KEYCLOAK_ADMIN_PASSWORD"])
        assert reply.status == 200, reply.body
        token = json.loads(reply.body)["access_token"]
        return self.call(
            method, f"{self.keycloak}/admin/realms/{realm}{path}", token=token, body=body
        )

    def gateway_admin(self, method, path, body=None):
        url = f"http://127.0.0.1:{self.env['SAIGONOS_ADMIN_PORT']}/apisix/admin{path}"
        headers = {"X-API-KEY": self.env["APISIX_ADMIN_KEY"]}
        return self.call(method, url, body=body, headers=headers)

    def create_client(self):
        client = {
            "clientId": CLIENT,
            "publicClient": True,
            "directAccessGrantsEnabled": True,
            "standardFlowEnabled": False,
        }
        reply = self.admin("POST", "/clients", client)
        assert reply.status == 201, reply.body

    def new_user(self, unit=None, role=None):
        name = f"thu-{secrets.token_hex(4)}"
        password = secrets.token_urlsafe(12)
        user = {
            "username": name,
            "enabled": True,
            "firstName": "Người",
            "lastName": "Thử",
            "email": f"{name}@example.com",
            "emailVerified": True,
            "attributes": {"unit": [unit]} if unit else {},
            "credentials": [{"type": "password", "value": password, "temporary": False}],
        }
        reply = self.admin("POST", "/users", user)
        assert reply.status == 201, reply.body
        user = User(reply.headers["Location"].rsplit("/", 1)[1], name, password)
        if role:
            self.grant_role(user, role)
        return user

    def grant_role(self, user, role):
        created = self.admin("POST", "/roles", {"name": role})
        assert created.status in (201, 409), created.body
        found = json.loads(self.admin("GET", f"/roles/{role}").body)
        reply = self.admin("POST", f"/users/{user.id}/role-mappings/realm", [found])
        assert reply.status == 204, reply.body

    def revoke_roles(self, user):
        path = f"/users/{user.id}/role-mappings/realm"
        roles = json.loads(self.admin("GET", path).body)
        reply = self.admin("DELETE", path, roles)
        assert reply.status == 204, reply.body

    def login(self, user, scope=None):
        form = {
            "grant_type": "password",
            "client_id": CLIENT,
            "username": user.name,
            "password": user.password,
        }
        if scope:
            form["scope"] = scope
        return self.call(
            "POST", f"{self.url}/auth/realms/{REALM}/protocol/openid-connect/token", form=form
        )

    def refresh(self, refresh_token):
        form = {"grant_type": "refresh_token", "client_id": CLIENT, "refresh_token": refresh_token}
        return self.call(
            "POST", f"{self.url}/auth/realms/{REALM}/protocol/openid-connect/token", form=form
        )

    def token(self, user):
        reply = self.login(user)
        assert reply.status == 200, reply.body
        return json.loads(reply.body)["access_token"]

    def app_login(self, user, app):
        redirect = f"{self.url}/apps/{app}/"
        verifier = secrets.token_urlsafe(32)
        digest = hashlib.sha256(verifier.encode()).digest()
        query = {
            "client_id": app,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": "openid",
            "code_challenge": base64.urlsafe_b64encode(digest).rstrip(b"=").decode(),
            "code_challenge_method": "S256",
        }
        endpoint = f"{self.url}/auth/realms/{REALM}/protocol/openid-connect"
        page = self.call("GET", f"{endpoint}/auth?{urlencode(query)}")
        assert page.status == 200, page.headers.get("Location")
        action = html.unescape(re.search(r'action="([^"]+)"', page.body.decode())[1])
        form = {"username": user.name, "password": user.password}
        sent = self.call("POST", action, form=form, headers={"Cookie": cookies_of(page)})
        assert sent.status == 302, sent.body
        code = parse_qs(urlsplit(sent.headers["Location"]).query)["code"][0]
        exchange = {
            "grant_type": "authorization_code",
            "client_id": app,
            "redirect_uri": redirect,
            "code": code,
            "code_verifier": verifier,
        }
        return self.call("POST", f"{endpoint}/token", form=exchange)

    def browser_login(self, client, redirect, user, otp=None, step=1, secret=None, wait=0):
        verifier = secrets.token_urlsafe(32)
        digest = hashlib.sha256(verifier.encode()).digest()
        query = {
            "client_id": client,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": "openid",
            "code_challenge": base64.urlsafe_b64encode(digest).rstrip(b"=").decode(),
            "code_challenge_method": "S256",
        }
        endpoint = f"{self.url}/auth/realms/{REALM}/protocol/openid-connect"
        cookies = {}

        def visit(method, url, form=None):
            while True:
                jar = "; ".join(f"{name}={value}" for name, value in cookies.items())
                headers = {"Cookie": jar} if jar else {}
                reply = self.call(method, url, form=form, headers=headers)
                for line in reply.headers.get_all("Set-Cookie", []):
                    name, _, value = line.split(";", 1)[0].partition("=")
                    cookies[name] = value
                location = reply.headers.get("Location", "")
                if reply.status not in REDIRECTS or location.startswith(redirect):
                    return reply
                method, url, form = "GET", urljoin(url, location), None

        page = visit("GET", f"{endpoint}/auth?{urlencode(query)}")
        reply = visit("POST", form_action(page), {"username": user.name, "password": user.password})
        if reply.status == 200:
            setup = TOTP_SECRET.search(reply.body.decode())
            if setup:
                otp = html.unescape(setup[1])
                form = {"totpSecret": otp, "totp": totp(otp), "userLabel": "thu"}
            else:
                form = {"otp": totp(otp, step)}
            reply = visit("POST", form_action(reply), form)
        assert reply.status in REDIRECTS, reply.body
        time.sleep(wait)
        exchange = {
            "grant_type": "authorization_code",
            "client_id": client,
            "redirect_uri": redirect,
            "code": parse_qs(urlsplit(reply.headers["Location"]).query)["code"][0],
            "code_verifier": verifier,
        }
        if secret:
            exchange["client_secret"] = secret
        return self.call("POST", f"{endpoint}/token", form=exchange), otp

    def app_token(self, user, app):
        reply = self.app_login(user, app)
        assert reply.status == 200, reply.body
        return json.loads(reply.body)["access_token"]

    def forged_tokens(self, user):
        header, payload, signature = self.token(user).split(".")
        claims = decode(payload) | {"preferred_username": "admin"}
        return {
            "khong-phai-jwt": "khong-phai-token",
            "sua-noi-dung": f"{header}.{encode(claims)}.{signature}",
            "khong-ky": f"{encode({'alg': 'none', 'typ': 'JWT'})}.{payload}.",
        }

    def realtime(self, headers=None):
        headers = {"Origin": self.url} if headers is None else headers
        return Realtime(f"{self.url}{REALTIME_PATH}", self.context, headers)

    def api(self, token=None, headers=None, address=None):
        return self.call("GET", f"{self.url}/api/", token=token, headers=headers, address=address)

    def discovery(self, headers=None, address=None):
        path = f"/auth/realms/{REALM}/.well-known/openid-configuration"
        reply = self.call("GET", f"{self.url}{path}", headers=headers, address=address)
        assert reply.status == 200, reply.body
        return json.loads(reply.body)

    def burst(self, token, calls, workers=8):
        def worker(count):
            connection = Connection(self.url, self.context)
            statuses = []
            try:
                for _ in range(count):
                    connection.request("GET", "/api/", headers={"Authorization": f"Bearer {token}"})
                    response = connection.getresponse()
                    response.read()
                    statuses.append(response.status)
            finally:
                connection.close()
            return statuses

        with ThreadPoolExecutor(workers) as pool:
            results = pool.map(worker, [calls // workers] * workers)
            return [status for statuses in results for status in statuses]

    def rotate_keys(self):
        component = {
            "name": f"rsa-{secrets.token_hex(4)}",
            "providerId": "rsa-generated",
            "providerType": "org.keycloak.keys.KeyProvider",
            "parentId": json.loads(self.admin("GET", "").body)["id"],
            "config": {"priority": ["200"], "algorithm": ["RS256"]},
        }
        reply = self.admin("POST", "/components", component)
        assert reply.status == 201, reply.body

    def logs(self, service):
        return self.compose("logs", "--no-log-prefix", service)

    def sql(self, query):
        options = ["--username=postgres", "--dbname=saigonos", "--no-psqlrc", "--tuples-only"]
        options += ["--no-align", "--set=ON_ERROR_STOP=1", f"--command={query}"]
        command = [self.docker, "compose", "exec", "-T", "postgres", "psql", *options]
        result = subprocess.run(
            command, cwd=self.home, check=False, capture_output=True, text=True, timeout=60
        )
        assert result.returncode == 0, result.stderr
        return [line.split("|") for line in result.stdout.splitlines()]

    def postgrest_status(self, path, token=None):
        fields = ["--header", f"Authorization: Bearer {token}"] if token else []
        options = ["-S", "-O", "/dev/null", *fields, f"http://postgrest:3000{path}"]
        command = [self.docker, "compose", "exec", "-T", "postgres", "wget", *options]
        result = subprocess.run(
            command, cwd=self.home, check=False, capture_output=True, text=True, timeout=60
        )
        return http_status(result)

    @property
    def s3_key(self):
        env = self.env
        return env["SEAWEEDFS_ACCESS_KEY"], env["SEAWEEDFS_SECRET_KEY"]

    def storage_call(self, method, url, key=None, body=None):
        image = self.inspect(self.container("seaweedfs"), "{{.Config.Image}}")
        options = ["--rm", "--network", self.network("storage"), "--entrypoint", "curl"]
        fields = ["--silent", "--dump-header", "/dev/stderr", "--request", method]
        if key is not None:
            fields += ["--aws-sigv4", "aws:amz:us-east-1:s3", "--user", ":".join(key)]
        if body is not None:
            fields += ["--data-binary", body]
        result = self.run_docker("run", *options, image, *fields, url, check=False)
        return http_status(result), result.stdout

    def s3(self, method, path, key=None, body=None):
        return self.storage_call(method, f"http://seaweedfs:8333{path}", key, body)

    def scan(self, content):
        image = self.inspect(self.container("clamav"), "{{.Config.Image}}")
        options = ["--rm", "--interactive", "--network", self.network("scan"), "--entrypoint", "nc"]
        command = [self.docker, "run", *options, image, "clamav", "3310"]
        chunks = struct.pack(">I", len(content)) + content + struct.pack(">I", 0)
        result = subprocess.run(
            command, input=b"zINSTREAM\0" + chunks, check=False, capture_output=True, timeout=60
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.rstrip(b"\0").decode()

    def add_migration(self, name, text):
        path = self.home / "config" / "postgres" / "migrations" / name
        path.write_text(text, encoding="utf-8")
        return path

    def container(self, service):
        return self.compose("ps", "--all", "--quiet", service)

    def inspect(self, container, template):
        command = [self.docker, "inspect", "--format", template, container]
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
        return result.stdout.strip()

    def kill(self, container):
        self.kill_process(self.inspect(container, "{{.State.Pid}}"))

    def kill_process(self, pid):
        image = self.inspect(self.container("postgres"), "{{.Config.Image}}")
        options = ["--rm", "--pid=host", "--privileged", "--entrypoint", "kill"]
        command = [self.docker, "run", *options, image, "-9", pid]
        subprocess.run(command, check=True, capture_output=True, timeout=60)

    def run_docker(self, *args, check=True):
        command = [self.docker, *args]
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0 or not check, result.stderr
        return result

    @contextmanager
    def outside_network(self):
        network = f"{self.home.name}-outside"
        gateway = self.container("apisix")
        self.run_docker("network", "create", "--subnet", secrets.choice(OUTSIDE_SUBNETS), network)
        try:
            self.run_docker("network", "connect", "--alias", "gateway", network, gateway)
            yield network
        finally:
            self.run_docker("network", "disconnect", "--force", network, gateway, check=False)
            self.run_docker("network", "rm", network, check=False)

    def outside_status(self, network, path, headers=None):
        image = self.inspect(self.container("postgres"), "{{.Config.Image}}")
        options = ["--rm", "--network", network, "--entrypoint", "wget"]
        fields = []
        for name, value in (headers or {}).items():
            fields += ["--header", f"{name}: {value}"]
        url = f"http://gateway:{self.env['SAIGONOS_HTTP_PORT']}{path}"
        result = self.run_docker(
            "run", *options, image, "-S", "-O", "/dev/null", *fields, url, check=False
        )
        return http_status(result)

    @contextmanager
    def public_network(self, family):
        subnet = ipaddress.ip_network(PUBLIC_SUBNETS[family])
        address = str(subnet[1])
        network = f"{self.home.name}-{family.lower()}"
        options = ["--subnet", str(subnet), "--gateway", address]
        options += ["-o", "com.docker.network.bridge.enable_ip_masquerade=false"]
        if subnet.version == 6:
            options.append("--ipv6")
        self.run_docker("network", "create", *options, network)
        try:
            yield address
        finally:
            self.run_docker("network", "rm", network, check=False)

    def certificate(self):
        connection = Connection(self.url, self.context)
        try:
            connection.connect()
            return hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest()
        finally:
            connection.close()

    def trust_caddy(self, timeout=60):
        deadline = time.monotonic() + timeout
        while True:
            certificate = caddy_root_certificate(self.home)
            if certificate:
                self.context = ssl.create_default_context(cadata=certificate)
                try:
                    self.certificate()
                except OSError:
                    pass
                else:
                    return
            assert time.monotonic() < deadline, "Caddy chưa cấp chứng chỉ"
            time.sleep(0.5)

    def logged_address(self, agent, timeout=30):
        deadline = time.monotonic() + timeout
        while True:
            for line in self.compose("logs", "--no-log-prefix", "apisix").splitlines():
                if f'"{agent}"' in line:
                    return line.split(" ", 1)[0]
            assert time.monotonic() < deadline, f"Log của APISIX không có lời gọi {agent}"
            time.sleep(1)

    def remove_data(self):
        if not (self.home / "data").exists():
            return
        services = json.loads(self.compose("config", "--format", "json"))["services"]
        options = ["--rm", "--volume", f"{self.home}:/home", "--entrypoint", "rm"]
        self.run_docker("run", *options, services["postgres"]["image"], "-rf", "/home/data")


def run_stack(stack, request):
    try:
        started = stack.up()
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
        stack.compose_result("--profile", "apps", "down", "--volumes", "--rmi", "local")
        stack.remove_data()


@pytest.fixture(scope="module")
def stack(tmp_path_factory, request):
    stack = Stack(tmp_path_factory.getbasetemp() / f"saigonos-it-{secrets.token_hex(4)}")
    created = stack.saigonos("init", *free_ports())
    assert created.returncode == 0, created.stdout + created.stderr
    yield from run_stack(stack, request)


@pytest.fixture(scope="module")
def idle_stack(tmp_path_factory):
    return Stack(tmp_path_factory.getbasetemp() / f"saigonos-idle-{secrets.token_hex(4)}")


@pytest.fixture(scope="module")
def caddy_stack(tmp_path_factory, request):
    stack = Stack(tmp_path_factory.getbasetemp() / f"saigonos-caddy-{secrets.token_hex(4)}")
    stack.home.mkdir()
    (stack.home / ".env").write_text(f"CADDY_HTTP_PORT={free_port()}\n", encoding="utf-8")
    options = ["--caddy", "--url", f"https://localhost:{free_port()}"]
    created = stack.saigonos("init", *options, *free_ports())
    assert created.returncode == 0, created.stdout + created.stderr
    yield from run_stack(stack, request)
