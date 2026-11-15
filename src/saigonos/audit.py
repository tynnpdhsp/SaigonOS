# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
from typing import Any, NamedTuple

from saigonos import compose

PSQL = (
    "psql",
    "--username=postgres",
    "--dbname=saigonos",
    "--no-psqlrc",
    "--quiet",
    "--tuples-only",
    "--no-align",
    "--set=ON_ERROR_STOP=1",
)
# Không gọi core.audit_hash() để kết quả không phụ thuộc hàm lưu trong chính CSDL đang kiểm tra
CHAIN = """\
SET search_path = pg_catalog;
SELECT json_build_object(
    'rows', count(*),
    'last_hash', (SELECT hash FROM core.audit_log ORDER BY id DESC LIMIT 1),
    'missing', min(previous_id + 1) FILTER (WHERE id <> previous_id + 1),
    'changed', min(id) FILTER (WHERE hash IS DISTINCT FROM expected)
)
FROM (
    SELECT id, hash,
        coalesce(lag(id) OVER chain, 0) AS previous_id,
        encode(sha256(convert_to(
            coalesce(lag(hash) OVER chain, repeat('0', 64)) || jsonb_build_object(
                'id', id,
                'occurred_at',
                to_char(occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
                'actor', actor,
                'db_role', db_role,
                'table_schema', table_schema,
                'table_name', table_name,
                'operation', operation,
                'old_row', old_row,
                'new_row', new_row
            )::text,
            'UTF8'
        )), 'hex') AS expected
    FROM core.audit_log
    WINDOW chain AS (ORDER BY id)
) AS checked;
"""


class Verdict(NamedTuple):
    ok: bool
    detail: str


def chain_state(chain: dict[str, Any]) -> Verdict:
    missing, changed = chain["missing"], chain["changed"]
    if missing is not None and (changed is None or missing < changed):
        return Verdict(
            False,
            f"Audit log thiếu dòng {missing}. Dòng này đã bị xóa hoặc bị đổi số thứ tự.",
        )
    if changed is not None:
        return Verdict(
            False,
            f"Dòng {changed} của audit log không khớp mã băm. "
            "Nội dung hoặc mã băm của dòng này đã bị sửa.",
        )
    if not chain["rows"]:
        return Verdict(True, "Audit log chưa có dòng nào.")
    return Verdict(
        True,
        f"Audit log có {chain['rows']} dòng. Chuỗi mã băm khớp.\n"
        f"Mã băm của dòng cuối: {chain['last_hash']}",
    )


def verify(home: Path) -> Verdict:
    output = compose.capture(home, "exec", "-T", "postgres", *PSQL, f"--command={CHAIN}")
    return chain_state(json.loads(output))
