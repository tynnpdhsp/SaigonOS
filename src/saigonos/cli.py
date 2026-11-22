# SPDX-License-Identifier: Apache-2.0
import os
import shlex
from ipaddress import IPv6Address, ip_address
from pathlib import Path
from urllib.parse import SplitResult, urlsplit

import click
from click.core import ParameterSource

from saigonos import __version__, compose
from saigonos.apps import (
    NAME,
    AppFolderError,
    app_folders,
    app_name,
    keep_new,
    locked,
    put_in_place,
    remove_copy,
    restore_old,
)
from saigonos.audit import verify as verify_chain
from saigonos.doctor import run_checks
from saigonos.home import (
    APPS_FOLDER,
    DEFAULT_ADMIN_PORT,
    DEFAULT_CENTRIFUGO_PORT,
    DEFAULT_HTTP_HOST,
    DEFAULT_HTTP_PORT,
    DEFAULT_KEYCLOAK_PORT,
    DEFAULT_MAX_FILE_SIZE,
    DEFAULT_SEAWEEDFS_PORT,
    LARGEST_FILE_SIZE,
    SettingsError,
    disabled_services,
    init_home,
    read_url,
)

PORT = click.IntRange(1, 65535)
DEFAULT_PORTS = {"http": 80, "https": 443}
MARKS = {True: ("BÌNH THƯỜNG", "green"), False: ("LỖI", "red")}
MARK_WIDTH = max(len(label) for label, _ in MARKS.values())
COLUMN_GAP = " " * 4
CHECK_FOLDER = "/check"

home_option = click.option(
    "--home",
    envvar="SAIGONOS_HOME",
    show_envvar=True,
    type=click.Path(file_okay=False, resolve_path=True, path_type=Path),
    default=lambda: Path.home() / "saigonos",
    help="Thư mục làm việc. Mặc định là ~/saigonos.",
)


def url_host(parts: SplitResult) -> str:
    host = parts.hostname or ""
    return f"[{IPv6Address(host).compressed}]" if parts.netloc.startswith("[") else host


def normalize_url(ctx: click.Context, param: click.Parameter, value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parts = urlsplit(value)
        host = url_host(parts)
        valid = (
            parts.scheme in {"http", "https"}
            and bool(host)
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
    port = "" if parts.port in {None, DEFAULT_PORTS[parts.scheme]} else f":{parts.port}"
    return f"{parts.scheme}://{host}{port}"


def normalize_host(ctx: click.Context, param: click.Parameter, value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return str(ip_address(value))
    except ValueError:
        raise click.BadParameter(
            "giá trị phải là một địa chỉ IP, ví dụ 127.0.0.1 hoặc 0.0.0.0."
        ) from None


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
    "--http-host",
    callback=normalize_host,
    help=(
        "Địa chỉ IP mà cổng HTTP của API Gateway lắng nghe. "
        f"Mặc định là {DEFAULT_HTTP_HOST}, chỉ truy cập được từ chính máy cài đặt. "
        "Giá trị 0.0.0.0 cho phép truy cập từ máy khác."
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
@click.option(
    "--keycloak-port",
    type=PORT,
    help=(
        "Cổng của Keycloak, chỉ truy cập được từ chính máy cài đặt. "
        "Admin Console của realm master dùng cổng này. "
        f"Mặc định là {DEFAULT_KEYCLOAK_PORT}."
    ),
)
@click.option(
    "--seaweedfs-port",
    type=PORT,
    help=(
        "Cổng Admin UI của SeaweedFS, chỉ truy cập được từ chính máy cài đặt. "
        f"Mặc định là {DEFAULT_SEAWEEDFS_PORT}."
    ),
)
@click.option(
    "--centrifugo-port",
    type=PORT,
    help=(
        "Cổng của API và Admin web của Centrifugo, chỉ truy cập được từ chính máy cài đặt. "
        f"Mặc định là {DEFAULT_CENTRIFUGO_PORT}."
    ),
)
@click.option(
    "--max-file-size",
    type=click.IntRange(1, LARGEST_FILE_SIZE),
    help=(
        f"Dung lượng tối đa của một file tải lên, tính bằng MB, từ 1 đến {LARGEST_FILE_SIZE}. "
        "API Gateway cũng từ chối các lời gọi có nội dung lớn hơn giá trị này. "
        f"Mặc định là {DEFAULT_MAX_FILE_SIZE}."
    ),
)
@click.option(
    "--caddy/--no-caddy",
    default=None,
    help=(
        "Bật hoặc tắt Caddy. Caddy là reverse proxy nhận kết nối HTTPS và tự động lấy "
        "chứng chỉ, dùng khi máy cài đặt chưa có reverse proxy. Mặc định tắt."
    ),
)
@click.pass_context
def init(
    ctx: click.Context,
    home: Path,
    url: str | None,
    http_host: str | None,
    http_port: int | None,
    admin_port: int | None,
    keycloak_port: int | None,
    seaweedfs_port: int | None,
    centrifugo_port: int | None,
    max_file_size: int | None,
    caddy: bool | None,
) -> None:
    try:
        result = init_home(
            home,
            url=url,
            http_host=http_host,
            http_port=http_port,
            admin_port=admin_port,
            keycloak_port=keycloak_port,
            seaweedfs_port=seaweedfs_port,
            centrifugo_port=centrifugo_port,
            max_file_size=max_file_size,
            caddy=caddy,
        )
    except SettingsError as error:
        raise click.UsageError(str(error)) from error
    except OSError as error:
        raise click.ClickException(f"Không ghi được vào {home}: {error.strerror}") from error
    click.echo(f"Thư mục làm việc: {home}")
    click.echo(f"Địa chỉ truy cập: {result.url}")
    click.echo(f"Địa chỉ lắng nghe: {result.listen}")
    if result.caddy:
        click.echo("Caddy: bật")
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


def remove_disabled_services(home: Path) -> None:
    services = disabled_services(home)
    if not services:
        return
    try:
        compose.capture(home, "rm", "--stop", "--force", *services)
    except compose.ComposeError as error:
        raise click.ClickException(str(error)) from error


def waiting() -> None:
    click.echo("Đang chờ một lệnh saigonos khác làm việc với ứng dụng chạy xong.")


@main.command(
    help=(
        "Khởi động các service bằng Docker Compose và chờ đến khi sẵn sàng. "
        "Sau đó, cài đặt lại các ứng dụng đã cài đặt."
    )
)
@home_option
@click.pass_context
def up(ctx: click.Context, home: Path) -> None:
    remove_disabled_services(home)
    run_compose(ctx, home, "up", "-d", "--wait")
    click.echo(f"Địa chỉ truy cập: {read_url(home)}")
    if app_folders(home / APPS_FOLDER):
        with locked(home, waiting):
            run_compose(ctx, home, "run", "--rm", "apps", "apply", "--all")


@main.command(help="Dừng và xóa các container. Dữ liệu được giữ lại.")
@home_option
@click.option("--volumes", is_flag=True, help="Xóa cả dữ liệu trong các volume.")
@click.pass_context
def down(ctx: click.Context, home: Path, volumes: bool) -> None:
    remove_disabled_services(home)
    run_compose(ctx, home, "down", *(["--volumes"] if volumes else []))


def install(ctx: click.Context, home: Path, folder: Path) -> None:
    try:
        name = app_name(folder)
    except (OSError, ValueError, AppFolderError) as error:
        raise click.ClickException(f"Không đọc được bản khai của ứng dụng: {error}") from error
    apps = home / APPS_FOLDER
    with locked(home, waiting):
        try:
            put_in_place(folder, apps, name)
        except (OSError, ValueError, AppFolderError) as error:
            raise click.ClickException(f"Không chép được ứng dụng vào {apps}: {error}") from error
        try:
            code = compose.run(home, "run", "--rm", "apps", "apply", name)
        except BaseException as error:
            restore_old(apps, name)
            if isinstance(error, compose.ComposeError):
                raise click.ClickException(str(error)) from error
            raise
        if code != 0:
            restore_old(apps, name)
            ctx.exit(code)
        keep_new(apps, name)


@main.command(
    short_help="Cài đặt một ứng dụng vào hệ thống.",
    help=(
        "Soát bản khai saigonos-app.json và các thư mục của ứng dụng trong THƯ_MỤC, "
        "chép ứng dụng vào thư mục apps của thư mục làm việc rồi cài đặt ứng dụng "
        "vào hệ thống đang chạy.\n\n"
        "Khi cài đặt lỗi, thư mục apps giữ bản đã cài đặt thành công gần nhất."
    ),
)
@home_option
@click.option(
    "--check",
    is_flag=True,
    help="Chỉ soát ứng dụng, không cài đặt vào hệ thống. Hệ thống không cần đang chạy.",
)
@click.argument("folder", metavar="THƯ_MỤC", type=click.Path(resolve_path=True, path_type=Path))
@click.pass_context
def apply(ctx: click.Context, home: Path, check: bool, folder: Path) -> None:
    if not folder.exists():
        raise click.ClickException(f"Không tìm thấy thư mục {folder}.")
    if not folder.is_dir():
        raise click.ClickException(f"{folder} không phải thư mục.")
    if ":" in str(folder):
        raise click.ClickException(
            f"Đường dẫn {folder} có dấu hai chấm, "
            "nên Docker Compose không gắn được thư mục này vào container."
        )
    run_compose(
        ctx,
        home,
        "run",
        "--rm",
        "--no-deps",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--volume",
        f"{folder}:{CHECK_FOLDER}:ro",
        "apps",
        "check",
        CHECK_FOLDER,
    )
    if not check:
        install(ctx, home, folder)


@main.command(
    short_help="Gỡ một ứng dụng khỏi hệ thống.",
    help=(
        "Gỡ client, route, giao diện và quy trình của ứng dụng TÊN rồi xóa bản chép của ứng dụng "
        "trong thư mục apps. Schema, dữ liệu, role và việc gán role được giữ lại. "
        "Cài đặt lại ứng dụng thì dùng tiếp dữ liệu cũ."
    ),
)
@home_option
@click.option(
    "--purge",
    is_flag=True,
    help="Xóa hẳn ứng dụng cùng schema, dữ liệu, role và quy trình. Lệnh hỏi lại trước khi xóa.",
)
@click.option("--yes", is_flag=True, help="Không hỏi lại khi dùng --purge.")
@click.argument("name", metavar="TÊN")
@click.pass_context
def remove(ctx: click.Context, home: Path, purge: bool, yes: bool, name: str) -> None:
    if not NAME.fullmatch(name):
        raise click.ClickException(f"Tên ứng dụng {name} không hợp lệ.")
    try:
        compose.command(home)
    except compose.ComposeError as error:
        raise click.ClickException(str(error)) from error
    flags = [*(["--purge"] if purge else []), *(["--yes"] if yes else [])]
    with locked(home, waiting):
        run_compose(ctx, home, "run", "--rm", "apps", "remove", name, *flags)
        remove_copy(home / APPS_FOLDER, name)


@main.command(help="Kiểm tra trạng thái các service, API Gateway và các ứng dụng đã cài đặt.")
@home_option
@click.pass_context
def doctor(ctx: click.Context, home: Path) -> None:
    try:
        checks = run_checks(home, read_url(home))
    except compose.ComposeError as error:
        raise click.ClickException(str(error)) from error
    name_width = max(len(check.name) for check in checks)
    for check in checks:
        label, color = MARKS[check.ok]
        mark = click.style(f"{label:<{MARK_WIDTH}}", fg=color)
        click.echo(COLUMN_GAP.join([mark, f"{check.name:<{name_width}}", check.detail]))
    failed = sum(not check.ok for check in checks)
    if failed:
        click.echo(f"Có {failed} mục lỗi.")
        ctx.exit(1)
    click.echo("Hệ thống hoạt động bình thường.")


@main.group(help="Làm việc với audit log của cơ sở dữ liệu.")
def audit() -> None:
    pass


@audit.command(
    short_help="Tính lại chuỗi mã băm của audit log.",
    help=(
        "Tính lại chuỗi mã băm của bảng core.audit_log và so sánh với mã băm đã lưu.\n\n"
        "Khi một dòng đã bị sửa hoặc bị xóa, lệnh chỉ ra dòng sai đầu tiên "
        "và kết thúc với mã thoát 1."
    ),
)
@home_option
@click.pass_context
def verify(ctx: click.Context, home: Path) -> None:
    try:
        verdict = verify_chain(home)
    except compose.ComposeError as error:
        raise click.ClickException(str(error)) from error
    click.echo(verdict.detail)
    if not verdict.ok:
        ctx.exit(1)
