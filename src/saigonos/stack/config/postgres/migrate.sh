#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
set -eu

if [ $# -ne 2 ]; then
    echo "Cách dùng: sh migrate.sh <scope> <thư mục chứa file SQL>" >&2
    exit 2
fi
scope=$1
folder=$2
export PGOPTIONS="-c client_min_messages=warning"

run() {
    psql --no-psqlrc --quiet --set ON_ERROR_STOP=1 --set migrate_scope="$scope" "$@"
}

if [ ! -d "$folder" ]; then
    echo "Không tìm thấy thư mục $folder" >&2
    exit 1
fi

run <<'SQL'
CREATE SCHEMA IF NOT EXISTS core;
CREATE TABLE IF NOT EXISTS core.migrations (
    scope text NOT NULL,
    name text NOT NULL,
    checksum text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, name)
);
SQL

applied=0
for file in "$folder"/*.sql; do
    [ -f "$file" ] || continue
    name=${file##*/}
    checksum=$(sha256sum "$file" | cut -d ' ' -f 1)
    recorded=$(run --tuples-only --no-align --set migrate_name="$name" <<'SQL'
SELECT checksum FROM core.migrations WHERE scope = :'migrate_scope' AND name = :'migrate_name';
SQL
)
    if [ "$recorded" = "$checksum" ]; then
        continue
    fi
    if [ -n "$recorded" ]; then
        echo "File $name đã được chạy trước đó nhưng nội dung đã thay đổi." >&2
        echo "Mỗi thay đổi của cơ sở dữ liệu cần được viết thành một file SQL mới." >&2
        exit 1
    fi
    if ! run --single-transaction --output /dev/null \
        --set migrate_name="$name" --set migrate_checksum="$checksum" \
        --file - --file "$file" <<'SQL'
INSERT INTO core.migrations (scope, name, checksum)
VALUES (:'migrate_scope', :'migrate_name', :'migrate_checksum');
SQL
    then
        echo "Không chạy được file $name. Mọi thay đổi của file này đã được hủy." >&2
        exit 1
    fi
    echo "Đã chạy file $name"
    applied=$((applied + 1))
done

if [ "$applied" -eq 0 ]; then
    echo "Không có file SQL mới"
    exit 0
fi
if ! run --command "NOTIFY pgrst, 'reload schema'"; then
    echo "Không báo được PostgREST nạp lại schema" >&2
    exit 1
fi
echo "Đã báo PostgREST nạp lại schema"
