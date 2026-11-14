# SPDX-License-Identifier: Apache-2.0
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from click.testing import CliRunner

from saigonos.cli import main

FAKE_DOCKER = """\
#!/bin/sh
dir="${0%/*}"
printf '%s\\n' "$(pwd -P): $*" >> "$dir/calls"
[ -f "$dir/$2.out" ] && cat "$dir/$2.out"
[ -f "$dir/$2.err" ] && cat "$dir/$2.err" >&2
[ -f "$dir/$2.code" ] && exit "$(cat "$dir/$2.code")"
exit 0
"""


class FakeDocker:
    def __init__(self, directory):
        self.directory = directory

    def reply(self, subcommand, output="", error="", code=0):
        (self.directory / f"{subcommand}.out").write_text(output, encoding="utf-8")
        (self.directory / f"{subcommand}.err").write_text(error, encoding="utf-8")
        (self.directory / f"{subcommand}.code").write_text(str(code), encoding="utf-8")

    def services(self, config, rows, array=False):
        lines = json.dumps(rows) if array else "\n".join(json.dumps(row) for row in rows)
        self.reply("config", json.dumps({"services": config}))
        self.reply("ps", lines)

    @property
    def calls(self):
        log = self.directory / "calls"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


class Gateway:
    def __init__(self, server):
        self.server = server
        self.url = f"http://127.0.0.1:{server.server_port}"
        self.routes = {}
        self.healthy()

    def healthy(self, seen_url=None):
        realm = "/auth/realms/saigonos"
        discovery = {
            "issuer": f"{self.url}{realm}",
            "token_endpoint": f"{seen_url or self.url}{realm}/protocol/openid-connect/token",
        }
        self.routes["/auth/realms/saigonos/.well-known/openid-configuration"] = (
            200,
            json.dumps(discovery).encode(),
        )
        self.routes["/api/"] = (401, b"")


@pytest.fixture(autouse=True)
def no_home_variable(monkeypatch):
    monkeypatch.delenv("SAIGONOS_HOME", raising=False)


@pytest.fixture
def cli():
    def invoke(*args):
        return CliRunner().invoke(main, [str(arg) for arg in args])

    return invoke


@pytest.fixture
def docker(tmp_path, monkeypatch):
    directory = tmp_path / "bin"
    directory.mkdir()
    script = directory / "docker"
    script.write_text(FAKE_DOCKER, encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ['PATH']}")
    return FakeDocker(directory)


@pytest.fixture
def gateway():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            status, body = gateway.routes.get(self.path, (404, b""))
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    gateway = Gateway(server)
    Thread(target=server.serve_forever, daemon=True).start()
    yield gateway
    server.shutdown()
    server.server_close()
