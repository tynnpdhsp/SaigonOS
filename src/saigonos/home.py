# SPDX-License-Identifier: Apache-2.0
import secrets
import string
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import NamedTuple

DEFAULT_HTTP_PORT = 9080
DEFAULT_ADMIN_PORT = 9180
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
    new_secrets: int


def new_secret() -> str:
    return "".join(secrets.choice(SECRET_ALPHABET) for _ in range(SECRET_LENGTH))


def local_url(port: str) -> str:
    return "http://localhost" if port == "80" else f"http://localhost:{port}"


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
    http_port: int | None = None,
    admin_port: int | None = None,
) -> Initialized:
    home.mkdir(parents=True, exist_ok=True)
    lines = read_env_lines(home)
    current = parse_env(lines)

    old_http_port = current.get("SAIGONOS_HTTP_PORT") or str(DEFAULT_HTTP_PORT)
    new_http_port = str(http_port or old_http_port)
    old_url = current.get("SAIGONOS_URL") or local_url(old_http_port)
    if url is None:
        url = local_url(new_http_port) if old_url == local_url(old_http_port) else old_url
    old_admin_port = current.get("SAIGONOS_ADMIN_PORT") or DEFAULT_ADMIN_PORT
    values = {
        "SAIGONOS_URL": url,
        "SAIGONOS_HTTP_PORT": new_http_port,
        "SAIGONOS_ADMIN_PORT": str(admin_port or old_admin_port),
    }
    missing = [key for key in SECRET_KEYS if not current.get(key)]
    for key in SECRET_KEYS:
        values[key] = new_secret() if key in missing else current[key]

    for key, value in values.items():
        if current.get(key) != value:
            set_value(lines, key, value)
    write_private(home / ".env", "\n".join(lines) + "\n")

    copy_tree(files("saigonos").joinpath("stack"), home)
    return Initialized(url=url, new_secrets=len(missing))
