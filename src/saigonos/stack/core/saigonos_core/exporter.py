# SPDX-License-Identifier: Apache-2.0
import json
import os
import sys
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, NamedTuple
from urllib.parse import quote, urlsplit

PORT = 9100
TIMEOUT = 5
HEALTHY = {None, "healthy"}
ONE_SHOT = {"", "no"}
CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


class DockerError(Exception):
    pass


class Service(NamedTuple):
    name: str
    up: bool
    memory: int | None
    cpu: float | None = None
    cpus: int | None = None


class Docker:
    def __init__(self, url: str) -> None:
        parts = urlsplit(url)
        self.host = parts.hostname or "localhost"
        self.port = parts.port or 80

    def get(self, path: str) -> Any:
        connection = HTTPConnection(self.host, self.port, timeout=TIMEOUT)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            body = response.read()
        except (OSError, HTTPException) as error:
            raise DockerError(f"Không gọi được Docker API: {error}") from error
        finally:
            connection.close()
        if response.status != 200:
            raise DockerError(f"Docker API trả mã {response.status} cho {path.split('?')[0]}")
        try:
            return json.loads(body)
        except ValueError as error:
            raise DockerError(f"Docker API trả nội dung không phải JSON cho {path}") from error


def memory_used(stats: dict[str, Any]) -> int | None:
    memory = stats.get("memory_stats") or {}
    usage = memory.get("usage")
    if usage is None:
        return None
    details = memory.get("stats") or {}
    cache = details.get("inactive_file", details.get("total_inactive_file", 0))
    return max(usage - cache, 0)


def cpu_seconds(stats: dict[str, Any]) -> float | None:
    usage = ((stats.get("cpu_stats") or {}).get("cpu_usage") or {}).get("total_usage")
    return None if usage is None else usage / 1e9


def online_cpus(stats: dict[str, Any]) -> int | None:
    cpu = stats.get("cpu_stats") or {}
    return (
        cpu.get("online_cpus")
        or len((cpu.get("cpu_usage") or {}).get("percpu_usage") or [])
        or None
    )


def read_services(docker: Docker, project: str) -> list[Service]:
    labels = [f"com.docker.compose.project={project}", "com.docker.compose.oneoff=False"]
    query = quote(json.dumps({"label": labels}))
    found = {}
    for item in docker.get(f"/containers/json?all=1&filters={query}"):
        info = docker.get(f"/containers/{item['Id']}/json")
        if info["HostConfig"]["RestartPolicy"]["Name"] in ONE_SHOT:
            continue
        state = info["State"]
        health = (state.get("Health") or {}).get("Status")
        running = state["Running"] and not state["Restarting"] and not state["Paused"]
        memory = cpu = cpus = None
        if state["Running"]:
            stats = docker.get(f"/containers/{item['Id']}/stats?stream=false&one-shot=true")
            memory, cpu, cpus = memory_used(stats), cpu_seconds(stats), online_cpus(stats)
        name = item["Labels"]["com.docker.compose.service"]
        found[name] = Service(name, running and health in HEALTHY, memory, cpu, cpus)
    return sorted(found.values())


def render(services: list[Service]) -> str:
    lines = [
        "# HELP saigonos_service_up Bằng 1 khi service đang chạy và đạt healthcheck.",
        "# TYPE saigonos_service_up gauge",
        *(f'saigonos_service_up{{service="{item.name}"}} {int(item.up)}' for item in services),
        "# HELP saigonos_service_memory_bytes RAM của container, tính như lệnh docker stats.",
        "# TYPE saigonos_service_memory_bytes gauge",
        *(
            f'saigonos_service_memory_bytes{{service="{item.name}"}} {item.memory}'
            for item in services
            if item.memory is not None
        ),
    ]
    used = [item for item in services if item.cpu is not None]
    if used:
        lines += [
            "# HELP saigonos_service_cpu_seconds_total Thời gian CPU đã dùng, tính bằng giây.",
            "# TYPE saigonos_service_cpu_seconds_total counter",
            *(
                f'saigonos_service_cpu_seconds_total{{service="{item.name}"}} {item.cpu}'
                for item in used
            ),
        ]
    cpus = max((item.cpus for item in services if item.cpus), default=None)
    if cpus:
        lines += [
            "# HELP saigonos_host_cpus Số nhân CPU của máy cài đặt.",
            "# TYPE saigonos_host_cpus gauge",
            f"saigonos_host_cpus {cpus}",
        ]
    return "\n".join(lines) + "\n"


def handler(docker: Docker, project: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/health":
                self.reply(200, "ok\n")
            elif self.path == "/metrics":
                try:
                    self.reply(200, render(read_services(docker, project)))
                except DockerError as error:
                    print(error, file=sys.stderr, flush=True)
                    self.reply(503, f"{error}\n")
            else:
                self.reply(404, "Không có đường dẫn này.\n")

        def reply(self, status: int, text: str) -> None:
            body = text.encode()
            self.send_response(status)
            self.send_header("Content-Type", CONTENT_TYPE)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    return Handler


def main() -> None:
    docker = Docker(os.environ["DOCKER_URL"])
    server = ThreadingHTTPServer(("0.0.0.0", PORT), handler(docker, os.environ["COMPOSE_PROJECT"]))
    server.serve_forever()


if __name__ == "__main__":
    main()
