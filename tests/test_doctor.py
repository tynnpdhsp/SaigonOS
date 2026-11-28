# SPDX-License-Identifier: Apache-2.0
import json
import re
import socket
import ssl

import pytest

from saigonos import doctor
from saigonos.doctor import (
    WAF_PROBE_PATH,
    api_state,
    app_state,
    core_state,
    gateway_checks,
    login_state,
    monitoring_state,
    operaton_state,
    realtime_state,
    service_state,
    settled_targets,
    waf_state,
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
WAF_OK = "API Gateway chặn lời gọi có dấu hiệu tấn công"
WAF_DETECT = "chế độ chỉ ghi log, lời gọi có dấu hiệu tấn công không bị chặn"
WAF_REPLY = b'{"code": "SGN04"}'


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
        f"BÌNH THƯỜNG    Tường lửa     {WAF_OK}",
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
    assert f"LỖI            Tường lửa     không kết nối được tới {closed_url}: " in result.output
    assert result.output.endswith("Có 6 mục lỗi.\n")


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

    assert [check.ok for check in checks] == [False] * 6
    assert all("không kết nối được" in check.detail for check in checks)


def test_doctor_trusts_root_certificate_of_caddy(caddy_home, cli, docker, trusted):
    docker.reply("exec", output="chứng chỉ gốc\n")

    result = cli("doctor", "--home", caddy_home)

    assert "BÌNH THƯỜNG    caddy         đang chạy\n" in result.output
    assert docker.calls[-1] == f"{caddy_home.resolve()}: {READ_ROOT_CERTIFICATE}"
    assert trusted == ["chứng chỉ gốc\n"] * 6


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
    assert gateway.requests[-3:-1] == ["/realtime/connection/websocket", "/realtime/api"]


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


GUARDED = "ứng dụng trả lời tại {path}, API đòi đăng nhập theo luật truy cập"


def installed(home, name, ui=False):
    folder = home / "apps" / name
    folder.mkdir(parents=True)
    manifest = {"name": name} | ({"ui": "ui"} if ui else {})
    (folder / "saigonos-app.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_doctor_adds_one_line_for_each_installed_app(home, cli, docker, gateway):
    docker.services(SERVICES, HEALTHY)
    installed(home, "don-tu")
    installed(home, "nghi-phep", ui=True)
    (home / "apps" / ".nghi-phep.old").mkdir()
    for path in ("/apps/don-tu/api/", "/apps/nghi-phep/api/", "/apps/nghi-phep/"):
        gateway.routes[path, False] = (200, b"{}")

    result = cli("doctor", "--home", home)

    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[-3:] == [
        "BÌNH THƯỜNG    Ứng dụng don-tu       API của ứng dụng trả lời tại /apps/don-tu/api/",
        "BÌNH THƯỜNG    Ứng dụng nghi-phep    "
        "API và giao diện của ứng dụng trả lời tại /apps/nghi-phep/",
        "Hệ thống hoạt động bình thường.",
    ]


def test_doctor_reports_app_that_does_not_answer(home, cli, docker, gateway):
    docker.services(SERVICES, HEALTHY)
    installed(home, "nghi-phep", ui=True)
    gateway.routes["/apps/nghi-phep/api/", False] = (200, b"{}")
    (home / "apps" / "hong").mkdir()
    (home / "apps" / "hong" / "saigonos-app.json").write_text("[]", encoding="utf-8")

    result = cli("doctor", "--home", home)

    assert result.exit_code == 1
    assert re.search(
        r"LỖI +Ứng dụng hong +không đọc được bản khai báo trong thư mục apps", result.output
    )
    assert "lời gọi /apps/nghi-phep/ nhận mã 404, đúng ra là 200" in result.output


@pytest.mark.parametrize(
    ("api", "code", "page", "ok", "detail"),
    [
        (404, None, None, False, "lời gọi /apps/x/api/ nhận mã 404, đúng ra là 200"),
        (406, None, 200, False, "lời gọi /apps/x/api/ nhận mã 406, đúng ra là 200"),
        (200, None, None, True, "API của ứng dụng trả lời tại /apps/x/api/"),
        (200, None, 500, False, "lời gọi /apps/x/ nhận mã 500, đúng ra là 200"),
        (401, "SGN03", None, True, GUARDED.format(path="/apps/x/api/")),
        (403, "SGN03", 200, True, GUARDED.format(path="/apps/x/")),
        (401, "SGN03", 404, False, "lời gọi /apps/x/ nhận mã 404, đúng ra là 200"),
        (401, None, None, False, "lời gọi /apps/x/api/ nhận mã 401, đúng ra là 200"),
        (503, "SGN03", None, False, "lời gọi /apps/x/api/ nhận mã 503, đúng ra là 200"),
    ],
    ids=[
        "khong-co-route",
        "schema-chua-mo",
        "khong-giao-dien",
        "giao-dien-loi",
        "luat-doi-dang-nhap",
        "luat-chan-dai-mang",
        "luat-doi-dang-nhap-giao-dien-loi",
        "401-khong-phai-cua-luat",
        "opa-dung",
    ],
)
def test_app_state_names_failing_call(api, code, page, ok, detail):
    assert app_state("x", api, page, code) == (ok, detail)


def test_doctor_accepts_app_whose_access_rules_require_login(home, cli, docker, gateway):
    docker.services(SERVICES, HEALTHY)
    installed(home, "phong-may", ui=True)
    gateway.routes["/apps/phong-may/api/", False] = (401, b'{"code": "SGN03"}')
    gateway.routes["/apps/phong-may/", False] = (200, b"<html>")

    result = cli("doctor", "--home", home)

    assert result.exit_code == 0, result.output
    assert f"Ứng dụng phong-may    {GUARDED.format(path='/apps/phong-may/')}" in result.output


def test_doctor_reports_unreachable_gateway_for_apps(tmp_path, cli, docker, closed_url):
    home = tmp_path / "home"
    cli("init", "--home", home, "--url", closed_url)
    docker.services(SERVICES, HEALTHY)
    installed(home, "nghi-phep")

    result = cli("doctor", "--home", home)

    assert f"Ứng dụng nghi-phep    không kết nối được tới {closed_url}" in result.output


@pytest.mark.parametrize(
    ("mode", "status", "body", "ok", "detail"),
    [
        ("block", 403, WAF_REPLY, True, WAF_OK),
        ("block", 200, b"{}", False, "nhận mã 200, đúng ra là 403 với mã SGN04"),
        ("block", 403, b'{"code": "SGN03"}', False, "nhận mã 403, đúng ra là 403 với mã SGN04"),
        ("block", 403, b"<html>", False, "nhận mã 403, đúng ra là 403 với mã SGN04"),
        ("detect", 200, b"{}", True, WAF_DETECT),
        ("detect", 403, WAF_REPLY, False, "là detect nhưng lời gọi vẫn bị chặn"),
        ("chan", 403, WAF_REPLY, False, "là chan, chỉ dùng block hoặc detect"),
    ],
    ids=[
        "chan-dung-ma",
        "de-lot",
        "403-cua-opa",
        "403-khong-phai-json",
        "chi-ghi-log",
        "chi-ghi-log-nhung-van-chan",
        "che-do-sai",
    ],
)
def test_waf_state_follows_mode_in_env(mode, status, body, ok, detail):
    result = waf_state(mode, status, body)

    assert result[0] is ok
    assert detail in result[1]


def test_doctor_sends_attack_with_query_string_and_reads_mode_from_env(home, cli, docker, gateway):
    docker.services(SERVICES, HEALTHY)
    env = home / ".env"
    env.write_text(env.read_text(encoding="utf-8") + "SAIGONOS_WAF_MODE=detect\n", encoding="utf-8")
    gateway.routes[WAF_PROBE_PATH, False] = (200, b"{}")

    result = cli("doctor", "--home", home)

    assert result.exit_code == 0
    assert f"BÌNH THƯỜNG    Tường lửa     {WAF_DETECT}\n" in result.output
    assert WAF_PROBE_PATH in gateway.requests


def test_doctor_reports_gateway_that_lets_attack_through(home, cli, docker, gateway):
    docker.services(SERVICES, HEALTHY)
    gateway.routes[WAF_PROBE_PATH, False] = (200, b"{}")

    result = cli("doctor", "--home", home)

    assert result.exit_code == 1
    assert "LỖI            Tường lửa     lời gọi có dấu hiệu tấn công nhận mã 200" in result.output


MONITORING_OK = "Grafana trả lời tại /grafana/, Prometheus đọc metrics của 2 target"
GRAFANA_HEALTH = b'{"database": "ok", "version": "13.3.1"}'
READ_TARGETS = (
    "compose exec -T prometheus wget -q -O - http://127.0.0.1:9090/api/v1/targets?state=active"
)


def targets(*healths):
    jobs = ("apisix", "keycloak", "loki")
    return [
        {"labels": {"job": job}, "health": health}
        for job, health in zip(jobs[: len(healths)], healths, strict=True)
    ]


@pytest.mark.parametrize(
    ("status", "body", "found", "ok", "detail"),
    [
        (200, GRAFANA_HEALTH, targets("up", "up"), True, MONITORING_OK),
        (403, b"", targets("up"), False, "lời gọi /grafana/api/health nhận mã 403, đúng ra là 200"),
        (200, b'{"database": "failing"}', targets("up"), False, "nhận mã 200, đúng ra là 200"),
        (200, b"khong-phai-json", targets("up"), False, "nhận mã 200, đúng ra là 200"),
        (200, GRAFANA_HEALTH, None, False, "không đọc được danh sách target của Prometheus"),
        (
            200,
            GRAFANA_HEALTH,
            targets("down", "up", "down"),
            False,
            "Prometheus không đọc được metrics của apisix, loki",
        ),
        (200, GRAFANA_HEALTH, [], False, "Prometheus chưa có target nào"),
        (
            200,
            GRAFANA_HEALTH,
            targets("up", "unknown", "unknown"),
            False,
            "Prometheus chưa đọc lần nào metrics của keycloak, loki",
        ),
    ],
    ids=[
        "dat",
        "bi-chan",
        "co-so-du-lieu-loi",
        "khong-phai-json",
        "khong-doc-duoc",
        "target-loi",
        "danh-sach-rong",
        "chua-doc-lan-nao",
    ],
)
def test_monitoring_state_needs_grafana_and_every_target(status, body, found, ok, detail):
    state = monitoring_state(status, body, found)

    assert state[0] is ok
    assert detail in state[1]


@pytest.fixture
def scrapes(monkeypatch):
    replies, sleeps = [], []
    monkeypatch.setattr(doctor, "prometheus_targets", lambda home: replies.pop(0))
    monkeypatch.setattr(doctor.time, "sleep", sleeps.append)
    return replies, sleeps


def test_doctor_waits_until_prometheus_has_read_every_target_once(scrapes, tmp_path):
    replies, sleeps = scrapes
    replies += [[], targets("up", "unknown"), targets("up", "down")]

    assert settled_targets(tmp_path) == targets("up", "down")
    assert sleeps == [doctor.TARGETS_POLL] * 2


def test_doctor_stops_waiting_for_targets_after_its_limit(scrapes, monkeypatch, tmp_path):
    replies, sleeps = scrapes
    replies += [targets("unknown")]
    monkeypatch.setattr(doctor, "TARGETS_WAIT", 0)

    assert settled_targets(tmp_path) == targets("unknown")
    assert sleeps == []


def test_doctor_does_not_wait_when_targets_cannot_be_read(scrapes, tmp_path):
    replies, sleeps = scrapes
    replies += [None]

    assert settled_targets(tmp_path) is None
    assert sleeps == []


@pytest.fixture
def monitoring_home(home, docker, gateway):
    grafana = {"Service": "grafana", "State": "running", "Health": "healthy", "ExitCode": 0}
    docker.services(SERVICES | {"grafana": {"restart": "unless-stopped"}}, [*HEALTHY, grafana])
    gateway.routes["/grafana/api/health", False] = (200, GRAFANA_HEALTH)
    return home


def test_doctor_checks_grafana_and_targets_of_prometheus_when_monitoring_is_on(
    monitoring_home, cli, docker
):
    docker.reply("exec", output=json.dumps({"data": {"activeTargets": targets("up", "up")}}))

    result = cli("doctor", "--home", monitoring_home)

    assert result.exit_code == 0, result.output
    assert f"BÌNH THƯỜNG    Giám sát      {MONITORING_OK}\n" in result.output
    assert f"{monitoring_home.resolve()}: {READ_TARGETS}" in docker.calls


def test_doctor_reports_target_that_prometheus_cannot_read(monitoring_home, cli, docker):
    docker.reply("exec", output=json.dumps({"data": {"activeTargets": targets("up", "down")}}))

    result = cli("doctor", "--home", monitoring_home)

    assert result.exit_code == 1
    assert "Prometheus không đọc được metrics của keycloak" in result.output


def test_doctor_skips_monitoring_when_grafana_is_not_in_compose(home, cli, docker):
    docker.services(SERVICES, HEALTHY)

    result = cli("doctor", "--home", home)

    assert "Giám sát" not in result.output
    assert not any(" exec " in call for call in docker.calls)
