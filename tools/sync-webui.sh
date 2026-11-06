#!/usr/bin/env bash
# Vendor the dashboard from the TwitchDropMiner_WebAddon checkout into webui/.
#
# Usage:
#   tools/sync-webui.sh [path-to-addon-checkout]
#
# Defaults to ../TwitchDropMiner_WebAddon next to this repository. The vendored
# copy is what PyInstaller bundles; the add-on repository stays the source of
# truth.
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src=${1:-"$root/../TwitchDropMiner_WebAddon"}
dst="$root/webui"

if [[ ! -f "$src/index.html" || ! -d "$src/assets" ]]; then
    echo "not a web add-on checkout: $src" >&2
    exit 2
fi

mkdir -p "$dst"
rm -rf "$dst/assets"
cp "$src/index.html" "$dst/index.html"
cp -R "$src/assets" "$dst/assets"
echo "Synced $dst from $src"
