#!/usr/bin/env bash
# Compile TwitchDropsMiner CLI into a single-file binary via PyInstaller.
#
# Usage:
#   ./build_cli.sh                    # build single-file CLI binary -> dist/
#   ./build_cli.sh --one-dir          # one-folder build (faster startup)
#   ./build_cli.sh --keep-gui         # include the original GUI build too
#   ./build_cli.sh --upx              # use UPX compression (smaller, slower)
#   ./build_cli.sh --clean            # remove dist/ build/ first
#   ./build_cli.sh --name <name>      # override binary name
#   ./build_cli.sh --venv <path>      # use a different venv (default: ./venv)

set -euo pipefail

dirpath=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$dirpath"

# Defaults
venv="$dirpath/venv"
do_clean=0
export ONE_FILE="${ONE_FILE:-1}"
export USE_UPX="${USE_UPX:-0}"
export EXCLUDE_GUI="${EXCLUDE_GUI:-1}"
export APP_NAME="${APP_NAME:-twitch-drops-miner-cli}"
export OPTIMIZE="${OPTIMIZE:-1}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --one-dir)   export ONE_FILE=0; shift ;;
        --one-file)  export ONE_FILE=1; shift ;;
        --keep-gui)  export EXCLUDE_GUI=0; shift ;;
        --upx)       export USE_UPX=1; shift ;;
        --clean)     do_clean=1; shift ;;
        --name)      export APP_NAME="${2:-}"; shift 2 ;;
        --venv)      venv="${2:-}"; shift 2 ;;
        -h|--help)
            sed -n '2,12p' "$0"
            exit 0
            ;;
        *)
            echo "unknown flag: $1" >&2
            exit 2
            ;;
    esac
done

if [[ ! -d "$venv" ]]; then
    echo "venv not found at $venv" >&2
    echo "create one with:  python3 -m venv venv && venv/bin/pip install -r requirements.txt" >&2
    exit 3
fi

PIP="$venv/bin/pip"
PY="$venv/bin/python"
PYI="$venv/bin/pyinstaller"

# Make sure project deps are present (skip if requirements unchanged).
"$PIP" install --quiet --upgrade pip wheel >/dev/null
"$PIP" install --quiet -r requirements.txt

# PyInstaller is a build-time dep, install on demand.
if [[ ! -x "$PYI" ]]; then
    echo ">> installing PyInstaller into $venv"
    "$PIP" install --quiet pyinstaller
fi

if [[ "$do_clean" -eq 1 ]]; then
    echo ">> cleaning dist/ build/"
    rm -rf "$dirpath/dist" "$dirpath/build"
fi

echo ">> building (one_file=$ONE_FILE, exclude_gui=$EXCLUDE_GUI, upx=$USE_UPX, name=$APP_NAME)"
"$PYI" --noconfirm --clean build_cli.spec

# Report
if [[ "$ONE_FILE" = "1" ]]; then
    bin_path="$dirpath/dist/$APP_NAME"
else
    bin_path="$dirpath/dist/$APP_NAME/$APP_NAME"
fi
if [[ -e "$bin_path" ]]; then
    size=$(du -h "$bin_path" | cut -f1)
    echo ">> built: $bin_path  ($size)"
else
    echo ">> WARN: expected binary not at $bin_path; check dist/" >&2
fi
