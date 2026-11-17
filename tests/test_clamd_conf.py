# SPDX-License-Identifier: Apache-2.0
import re
from importlib.resources import files

from saigonos.home import LARGEST_FILE_SIZE

CONF = files("saigonos") / "stack" / "config" / "clamav" / "clamd.conf"
UNITS = {"": 1, "K": 1024, "M": 1024 * 1024}
MB = 1024 * 1024


def settings():
    lines = CONF.read_text(encoding="utf-8").splitlines()
    return dict(line.split(maxsplit=1) for line in lines if line and not line.startswith("#"))


def size(value):
    number, unit = re.fullmatch(r"(\d+)([KM]?)", value).groups()
    return int(number) * UNITS[unit]


def test_clamav_flags_large_inner_file_instead_of_scanning_only_its_start():
    config = settings()

    assert config["AlertExceedsMax"] == "yes"
    assert size(config["MaxFileSize"]) > size(config["MaxScanSize"])


def test_clamav_accepts_largest_allowed_upload():
    assert size(settings()["StreamMaxLength"]) >= LARGEST_FILE_SIZE * MB
