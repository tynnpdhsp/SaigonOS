# SPDX-License-Identifier: Apache-2.0
import click

from saigonos import __version__


@click.group(
    help="Quản trị lõi SaigonOS từ dòng lệnh.",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, prog_name="saigonos", message="%(prog)s %(version)s")
def main() -> None:
    pass
