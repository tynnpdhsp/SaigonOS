# SPDX-License-Identifier: Apache-2.0
import json
import threading
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from saigonos_core.exporter import (
    Docker,
    DockerError,
    Service,
    handler,
    memory_used,
    read_services,
    render,
)

PROJECT = "saigonos"


def container(service, restart="unless-stopped", running=True, health=None, **state):
    return {
        "Labels": {"com.docker.compose.service": service},
        "HostConfig": {"RestartPolicy": {"Name": restart}},
        "State": {
            "Running": running,
            "Restarting": state.get("restarting", False),
            "Paused": state.get("paused", False),
            **({"Health": {"Status": health}} if health else {}),
        },
        "Memory": state.get("memory", 1000),
    }


class FakeDocker:
    def __init__(self, containers):
        self.containers = {f"{index:064x}": item for index, item in enumerate(containers, 1)}
        self.paths = []
        self.status = 200

    def answer(self, path):
        self.paths.append(path)
        parts = urlsplit(path)
        if self.status != 200:
            return self.status, {}
        if parts.path == "/containers/json":
            labels = json.loads(parse_qs(parts.query)["filters"][0])["label"]
            assert labels == [
                f"com.docker.compose.project={PROJECT}",
                "com.docker.compose.oneoff=False",
            ]
            assert parse_qs(parts.query)["all"] == ["1"]
            return 200, [
                {"Id": key, "Labels": item["Labels"]} for key, item in self.containers.items()
            ]
        key, kind = parts.path.split("/")[2:4]
        item = self.containers[key]
        if kind == "json":
            return 200, {"HostConfig": item["HostConfig"], "State": item["State"]}
        assert parse_qs(parts.query) == {"stream": ["false"], "one-shot": ["true"]}
        stats = {"usage": item["Memory"] + 200, "stats": {"inactive_file": 200}}
        return 200, {"memory_stats": stats}


@pytest.fixture
def docker_api(request):
    fake = FakeDocker(getattr(request, "param", []))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            status, body = fake.answer(self.path)
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fake.docker = Docker(f"http://127.0.0.1:{server.server_address[1]}")
    yield fake
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize(
    "docker_api",
    [
        [
            container("postgres", health="healthy", memory=5000),
            container("routes", restart="no", running=False),
            container("waf", restart="", running=False),
            container("freshclam", running=False),
            container("keycloak", health="starting"),
            container("clamav", health="unhealthy"),
            container("seaweedfs", paused=True, health="healthy"),
            container("operaton", restarting=True),
            container("etcd"),
        ]
    ],
    indirect=True,
)
def test_services_skip_one_shots_and_are_up_only_when_running_and_healthy(docker_api):
    services = read_services(docker_api.docker, PROJECT)

    assert services == [
        Service("clamav", False, 1000),
        Service("etcd", True, 1000),
        Service("freshclam", False, None),
        Service("keycloak", False, 1000),
        Service("operaton", False, 1000),
        Service("postgres", True, 5000),
        Service("seaweedfs", False, 1000),
    ]
    asked = {path.split("/")[2] for path in docker_api.paths if "/stats?" in path}
    running = {
        key
        for key, item in docker_api.containers.items()
        if item["State"]["Running"]
        and item["HostConfig"]["RestartPolicy"]["Name"] not in ("", "no")
    }
    assert asked == running


def test_unreachable_docker_api_is_reported():
    with pytest.raises(DockerError, match="Không gọi được Docker API"):
        read_services(Docker("http://127.0.0.1:9"), PROJECT)


def test_refused_call_is_reported_without_query(docker_api):
    docker_api.status = 403

    with pytest.raises(DockerError, match=r"Docker API trả mã 403 cho /containers/json$"):
        read_services(docker_api.docker, PROJECT)


@pytest.mark.parametrize(
    ("stats", "used"),
    [
        ({"memory_stats": {"usage": 900, "stats": {"inactive_file": 100}}}, 800),
        ({"memory_stats": {"usage": 900, "stats": {"total_inactive_file": 300}}}, 600),
        ({"memory_stats": {"usage": 900}}, 900),
        ({"memory_stats": {"usage": 50, "stats": {"inactive_file": 100}}}, 0),
        ({"memory_stats": {}}, None),
        ({}, None),
    ],
    ids=["cgroup-v2", "cgroup-v1", "khong-cache", "khong-am", "khong-usage", "rong"],
)
def test_memory_is_counted_like_docker_stats(stats, used):
    assert memory_used(stats) == used


def test_metrics_follow_prometheus_text_format():
    text = render([Service("apisix", True, 123), Service("caddy", False, None)])

    assert text.splitlines() == [
        "# HELP saigonos_service_up Bằng 1 khi service đang chạy và đạt healthcheck.",
        "# TYPE saigonos_service_up gauge",
        'saigonos_service_up{service="apisix"} 1',
        'saigonos_service_up{service="caddy"} 0',
        "# HELP saigonos_service_memory_bytes RAM của container, tính như lệnh docker stats.",
        "# TYPE saigonos_service_memory_bytes gauge",
        'saigonos_service_memory_bytes{service="apisix"} 123',
    ]


@pytest.fixture
def exporter(docker_api):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(docker_api.docker, PROJECT))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def get(path):
        connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.getheader("Content-Type"), response.read().decode()

    yield get
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize("docker_api", [[container("core", health="healthy")]], indirect=True)
def test_exporter_serves_metrics_health_and_nothing_else(exporter):
    status, content_type, body = exporter("/metrics")

    assert status == 200
    assert content_type == "text/plain; version=0.0.4; charset=utf-8"
    assert 'saigonos_service_up{service="core"} 1' in body
    assert exporter("/health")[0::2] == (200, "ok\n")
    assert exporter("/khac")[0] == 404


def test_exporter_answers_503_while_docker_api_refuses(exporter, docker_api, capsys):
    docker_api.status = 500

    status, _, body = exporter("/metrics")

    assert status == 503
    assert body == "Docker API trả mã 500 cho /containers/json\n"
    assert "Docker API trả mã 500" in capsys.readouterr().err
