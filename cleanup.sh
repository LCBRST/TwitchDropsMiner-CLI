#!/usr/bin/env bash
# Removes upstream files that the CLI build no longer needs.
#
# Usage:
#   ./cleanup.sh             # interactive: shows what will go, asks to confirm
#   ./cleanup.sh --dry-run   # just print, don't delete
#   ./cleanup.sh --yes       # delete without prompting
#   ./cleanup.sh --purge-gui # ALSO remove gui.py / cache.py / icons/ (no GUI fallback)

set -euo pipefail

dirpath=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

dry_run=0
auto_yes=0
purge_gui=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) dry_run=1 ;;
        --yes|-y)  auto_yes=1 ;;
        --purge-gui) purge_gui=1 ;;
        -h|--help)
            sed -n '2,12p' "$0"
            exit 0
            ;;
        *)
            echo "unknown flag: $arg" >&2
            exit 2
            ;;
    esac
done

# Always-cleanup targets: Windows-only / dev-only / build artifacts.
# Paths are relative to the project root.
core_targets=(
    "build.bat"
    "build.sh"
    "build.spec"
    "pack.bat"
    "run_dev.bat"
    "setup_env.bat"
    "setup_env.sh"
    "manual.txt"
    "appimage"
    "__pycache__"
    "build"
    "dist"
    "lock.file"
    "dump.dat"
    "log.txt"
    ".mypy_cache"
)

# Optional GUI purge: removes the original tkinter GUI build entirely.
# After this, TDM_GUI=1 will fail — you only get the CLI.
gui_targets=(
    "gui.py"
    "cache.py"
    "icons"
)

targets=("${core_targets[@]}")
if [[ "$purge_gui" -eq 1 ]]; then
    targets+=("${gui_targets[@]}")
fi

# Filter to existing paths
existing=()
for t in "${targets[@]}"; do
    if [[ -e "$dirpath/$t" ]]; then
        existing+=("$t")
    fi
done

if [[ ${#existing[@]} -eq 0 ]]; then
    echo "nothing to clean"
    exit 0
fi

echo "Cleanup targets in $dirpath:"
for t in "${existing[@]}"; do
    if [[ -d "$dirpath/$t" ]]; then
        size=$(du -sh "$dirpath/$t" | cut -f1)
        echo "  rm -rf  $t   ($size)"
    else
        size=$(du -h "$dirpath/$t" | cut -f1)
        echo "  rm      $t   ($size)"
    fi
done

if [[ "$dry_run" -eq 1 ]]; then
    echo
    echo "(dry-run, nothing removed)"
    exit 0
fi

if [[ "$auto_yes" -ne 1 ]]; then
    echo
    read -r -p "Proceed? [y/N] " ans
    case "$ans" in
        y|Y|yes|YES) ;;
        *) echo "aborted"; exit 1 ;;
    esac
fi

for t in "${existing[@]}"; do
    rm -rf -- "$dirpath/$t"
done

echo "done."
