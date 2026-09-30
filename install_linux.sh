#!/usr/bin/env bash
# Install TwitchDropsMiner CLI on Linux, from nothing.
#
# Fetch this file and run it - there is no repository to clone first:
#
#     wget -O install_linux.sh https://raw.githubusercontent.com/LCBRST/TwitchDropsMiner-CLI/main/install_linux.sh
#     chmod +x install_linux.sh
#     ./install_linux.sh
#
# It installs what the program needs from the system (a Chromium-based browser,
# and Xvfb for a machine with no screen), downloads the source, builds a
# self-contained binary, and then throws the source and the build environment
# away again. What is left is the browser, Xvfb, and the binary.
#
# Usage:
#   ./install_linux.sh                 # install into the current directory
#   ./install_linux.sh --dry-run       # say what it would do, change nothing
#   ./install_linux.sh --yes           # do not ask before installing packages
#   ./install_linux.sh --dir ~/tdm     # put the binary somewhere else
#   ./install_linux.sh --ref v1.2.3    # build a tag or branch other than main
#   ./install_linux.sh --tarball URL   # build from a source archive URL
#   ./install_linux.sh --python PATH   # use a particular Python interpreter
#   ./install_linux.sh --skip-browser  # do not touch the browser
#   ./install_linux.sh --skip-xvfb     # do not install Xvfb
#   ./install_linux.sh --keep-source   # leave the source and venv behind
#   ./install_linux.sh --work-dir DIR  # build in DIR (then it is left alone)
#
# Nothing outside its own working directory is ever deleted.

set -euo pipefail

REPO_URL="https://github.com/LCBRST/TwitchDropsMiner-CLI"
TARBALL=""
REF="main"
OUT_DIR="$PWD"
WORK_DIR=""
PYTHON=""
APP_NAME="TwitchDropsMiner-CLI"

dry_run=0
assume_yes=0
do_browser=1
do_xvfb=1
keep_source=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir)          OUT_DIR="${2:-}"; shift 2 ;;
        --repo)         REPO_URL="${2:-}"; shift 2 ;;
        --ref)          REF="${2:-}"; shift 2 ;;
        --tarball)      TARBALL="${2:-}"; shift 2 ;;
        --python)       PYTHON="${2:-}"; shift 2 ;;
        --work-dir)     WORK_DIR="${2:-}"; shift 2 ;;
        --name)         APP_NAME="${2:-}"; shift 2 ;;
        --dry-run)      dry_run=1; shift ;;
        --yes|-y)       assume_yes=1; shift ;;
        --skip-browser) do_browser=0; shift ;;
        --skip-xvfb)    do_xvfb=0; shift ;;
        --keep-source)  keep_source=1; shift ;;
        -h|--help)      sed -n '2,26p' "$0"; exit 0 ;;
        *) echo "unknown flag: $1" >&2; exit 2 ;;
    esac
done

# --- output ----------------------------------------------------------------

step() { printf '\n\033[1m>> %s\033[0m\n' "$*"; }
info() { printf '   %s\n' "$*"; }
warn() { printf '   \033[33m%s\033[0m\n' "$*" >&2; }
die()  { printf '\n\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

run() {
    printf '   \033[36m$ %s\033[0m\n' "$*"
    [[ "$dry_run" -eq 1 ]] || "$@"
}

confirm() {
    [[ "$assume_yes" -eq 1 || "$dry_run" -eq 1 ]] && return 0
    read -r -p "   Continue? [y/N] " reply
    [[ "$reply" =~ ^[Yy]$ ]]
}

# --- privileges ------------------------------------------------------------

SUDO=()
if [[ "$(id -u)" -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO=(sudo)
    else
        die "Installing packages needs root, and sudo is not available.
Install these by hand and re-run with --skip-browser --skip-xvfb:
  - Xvfb
  - a Chromium-based browser (Google Chrome, Chromium, or Edge)"
    fi
fi

# --- distribution ----------------------------------------------------------

ID=""; ID_LIKE=""
[[ -r /etc/os-release ]] && . /etc/os-release

case " $ID $ID_LIKE " in
    *" debian "*|*" ubuntu "*|*" linuxmint "*|*" pop "*|*" raspbian "*|*" kali "*) family="apt" ;;
    *" fedora "*|*" rhel "*|*" centos "*|*" rocky "*|*" almalinux "*)             family="dnf" ;;
    *" arch "*|*" manjaro "*|*" endeavouros "*)                                    family="pacman" ;;
    *" alpine "*)                                                                  family="apk" ;;
    *" suse "*|*" opensuse "*)                                                     family="zypper" ;;
    *) family="" ;;
esac
if [[ -z "$family" ]]; then
    for candidate in apt-get dnf pacman apk zypper; do
        if command -v "$candidate" >/dev/null 2>&1; then family="$candidate"; break; fi
    done
fi
[[ "$family" == "apt-get" ]] && family="apt"

step "Distribution"
info "ID=${ID:-?}  ID_LIKE=${ID_LIKE:-?}  package manager: ${family:-unknown}"

install_packages() {
    case "$family" in
        apt)    run "${SUDO[@]}" apt-get update -qq; run "${SUDO[@]}" apt-get install -y "$@" ;;
        dnf)    run "${SUDO[@]}" dnf install -y "$@" ;;
        pacman) run "${SUDO[@]}" pacman -S --noconfirm "$@" ;;
        apk)    run "${SUDO[@]}" apk add "$@" ;;
        zypper) run "${SUDO[@]}" zypper --non-interactive install "$@" ;;
        *)      return 1 ;;
    esac
}

# --- what the program needs from the system --------------------------------
#
# Signing in opens a browser window, which on a machine with no screen means a
# Chromium-based browser *and* Xvfb for it to draw on.

XVFB_PACKAGE="xvfb"
case "$family" in
    dnf)    XVFB_PACKAGE="xorg-x11-server-Xvfb" ;;
    pacman) XVFB_PACKAGE="xorg-server-xvfb" ;;
    zypper) XVFB_PACKAGE="xorg-x11-server-Xvfb" ;;
esac

if [[ "$do_xvfb" -eq 1 ]]; then
    step "Xvfb"
    if command -v Xvfb >/dev/null 2>&1; then
        info "already installed: $(command -v Xvfb)"
    elif [[ -n "${DISPLAY:-}" ]]; then
        info "this machine has a display (DISPLAY=$DISPLAY), so a browser window"
        info "has somewhere to go already; Xvfb is only needed without one."
        info "install it anyway? [Y/n]"
        if confirm; then
            install_packages "$XVFB_PACKAGE" || warn "could not install $XVFB_PACKAGE"
        fi
    else
        info "installing '$XVFB_PACKAGE'"
        install_packages "$XVFB_PACKAGE" || warn "could not install $XVFB_PACKAGE"
    fi
fi

# The browser is the awkward one. Ubuntu 20.04 and later answer
# `apt install chromium` with a *snap wrapper*, which cannot drive a browser
# this program can use, and flatpak has the same shape of problem. Rather than
# encode every distribution's quirks, whatever gets installed is asked for its
# version afterwards: a browser that answers is one that works, and one that
# does not gets Google's own package instead.

browser_candidates=(google-chrome google-chrome-stable chromium chromium-browser microsoft-edge)

find_browser_binary() {
    for candidate in "${browser_candidates[@]}"; do
        command -v "$candidate" >/dev/null 2>&1 && { printf '%s' "$candidate"; return 0; }
    done
    return 1
}

browser_works() {
    "$1" --version 2>/dev/null | grep -qiE 'chrome|chromium|edge'
}

install_google_chrome() {
    local tmp url
    tmp=$(mktemp -d)
    case "$family" in
        apt)
            url="https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"
            [[ "$(uname -m)" == "aarch64" || "$(uname -m)" == "arm64" ]] &&
                url="https://dl.google.com/linux/direct/google-chrome-stable_current_arm64.deb"
            info "downloading Google Chrome from dl.google.com"
            run curl -fsSL -o "$tmp/chrome.deb" "$url"
            run "${SUDO[@]}" apt-get install -y "$tmp/chrome.deb"
            ;;
        dnf)
            run "${SUDO[@]}" dnf install -y \
                "https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm"
            ;;
        *)
            rm -rf "$tmp"
            return 1
            ;;
    esac
    rm -rf "$tmp"
}

if [[ "$do_browser" -eq 1 ]]; then
    step "Chromium-based browser"
    existing="$(find_browser_binary || true)"
    if [[ -n "$existing" ]] && browser_works "$existing"; then
        info "already installed and working: $existing ($("$existing" --version))"
    else
        [[ -n "$existing" ]] &&
            warn "$existing is present but does not work as a browser" &&
            warn "(on Ubuntu, 'chromium' is usually a snap wrapper with this problem)"
        info "installing one"
        case "$family" in
            apt)
                # Debian ships a real chromium package; Ubuntu's is the snap
                # wrapper, so Ubuntu and its derivatives get Google's instead.
                if [[ "$ID" == "debian" ]]; then
                    install_packages chromium || install_google_chrome
                else
                    install_google_chrome || install_packages chromium
                fi
                ;;
            dnf)    install_google_chrome || install_packages chromium ;;
            pacman) install_packages chromium ;;
            apk)    install_packages chromium ;;
            zypper) install_packages chromium ;;
            *)      warn "do not know how to install a browser here" ;;
        esac
        if [[ "$dry_run" -eq 0 ]]; then
            existing="$(find_browser_binary || true)"
            if [[ -n "$existing" ]] && browser_works "$existing"; then
                info "installed: $existing ($("$existing" --version))"
            else
                warn "no working browser found afterwards - install Google Chrome by"
                warn "hand, or point the program at one later with:"
                warn "  set renewal_browser_path /path/to/chrome"
            fi
        fi
    fi
fi

# --- python and the build --------------------------------------------------

step "Source"
command -v tar >/dev/null 2>&1 || die "tar is required but not installed"

# The interpreter has to be a shared-library build: PyInstaller needs to load
# libpython, and one built without `--enable-shared` - which is what pyenv and
# asdf produce by default - cannot make a one-file binary at all. Asking first
# beats downloading the source and failing a minute later.
usable_python() {
    "$1" -c 'import sys, sysconfig
raise SystemExit(0 if sys.version_info >= (3, 10)
                      and sysconfig.get_config_var("Py_ENABLE_SHARED") else 1)' 2>/dev/null
}

if [[ -n "$PYTHON" ]]; then
    command -v "$PYTHON" >/dev/null 2>&1 || die "no such interpreter: $PYTHON"
    usable_python "$PYTHON" ||
        die "$PYTHON cannot build a one-file binary: it needs Python 3.10+ and a
shared-library build (pyenv and asdf produce ones that are not)."
else
    for candidate in python3 /usr/bin/python3 /usr/local/bin/python3 \
                     python3.13 python3.12 python3.11 python3.10; do
        path="$(command -v "$candidate" 2>/dev/null)" || continue
        if usable_python "$path"; then PYTHON="$path"; break; fi
    done
    if [[ -z "$PYTHON" ]]; then
        die "No usable Python found. This needs Python 3.10 or newer built with a
shared library (Linux distributions ship one; pyenv and asdf do not by
default - install the distribution's python3), or point at one with --python."
    fi
fi
info "$("$PYTHON" --version) at $PYTHON"

created_work=0
if [[ -z "$WORK_DIR" ]]; then
    WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/tdm-build.XXXXXX")"
    created_work=1
fi
info "building in $WORK_DIR"

cleanup() {
    # Only ever a directory this script created. A --work-dir belongs to whoever
    # passed it, and is left where it is even when the build fails.
    [[ "$created_work" -eq 1 && "$keep_source" -eq 0 && "$dry_run" -eq 0 ]] || return 0
    case "$WORK_DIR" in
        */tdm-build.*) rm -rf "$WORK_DIR" ;;
    esac
}
trap cleanup EXIT

if [[ "$dry_run" -eq 0 ]]; then
    # An archive rather than a clone: it needs no git, and the history is not
    # wanted for a build anyway. `git` is the fallback, for a repository that
    # has no archive at a URL this can work out.
    if [[ -z "$TARBALL" && "$REPO_URL" == https://github.com/* ]]; then
        slug="${REPO_URL#https://github.com/}"
        slug="${slug%.git}"
        TARBALL="https://codeload.github.com/${slug}/tar.gz/refs/heads/${REF}"
    fi

    mkdir -p "$WORK_DIR/src"
    if [[ -n "$TARBALL" ]]; then
        info "downloading ${TARBALL}"
        curl -fsSL -o "$WORK_DIR/src.tar.gz" "$TARBALL" ||
            die "could not download $TARBALL"
        tar -xzf "$WORK_DIR/src.tar.gz" -C "$WORK_DIR/src"
        rm -f "$WORK_DIR/src.tar.gz"
        # Archives hold their contents under one top-level directory, whose name
        # varies by how it was made. Moving it up rather than asking tar to strip
        # it keeps this working with the smaller tar implementations too.
        if [[ ! -f "$WORK_DIR/src/build_cli.sh" ]]; then
            inner="$(find "$WORK_DIR/src" -mindepth 1 -maxdepth 1 -type d | head -1)"
            [[ -n "$inner" ]] || die "the archive did not contain a directory"
            mv "$inner"/* "$inner"/.[!.]* "$WORK_DIR/src/" 2>/dev/null || true
            rmdir "$inner"
        fi
    elif command -v git >/dev/null 2>&1; then
        info "cloning ${REPO_URL}@${REF}"
        rm -rf "$WORK_DIR/src"
        git clone --depth 1 --branch "$REF" "$REPO_URL" "$WORK_DIR/src"
    else
        die "nothing to download $REPO_URL from, and git is not installed"
    fi
fi

src_dir="$WORK_DIR/src"
[[ -f "$src_dir/build_cli.sh" ]] || die "the downloaded source has no build_cli.sh"

step "Building"
info "this takes a minute or two"
run chmod +x "$src_dir/build_cli.sh"
if [[ "$dry_run" -eq 0 ]]; then
    # build_cli.sh wants a venv already there; it installs the rest itself.
    info "creating a virtual environment"
    if ! "$PYTHON" -m venv "$src_dir/venv" 2>/dev/null; then
        info "python3-venv is missing; installing it"
        case "$family" in
            apt) install_packages "python3-venv" || install_packages "python${PY_MAJOR_MINOR:-3}-venv" ;;
            *)   install_packages python3-venv || true ;;
        esac
        "$PYTHON" -m venv "$src_dir/venv" ||
            die "could not create a virtual environment"
    fi
    APP_NAME="$APP_NAME" "$src_dir/build_cli.sh"
fi

built="$src_dir/dist/$APP_NAME"
[[ "$dry_run" -eq 1 || -x "$built" ]] || die "the build produced no binary at $built"

# --- install it ------------------------------------------------------------

step "Installing"
run mkdir -p "$OUT_DIR"
destination="$OUT_DIR/$APP_NAME"
run cp -f "$built" "$destination"
run chmod +x "$destination"

# --- clean up --------------------------------------------------------------
#
# The source, the virtual environment and PyInstaller's intermediates are all
# this script's own making, and none of them are needed once the binary exists.
# Only a directory this script created is ever removed: a --work-dir belongs to
# whoever passed it, and is left where it is.

if [[ "$keep_source" -eq 1 ]]; then
    step "Keeping the build directory, as asked"
    info "$WORK_DIR"
elif [[ "$created_work" -eq 1 ]]; then
    step "Cleaning up"
    info "removing $WORK_DIR (source, venv and build intermediates)"
    cleanup
else
    step "Leaving the build directory, since it was given"
    info "$WORK_DIR"
fi

# --- done ------------------------------------------------------------------

if [[ "$dry_run" -eq 1 ]]; then
    step "Rehearsal only - nothing was changed"
    info "run it again without --dry-run"
else
    step "Installed. Start it with:"
    printf '\n    %s\n\n' "$destination"
fi
