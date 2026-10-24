#!/usr/bin/env bash
set -euo pipefail

dry_run=false
case "${1:-}" in
    '') ;;
    --dry-run) dry_run=true ;;
    --help|-h)
        echo 'Usage: scripts/install-deps.sh [--dry-run]'
        echo 'Install native source and standalone-build dependencies on Ubuntu, Debian, or Fedora.'
        echo 'uv and nFPM are installed separately. Use --dry-run to print commands without running them.'
        exit 0
        ;;
    *)
        echo 'Usage: scripts/install-deps.sh [--dry-run]' >&2
        exit 1
        ;;
esac
if [[ "$#" -gt 1 ]]; then
    echo 'Usage: scripts/install-deps.sh [--dry-run]' >&2
    exit 1
fi

source /etc/os-release
case "$ID" in
    ubuntu|debian)
        # Ubuntu 24.04+ and Debian 13+ renamed these runtime packages for time64.
        alsa_package=libasound2
        glib_package=libglib2.0-0
        if { [[ "$ID" == ubuntu ]] && dpkg --compare-versions "$VERSION_ID" ge 24.04; } ||
           { [[ "$ID" == debian ]] && dpkg --compare-versions "$VERSION_ID" ge 13; }; then
            alsa_package=libasound2t64
            glib_package=libglib2.0-0t64
        fi
        packages=(
            ca-certificates build-essential ccache python3-dev python3-venv
            linux-libc-dev patchelf libffi-dev libwayland-dev
            libxkbcommon-dev libxkbcommon-x11-dev libxcb-cursor0 libxcb-icccm4
            libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-xkb1
            libxcb-shape0 libxrandr2 libegl1 libgl1 libdbus-1-3
            "$alsa_package" libpulse0 "$glib_package" libfontconfig1 libfreetype6
            libgssapi-krb5-2 sudo xdg-desktop-portal
        )
        ;;
    fedora)
        packages=(
            ca-certificates gcc gcc-c++ make ccache python3-devel python3-pip
            kernel-headers libffi-devel wayland-devel patchelf
            libxkbcommon libxkbcommon-x11 xcb-util-cursor xcb-util-wm
            xcb-util-image xcb-util-keysyms xcb-util-renderutil libXrandr
            mesa-libGL mesa-libEGL dbus-libs alsa-lib pulseaudio-libs
            glib2 fontconfig freetype krb5-libs sudo xdg-desktop-portal
            # Nuitka reads -l:libatomic.a from uv-managed Python's MODLIBS.
            libatomic-static
        )
        ;;
    *)
        echo "Native dependency installation is not supported on ${PRETTY_NAME:-$ID}." >&2
        echo 'Use scripts/build-container.sh for standalone releases, or makepkg -sif on Arch Linux.' >&2
        exit 1
        ;;
esac

privilege_command=()
if [[ "$EUID" -ne 0 ]]; then
    privilege_command=(sudo --)
fi

run() {
    if [[ "$dry_run" == true ]]; then
        printf '%q ' "${privilege_command[@]}" "$@"
        printf '\n'
    else
        "${privilege_command[@]}" "$@"
    fi
}

if [[ "$ID" == fedora ]]; then
    run dnf install -y --setopt=install_weak_deps=False "${packages[@]}"
else
    run apt-get update
    run apt-get install -y --no-install-recommends "${packages[@]}"
fi
