# SPDX-License-Identifier: Apache-2.0
import re
from importlib.resources import files

MIGRATIONS = files("saigonos") / "stack" / "config" / "postgres" / "migrations"


def test_migration_files_are_numbered_without_gaps():
    names = sorted(entry.name for entry in MIGRATIONS.iterdir())

    assert names
    assert all(re.fullmatch(r"\d{4}_[a-z0-9_]+\.sql", name) for name in names)
    assert [int(name[:4]) for name in names] == list(range(1, len(names) + 1))
