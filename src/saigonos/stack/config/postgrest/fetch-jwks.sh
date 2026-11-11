#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
set -eu

target=/jwks/jwks.json
trap 'rm -f "$target.tmp"' EXIT

if ! wget -q -T 10 -O "$target.tmp" "$JWKS_URL"; then
    echo "Không lấy được JWKS từ $JWKS_URL" >&2
    exit 1
fi
if ! grep -q '"kty"' "$target.tmp"; then
    echo "JWKS lấy từ $JWKS_URL không có khóa nào" >&2
    exit 1
fi
mv "$target.tmp" "$target"
echo "Đã ghi JWKS vào $target"

if ! psql --quiet --no-psqlrc --command "NOTIFY pgrst, 'reload config'"; then
    echo "Không báo được PostgREST nạp lại JWKS" >&2
    exit 1
fi
echo "Đã báo PostgREST nạp lại JWKS"
