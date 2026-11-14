# SPDX-License-Identifier: Apache-2.0
import secrets
import string
from importlib.resources import files
from importlib.resources.abc import Traversable
from ipaddress import ip_address
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlsplit

DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 9080
DEFAULT_ADMIN_PORT = 9180
DEFAULT_CADDY_HTTP_PORT = 80
DEFAULT_HTTPS_PORT = 443
CADDY_PROFILE = "caddy"
OPTIONAL_SERVICES = (CADDY_PROFILE,)
SECRET_KEYS = (
    "POSTGRES_PASSWORD",
    "KEYCLOAK_DB_PASSWORD",
    "KEYCLOAK_ADMIN_PASSWORD",
    "POSTGREST_DB_PASSWORD",
    "APISIX_ADMIN_KEY",
)
SECRET_ALPHABET = string.ascii_letters + string.digits
SECRET_LENGTH = 32


class Initialized(NamedTuple):
    url: str
    listen: str
    new_secrets: int
    caddy: bool


class SettingsError(Exception):
    pass


def new_secret() -> str:
    return "".join(secrets.choice(SECRET_ALPHABET) for _ in range(SECRET_LENGTH))


def local_url(port: str) -> str:
    return "http://localhost" if port == "80" else f"http://localhost:{port}"


def listen_address(host: str, port: str) -> str:
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def read_env_lines(home: Path) -> list[str]:
    env_file = home / ".env"
    return env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []


def parse_env(lines: list[str]) -> dict[str, str]:
    pairs = (line.partition("=") for line in lines)
    return {key.strip(): value.strip() for key, separator, value in pairs if separator}


def set_value(lines: list[str], key: str, value: str) -> None:
    matches = [index for index, line in enumerate(lines) if line.partition("=")[0].strip() == key]
    if matches:
        lines[matches[-1]] = f"{key}={value}"
    else:
        lines.append(f"{key}={value}")


def read_url(home: Path) -> str:
    env = parse_env(read_env_lines(home))
    http_port = env.get("SAIGONOS_HTTP_PORT") or str(DEFAULT_HTTP_PORT)
    return env.get("SAIGONOS_URL") or local_url(http_port)


def split_profiles(value: str) -> list[str]:
    return [name.strip() for name in value.split(",") if name.strip()]


def disabled_services(home: Path) -> list[str]:
    env = parse_env(read_env_lines(home))
    if "COMPOSE_PROFILES" not in env:
        return []
    enabled = split_profiles(env["COMPOSE_PROFILES"])
    return [name for name in OPTIONAL_SERVICES if name not in enabled]


def https_port(url: str) -> str | None:
    try:
        parts = urlsplit(url)
        return str(parts.port or DEFAULT_HTTPS_PORT) if parts.scheme == "https" else None
    except ValueError:
        return None


def reachable_from_caddy(http_host: str) -> bool:
    if http_host == DEFAULT_HTTP_HOST:
        return True
    try:
        address = ip_address(http_host)
    except ValueError:
        return False
    return address.version == 4 and address.is_unspecified


def check_caddy(url: str, http_host: str, http_port: str, caddy_http_port: str) -> None:
    caddy_https_port = https_port(url)
    if caddy_https_port is None:
        raise SettingsError(
            "Caddy đang bật nên địa chỉ truy cập phải có dạng https://tên-máy. "
            "Hãy đặt địa chỉ bằng tùy chọn --url hoặc tắt Caddy bằng tùy chọn --no-caddy."
        )
    if not reachable_from_caddy(http_host):
        raise SettingsError(
            "Caddy đang bật nên cổng HTTP của API Gateway phải lắng nghe trên địa chỉ "
            f"{DEFAULT_HTTP_HOST}. Hãy đặt lại bằng tùy chọn --http-host {DEFAULT_HTTP_HOST}."
        )
    if http_port in {caddy_http_port, caddy_https_port}:
        raise SettingsError(
            f"Cổng HTTP {http_port} của API Gateway trùng với cổng mà Caddy sử dụng. "
            "Hãy chọn cổng khác bằng tùy chọn --http-port."
        )


def copy_tree(source: Traversable, target: Path) -> None:
    for entry in source.iterdir():
        path = target / entry.name
        if entry.is_dir():
            path.mkdir(exist_ok=True)
            path.chmod(0o755)
            copy_tree(entry, path)
        else:
            path.write_bytes(entry.read_bytes())
            path.chmod(0o644)


def write_private(path: Path, text: str) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.unlink(missing_ok=True)
    temporary.touch(mode=0o600)
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def init_home(
    home: Path,
    url: str | None = None,
    http_host: str | None = None,
    http_port: int | None = None,
    admin_port: int | None = None,
    caddy: bool | None = None,
) -> Initialized:
    lines = read_env_lines(home)
    current = parse_env(lines)

    old_http_port = current.get("SAIGONOS_HTTP_PORT") or str(DEFAULT_HTTP_PORT)
    new_http_port = str(http_port or old_http_port)
    old_url = current.get("SAIGONOS_URL") or local_url(old_http_port)
    if url is None:
        url = local_url(new_http_port) if old_url == local_url(old_http_port) else old_url
    new_http_host = http_host or current.get("SAIGONOS_HTTP_HOST") or DEFAULT_HTTP_HOST
    old_admin_port = current.get("SAIGONOS_ADMIN_PORT") or DEFAULT_ADMIN_PORT
    values = {
        "SAIGONOS_URL": url,
        "SAIGONOS_HTTP_HOST": new_http_host,
        "SAIGONOS_HTTP_PORT": new_http_port,
        "SAIGONOS_ADMIN_PORT": str(admin_port or old_admin_port),
    }
    missing = [key for key in SECRET_KEYS if not current.get(key)]
    for key in SECRET_KEYS:
        values[key] = new_secret() if key in missing else current[key]

    profiles = split_profiles(current.get("COMPOSE_PROFILES", ""))
    if caddy is not None and caddy != (CADDY_PROFILE in profiles):
        if caddy:
            profiles.append(CADDY_PROFILE)
        else:
            profiles.remove(CADDY_PROFILE)
        values["COMPOSE_PROFILES"] = ",".join(profiles)
    if CADDY_PROFILE in profiles:
        caddy_http_port = current.get("CADDY_HTTP_PORT") or str(DEFAULT_CADDY_HTTP_PORT)
        check_caddy(url, new_http_host, new_http_port, caddy_http_port)

    home.mkdir(parents=True, exist_ok=True)
    for key, value in values.items():
        if current.get(key) != value:
            set_value(lines, key, value)
    write_private(home / ".env", "\n".join(lines) + "\n")

    copy_tree(files("saigonos").joinpath("stack"), home)
    listen = listen_address(new_http_host, new_http_port)
    return Initialized(
        url=url, listen=listen, new_secrets=len(missing), caddy=CADDY_PROFILE in profiles
    )
