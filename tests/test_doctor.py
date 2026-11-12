# SPDX-License-Identifier: Apache-2.0
import json
import socket

import pytest

from saigonos.doctor import api_state, gateway_checks, login_state, service_state

SERVICES = {
    "postgres": {"restart": "unless-stopped"},
    "routes": {"restart": "no"},
    "jwks": {},
}
HEALTHY = [
    {"Service": "postgres", "State": "running", "Health": "healthy", "ExitCode": 0},
    {"Service": "routes", "State": "exited", "Health": "", "ExitCode": 0},
    {"Service": "jwks", "State": "exited", "Health": "", "ExitCode": 0},
]
URL = "http://dx.example.com"
ISSUER = json.dumps({"issuer": f"{URL}/auth/realms/saigonos"}).encode()


@pytest.fixture
def home(tmp_path, cli, gateway):
    path = tmp_path / "home"
    cli("init", "--home", path, "--url", gateway.url)
    return path


@pytest.fixture
def closed_url():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{listener.getsockname()[1]}"


@pytest.mark.parametrize("array", [False, True])
def test_doctor_passes_when_everything_works(home, cli, docker, gateway, array):
    docker.services(SERVICES, HEALTHY, array=array)

    result = cli("doctor", "--home", home)

    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "ĐẠT  postgres   đang chạy",
        "ĐẠT  routes     đã chạy xong",
        "ĐẠT  jwks       đã chạy xong",
        f"ĐẠT  Đăng nhập  Keycloak trả lời tại {gateway.url}/auth",
        "ĐẠT  API        lời gọi không có access token bị từ chối",
        "Hệ thống hoạt động bình thường.",
    ]
    assert docker.calls == [
        f"{home.resolve()}: compose config --format json",
        f"{home.resolve()}: compose ps --all --format json",
    ]


def test_doctor_reports_each_failure_and_exits_with_1(home, cli, docker, gateway):
    docker.services(SERVICES, HEALTHY[1:])
    gateway.routes["/api/"] = (200, b"[]")

    result = cli("doctor", "--home", home)

    assert result.exit_code == 1
    assert "LỖI  postgres   chưa được tạo\n" in result.output
    assert "ĐẠT  routes     đã chạy xong\n" in result.output
    assert "LỖI  API        lời gọi không có access token nhận mã 200" in result.output
    assert result.output.endswith("Có 2 mục lỗi.\n")


def test_doctor_reports_unreachable_gateway(tmp_path, cli, docker, closed_url):
    home = tmp_path / "home"
    cli("init", "--home", home, "--url", closed_url)
    docker.services(SERVICES, HEALTHY)

    result = cli("doctor", "--home", home)

    assert result.exit_code == 1
    assert f"LỖI  Đăng nhập  không kết nối được tới {closed_url}: " in result.output
    assert f"LỖI  API        không kết nối được tới {closed_url}: " in result.output


def test_doctor_stops_when_compose_fails(home, cli, docker):
    docker.services(SERVICES, HEALTHY)
    docker.reply("ps", error="Cannot connect to the Docker daemon\n", code=1)

    result = cli("doctor", "--home", home)

    assert result.exit_code == 1
    assert "Lệnh docker compose ps không chạy được: Cannot connect to the Docker daemon" in (
        result.output
    )
    assert "ĐẠT" not in result.output


@pytest.mark.parametrize(
    ("restart", "container", "expected"),
    [
        ("unless-stopped", None, (False, "chưa được tạo")),
        ("unless-stopped", {"State": "running", "Health": "healthy"}, (True, "đang chạy")),
        ("unless-stopped", {"State": "running", "Health": ""}, (True, "đang chạy")),
        ("unless-stopped", {"State": "running", "Health": "starting"}, (False, "đang khởi động")),
        (
            "unless-stopped",
            {"State": "running", "Health": "unhealthy"},
            (False, "không đạt healthcheck"),
        ),
        (
            "unless-stopped",
            {"State": "exited", "ExitCode": 137},
            (False, "đã dừng với mã thoát 137"),
        ),
        ("unless-stopped", {"State": "restarting"}, (False, "đang khởi động lại")),
        ("unless-stopped", {"State": "dead"}, (False, "không chạy, trạng thái dead")),
        ("no", None, (False, "chưa được tạo")),
        ("no", {"State": "exited", "ExitCode": 0}, (True, "đã chạy xong")),
        ("no", {"State": "exited", "ExitCode": 1}, (False, "kết thúc với mã lỗi 1")),
        ("no", {"State": "running"}, (False, "chưa chạy xong")),
    ],
)
def test_service_state(restart, container, expected):
    assert service_state({"restart": restart}, container) == expected


def test_login_state_accepts_issuer_matching_url():
    assert login_state(URL, 200, ISSUER) == (True, f"Keycloak trả lời tại {URL}/auth")


@pytest.mark.parametrize(
    ("status", "body", "detail"),
    [
        (502, b"", "Keycloak trả về mã 502"),
        (200, b"<html>", "Keycloak dùng địa chỉ None, khác với SAIGONOS_URL trong file .env"),
        (200, b"[]", "Keycloak dùng địa chỉ None, khác với SAIGONOS_URL trong file .env"),
        (
            200,
            b'{"issuer": "http://localhost:9080/auth/realms/saigonos"}',
            "Keycloak dùng địa chỉ http://localhost:9080/auth/realms/saigonos, "
            "khác với SAIGONOS_URL trong file .env",
        ),
    ],
)
def test_login_state_rejects_other_answers(status, body, detail):
    assert login_state(URL, status, body) == (False, detail)


def test_api_state_requires_401_without_token():
    assert api_state(URL, 401, b"") == (True, "lời gọi không có access token bị từ chối")
    assert api_state(URL, 200, b"[]")[0] is False


def test_gateway_checks_use_tls_for_https_address(gateway):
    checks = gateway_checks(gateway.url.replace("http://", "https://"))

    assert [check.ok for check in checks] == [False, False]
    assert all("không kết nối được" in check.detail for check in checks)
