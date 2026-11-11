# SPDX-License-Identifier: Apache-2.0
import shlex
from pathlib import Path
from urllib.parse import urlsplit

import click

from saigonos import __version__
from saigonos.home import DEFAULT_ADMIN_PORT, DEFAULT_HTTP_PORT, init_home

PORT = click.IntRange(1, 65535)

home_option = click.option(
    "--home",
    envvar="SAIGONOS_HOME",
    show_envvar=True,
    type=click.Path(file_okay=False, resolve_path=True, path_type=Path),
    default=lambda: Path.home() / "saigonos",
    help="Thư mục làm việc. Mặc định là ~/saigonos.",
)


def normalize_url(ctx: click.Context, param: click.Parameter, value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parts = urlsplit(value)
        valid = (
            parts.scheme in {"http", "https"}
            and bool(parts.hostname)
            and parts.port != 0
            and "@" not in parts.netloc
            and parts.path in {"", "/"}
            and not parts.query
            and not parts.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise click.BadParameter(
            "địa chỉ phải có dạng http://tên-máy[:cổng] hoặc https://tên-máy[:cổng], "
            "không kèm đường dẫn."
        )
    return f"{parts.scheme}://{parts.netloc.lower()}"


@click.group(
    help="Quản trị lõi SaigonOS từ dòng lệnh.",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, prog_name="saigonos", message="%(prog)s %(version)s")
def main() -> None:
    pass


@main.command(
    short_help="Tạo thư mục làm việc và file .env.",
    help=(
        "Tạo thư mục làm việc gồm file compose.yaml, thư mục config và file .env "
        "chứa mật khẩu ngẫu nhiên.\n\n"
        "Khi chạy lại, lệnh cập nhật file compose.yaml và thư mục config. "
        "Các giá trị đã có trong file .env được giữ nguyên, trừ những giá trị "
        "được chỉ định lại bằng tùy chọn."
    ),
)
@home_option
@click.option(
    "--url",
    callback=normalize_url,
    help=(
        "Địa chỉ mà người dùng truy cập hệ thống, ví dụ https://dx.example.com. "
        "Mặc định là http://localhost kèm cổng HTTP."
    ),
)
@click.option(
    "--http-port",
    type=PORT,
    help=f"Cổng HTTP của API Gateway trên máy cài đặt. Mặc định là {DEFAULT_HTTP_PORT}.",
)
@click.option(
    "--admin-port",
    type=PORT,
    help=(
        "Cổng quản trị của APISIX, chỉ truy cập được từ chính máy cài đặt. "
        f"Mặc định là {DEFAULT_ADMIN_PORT}."
    ),
)
def init(home: Path, url: str | None, http_port: int | None, admin_port: int | None) -> None:
    try:
        result = init_home(home, url, http_port, admin_port)
    except OSError as error:
        raise click.ClickException(f"Không ghi được vào {home}: {error.strerror}") from error
    click.echo(f"Thư mục làm việc: {home}")
    click.echo(f"Địa chỉ truy cập: {result.url}")
    if result.new_secrets:
        click.echo(f"Đã tạo {result.new_secrets} mật khẩu ngẫu nhiên trong file .env.")
    else:
        click.echo("Các mật khẩu trong file .env được giữ nguyên.")
    start = f"cd {shlex.quote(str(home))} && docker compose up -d --wait"
    click.echo(f"Để khởi động, chạy lệnh: {start}")
