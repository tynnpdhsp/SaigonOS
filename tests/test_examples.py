# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

from saigonos_core.manifest import check_app

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "phong-may"


def test_sample_app_passes_check_without_warnings():
    checked = check_app(EXAMPLE)

    assert checked.problems == []
    assert checked.warnings == ()
    assert checked.manifest.name == "phong-may"


def test_sql_files_of_sample_app_run_in_name_order():
    names = [path.name for path in sorted((EXAMPLE / "database").glob("*.sql"))]

    assert names == ["0001_phong.sql", "0002_nguoi_dung.sql", "0003_don.sql", "0004_quy_trinh.sql"]
