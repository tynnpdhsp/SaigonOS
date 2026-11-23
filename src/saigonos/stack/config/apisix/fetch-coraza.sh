#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
set -eu

target=/wasm/coraza-proxy-wasm.wasm
url="https://github.com/corazawaf/coraza-proxy-wasm/releases/download/$CORAZA_VERSION/coraza-proxy-wasm-$CORAZA_VERSION.zip"

if [ -f "$target" ] && echo "$CORAZA_WASM_SHA256  $target" | sha256sum -c -s; then
    echo "Đã có coraza-proxy-wasm $CORAZA_VERSION"
    exit 0
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

if ! wget -q -T 60 -O "$work/coraza.zip" "$url"; then
    echo "Không tải được $url" >&2
    exit 1
fi
if ! echo "$CORAZA_ZIP_SHA256  $work/coraza.zip" | sha256sum -c -s; then
    echo "Mã SHA-256 của file $url không khớp" >&2
    exit 1
fi
unzip -q "$work/coraza.zip" coraza-proxy-wasm.wasm -d "$work"
if ! echo "$CORAZA_WASM_SHA256  $work/coraza-proxy-wasm.wasm" | sha256sum -c -s; then
    echo "Mã SHA-256 của file coraza-proxy-wasm.wasm không khớp" >&2
    exit 1
fi

chmod 644 "$work/coraza-proxy-wasm.wasm"
mv "$work/coraza-proxy-wasm.wasm" "$target.new"
mv "$target.new" "$target"
echo "Đã tải coraza-proxy-wasm $CORAZA_VERSION"
