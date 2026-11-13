# SPDX-License-Identifier: Apache-2.0
import os
import re
import stat
from importlib.resources import files

import pytest
from click.testing import CliRunner

from saigonos.cli import main
from saigonos.home import SECRET_KEYS

STACK = files("saigonos").joinpath("stack")
SETTING_KEYS = [
    "SAIGONOS_URL",
    "SAIGONOS_HTTP_HOST",
    "SAIGONOS_HTTP_PORT",
    "SAIGONOS_ADMIN_PORT",
    *SECRET_KEYS,
]


@pytest.fixture
def home(tmp_path):
    return tmp_path / "home"


@pytest.fixture
def strict_umask():
    previous = os.umask(0o077)
    yield
    os.umask(previous)


def init(*args):
    return CliRunner().invoke(main, ["init", *map(str, args)])


def read_env(home):
    lines = (home / ".env").read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line)


def stack_files(directory=STACK, prefix=""):
    for entry in directory.iterdir():
        if entry.is_dir():
            yield from stack_files(entry, f"{prefix}{entry.name}/")
        else:
            yield f"{prefix}{entry.name}", entry.read_bytes()


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_init_copies_stack_files(home):
    result = init("--home", home)

    shipped = dict(stack_files())
    assert result.exit_code == 0
    assert "compose.yaml" in shipped
    assert "config/apisix/routes/api.json" in shipped
    assert {name: (home / name).read_bytes() for name in shipped} == shipped
    assert f"Thư mục làm việc: {home}\n" in result.output


def test_init_writes_env_with_defaults_and_random_secrets(home):
    result = init("--home", home)

    env = read_env(home)
    generated = [env[key] for key in SECRET_KEYS]
    assert list(env) == SETTING_KEYS
    assert env["SAIGONOS_URL"] == "http://localhost:9080"
    assert env["SAIGONOS_HTTP_HOST"] == "127.0.0.1"
    assert env["SAIGONOS_HTTP_PORT"] == "9080"
    assert env["SAIGONOS_ADMIN_PORT"] == "9180"
    assert all(re.fullmatch(r"[A-Za-z0-9]{32}", value) for value in generated)
    assert len(set(generated)) == len(generated)
    assert not (home / ".env.tmp").exists()
    assert "Địa chỉ truy cập: http://localhost:9080\n" in result.output
    assert "Địa chỉ lắng nghe: 127.0.0.1:9080\n" in result.output
    assert f"Đã tạo {len(SECRET_KEYS)} mật khẩu ngẫu nhiên" in result.output


def test_env_defines_exactly_the_variables_required_by_compose(home):
    init("--home", home)

    compose = (home / "compose.yaml").read_text(encoding="utf-8")
    assert set(re.findall(r"\$\{(\w+):\?\}", compose)) == set(read_env(home))


def test_env_is_private_and_config_is_readable_under_strict_umask(home, strict_umask):
    init("--home", home)

    paths = [path for path in home.rglob("*") if path.name != ".env"]
    assert mode(home / ".env") == 0o600
    assert {mode(path) for path in paths if path.is_dir()} == {0o755}
    assert {mode(path) for path in paths if path.is_file()} == {0o644}


def test_init_again_keeps_env_and_restores_stack_files(home):
    init("--home", home)
    env_file = home / ".env"
    env_file.write_text(
        f"# ghi chú\n{env_file.read_text(encoding='utf-8')}EXTRA=1\n", encoding="utf-8"
    )
    before = env_file.read_text(encoding="utf-8")
    (home / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    extra_route = home / "config" / "apisix" / "routes" / "extra.json"
    extra_route.write_text("{}", encoding="utf-8")

    result = init("--home", home)

    assert result.exit_code == 0
    assert env_file.read_text(encoding="utf-8") == before
    assert (home / "compose.yaml").read_bytes() == STACK.joinpath("compose.yaml").read_bytes()
    assert extra_route.exists()
    assert "Các mật khẩu trong file .env được giữ nguyên." in result.output


def test_init_fills_only_missing_and_empty_values(home):
    kept = "da-co"
    home.mkdir()
    (home / ".env").write_text(
        f"POSTGRES_PASSWORD={kept}\nKEYCLOAK_DB_PASSWORD=\nSAIGONOS_ADMIN_PORT=9999\n",
        encoding="utf-8",
    )

    result = init("--home", home)

    env = read_env(home)
    assert set(env) == set(SETTING_KEYS)
    assert env["POSTGRES_PASSWORD"] == kept
    assert len(env["KEYCLOAK_DB_PASSWORD"]) == 32
    assert env["SAIGONOS_ADMIN_PORT"] == "9999"
    assert f"Đã tạo {len(SECRET_KEYS) - 1} mật khẩu ngẫu nhiên" in result.output


def test_init_adds_http_host_to_env_of_older_version(home):
    init("--home", home)
    env_file = home / ".env"
    older = [
        line
        for line in env_file.read_text(encoding="utf-8").splitlines()
        if not line.startswith("SAIGONOS_HTTP_HOST=")
    ]
    env_file.write_text("\n".join(older) + "\n", encoding="utf-8")

    result = init("--home", home)

    assert result.exit_code == 0
    assert env_file.read_text(encoding="utf-8").splitlines() == [
        *older,
        "SAIGONOS_HTTP_HOST=127.0.0.1",
    ]


def test_options_set_url_and_ports(home):
    options = ["--url", "https://DX.example.com/", "--http-port", 8000, "--admin-port", 9999]

    result = init("--home", home, *options)

    env = read_env(home)
    assert env["SAIGONOS_URL"] == "https://dx.example.com"
    assert env["SAIGONOS_HTTP_PORT"] == "8000"
    assert env["SAIGONOS_ADMIN_PORT"] == "9999"
    assert "Địa chỉ truy cập: https://dx.example.com\n" in result.output


def test_url_follows_http_port_until_set_explicitly(home):
    init("--home", home, "--http-port", 8000)
    assert read_env(home)["SAIGONOS_URL"] == "http://localhost:8000"

    init("--home", home, "--http-port", 80)
    assert read_env(home)["SAIGONOS_URL"] == "http://localhost"

    init("--home", home, "--url", "https://dx.example.com")
    init("--home", home, "--http-port", 8001)
    env = read_env(home)
    assert env["SAIGONOS_URL"] == "https://dx.example.com"
    assert env["SAIGONOS_HTTP_PORT"] == "8001"


def test_http_host_is_kept_until_set_again(home):
    result = init("--home", home, "--http-host", "192.168.1.10")
    assert read_env(home)["SAIGONOS_HTTP_HOST"] == "192.168.1.10"
    assert "Địa chỉ lắng nghe: 192.168.1.10:9080\n" in result.output

    result = init("--home", home, "--http-port", 8000)
    assert read_env(home)["SAIGONOS_HTTP_HOST"] == "192.168.1.10"
    assert "Địa chỉ lắng nghe: 192.168.1.10:8000\n" in result.output

    result = init("--home", home, "--http-host", "0:0:0:0:0:0:0:1")
    assert read_env(home)["SAIGONOS_HTTP_HOST"] == "::1"
    assert "Địa chỉ lắng nghe: [::1]:8000\n" in result.output


@pytest.mark.parametrize("host", ["localhost", "256.0.0.1", "127.0.0.1:9080", "10.0.0.0/8", ""])
def test_invalid_http_host_is_rejected(home, host):
    result = init("--home", home, "--http-host", host)

    assert result.exit_code == 2
    assert "Invalid value for '--http-host'" in result.output
    assert not home.exists()


@pytest.mark.parametrize(
    "url",
    [
        "dx.example.com",
        "ftp://dx.example.com",
        "http://",
        "http://dx.example.com/app",
        "http://dx.example.com?a=1",
        "http://dx.example.com#a",
        "http://user@dx.example.com",
        "http://dx.example.com:abc",
        "http://dx.example.com:0",
        "http://[::1",
    ],
)
def test_invalid_url_is_rejected(home, url):
    result = init("--home", home, "--url", url)

    assert result.exit_code == 2
    assert "Invalid value for '--url'" in result.output
    assert not home.exists()


@pytest.mark.parametrize("option", ["--http-port", "--admin-port"])
@pytest.mark.parametrize("port", ["0", "65536", "abc"])
def test_invalid_port_is_rejected(home, option, port):
    result = init("--home", home, option, port)

    assert result.exit_code == 2
    assert not home.exists()


def test_home_comes_from_environment_variable(home, monkeypatch):
    monkeypatch.setenv("SAIGONOS_HOME", str(home))

    result = init()

    assert result.exit_code == 0
    assert (home / ".env").exists()
    assert result.output.endswith("Để khởi động, chạy lệnh: saigonos up\n")


def test_default_home_is_in_user_home_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    result = init()

    assert result.exit_code == 0
    assert (tmp_path / "saigonos" / "compose.yaml").exists()
    assert result.output.endswith("Để khởi động, chạy lệnh: saigonos up\n")


def test_start_hint_repeats_home_given_on_command_line(tmp_path):
    home = tmp_path / "thư mục"

    result = init("--home", home)

    assert result.output.endswith(f"Để khởi động, chạy lệnh: saigonos up --home '{home}'\n")


def test_unwritable_home_is_reported(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")

    result = init("--home", blocker / "home")

    assert result.exit_code == 1
    assert "Không ghi được vào" in result.output
