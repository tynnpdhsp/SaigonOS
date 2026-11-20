# SPDX-License-Identifier: Apache-2.0
import json
import socket
import ssl

import pytest

from saigonos.doctor import (
    api_state,
    core_state,
    gateway_checks,
    login_state,
    operaton_state,
    realtime_state,
    service_state,
    websocket_accept,
)

CADDY_SERVICE = {"caddy": {"restart": "unless-stopped"}}
CADDY_RUNNING = {"Service": "caddy", "State": "running", "Health": "healthy", "ExitCode": 0}
READ_ROOT_CERTIFICATE = "compose exec -T caddy cat /data/caddy/pki/authorities/local/root.crt"

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
REALM_PATH = "/auth/realms/saigonos"
TOKEN_PATH = f"{REALM_PATH}/protocol/openid-connect/token"
LOGIN_PAGE = f"{REALM_PATH}/protocol/openid-connect/auth"
CALLBACK_PATH = "/operaton/login/oauth2/code/operaton"
OPERATON_OK = "Operaton chuyển tới trang đăng nhập, REST của Operaton bị chặn"
REALTIME_OK = "Centrifugo nhận kết nối WebSocket, API của Centrifugo bị chặn"


def discovery(issuer=f"{URL}{REALM_PATH}", token_endpoint=f"{URL}{TOKEN_PATH}"):
    return json.dumps({"issuer": issuer, "token_endpoint": token_endpoint}).encode()


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


@pytest.fixture
def caddy_home(tmp_path, cli, docker, gateway):
    path = tmp_path / "home"
    cli("init", "--home", path, "--url", gateway.url.replace("http://", "https://"), "--caddy")
    docker.services(SERVICES | CADDY_SERVICE, [*HEALTHY, CADDY_RUNNING])
    return path


@pytest.fixture
def trusted(monkeypatch):
    certificates = []
    monkeypatch.setattr(
        ssl.SSLContext, "load_verify_locations", lambda self, cadata: certificates.append(cadata)
    )
    return certificates


@pytest.mark.parametrize("array", [False, True])
def test_doctor_passes_when_everything_works(home, cli, docker, gateway, array):
    docker.services(SERVICES, HEALTHY, array=array)

    result = cli("doctor", "--home", home)

    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "BÌNH THƯỜNG    postgres      đang chạy",
        "BÌNH THƯỜNG    routes        đã chạy xong",
        "BÌNH THƯỜNG    jwks          đã chạy xong",
        f"BÌNH THƯỜNG    Đăng nhập     Keycloak trả lời tại {gateway.url}/auth",
        "BÌNH THƯỜNG    API           PostgREST trả lời, access token không hợp lệ bị từ chối",
        "BÌNH THƯỜNG    Core API      service core trả lời, access token không hợp lệ bị từ chối",
        f"BÌNH THƯỜNG    Operaton      {OPERATON_OK}",
        f"BÌNH THƯỜNG    Centrifugo    {REALTIME_OK}",
        "Hệ thống hoạt động bình thường.",
    ]
    assert docker.calls == [
        f"{home.resolve()}: compose config --format json",
        f"{home.resolve()}: compose ps --all --format json",
    ]


def test_doctor_reports_each_failure_and_exits_with_1(home, cli, docker, gateway):
    docker.services(SERVICES, HEALTHY[1:])
    gateway.routes["/api/", False] = (401, b"")

    result = cli("doctor", "--home", home)

    assert result.exit_code == 1
    assert "LỖI            postgres      chưa được tạo\n" in result.output
    assert "BÌNH THƯỜNG    routes        đã chạy xong\n" in result.output
    assert "LỖI            API           lời gọi không có access token nhận mã 401" in result.output
    assert result.output.endswith("Có 2 mục lỗi.\n")


def test_doctor_reports_gateway_that_accepts_invalid_access_token(home, cli, docker, gateway):
    docker.services(SERVICES, HEALTHY)
    gateway.routes["/api/", True] = (200, b"{}")

    result = cli("doctor", "--home", home)

    assert result.exit_code == 1
    assert (
        "LỖI            API           lời gọi có access token không hợp lệ nhận mã 200, "
        "đúng ra là 401\n" in result.output
    )
    assert result.output.endswith("Có 1 mục lỗi.\n")


def test_doctor_reports_unreachable_gateway(tmp_path, cli, docker, closed_url):
    home = tmp_path / "home"
    cli("init", "--home", home, "--url", closed_url)
    docker.services(SERVICES, HEALTHY)

    result = cli("doctor", "--home", home)

    assert result.exit_code == 1
    assert f"LỖI            Đăng nhập     không kết nối được tới {closed_url}: " in result.output
    assert f"LỖI            API           không kết nối được tới {closed_url}: " in result.output
    assert f"LỖI            Core API      không kết nối được tới {closed_url}: " in result.output
    assert f"LỖI            Centrifugo    không kết nối được tới {closed_url}: " in result.output
    assert result.output.endswith("Có 5 mục lỗi.\n")


def test_doctor_stops_when_compose_fails(home, cli, docker):
    docker.services(SERVICES, HEALTHY)
    docker.reply("ps", error="Cannot connect to the Docker daemon\n", code=1)

    result = cli("doctor", "--home", home)

    assert result.exit_code == 1
    assert "Lệnh docker compose ps không chạy được: Cannot connect to the Docker daemon" in (
        result.output
    )
    assert "BÌNH THƯỜNG" not in result.output


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
            (False, "healthcheck báo lỗi"),
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


def test_login_state_accepts_addresses_matching_url():
    assert login_state(URL, 200, discovery()) == (True, f"Keycloak trả lời tại {URL}/auth")


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
    ids=["ma-502", "html", "mang-json", "issuer-khac"],
)
def test_login_state_rejects_other_answers(status, body, detail):
    assert login_state(URL, status, body) == (False, detail)


@pytest.mark.parametrize(
    ("token_endpoint", "seen"),
    [
        (f"http://dx.example.com:9080{TOKEN_PATH}", "http://dx.example.com:9080"),
        (f"https://dx.example.com{TOKEN_PATH}", "https://dx.example.com"),
        (None, "None"),
    ],
)
def test_login_state_rejects_token_endpoint_of_another_address(token_endpoint, seen):
    ok, detail = login_state(URL, 200, discovery(token_endpoint=token_endpoint))

    assert ok is False
    assert detail.startswith(
        f"Keycloak nhận lời gọi qua địa chỉ {seen}, khác với SAIGONOS_URL trong file .env. "
    )
    assert detail.endswith("X-Forwarded-Host và X-Forwarded-Port của reverse proxy")


def test_doctor_reports_reverse_proxy_that_sends_wrong_address(home, cli, docker, gateway):
    docker.services(SERVICES, HEALTHY)
    gateway.healthy(seen_url=f"{URL}:9080")

    result = cli("doctor", "--home", home)

    assert result.exit_code == 1
    assert (
        f"LỖI            Đăng nhập     Keycloak nhận lời gọi qua địa chỉ {URL}:9080, "
        in result.output
    )
    assert f"LỖI            Operaton      Operaton nhận lời gọi qua địa chỉ {URL}:9080, " in (
        result.output
    )
    assert result.output.endswith("Có 2 mục lỗi.\n")


def test_api_state_requires_answer_without_token_and_401_for_invalid_token():
    assert api_state(200, 401) == (
        True,
        "PostgREST trả lời, access token không hợp lệ bị từ chối",
    )
    assert api_state(401, 401) == (
        False,
        "lời gọi không có access token nhận mã 401, đúng ra là 200",
    )
    assert api_state(200, 200) == (
        False,
        "lời gọi có access token không hợp lệ nhận mã 200, đúng ra là 401",
    )


def test_core_state_requires_health_and_401_for_invalid_token():
    assert core_state(200, 401) == (
        True,
        "service core trả lời, access token không hợp lệ bị từ chối",
    )
    assert core_state(502, 401) == (False, "lời gọi /core/health nhận mã 502, đúng ra là 200")
    assert core_state(200, 200) == (
        False,
        "lời gọi có access token không hợp lệ nhận mã 200, đúng ra là 401",
    )


@pytest.mark.parametrize(
    ("route", "reply", "detail"),
    [
        (("/core/health", False), (503, b""), "lời gọi /core/health nhận mã 503, đúng ra là 200"),
        (
            ("/core/me", True),
            (200, b"{}"),
            "lời gọi có access token không hợp lệ nhận mã 200, đúng ra là 401",
        ),
    ],
    ids=["health-503", "token-sai-nhan-200"],
)
def test_doctor_reports_core_service_that_fails_through_gateway(
    home, cli, docker, gateway, route, reply, detail
):
    docker.services(SERVICES, HEALTHY)
    gateway.routes[route] = reply

    result = cli("doctor", "--home", home)

    assert result.exit_code == 1
    assert f"LỖI            Core API      {detail}\n" in result.output
    assert result.output.endswith("Có 1 mục lỗi.\n")


def test_gateway_checks_use_tls_for_https_address(gateway):
    checks = gateway_checks(gateway.url.replace("http://", "https://"))

    assert [check.ok for check in checks] == [False, False, False, False, False]
    assert all("không kết nối được" in check.detail for check in checks)


def test_doctor_trusts_root_certificate_of_caddy(caddy_home, cli, docker, trusted):
    docker.reply("exec", output="chứng chỉ gốc\n")

    result = cli("doctor", "--home", caddy_home)

    assert "BÌNH THƯỜNG    caddy         đang chạy\n" in result.output
    assert docker.calls[-1] == f"{caddy_home.resolve()}: {READ_ROOT_CERTIFICATE}"
    assert trusted == ["chứng chỉ gốc\n"] * 5


@pytest.mark.parametrize("reply", [{"output": ""}, {"error": "No such file\n", "code": 1}])
def test_doctor_trusts_only_system_certificates_without_root_certificate_of_caddy(
    caddy_home, cli, docker, trusted, reply
):
    docker.reply("exec", **reply)

    result = cli("doctor", "--home", caddy_home)

    assert "BÌNH THƯỜNG    caddy         đang chạy\n" in result.output
    assert docker.calls[-1] == f"{caddy_home.resolve()}: {READ_ROOT_CERTIFICATE}"
    assert trusted == []


def test_doctor_does_not_ask_for_root_certificate_without_caddy(home, cli, docker):
    docker.services(SERVICES, HEALTHY)

    cli("doctor", "--home", home)

    assert not any(" exec " in call for call in docker.calls)


def login_redirect(url=URL, callback=f"{URL}{CALLBACK_PATH}"):
    return f"{url}{LOGIN_PAGE}?client_id=operaton&redirect_uri={callback}&state=x"


def test_operaton_state_accepts_login_page_at_url_and_closed_rest():
    assert operaton_state(URL, 302, login_redirect(), 404) == (True, OPERATON_OK)


@pytest.mark.parametrize(
    ("status", "location", "rest", "detail"),
    [
        (
            502,
            None,
            404,
            "lời gọi /operaton/oauth2/authorization/operaton nhận mã 502, đúng ra là 302",
        ),
        (
            302,
            login_redirect(url="http://localhost:9080"),
            404,
            f"Operaton chuyển người dùng tới http://localhost:9080{LOGIN_PAGE}, "
            "không phải trang đăng nhập của Keycloak",
        ),
        (
            302,
            None,
            404,
            "Operaton không cho biết địa chỉ của trang đăng nhập",
        ),
        (
            302,
            login_redirect(),
            200,
            "REST của Operaton nhận mã 200 qua API Gateway, đúng ra là 404",
        ),
    ],
    ids=["ma-502", "sai-trang-dang-nhap", "thieu-location", "rest-mo"],
)
def test_operaton_state_rejects_other_answers(status, location, rest, detail):
    assert operaton_state(URL, status, location, rest) == (False, detail)


def test_operaton_state_names_address_seen_by_operaton():
    callback = f"http://dx.example.com:9080{CALLBACK_PATH}"

    ok, detail = operaton_state(URL, 302, login_redirect(callback=callback), 404)

    assert ok is False
    assert detail.startswith(
        "Operaton nhận lời gọi qua địa chỉ http://dx.example.com:9080, "
        "khác với SAIGONOS_URL trong file .env. "
    )


@pytest.mark.parametrize(
    ("route", "reply", "detail"),
    [
        (
            ("/operaton/oauth2/authorization/operaton", False),
            (404, b""),
            "lời gọi /operaton/oauth2/authorization/operaton nhận mã 404, đúng ra là 302",
        ),
        (
            ("/operaton/engine-rest/version", False),
            (200, b"{}"),
            "REST của Operaton nhận mã 200 qua API Gateway, đúng ra là 404",
        ),
    ],
    ids=["dang-nhap-404", "rest-mo"],
)
def test_doctor_reports_operaton_that_fails_through_gateway(
    home, cli, docker, gateway, route, reply, detail
):
    docker.services(SERVICES, HEALTHY)
    gateway.routes[route] = reply

    result = cli("doctor", "--home", home)

    assert result.exit_code == 1
    assert f"LỖI            Operaton      {detail}\n" in result.output
    assert result.output.endswith("Có 1 mục lỗi.\n")


def test_websocket_accept_follows_example_of_rfc_6455():
    assert websocket_accept("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="


def test_realtime_state_accepts_websocket_and_closed_api():
    assert realtime_state(URL, 101, True, 404) == (True, REALTIME_OK)


@pytest.mark.parametrize(
    ("status", "accepted", "api", "detail"),
    [
        (
            400,
            False,
            404,
            "Centrifugo không nhận được yêu cầu kết nối WebSocket. "
            "Hãy kiểm tra header Upgrade và Connection của reverse proxy",
        ),
        (
            403,
            False,
            404,
            f"Centrifugo từ chối kết nối từ trang {URL}. "
            "Hãy chạy lệnh saigonos init rồi saigonos up để Centrifugo nhận địa chỉ này",
        ),
        (502, False, 404, "lời gọi /realtime/connection/websocket nhận mã 502, đúng ra là 101"),
        (101, False, 404, "API Gateway không trả lời đúng giao thức WebSocket"),
        (101, True, 405, "API của Centrifugo nhận mã 405 qua API Gateway, đúng ra là 404"),
    ],
    ids=["thieu-upgrade", "origin-khac", "ma-502", "sai-accept", "api-mo"],
)
def test_realtime_state_rejects_other_answers(status, accepted, api, detail):
    assert realtime_state(URL, status, accepted, api) == (False, detail)


def test_doctor_opens_websocket_with_url_as_origin(home, cli, docker, gateway):
    docker.services(SERVICES, HEALTHY)

    result = cli("doctor", "--home", home)

    assert f"BÌNH THƯỜNG    Centrifugo    {REALTIME_OK}\n" in result.output
    assert gateway.requests[-2:] == ["/realtime/connection/websocket", "/realtime/api"]


@pytest.mark.parametrize(
    ("change", "detail"),
    [
        (
            {"upgrade": 400},
            "Centrifugo không nhận được yêu cầu kết nối WebSocket. "
            "Hãy kiểm tra header Upgrade và Connection của reverse proxy",
        ),
        ({"accept": False}, "API Gateway không trả lời đúng giao thức WebSocket"),
    ],
    ids=["reverse-proxy-bo-upgrade", "sai-accept"],
)
def test_doctor_reports_websocket_that_fails_through_gateway(
    home, cli, docker, gateway, change, detail
):
    docker.services(SERVICES, HEALTHY)
    for name, value in change.items():
        setattr(gateway, name, value)

    result = cli("doctor", "--home", home)

    assert result.exit_code == 1
    assert f"LỖI            Centrifugo    {detail}\n" in result.output
    assert result.output.endswith("Có 1 mục lỗi.\n")


def test_doctor_reports_api_of_centrifugo_open_through_gateway(home, cli, docker, gateway):
    docker.services(SERVICES, HEALTHY)
    gateway.routes["/realtime/api", False] = (405, b"")

    result = cli("doctor", "--home", home)

    assert result.exit_code == 1
    assert "LỖI            Centrifugo    API của Centrifugo nhận mã 405 qua API Gateway" in (
        result.output
    )
