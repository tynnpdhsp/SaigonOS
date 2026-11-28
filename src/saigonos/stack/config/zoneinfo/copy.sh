#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
set -eu

zone=${TZ:-}
case "$zone" in
    "" | *[!A-Za-z0-9_+/-]*) magic="" ;;
    *) magic=$(head -c 4 "/usr/share/zoneinfo/$zone" 2>/dev/null || true) ;;
esac
if [ "$magic" != TZif ]; then
    echo "Múi giờ $zone trong SAIGONOS_TIMEZONE không hợp lệ. Ví dụ: Asia/Ho_Chi_Minh" >&2
    exit 1
fi
cp -a /usr/share/zoneinfo/. /zoneinfo/
echo "Đã chép dữ liệu múi giờ. Múi giờ của hệ thống là $zone"
