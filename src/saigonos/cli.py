# SPDX-License-Identifier: Apache-2.0
import shlex
from pathlib import Path
from urllib.parse import urlsplit

import click
from click.core import ParameterSource

from saigonos import __version__, compose
from saigonos.doctor import gateway_checks, service_checks
from saigonos.home import DEFAULT_ADMIN_PORT, DEFAULT_HTTP_PORT, init_home, read_url

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
@click.pass_context
def init(
    ctx: click.Context, home: Path, url: str | None, http_port: int | None, admin_port: int | None
) -> None:
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
    start = "saigonos up"
    if ctx.get_parameter_source("home") is ParameterSource.COMMANDLINE:
        start += f" --home {shlex.quote(str(home))}"
    click.echo(f"Để khởi động, chạy lệnh: {start}")


def run_compose(ctx: click.Context, home: Path, *args: str) -> None:
    try:
        code = compose.run(home, *args)
    except compose.ComposeError as error:
        raise click.ClickException(str(error)) from error
    if code != 0:
        ctx.exit(code)


@main.command(help="Khởi động các dịch vụ bằng Docker Compose và chờ đến khi sẵn sàng.")
@home_option
@click.pass_context
def up(ctx: click.Context, home: Path) -> None:
    run_compose(ctx, home, "up", "-d", "--wait")
    click.echo(f"Địa chỉ truy cập: {read_url(home)}")


@main.command(help="Dừng và xóa các container. Dữ liệu được giữ lại.")
@home_option
@click.option("--volumes", is_flag=True, help="Xóa cả dữ liệu trong các volume.")
@click.pass_context
def down(ctx: click.Context, home: Path, volumes: bool) -> None:
    run_compose(ctx, home, "down", *(["--volumes"] if volumes else []))


@main.command(help="Kiểm tra trạng thái các dịch vụ và API Gateway.")
@home_option
@click.pass_context
def doctor(ctx: click.Context, home: Path) -> None:
    try:
        checks = [*service_checks(home), *gateway_checks(read_url(home))]
    except compose.ComposeError as error:
        raise click.ClickException(str(error)) from error
    width = max(len(check.name) for check in checks)
    for check in checks:
        mark = click.style("ĐẠT", fg="green") if check.ok else click.style("LỖI", fg="red")
        click.echo(f"{mark}  {check.name:<{width}}  {check.detail}")
    failed = sum(not check.ok for check in checks)
    if failed:
        click.echo(f"Có {failed} mục lỗi.")
        ctx.exit(1)
    click.echo("Hệ thống hoạt động bình thường.")
